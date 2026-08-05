#!/usr/bin/env python3
"""
Kaggle Client Utility
=====================
Sends inference requests to the Kaggle-hosted models (e.g. Whisper)
running on T4 GPUs, exposed via a Cloudflare Tunnel endpoint.

Provides graceful fallback to local inference if the remote server
is offline or misconfigured.
"""

import base64
import os
import requests
from typing import Optional, Dict, Any

class KaggleClient:
    """Client for interacting with models hosted on a remote Kaggle environment."""

    def __init__(self, endpoint_url: Optional[str] = None):
        # Resolve endpoint: parameter first, then environment variable
        self.endpoint_url = endpoint_url or os.getenv("KAGGLE_ENDPOINT", "")
        if self.endpoint_url:
            self.endpoint_url = self.endpoint_url.rstrip("/")
            print(f"[KaggleClient] Initialized with endpoint: {self.endpoint_url}")
        else:
            print("[KaggleClient] No endpoint configured. Falling back to local mode.")

    def is_available(self) -> bool:
        """Check if the remote Kaggle/Cloudflare server is online."""
        if not self.endpoint_url:
            return False
        try:
            resp = requests.get(f"{self.endpoint_url}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[KaggleClient] Connected to remote model server. GPU={data.get('gpu')}, Model={data.get('model')}")
                return True
        except Exception as e:
            print(f"[KaggleClient] Remote server health check failed: {e}")
        return False

    def transcribe(self, audio_path: str, language: str = "en") -> Optional[str]:
        """Send local audio file to Kaggle server for Whisper transcription."""
        if not self.endpoint_url:
            return None
        
        if not os.path.exists(audio_path):
            print(f"[KaggleClient] Audio file not found: {audio_path}")
            return None

        try:
            # Read and encode audio file
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

            payload = {
                "audio": audio_b64,
                "language": language,
                "temperature": 0.0
            }

            resp = requests.post(
                f"{self.endpoint_url}/transcribe",
                json=payload,
                timeout=30
            )

            if resp.status_code == 200:
                result = resp.json()
                return result.get("text", "").strip()
            else:
                print(f"[KaggleClient] Remote transcription failed (HTTP {resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"[KaggleClient] Error calling remote transcriber: {e}")
        
        return None
