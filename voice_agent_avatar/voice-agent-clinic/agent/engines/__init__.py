"""
Free SOTA engine package.
All engines are zero-cost, self-hostable, with optional GPU acceleration.
"""

from .llm import GeminiEngine, GroqEngine, OllamaEngine
from .tts import KokoroTTSEngine, F5TTSEngine, XTTSEngine
from .stt import DeepgramSTTEngine
from .avatar import LivePortraitEngine
from .core import VoiceAgent

__all__ = [
    # LLM
    "GeminiEngine",
    "GroqEngine",
    "OllamaEngine",
    # TTS
    "KokoroTTSEngine",
    "F5TTSEngine",
    "XTTSEngine",
    # STT
    "DeepgramSTTEngine",
    # Avatar
    "LivePortraitEngine",
    # Core
    "VoiceAgent",
]
