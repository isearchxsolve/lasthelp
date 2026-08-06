"""Credential discovery and session-scoped storage for OMEGA."""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("omega_agent.interaction.credentials")


CREDENTIAL_SCHEMA: Dict[str, Dict[str, Any]] = {
    "GROQ_API_KEY": {
        "name": "Groq API Key",
        "description": "Powers live LLM reasoning (Llama models on Groq).",
        "pattern": r"^gsk_[\w-]+$",
        "url": "https://console.groq.com/keys",
        "tier": "recommended",
    },
    "ANTHROPIC_API_KEY": {
        "name": "Anthropic API Key",
        "description": "Claude models when Groq is unavailable.",
        "pattern": r"^sk-ant-[\w-]+$",
        "url": "https://console.anthropic.com/settings/keys",
        "tier": "optional",
    },
    "OPENAI_API_KEY": {
        "name": "OpenAI API Key",
        "description": "GPT models when other providers are unavailable.",
        "pattern": r"^sk-[\w-]+$",
        "url": "https://platform.openai.com/api-keys",
        "tier": "optional",
    },
    "GITHUB_TOKEN": {
        "name": "GitHub Personal Access Token",
        "description": "Create repos, push code, or trigger GitHub Actions.",
        "pattern": r"^(ghp_|github_pat_)[\w]+$",
        "url": "https://github.com/settings/tokens",
        "tier": "optional",
    },
    "AWS_ACCESS_KEY_ID": {
        "name": "AWS Access Key ID",
        "description": "Deploy or manage AWS resources.",
        "pattern": r"^AKIA[\w]{16}$",
        "url": "https://console.aws.amazon.com/iam/",
        "tier": "optional",
    },
    "AWS_SECRET_ACCESS_KEY": {
        "name": "AWS Secret Access Key",
        "description": "Companion secret for AWS Access Key ID.",
        "pattern": r"^[\w/+=]{40}$",
        "url": "https://console.aws.amazon.com/iam/",
        "tier": "optional",
    },
    "REPLICATE_API_KEY": {
        "name": "Replicate API Key",
        "description": "Image generation via Replicate API.",
        "pattern": r"^r8_[\w]+$",
        "url": "https://replicate.com/account/api-tokens",
        "tier": "optional",
    },
}


class CredentialManager:
    """Resolve credentials from env, disk vault, or interactive session."""

    def __init__(self, vault_path: str = "./data/omega_vault.json"):
        self.vault_path = Path(vault_path)
        self._session: Dict[str, str] = {}
        self._load_vault()

    def _load_vault(self) -> None:
        if self.vault_path.exists():
            try:
                data = json.loads(self.vault_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._session.update({k: str(v) for k, v in data.items()})
            except Exception as e:
                logger.warning("Could not load vault: %s", e)

    def _save_vault(self) -> None:
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_text(json.dumps(self._session, indent=2), encoding="utf-8")

    def get(self, key: str) -> Optional[str]:
        if key in self._session and self._session[key]:
            return self._session[key]
        env_val = os.environ.get(key)
        return env_val if env_val else None

    def has(self, key: str) -> bool:
        return bool(self.get(key))

    def store(self, key: str, value: str, persist: bool = True) -> None:
        self._session[key] = value.strip()
        os.environ[key] = value.strip()
        if persist:
            self._save_vault()
        logger.info("Stored credential %s for session", key)

    def apply_to_environment(self) -> None:
        for key, value in self._session.items():
            if value:
                os.environ[key] = value

    def missing_for_goal(self, goal: str, require_llm: bool = True, orchestrator=None) -> List[str]:
        """Return env var names likely required for this goal."""
        goal_lower = goal.lower()
        missing: List[str] = []

        if require_llm and not any(self.has(k) for k in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")):
            missing.append("GROQ_API_KEY")

        # Use LLM to detect credential requirements when orchestrator is available
        if orchestrator:
            try:
                import asyncio
                from omega_agent.tools.registry import ToolRegistry
                keys_to_check = [k for k in CREDENTIAL_SCHEMA if k not in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")]
                prompt = (
                    f"Given this goal, which of the following API keys or tokens might be needed?\n\n"
                    f"Goal: {goal[:500]}\n\n"
                    f"Options: {', '.join(keys_to_check)}\n\n"
                    f"Return ONLY a comma-separated list of the relevant key names, or 'none'."
                )
                resp, _ = asyncio.run(orchestrator.invoke(
                    prompt=prompt,
                    system="You classify which API keys are needed for a goal. Return comma-separated names or 'none'.",
                    temperature=0.1,
                    max_tokens=100,
                ))
                detected = [k.strip() for k in resp.split(",")]
                for key in keys_to_check:
                    if key in detected and not self.has(key):
                        missing.append(key)
            except Exception:
                pass
        
        return missing

    def validate(self, key: str, value: str) -> Optional[str]:
        cleaned = value.strip()
        if not cleaned or len(cleaned) < 8:
            return "Please provide a non-empty value (at least 8 characters)."
        meta = CREDENTIAL_SCHEMA.get(key, {})
        pattern = meta.get("pattern")
        if pattern and not re.match(pattern, cleaned):
            logger.warning("Credential %s format mismatch (accepted anyway)", key)
        return None

    def schema_for(self, key: str) -> Dict[str, Any]:
        return CREDENTIAL_SCHEMA.get(key, {"name": key, "description": "", "url": None})
