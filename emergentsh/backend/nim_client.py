"""NVIDIA NIM API Client for chat completions."""
import os
import requests
from typing import Dict, List, Optional, Any, Iterator


class NIMConfig:
    """Configuration for NIM client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.nv.nvidia.com/v1",
        default_model: str = "nvidia/llama-3.1-nim-70b",
        timeout: int = 30,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature


class NIMClient:
    """Client for NVIDIA NIM inference API."""

    def __init__(self, api_key: str, base_url: str = "https://api.nv.nvidia.com/v1"):
        if not api_key:
            raise ValueError("API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.config = NIMConfig(api_key=api_key, base_url=base_url)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def _post(self, endpoint: str, body: Dict) -> Dict:
        url = f"{self.base_url}{endpoint}"
        response = self.session.post(url, json=body, timeout=self.config.timeout)
        response.raise_for_status()
        return response.json()

    def _get(self, endpoint: str) -> Dict:
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, timeout=self.config.timeout)
        response.raise_for_status()
        return response.json()

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
        return self._post("/chat/completions", body)

    def get_models(self) -> List[str]:
        """Get available models from NIM."""
        response = self._get("/models")
        return [m["id"] for m in response.get("data", [])]
