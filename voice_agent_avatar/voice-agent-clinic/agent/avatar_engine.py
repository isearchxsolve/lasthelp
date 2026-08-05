"""
Avatar Engine — Real-time streaming avatar orchestrator.
Manages HeyGen streaming session, sentiment-driven expressions,
lip-sync triggering, and WebRTC bridge for the voice agent.
"""

import asyncio
import json
import logging
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger("avatar_engine")


class Expression(Enum):
    """Facial expressions mapped to conversation sentiment."""
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    SMILE = "smile"
    CONCERNED = "concerned"
    EMPATHETIC = "empathetic"
    CELEBRATORY = "celebratory"
    THINKING = "thinking"
    LISTENING = "listening"
    SURPRISED = "surprised"


class AvatarState(Enum):
    """Current avatar activity state."""
    IDLE = "idle"
    LISTENING = "listening"
    SPEAKING = "speaking"
    THINKING = "thinking"
    PROCESSING = "processing"


@dataclass
class AvatarConfig:
    """Configuration for avatar behavior."""
    api_key: str
    avatar_id: str
    voice_id: str
    base_url: str = "https://api.heygen.com/v1"
    # Latency targets
    max_startup_ms: int = 3000
    max_speech_latency_ms: int = 500
    # Expression settings
    enable_sentiment_expressions: bool = True
    enable_idle_animations: bool = True
    idle_blink_interval_sec: float = 3.5
    # Lip sync
    enable_lip_sync: bool = True
    lip_sync_smoothing: float = 0.3
    # Quality
    video_quality: str = "high"  # high, medium, low
    resolution: str = "720p"  # 1080p, 720p, 480p


class AvatarEngine:
    """
    Real-time avatar engine for human-like AI representation.

    Features:
    - WebRTC streaming session management
    - Sentiment-aware facial expressions
    - Lip-sync with TTS audio
    - Idle animations (blinking, breathing, micro-expressions)
    - Turn-taking cues (listening vs speaking states)
    - Low-latency (<500ms) speech-to-avatar movement
    """

    def __init__(self, config: AvatarConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            headers={"X-Api-Key": config.api_key},
            timeout=30.0,
        )
        self.session_id: Optional[str] = None
        self.webrtc_url: Optional[str] = None
        self.state = AvatarState.IDLE
        self._current_expression = Expression.NEUTRAL
        self._last_blink_time = 0.0
        self._session_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._is_running = False

    async def start_session(self) -> Dict[str, Any]:
        """
        Start a new real-time streaming avatar session.

        Returns:
            Session info dict with session_id, webrtc_url, and ICE config.
        """
        logger.info(f"Starting avatar session for avatar_id={self.config.avatar_id}")
        payload = {
            "avatar_id": self.config.avatar_id,
            "voice_id": self.config.voice_id,
            "quality": self.config.video_quality,
            "resolution": self.config.resolution,
            "enable_lip_sync": self.config.enable_lip_sync,
        }
        resp = await self.client.post("/streaming/start", json=payload)
        resp.raise_for_status()
        data = resp.json()

        self.session_id = data.get("session_id")
        self.webrtc_url = data.get("webrtc_url")
        self._is_running = True

        # Start idle animation loop
        if self.config.enable_idle_animations:
            self._idle_task = asyncio.create_task(self._idle_loop())

        logger.info(f"Avatar session started: {self.session_id}")
        return {
            "session_id": self.session_id,
            "webrtc_url": self.webrtc_url,
            "ice_servers": data.get("ice_servers", []),
            "sdp_offer": data.get("sdp_offer"),
        }

    async def send_speech(self, text: str, expression: Optional[Expression] = None) -> Dict[str, Any]:
        """
        Send text for the avatar to speak with synchronized expression.

        Args:
            text: Text to speak
            expression: Override expression, or auto-detect if None
        Returns:
            Task info with timing
        """
        if not self.session_id:
            raise RuntimeError("Avatar session not started")

        # Auto-detect sentiment if not provided
        if expression is None and self.config.enable_sentiment_expressions:
            expression = self._detect_sentiment(text)
        elif expression is None:
            expression = Expression.NEUTRAL

        self.state = AvatarState.SPEAKING
        self._current_expression = expression

        # Pre-send expression change for natural transition
        await self._set_expression(expression, duration=0.5)

        payload = {
            "session_id": self.session_id,
            "text": text,
            "voice_id": self.config.voice_id,
            "expression": expression.value,
            "quality": self.config.video_quality,
            "enable_lip_sync": self.config.enable_lip_sync,
            "lip_sync_smoothing": self.config.lip_sync_smoothing,
        }

        resp = await self.client.post("/streaming/task", json=payload)
        resp.raise_for_status()
        data = resp.json()

        task_id = data.get("task_id")
        estimated_duration_ms = data.get("estimated_duration_ms", len(text) * 80)

        logger.debug(f"Avatar speech task: {task_id}, text='{text[:50]}...', expr={expression.value}")

        # After speech completes, return to neutral/listening
        asyncio.create_task(self._post_speech_reset(estimated_duration_ms / 1000.0))

        return {
            "task_id": task_id,
            "estimated_duration_sec": estimated_duration_ms / 1000.0,
            "expression": expression.value,
        }

    async def set_listening_state(self):
        """Set avatar to 'listening' state — subtle nodding, eye contact."""
        if self.state == AvatarState.SPEAKING:
            return  # Don't interrupt speech
        self.state = AvatarState.LISTENING
        await self._set_expression(Expression.LISTENING, duration=2.0)

    async def set_thinking_state(self):
        """Set avatar to 'thinking' state — slight head tilt, contemplative."""
        if self.state == AvatarState.SPEAKING:
            return
        self.state = AvatarState.THINKING
        await self._set_expression(Expression.THINKING, duration=1.5)

    async def stop_session(self) -> Dict[str, Any]:
        """Stop the avatar streaming session and cleanup."""
        self._is_running = False

        if self._idle_task:
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass
            self._idle_task = None

        if self.session_id:
            try:
                resp = await self.client.post("/streaming/stop", json={"session_id": self.session_id})
                resp.raise_for_status()
                logger.info(f"Avatar session stopped: {self.session_id}")
            except Exception as e:
                logger.warning(f"Error stopping avatar session: {e}")

        self.session_id = None
        self.webrtc_url = None
        self.state = AvatarState.IDLE
        return {"status": "stopped"}

    async def _set_expression(self, expression: Expression, duration: float = 2.0) -> Dict[str, Any]:
        """Send expression command to avatar."""
        if not self.session_id:
            return {"status": "no_session"}

        payload = {
            "session_id": self.session_id,
            "expression": expression.value,
            "duration": duration,
        }
        try:
            resp = await self.client.post("/streaming/expression", json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Expression change failed: {e}")
            return {"status": "error", "message": str(e)}

    async def _idle_loop(self):
        """Background loop for idle animations: blinking, micro-expressions, breathing."""
        import time
        import random

        while self._is_running and self.session_id:
            await asyncio.sleep(0.5)

            if self.state not in (AvatarState.IDLE, AvatarState.LISTENING):
                continue

            now = time.time()

            # Random blink every 2.5-5 seconds (human-like)
            if now - self._last_blink_time > random.uniform(2.5, 5.0):
                await self._trigger_blink()
                self._last_blink_time = now

            # Random micro-expression (subtle emotional shifts)
            if random.random() < 0.05:  # 5% chance per 0.5s tick
                micro = random.choice([
                    Expression.NEUTRAL,
                    Expression.FRIENDLY,
                    Expression.SMILE,
                ])
                await self._set_expression(micro, duration=0.8)

    async def _trigger_blink(self):
        """Trigger a natural blink animation."""
        if not self.session_id:
            return
        try:
            await self.client.post("/streaming/expression", json={
                "session_id": self.session_id,
                "expression": "blink",
                "duration": 0.15,
            })
        except Exception:
            pass

    async def _post_speech_reset(self, delay_sec: float):
        """Return avatar to neutral/listening after speech completes."""
        await asyncio.sleep(delay_sec)
        if self._is_running and self.state == AvatarState.SPEAKING:
            self.state = AvatarState.LISTENING
            await self._set_expression(Expression.LISTENING, duration=2.0)

    def _detect_sentiment(self, text: str) -> Expression:
        """Simple sentiment detection for expression mapping."""
        text_lower = text.lower()

        # Emergency / concern
        if any(w in text_lower for w in ["emergency", "pain", "hurt", "urgent", "worried", "sorry"]):
            return Expression.CONCERNED

        # Celebration / good news
        if any(w in text_lower for w in ["congratulations", "excellent", "great news", "confirmed", "booked"]):
            return Expression.CELEBRATORY

        # Empathy / comfort
        if any(w in text_lower for w in ["understand", "feel", "difficult", "stress", "anxiety"]):
            return Expression.EMPATHETIC

        # Surprised
        if any(w in text_lower for w in ["wow", "amazing", "unexpected", "surprised"]):
            return Expression.SURPRISED

        # Friendly greeting
        if any(w in text_lower for w in ["hello", "hi there", "welcome", "good morning", "good afternoon"]):
            return Expression.FRIENDLY

        # Smile / positive
        if any(w in text_lower for w in ["happy", "perfect", "wonderful", "glad", "pleased"]):
            return Expression.SMILE

        return Expression.NEUTRAL

    async def close(self):
        """Close HTTP client."""
        await self.stop_session()
        await self.client.aclose()


class AvatarEngineFactory:
    """Factory for creating avatar engines from environment config."""

    @staticmethod
    def from_env() -> AvatarEngine:
        """Create an AvatarEngine from environment variables."""
        config = AvatarConfig(
            api_key=os.getenv("HEYGEN_API_KEY", ""),
            avatar_id=os.getenv("HEYGEN_AVATAR_ID", ""),
            voice_id=os.getenv("HEYGEN_VOICE_ID", ""),
            base_url=os.getenv("HEYGEN_BASE_URL", "https://api.heygen.com/v1"),
            video_quality=os.getenv("HEYGEN_QUALITY", "high"),
            resolution=os.getenv("HEYGEN_RESOLUTION", "720p"),
            enable_lip_sync=os.getenv("HEYGEN_LIP_SYNC", "true").lower() == "true",
            enable_sentiment_expressions=True,
            enable_idle_animations=True,
        )
        return AvatarEngine(config)
