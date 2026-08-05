"""
TTS engines — free/self-hosted text-to-speech.
Supports Kokoro (CPU), F5-TTS (zero-shot voice clone), XTTS v2.
"""

import asyncio
import io
import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# KOKORO — runs on CPU, 82 voices, multilingual
# ─────────────────────────────────────────────────────────────────────────────

class KokoroTTSEngine:
    """
    Kokoro TTS — 82 voices, multilingual, runs on CPU.
    Best for: Quick deployment, no GPU needed.
    """

    def __init__(
        self,
        model_path: str = "/kaggle/working/models/kokoro-v0_19.onnx",
        voices_path: str = "/kaggle/working/models/voices.bin",
        lang_code: str = "a",
        voice: str = "af_heart",
    ):
        from kokoro_onnx import Kokoro
        import onnxruntime as ort

        if "CUDAExecutionProvider" in ort.get_available_providers():
            logger.info("Initializing Kokoro on GPU (cuda:1 with fallback to cuda:0)...")
            providers = [("CUDAExecutionProvider", {"device_id": 1}), "CUDAExecutionProvider", "CPUExecutionProvider"]
            try:
                self.pipeline = Kokoro.from_session(
                    ort.InferenceSession(model_path, providers=providers),
                    voices_path
                )
            except Exception as e:
                logger.warning(f"Failed to load Kokoro on GPU, falling back to CPU: {e}")
                self.pipeline = Kokoro(model_path, voices_path)
        else:
            logger.info("Initializing Kokoro on CPU...")
            self.pipeline = Kokoro(model_path, voices_path)
        self.voice = voice
        self.lang_code = lang_code
        logger.info(f"Kokoro TTS loaded: voice={voice}, lang={lang_code}")

    async def synthesize(self, text: str, speed: float = 1.0) -> bytes:
        """Synthesize speech from text. Returns WAV bytes."""
        import torch
        import torchaudio
        import numpy as np

        loop = asyncio.get_event_loop()

        def _generate():
            samples, sample_rate = self.pipeline.create(
                text, voice=self.voice, speed=speed, lang=self.lang_code
            )
            audio_tensor = torch.from_numpy(samples).float().unsqueeze(0)
            return audio_tensor, sample_rate

        audio_tensor, sample_rate = await loop.run_in_executor(None, _generate)

        buffer = io.BytesIO()
        torchaudio.save(buffer, audio_tensor, sample_rate, format="wav")
        return buffer.getvalue()

    async def synthesize_base64(self, text: str, speed: float = 1.0) -> str:
        """Synthesize and return base64-encoded WAV."""
        wav_bytes = await self.synthesize(text, speed)
        return base64.b64encode(wav_bytes).decode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# F5-TTS — zero-shot voice cloning, best quality
# ─────────────────────────────────────────────────────────────────────────────

class F5TTSEngine:
    """
    Self-hosted F5-TTS engine.
    Zero-shot voice cloning from a reference audio sample.
    Requires 4GB+ VRAM.
    """

    def __init__(
        self,
        model_path: str = "SWivid/F5-TTS_v1",
        device: str = "cuda",
        ref_audio_path: Optional[str] = None,
    ):
        import torch
        from f5_tts.model import DiT
        from f5_tts.infer.utils_infer import load_model, preprocess_ref_audio_text

        self.device = device if torch.cuda.is_available() else "cpu"
        self.model, self.vocoder = load_model(model_path, device=self.device)
        self.ref_audio_path = ref_audio_path or "assets/ref_voice_clinic.wav"
        self._ref_cache = None
        self._preprocess = preprocess_ref_audio_text

        logger.info(f"F5-TTS loaded on {self.device}")

    def _get_ref_audio(self):
        if self._ref_cache is None:
            self._ref_cache = self._preprocess(
                self.ref_audio_path,
                "Welcome to our clinic, how can I help you today?",
            )
        return self._ref_cache

    async def synthesize(self, text: str, speed: float = 1.0) -> bytes:
        """Synthesize speech from text. Returns WAV bytes."""
        import torch
        import torchaudio
        from f5_tts.infer.utils_infer import infer_process

        try:
            ref_audio, ref_text = self._get_ref_audio()

            loop = asyncio.get_event_loop()
            wav, sr, _ = await loop.run_in_executor(
                None,
                lambda: infer_process(
                    ref_audio,
                    ref_text,
                    text,
                    model=self.model,
                    vocoder=self.vocoder,
                    mel_spec_type="vocos",
                    speed=speed,
                    device=self.device,
                ),
            )

            buffer = io.BytesIO()
            torchaudio.save(buffer, torch.tensor(wav).unsqueeze(0), sr, format="wav")
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"F5-TTS synthesis failed: {e}")
            raise

    async def synthesize_base64(self, text: str, speed: float = 1.0) -> str:
        """Synthesize and return base64-encoded WAV."""
        wav_bytes = await self.synthesize(text, speed)
        return base64.b64encode(wav_bytes).decode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# XTTS v2 — most natural for short phrases, 6s voice clone
# ─────────────────────────────────────────────────────────────────────────────

class XTTSEngine:
    """
    XTTS v2 — Most natural free TTS for short phrases.
    6-second voice clone. Good for clinic receptionist voice.
    """

    def __init__(self, speaker_wav: str = "assets/clinic_voice.wav"):
        from TTS.api import TTS

        self.tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        self.speaker_wav = speaker_wav
        logger.info("XTTS v2 loaded")

    async def synthesize(self, text: str, language: str = "en") -> bytes:
        import torch
        import numpy as np

        loop = asyncio.get_event_loop()

        def _generate():
            wav = self.tts.tts(text=text, speaker_wav=self.speaker_wav, language=language)
            tensor = torch.from_numpy(np.array(wav)).unsqueeze(0).float()
            buffer = io.BytesIO()
            torchaudio.save(buffer, tensor, 24000, format="wav")
            return buffer.getvalue()

        return await loop.run_in_executor(None, _generate)
