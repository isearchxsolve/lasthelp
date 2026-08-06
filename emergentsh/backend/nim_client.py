"""NVIDIA NIM API Client for chat completions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class NIMConfig:
    """Configuration for NIM client."""

    api_key: str
    base_url: str = "https://api.nv.nvidia.com/v1"
    default_model: str = "nvidia/llama-3.1-nim-70b"
    timeout: int = 30
    max_tokens: int = 4096
    temperature: float = 0.7


class NIMClient:
    """Client for NVIDIA NIM inference API."""

    def __init__(self, api_key: str, base_url: str = "https://api.nv.nvidia.com/v1"):
        if not api_key:
            raise ValueError("API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.config = NIMConfig(api_key=api_key, base_url=base_url)

    def _request_json(self, endpoint: str, body: Optional[Dict[str, Any]] = None, method: str = "GET") -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            raise RuntimeError(f"NIM request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"NIM request failed: {exc.reason}") from exc
        return json.loads(payload or "{}")

    def chat_completion(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        """Send chat completion request to NVIDIA NIM."""
        body = {
            "model": model or self.config.default_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }
        return self._request_json("/chat/completions", body=body, method="POST")

    def get_models(self) -> List[str]:
        """Get available models from NIM."""
        response = self._request_json("/models")
        return [m["id"] for m in response.get("data", [])]

