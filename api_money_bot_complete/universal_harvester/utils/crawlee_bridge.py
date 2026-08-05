"""
CrawleeBridge — Python client for the Crawlee Node.js engine.

Usage:
    from utils.crawlee_bridge import CrawleeBridge
    bridge = CrawleeBridge(base_url="http://localhost:3001", api_key="secret")
    result = bridge.signup("github", {"email": "a@b.com", "password": "pass"})
    batch = bridge.batch([
        {"platform": "github", "credentials": {...}, "mode": "signup"},
        {"platform": "openai", "credentials": {...}, "mode": "signup"},
    ])
"""

import time
from typing import Dict, List, Optional
import requests


class CrawleeBridge:
    """HTTP client for the Crawlee stealth browser engine."""

    def __init__(self, base_url: str = "http://localhost:3001", api_key: str = "", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _post(self, endpoint: str, payload: Dict) -> Dict:
        url = f"{self.base_url}{endpoint}"
        resp = self.session.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _get(self, endpoint: str) -> Dict:
        url = f"{self.base_url}{endpoint}"
        resp = self.session.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def health(self) -> Dict:
        """Check if Crawlee engine is alive."""
        return self._get("/health")

    def signup(self, platform: str, credentials: Dict, mode: str = "signup", options: Optional[Dict] = None) -> Dict:
        """Run signup/signin for a single platform."""
        payload = {
            "platform": platform,
            "credentials": credentials,
            "mode": mode,
            "options": options or {},
        }
        return self._post("/signup", payload)

    def batch(self, jobs: List[Dict], options: Optional[Dict] = None) -> Dict:
        """Run batch signup across multiple platforms."""
        payload = {
            "jobs": jobs,
            "options": options or {},
        }
        return self._post("/batch", payload)

    def list_sessions(self) -> Dict:
        """List saved browser sessions."""
        return self._get("/sessions")

    def delete_session(self, platform: str) -> Dict:
        """Delete a saved session."""
        url = f"{self.base_url}/sessions/{platform}"
        resp = self.session.delete(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def is_alive(self) -> bool:
        """Quick check if server is running."""
        try:
            self.health()
            return True
        except Exception:
            return False

    def wait_for_server(self, max_wait: int = 30) -> bool:
        """Poll until Crawlee server is ready."""
        for i in range(max_wait):
            if self.is_alive():
                return True
            time.sleep(1)
        return False
