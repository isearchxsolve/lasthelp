"""
FREE SOTA Configuration - Zero API Costs
Drop this in to replace all paid services with one line change.

Usage:
    from config_free import Config
    
    # Switch providers instantly:
    Config.LLM_PROVIDER = "gemini"  # or "groq" or "ollama"
    Config.TTS_PROVIDER = "kokoro"  # or "f5_tts" or "xtts"
    Config.AVATAR_PROVIDER = "liveportrait"  # or "sonic"
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Literal

# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER SELECTION - Change these to swap entire stack
# ─────────────────────────────────────────────────────────────────────────────

LLM_PROVIDER: Literal["gemini", "groq", "ollama"] = "gemini"
TTS_PROVIDER: Literal["kokoro", "f5_tts", "xtts"] = "kokoro"
STT_PROVIDER: Literal["deepgram", "local_whisper"] = "deepgram"
AVATAR_PROVIDER: Literal["liveportrait", "sonic", "none"] = "liveportrait"

# ─────────────────────────────────────────────────────────────────────────────
# LLM CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LLMConfig:
    provider: str = LLM_PROVIDER
    
    # Gemini (Free: 1500 req/day, 1M tokens/min)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = "gemini-3.5-flash"  # or "gemini-1.5-pro-latest"
    
    # Groq (Free: 144k tokens/day, 20 req/min, 800 tok/s)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = "llama-3.3-70b-versatile"
    
    # Ollama (Self-hosted, unlimited)
    ollama_base_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = "llama3.3:70b"
    
    # Voice-optimized settings
    temperature: float = 0.3
    max_tokens: int = 256
    top_p: float = 0.95
    
    def get_api_key(self) -> str:
        if self.provider == "gemini":
            return self.gemini_api_key
        elif self.provider == "groq":
            return self.groq_api_key
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# TTS CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TTSConfig:
    provider: str = TTS_PROVIDER
    
    # Kokoro (Free, CPU, 82 voices, 50x real-time on GPU)
    kokoro_model_path: str = "/kaggle/working/models/kokoro-v0_19.onnx"
    kokoro_voices_path: str = "/kaggle/working/models/voices.bin"
    kokoro_lang_code: str = "a"  # a=US, b=UK, j=JP, z=CN
    kokoro_voice: str = "af_heart"  # 82 voices available
    
    # F5-TTS (Free, GPU, voice cloning from 10s audio)
    f5_tts_model: str = "SWivid/F5-TTS_v1"
    f5_tts_ref_audio: str = "assets/clinic_voice.wav"
    f5_tts_device: str = "cuda"
    
    # XTTS v2 (Free, GPU, voice cloning from 6s audio)
    xtts_speaker_wav: str = "assets/clinic_voice.wav"
    xtts_language: str = "en"
    
    # Voice settings
    speed: float = 1.0
    sample_rate: int = 24000

# ─────────────────────────────────────────────────────────────────────────────
# STT CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class STTConfig:
    provider: str = STT_PROVIDER
    
    # Deepgram (Free: 200 min/month)
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
    deepgram_model: str = "nova-2"
    deepgram_language: str = "en"
    
    # Local Whisper (Free, self-hosted)
    whisper_model: str = "base"  # tiny, base, small, medium, large
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

# ─────────────────────────────────────────────────────────────────────────────
# AVATAR CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AvatarConfig:
    provider: str = AVATAR_PROVIDER
    
    # LivePortrait (Free, GPU, real-time)
    liveportrait_checkpoint_dir: str = "/kaggle/working/LivePortrait/checkpoints"
    liveportrait_ref_image: str = "/kaggle/working/reference_image.jpg"
    liveportrait_device: str = "cuda"
    liveportrait_fps: int = 30
    liveportrait_resolution: tuple = (512, 512)
    
    # Sonic (Free, GPU, real-time lip-sync)
    sonic_checkpoint_path: str = "/kaggle/working/Sonic/checkpoints"
    sonic_ref_image: str = "/kaggle/working/reference_image.jpg"
    sonic_device: str = "cuda"
    
    # WebRTC signaling
    signaling_host: str = "0.0.0.0"
    signaling_port: int = 7860
    gradio_port: int = 7861

# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION CONFIGURATION (Unchanged - use free tiers)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IntegrationConfig:
    # LiveKit (Free tier available)
    livekit_url: str = os.getenv("LIVEKIT_URL", "")
    livekit_api_key: str = os.getenv("LIVEKIT_API_KEY", "")
    livekit_api_secret: str = os.getenv("LIVEKIT_API_SECRET", "")
    
    # Cal.com (Free tier)
    calcom_api_key: str = os.getenv("CALCOM_API_KEY", "")
    calcom_event_type_id: int = int(os.getenv("CALCOM_EVENT_TYPE_ID", "12345"))
    
    # CRM Webhook (Your endpoint)
    crm_webhook_url: str = os.getenv("CRM_WEBHOOK_URL", "")
    crm_api_key: str = os.getenv("CRM_API_KEY", "")
    
    # Twilio SMS (Free tier)
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from_number: str = os.getenv("TWILIO_FROM_NUMBER", "")
    
    # SendGrid Email (Free tier)
    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    sendgrid_from_email: str = os.getenv("SENDGRID_FROM_EMAIL", "noreply@clinic.com")
    
    # Escalation
    oncall_phone: str = os.getenv("ONCALL_PHONE", "")
    
    # Clinic settings
    clinic_timezone: str = os.getenv("CLINIC_TIMEZONE", "America/New_York")
    vertical: str = "dental"

# ─────────────────────────────────────────────────────────────────────────────
# MASTER CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    avatar: AvatarConfig = field(default_factory=AvatarConfig)
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)
    
    # Kaggle-specific
    is_kaggle: bool = field(default_factory=lambda: "KAGGLE_KERNEL_RUN_TYPE" in os.environ)
    
    def validate(self) -> list[str]:
        """Return list of missing required configs."""
        errors = []
        
        # LLM
        if self.llm.provider == "gemini" and not self.llm.gemini_api_key:
            errors.append("GEMINI_API_KEY required for Gemini provider")
        elif self.llm.provider == "groq" and not self.llm.groq_api_key:
            errors.append("GROQ_API_KEY required for Groq provider")
        elif self.llm.provider == "ollama" and not self.llm.ollama_base_url:
            errors.append("OLLAMA_URL required for Ollama provider")
        
        # STT
        if self.stt.provider == "deepgram" and not self.stt.deepgram_api_key:
            errors.append("DEEPGRAM_API_KEY required for Deepgram STT")
        
        # LiveKit
        if not self.integration.livekit_url:
            errors.append("LIVEKIT_URL required")
        if not self.integration.livekit_api_key:
            errors.append("LIVEKIT_API_KEY required")
        if not self.integration.livekit_api_secret:
            errors.append("LIVEKIT_API_SECRET required")
        
        # Calendar
        if not self.integration.calcom_api_key:
            errors.append("CALCOM_API_KEY required for calendar")
        
        return errors
    
    def print_summary(self):
        """Print configuration summary."""
        print("=" * 60)
        print("VOICE AGENT CLINIC - FREE STACK CONFIGURATION")
        print("=" * 60)
        print(f"LLM:       {self.llm.provider.upper()} ({self.llm.gemini_model if self.llm.provider=='gemini' else self.llm.groq_model if self.llm.provider=='groq' else self.llm.ollama_model})")
        print(f"TTS:       {self.tts.provider.upper()}")
        print(f"STT:       {self.stt.provider.upper()}")
        print(f"Avatar:    {self.avatar.provider.upper()}")
        print(f"Platform:  {'Kaggle' if self.is_kaggle else 'Local/Docker'}")
        print("-" * 60)
        errors = self.validate()
        if errors:
            print("⚠️  MISSING CONFIG:")
            for e in errors:
                print(f"   - {e}")
        else:
            print("✅ All required configs present")
        print("=" * 60)

# Global instance
config = Config()

if __name__ == "__main__":
    config.print_summary()