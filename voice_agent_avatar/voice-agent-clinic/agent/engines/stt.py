"""
STT engines — speech-to-text providers.
Free tier: Deepgram Nova-2 (200 min/mo free).
"""

import asyncio
import json
import logging
from typing import Optional, Callable

import websockets

logger = logging.getLogger(__name__)


class DeepgramSTTEngine:
    """
    Streaming STT with Deepgram Nova-2.
    Free tier: 200 minutes/month.
    """

    def __init__(self, api_key: str, language: str = "en"):
        self.api_key = api_key
        self.language = language
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._transcript_callback: Optional[Callable] = None
        self._is_connected = False

    async def connect(self, on_transcript: Callable):
        """Connect to Deepgram streaming API."""
        self._transcript_callback = on_transcript

        url = (
            f"wss://api.deepgram.com/v1/listen?"
            f"model=nova-2&language={self.language}&"
            f"interim_results=true&punctuate=true&smart_format=true"
        )

        self._ws = await websockets.connect(
            url,
            extra_headers={"Authorization": f"Token {self.api_key}"},
            ping_interval=20,
            ping_timeout=10,
        )
        self._is_connected = True

        asyncio.create_task(self._listen())
        logger.info("Deepgram STT connected")

    async def _listen(self):
        """Listen for transcripts."""
        try:
            async for message in self._ws:
                data = json.loads(message)

                if data.get("type") == "Results":
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        is_final = data.get("is_final", False)

                        if transcript and self._transcript_callback:
                            await self._transcript_callback(transcript, is_final)

        except Exception as e:
            logger.error(f"STT listen error: {e}")
        finally:
            self._is_connected = False

    async def send_audio(self, audio_chunk: bytes):
        """Send audio chunk to Deepgram."""
        if self._is_connected and self._ws:
            try:
                await self._ws.send(audio_chunk)
            except Exception as e:
                logger.error(f"STT send error: {e}")

    async def close(self):
        if self._ws:
            await self._ws.close()
            self._is_connected = False
