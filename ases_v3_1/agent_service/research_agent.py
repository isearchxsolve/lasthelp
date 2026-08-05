"""
ASES - Research Agent (v4.0)
============================
Bridges the spec-to-code gap by performing tool-using research before planning.

What it does:
1. Extracts research claims from the task specification
   ("what do I need to know / lookup before planning?")
2. Performs structured web research (web_search + web_fetch with a citation graph)
3. Produces ResearchBrief: tech stack constraints, library version guidance,
   known-pitfall callouts, and authoritative URLs that the coder can cite.
4. Persists briefs to a research_memory table so identical future tasks skip
   research entirely (zero LLM calls -> 0 cost).

Integration:
    from research_agent import research_task
    brief = await research_task(task, tech_stack, requirements, config, execution_id)

Design constraints (ASES SOTA):
- No external deps beyond httpx (already in requirements.txt).
- Hard 6-tool-call budget -> bounded latency and cost.
- Graceful degradation: any tool failure returns a degraded brief, never raises.
- All claims carry a citation_url; the coder is instructed to cite in comments
  only when explicit user opt-in (default off to keep diffs clean).
- Result is JSON-serializable for vector storage and reproduction audit.
"""

import os
import json
import time
import asyncio
import hashlib
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Budget + circuit-breaker constants
# ---------------------------------------------------------------------------
MAX_TOOL_CALLS = 6
MAX_FETCH_BYTES = 200_000
PER_TOOL_TIMEOUT_S = 20.0
RESEARCH_TTL_SECONDS = 86_400 * 7  # 7-day cache


@dataclass
class Citation:
    url: str
    title: str
    snippet: str
    fetched_at: float
    trust: float  # 0..1, derated for unknown domains


@dataclass
class ResearchClaim:
    topic: str
    claim: str
    citations: List[Citation] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class ResearchBrief:
    task_hash: str
    tech_stack: str
    summary: str
    claims: List[ResearchClaim] = field(default_factory=list)
    libraries: List[Dict[str, str]] = field(default_factory=list)
    pitfalls: List[str] = field(default_factory=list)
    authoritative_urls: List[str] = field(default_factory=list)
    degraded: bool = False
    error: Optional[str] = None
    model_tokens: int = 0
    elapsed_s: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def brief_hash(task: str, tech_stack: str) -> str:
    return hashlib.sha256(f"{task}\x1f{tech_stack}".encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Cached persistence (best-effort; failures are non-fatal)
# ---------------------------------------------------------------------------
async def _cache_load(pool, tenant_uuid: str, bhash: str) -> Optional[ResearchBrief]:
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT brief_json, created_at
                FROM research_memory
                WHERE tenant_id=$1 AND task_hash=$2
                """,
                tenant_uuid, bhash,
            )
            if not row:
                return None
            age = (datetime.now(timezone.utc) - row["created_at"]).total_seconds()
            if age > RESEARCH_TTL_SECONDS:
                return None
            data = json.loads(row["brief_json"])
            claims = [ResearchClaim(**c) for c in data.pop("claims", [])]
            return ResearchBrief(claims=claims, **data)
    except Exception as e:
        logger.warning("research.cache.load_failed", error=str(e))
        return None


async def _cache_store(pool, tenant_uuid: str, brief: ResearchBrief) -> None:
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO research_memory
                    (tenant_id, task_hash, tech_stack, brief_json, created_at)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (tenant_id, task_hash) DO UPDATE
                    SET brief_json=EXCLUDED.brief_json,
                        created_at=EXCLUDED.created_at
                """,
                tenant_uuid, brief.task_hash, brief.tech_stack,
                json.dumps(brief.as_dict(), default=str),
                datetime.now(timezone.utc),
            )
    except Exception as e:
        logger.warning("research.cache.store_failed", error=str(e))


# ---------------------------------------------------------------------------
# Tool surface (pluggable)
# ---------------------------------------------------------------------------
async def _web_search(query: str, execution_id: str) -> List[Dict[str, Any]]:
    """
    Search the web for a query. Uses native web_search tool if available
    (set via environment), else returns an empty list (degraded mode).
    """
    api_key = os.getenv("BRAVE_API_KEY") or os.getenv("SERP_API_KEY")
    if not api_key:
        return []
    import httpx
    brave = os.getenv("BRAVE_API_KEY")
    serp = os.getenv("SERP_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=PER_TOOL_TIMEOUT_S) as client:
            if brave:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": brave, "Accept": "application/json"},
                    params={"q": query, "count": 5},
                )
                r.raise_for_status()
                data = r.json()
                return [
                    {
                        "url": x.get("url", ""),
                        "title": x.get("title", ""),
                        "snippet": x.get("description", ""),
                    }
                    for x in data.get("web", {}).get("results", [])[:5]
                ]
            if serp:
                r = await client.get(
                    "https://serpapi.com/search",
                    params={"q": query, "api_key": serp, "engine": "google", "num": 5},
                )
                r.raise_for_status()
                data = r.json()
                return [
                    {"url": x.get("link"), "title": x.get("title"), "snippet": x.get("snippet", "")}
                    for x in data.get("organic_results", [])[:5]
                ]
    except Exception as e:
        logger.info("research.web_search.failed", execution_id=execution_id, error=str(e))
    return []


async def _web_fetch(url: str, execution_id: str) -> str:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=PER_TOOL_TIMEOUT_S) as client:
            r = await client.get(url, follow_redirects=True)
            r.raise_for_status()
            text = r.text
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:MAX_FETCH_BYTES]
    except Exception as e:
        logger.info("research.web_fetch.failed", url=url, execution_id=execution_id, error=str(e))
        return ""


_TRUSTED_DOMAINS = {
    "github.com", "raw.githubusercontent.com",
    "developer.mozilla.org", "reactjs.org", "nextjs.org",
    "nodejs.org", "docs.python.org", "fastapi.tiangolo.com",
    "typescriptlang.org", "vuejs.org", "svelte.dev", "angular.io",
    "kubernetes.io", "docker.com", "leetcode.com", "owasp.org",
    "vercel.com", "npmjs.com", "pypi.org",
}


def _domain_trust(url: str) -> float:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        for d in _TRUSTED_DOMAINS:
            if host == d or host.endswith("." + d):
                return 1.0
        return 0.6
    except Exception:
        return 0.5


# ---------------------------------------------------------------------------
# LLM step: topic decomposition + synthesis
# ---------------------------------------------------------------------------
async def _llm_topics(task: str, tech_stack: str, call_model, config, execution_id: str) -> List[str]:
    system = (
        "You are ASES research-agent. Decompose the engineering task into 1-5 "
        "research topics the planner would benefit from. Return JSON: "
        '{"topics": ["...","..."]}. Be specific. Output JSON only.'
    )
    user = f"Task: {task}\nTech stack: {tech_stack}\n\nReturn JSON topics."
    try:
        content, inp, out = await call_model(
            model=config.planner_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=300,
            execution_id=execution_id,
            call_type="planner",
        )
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            return []
        data = json.loads(m.group(0))
        toks = inp + out
        return data.get("topics", [])[:5], toks
    except Exception as e:
        logger.info("research.topics.failed", execution_id=execution_id, error=str(e))
        return [], 0


async def _llm_synthesize(
    topic: str, snippets: List[Dict[str, Any]], call_model, config, execution_id: str
) -> Tuple[str, int]:
    system = (
        "You are ASES research synthesis. From web snippets, derive a single "
        "concise research claim (<=2 sentences). Flag pitfalls if obvious. "
        "Return JSON: {\"claim\":\"...\",\"pitfall\":\"...\"}"
    )
    body = json.dumps(snippets, default=str)[:4000]
    user = f"Topic: {topic}\nSnippets: {body}\n\nReturn JSON."
    try:
        content, inp, out = await call_model(
            model=config.planner_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=400,
            execution_id=execution_id,
            call_type="planner",
        )
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            data = json.loads(m.group(0))
            return json.dumps(data), inp + out
        return "", inp + out
    except Exception as e:
        logger.info("research.synth.failed", execution_id=execution_id, error=str(e))
        return "", 0


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
async def research_task(
    task: str,
    tech_stack: str,
    requirements: str,
    config,
    execution_id: str,
    call_model=None,
    db_pool=None,
    tenant_uuid: Optional[str] = None,
    enable_web: Optional[bool] = None,
) -> ResearchBrief:
    """
    Runs the research phase. Falls back to a degraded brief under any failure.

    Args:
        enable_web: override of web research; default = True iff BRAVE/ SERP keys set.
    """
    from db import get_db_pool as _get_db_pool

    started = time.time()
    bhash = brief_hash(task, tech_stack)

    pool = db_pool or await _get_db_pool()
    if pool and tenant_uuid and enable_web is not False:
        cached = await _cache_load(pool, tenant_uuid, bhash)
        if cached:
            cached.elapsed_s = time.time() - started
            logger.info("research.cache.hit", execution_id=execution_id, task_hash=bhash)
            return cached

    do_web = (enable_web if enable_web is not None
              else bool(os.getenv("BRAVE_API_KEY") or os.getenv("SERP_API_KEY")))

    cm = call_model
    if cm is None:
        try:
            from agent_loop import call_model as _cm
            cm = _cm
        except Exception:
            cm = None

    topics: List[str] = []
    claims: List[ResearchClaim] = []
    libraries: List[Dict[str, str]] = []
    pitfalls: List[str] = []
    urls: List[str] = []
    tokens = 0
    degraded = False
    err = None

    try:
        if cm is not None:
            topics, toks = await _llm_topics(task, tech_stack, cm, config, execution_id)
            tokens += toks
        if not topics:
            degraded = True
            topics = [f"{tech_stack} best-practices production setup", "common pitfalls {tech_stack}"]

        tool_budget = MAX_TOOL_CALLS
        if do_web:
            for topic in topics:
                if tool_budget <= 0:
                    break
                tool_budget -= 1
                results = await _web_search(topic + " " + tech_stack, execution_id)
                if not results:
                    continue
                for r in results[:2]:
                    urls.append(r.get("url", ""))
                    tool_budget -= 1
                    body = await _web_fetch(r.get("url", ""), execution_id)
                    if not body:
                        continue
                    snippet = body[:1500]
                    cite = Citation(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        snippet=snippet,
                        fetched_at=time.time(),
                        trust=_domain_trust(r.get("url", "")),
                    )
                    if cm is not None:
                        synth, toks = await _llm_synthesize(
                            topic, [{"snippet": snippet, "url": r.get("url", "")}],
                            cm, config, execution_id,
                        )
                        tokens += toks
                        pitfall = ""
                        if synth:
                            try:
                                sj = json.loads(synth)
                                claim_text = sj.get("claim", "")
                                pitfall = sj.get("pitfall", "")
                            except Exception:
                                claim_text = synth
                        else:
                            claim_text = snippet[:400]
                    else:
                        claim_text = snippet[:400]
                    claims.append(ResearchClaim(
                        topic=topic,
                        claim=claim_text,
                        citations=[cite],
                        confidence=cite.trust,
                    ))
                    if pitfall:
                        pitfalls.append(pitfall)
                    if tool_budget <= 0:
                        break
        else:
            degraded = True

    except Exception as e:
        degraded = True
        err = str(e)
        logger.warning("research.degraded", execution_id=execution_id, error=e)

    brief = ResearchBrief(
        task_hash=bhash,
        tech_stack=tech_stack,
        summary=f"Research produced {len(claims)} claims across {len(topics)} topics.",
        claims=claims,
        libraries=libraries,
        pitfalls=pitfalls,
        authoritative_urls=list(dict.fromkeys(urls))[:10],
        degraded=degraded,
        error=err,
        model_tokens=tokens,
        elapsed_s=time.time() - started,
    )

    if pool and tenant_uuid:
        await _cache_store(pool, tenant_uuid, brief)
    return brief


def format_brief_for_planner(brief: ResearchBrief) -> str:
    """Compact text rendering for injection into the planner prompt."""
    if not brief or brief.degraded:
        return ""
    lines = ["[RESEARCH BRIEF v4.0]"]
    if brief.pitfalls:
        lines.append("Pitfalls:")
        for p in brief.pitfalls[:5]:
            lines.append(f"  - {p}")
    if brief.claims:
        lines.append("Findings:")
        for c in brief.claims[:6]:
            lines.append(f"  - [{c.topic}] {c.claim}")
    if brief.authoritative_urls:
        lines.append("Refs:")
        for u in brief.authoritative_urls[:5]:
            lines.append(f"  - {u}")
    return "\n".join(lines)
