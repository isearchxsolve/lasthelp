"""
rate_limit_kit.py  -  never hit the wall again.
Self-contained: disk cache + token-bucket limiter + error classifier + provider pool.
Depends only on the standard library and your existing call_model(model, system, user).
"""
import os, json, time, hashlib, threading, random

# ----------------------------------------------------------------- disk cache
CACHE_DIR = os.environ.get("LLM_CACHE_DIR", ".llm_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def _key(model, system, user):
    h = hashlib.sha256(f"{model}\x00{system}\x00{user}".encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, h + ".json")

def cached_call(model, system, user, fn):
    """Return a cached response for this exact (model, system, user), else call fn and store it."""
    p = _key(model, system, user)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))["response"]
        except Exception:
            pass  # corrupt entry -> refetch
    resp = fn(model, system, user)
    tmp = p + ".tmp"
    json.dump({"model": model, "response": resp}, open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, p)  # atomic write
    return resp

# ----------------------------------------------------------------- typed error
class RateLimitError(Exception):
    def __init__(self, status, body, retry_after=None):
        super().__init__(f"{status}: {str(body)[:200]}")
        self.status = status
        self.body = body or ""
        self.retry_after = retry_after

def raise_for_rate_limit(resp):
    """Call inside post_json on a non-2xx response to raise a typed, classifiable error."""
    if resp.status_code >= 400:
        ra = resp.headers.get("Retry-After")
        try:
            retry_after = float(ra) if ra is not None else None
        except (TypeError, ValueError):
            retry_after = None
        raise RateLimitError(resp.status_code, resp.text, retry_after)

# ----------------------------------------------------------------- classify
_HARD = ("per day", "per-day", "daily", "quota", "resource_exhausted",
         "insufficient", "exceeded your current quota", "out of credit",
         "billing", "payment required")

def classify_error(status, body):
    b = (body or "").lower()
    if status == 429:
        return "hard" if any(m in b for m in _HARD) else "transient"   # day-quota vs per-minute
    if status in (402, 403) and any(m in b for m in _HARD):
        return "hard"
    if status in (500, 502, 503, 504):
        return "transient"
    return "fatal"

# ----------------------------------------------------------------- limiter
class RateLimiter:
    def __init__(self, rpm, tpm):
        self.rpm, self.tpm = rpm, tpm
        self.reqs, self.toks = [], []
        self.lock = threading.Lock()
    def acquire(self, est_tokens=1500):
        while True:
            with self.lock:
                now = time.time()
                self.reqs = [t for t in self.reqs if now - t < 60]
                self.toks = [(t, n) for t, n in self.toks if now - t < 60]
                if len(self.reqs) < self.rpm and sum(n for _, n in self.toks) + est_tokens <= self.tpm:
                    self.reqs.append(now)
                    self.toks.append((now, est_tokens))
                    return
            time.sleep(0.5)

# ----------------------------------------------------------------- provider pool
class Provider:
    def __init__(self, name, model, rpm, tpm):
        self.name = name
        self.model = model            # full "vendor:model" string your call_model expects
        self.limiter = RateLimiter(rpm, tpm)
        self.cool_until = 0.0
    def up(self):
        return time.time() >= self.cool_until

class ProviderPool:
    def __init__(self, providers, caller):
        self.providers = providers    # ordered by preference
        self.caller = caller          # your call_model(model, system, user) -> text
    def call(self, system, user, est_tokens=1500, max_retries=5):
        last = None
        for p in self.providers:
            if not p.up():
                continue
            for attempt in range(max_retries):
                try:
                    p.limiter.acquire(est_tokens)
                    return cached_call(p.model, system, user, self.caller), p.name
                except RateLimitError as e:
                    kind = classify_error(e.status, e.body)
                    if kind == "hard":                       # out for the day -> park + rotate
                        p.cool_until = time.time() + (e.retry_after or 3600)
                        last = e; break
                    if kind == "transient":                  # per-minute -> wait + retry
                        time.sleep((e.retry_after or 2 ** attempt) + random.uniform(0, 1))
                        last = e; continue
                    last = e; break                          # fatal -> next provider
                except Exception as e:                       # non-HTTP failure -> next provider
                    last = e; break
        raise RuntimeError(f"All providers exhausted; last error: {last}")

# ----------------------------------------------------------------- pool builder
# Conservative free-tier ceilings; tune to your actual plan.
_CANDIDATE_SPECS = [
    ("mistral",  "mistral:mistral-large-latest",   "MISTRAL_API_KEY",  1,  30000),
    ("cerebras", "cerebras:llama-3.3-70b",         "CEREBRAS_API_KEY", 25, 60000),
    ("groq",     "groq:llama-3.3-70b-versatile",   "GROQ_API_KEY",     25, 6000),
    ("google",   "google:gemini-2.5-flash",        "GOOGLE_API_KEY",   10, 250000),
]
_LOCAL_FLOOR = ("ollama", "ollama:llama3.1:8b", None, 100000, 100000000)

def build_pool(caller, specs=None, include_local=True):
    specs = _CANDIDATE_SPECS if specs is None else specs
    providers = []
    for name, model, env, rpm, tpm in specs:
        if env is None or os.environ.get(env):        # only include providers whose key is set
            providers.append(Provider(name, model, rpm, tpm))
    if include_local and (os.environ.get("OLLAMA_HOST") or os.environ.get("USE_LOCAL_FLOOR")):
        n, m, _, rpm, tpm = _LOCAL_FLOOR
        providers.append(Provider(n, m, rpm, tpm))    # always-on floor: never hard-fails
    if not providers:
        raise RuntimeError("No providers: set at least one *_API_KEY, or USE_LOCAL_FLOOR=1")
    return ProviderPool(providers, caller)
