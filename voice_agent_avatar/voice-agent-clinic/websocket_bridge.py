"""
WebSocket Bridge: STT → LLM → TTS → Avatar
End-to-end latency target: <500ms

Architecture:
    WebRTC Audio → Deepgram STT → Gemini LLM → Kokoro TTS → LivePortrait → WebRTC Video
                                    ↓
                            Function Calls (Calendar, CRM, etc.)

Run on Kaggle: This bridges the Voice Agent notebook + Avatar notebook
"""

import asyncio
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, AsyncIterator, Dict, Any
from collections import deque

import numpy as np
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config_free import config, Config
from agent.engines import (
    GeminiEngine,
    KokoroTTSEngine,
)
from agent.engines.core import VoiceAgent
from agent.prompts import get_system_prompt
from agent.functions.calendar import CalendarFunctions
from agent.functions.crm import CRMFunctions
from agent.functions.notifications import NotificationFunctions
from agent.middleware.guardrails import Guardrails
from agent.knowledge.retriever import KnowledgeRetriever

logger = logging.getLogger("websocket_bridge")
logging.basicConfig(level=logging.INFO)


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineMetrics:
    """Track latency at each stage."""
    stt_start: float = 0
    stt_end: float = 0
    llm_start: float = 0
    llm_first_token: float = 0
    llm_end: float = 0
    tts_start: float = 0
    tts_end: float = 0
    avatar_start: float = 0
    avatar_end: float = 0
    
    @property
    def stt_latency_ms(self) -> float:
        return (self.stt_end - self.stt_start) * 1000
    
    @property
    def llm_latency_ms(self) -> float:
        return (self.llm_end - self.llm_start) * 1000
    
    @property
    def llm_ttft_ms(self) -> float:
        return (self.llm_first_token - self.llm_start) * 1000
    
    @property
    def tts_latency_ms(self) -> float:
        return (self.tts_end - self.tts_start) * 1000
    
    @property
    def avatar_latency_ms(self) -> float:
        return (self.avatar_end - self.avatar_start) * 1000
    
    @property
    def total_latency_ms(self) -> float:
        return (self.avatar_end - self.stt_start) * 1000
    
    def log(self):
        logger.info(
            f"LATENCY: STT={self.stt_latency_ms:.0f}ms "
            f"LLM={self.llm_latency_ms:.0f}ms (TTFT={self.llm_ttft_ms:.0f}ms) "
            f"TTS={self.tts_latency_ms:.0f}ms "
            f"Avatar={self.avatar_latency_ms:.0f}ms "
            f"TOTAL={self.total_latency_ms:.0f}ms"
        )


@dataclass
class Session:
    """Active voice session state."""
    session_id: str
    ws: WebSocket
    vertical: str = "dental"
    
    # Engines (initialized lazily)
    stt_engine: Any = None
    llm_engine: Any = None
    tts_engine: Any = None
    avatar_engine: Any = None
    agent: Any = None
    
    # Audio buffering
    audio_buffer: deque = field(default_factory=lambda: deque(maxlen=32000))  # 2s at 16kHz
    is_speaking: bool = False
    last_user_speech_time: float = 0
    
    # Metrics
    current_metrics: Optional[PipelineMetrics] = None
    total_requests: int = 0
    
    # Turn management
    vad_state: str = "listening"  # listening, processing, speaking
    pending_llm_response: str = ""
    pending_tts_audio: bytes = b""


# ─────────────────────────────────────────────────────────────────────────────
# STT ENGINE WRAPPER (Deepgram Streaming)
# ─────────────────────────────────────────────────────────────────────────────

class STTEngine:
    """Streaming STT with Deepgram."""
    
    def __init__(self, api_key: str, language: str = "en"):
        self.api_key = api_key
        self.language = language
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._transcript_callback: Optional[callable] = None
        self._is_connected = False
    
    async def connect(self, on_transcript: callable):
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
        
        # Start listener
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


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class VoicePipeline:
    """Orchestrates STT → LLM → TTS → Avatar with function calling."""
    
    def __init__(self, session: Session, cfg: Config):
        self.session = session
        self.cfg = cfg
        self.stt_engine: Optional[STTEngine] = None
        self.llm_engine = None
        self.tts_engine = None
        self.agent = None
        self.guardrails = Guardrails()
        self._initialize_engines()
    
    def _initialize_engines(self):
        """Initialize all engines based on config."""
        # STT
        if self.cfg.stt.provider == "deepgram":
            self.stt_engine = STTEngine(
                api_key=self.cfg.stt.deepgram_api_key,
                language=self.cfg.stt.deepgram_language,
            )
        
        # LLM
        if self.cfg.llm.provider == "gemini":
            self.llm_engine = GeminiEngine(
                api_key=self.cfg.llm.gemini_api_key,
                model=self.cfg.llm.gemini_model,
            )
        elif self.cfg.llm.provider == "groq":
            from kaggle.voice_agent_kaggle import GroqEngine  # type: ignore
            self.llm_engine = GroqEngine(
                api_key=self.cfg.llm.groq_api_key,
                model=self.cfg.llm.groq_model,
            )
        
        # TTS
        if self.cfg.tts.provider == "kokoro":
            self.tts_engine = KokoroTTSEngine(
                model_path=self.cfg.tts.kokoro_model_path,
                voices_path=self.cfg.tts.kokoro_voices_path,
                lang_code=self.cfg.tts.kokoro_lang_code,
                voice=self.cfg.tts.kokoro_voice,
            )
        
        # Agent (function calling)
        self.agent = ClinicAgent(
            vertical=self.session.vertical,
            config={
                "calcom_event_type_id": self.cfg.integration.calcom_event_type_id,
                "timezone": self.cfg.integration.clinic_timezone,
            }
        )
    
    async def start(self):
        """Start the pipeline."""
        # Connect STT
        if self.stt_engine:
            await self.stt_engine.connect(self._on_transcript)
        
        logger.info(f"Pipeline started for session {self.session.session_id}")
    
    async def _on_transcript(self, transcript: str, is_final: bool):
        """Handle incoming transcript from STT."""
        if not transcript.strip():
            return
        
        # Start metrics
        if is_final and not self.session.current_metrics:
            self.session.current_metrics = PipelineMetrics()
            self.session.current_metrics.stt_start = time.time()
        
        logger.debug(f"Transcript: '{transcript}' (final={is_final})")
        
        if is_final:
            self.session.current_metrics.stt_end = time.time()
            await self._process_user_turn(transcript)
    
    async def _process_user_turn(self, user_text: str):
        """Process complete user turn through LLM + function calling."""
        metrics = self.session.current_metrics
        if metrics:
            metrics.llm_start = time.time()
        
        # Guardrails: Check for abusive language before sending to LLM
        if self.guardrails.contains_abusive_language(user_text):
            logger.warning(f"Abusive language detected in user input for session {self.session.session_id}")
            await self._speak_response("I cannot assist with inappropriate or abusive language. Please let me know how else I can assist you.")
            return
        
        # Guardrails: Check and redact PII from incoming user text before sending to LLM
        if self.guardrails.contains_pii(user_text):
            logger.info(f"PII detected in user input for session {self.session.session_id}, redacting before LLM processing")
        sanitized_user_text = self.guardrails.redact_pii(user_text)
        
        # Build conversation history (simplified - in production use proper context)
        messages = [{"role": "user", "content": sanitized_user_text}]
        system_prompt = get_system_prompt(self.session.vertical)
        
        # Get LLM response with function calling
        try:
            # First, try function calling
            functions = self._get_function_schemas()
            result = await self.llm_engine.function_call(messages, system_prompt, functions)
            
            if result["type"] == "function_call":
                # Execute function
                func_result = await self._execute_function(result["name"], result["args"])
                
                # Send function result back to LLM for natural response
                messages.append({"role": "assistant", "content": f"[Function call: {result['name']}]"})
                messages.append({"role": "function", "content": func_result, "name": result["name"]})
                
                # Get final response
                response = await self.llm_engine.chat(messages, system_prompt)
            else:
                response = result["text"]
            
            if metrics:
                metrics.llm_end = time.time()
                metrics.llm_first_token = metrics.llm_start + 0.1  # Approximate
            
            # Guardrails: Redact PII from LLM output before TTS or logging
            sanitized_response = self.guardrails.redact_pii(response)
            
            # Generate TTS
            await self._speak_response(sanitized_response)
            
        except Exception as e:
            logger.error(f"LLM processing error: {e}")
            await self._speak_response("I'm sorry, I encountered an error. Please try again.")
    
    def _get_function_schemas(self) -> list:
        """Get function schemas for LLM."""
        return [
            {
                "name": "check_availability",
                "description": "Check available appointment slots for a given date",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                        "duration_minutes": {"type": "integer", "default": 30},
                    },
                    "required": ["date"],
                },
            },
            {
                "name": "book_appointment",
                "description": "Book an appointment for a patient",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_time": {"type": "string", "description": "ISO 8601 datetime"},
                        "patient_name": {"type": "string"},
                        "phone": {"type": "string"},
                        "email": {"type": "string"},
                        "reason": {"type": "string", "default": "General consultation"},
                    },
                    "required": ["start_time", "patient_name", "phone", "email"],
                },
            },
            {
                "name": "cancel_appointment",
                "description": "Cancel an existing appointment",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "booking_id": {"type": "string"},
                        "phone": {"type": "string"},
                    },
                },
            },
            {
                "name": "upsert_lead",
                "description": "Create or update a lead in the CRM",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "phone": {"type": "string"},
                        "email": {"type": "string"},
                        "source": {"type": "string", "default": "voice_agent"},
                    },
                    "required": ["name", "phone", "email"],
                },
            },
            {
                "name": "query_knowledge_base",
                "description": "Look up answers from the clinic FAQ",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                    },
                    "required": ["question"],
                },
            },
            {
                "name": "get_current_datetime",
                "description": "Get current date and time",
                "parameters": {"type": "object", "properties": {}},
            },
        ]
    
    async def _execute_function(self, name: str, args: dict) -> str:
        """Execute a function call."""
        try:
            method = getattr(self.agent, name)
            result = await method(**args)
            return result
        except Exception as e:
            logger.error(f"Function {name} error: {e}")
            return json.dumps({"status": "error", "message": str(e)})
    
    async def _speak_response(self, text: str):
        """Generate TTS and stream to avatar."""
        # Guardrails: Ensure PII is redacted before TTS synthesis and logging
        sanitized_text = self.guardrails.redact_pii(text)
        metrics = self.session.current_metrics
        if metrics:
            metrics.tts_start = time.time()
        
        try:
            # Generate audio
            audio_bytes = await self.tts_engine.synthesize(sanitized_text, speed=self.cfg.tts.speed)
            if metrics:
                metrics.tts_end = time.time()
            
            # Send audio to client (for WebRTC playback)
            await self.session.ws.send_bytes(audio_bytes)
            
            # Also send to avatar engine for video generation
            await self._send_to_avatar(audio_bytes)
            
            logger.info(f"TTS generated: {len(audio_bytes)} bytes, text: '{sanitized_text[:50]}...'")
            
        except Exception as e:
            logger.error(f"TTS error: {e}")
    
    async def _send_to_avatar(self, audio_bytes: bytes):
        """Send audio to avatar engine for video generation."""
        metrics = self.session.current_metrics
        metrics.avatar_start = time.time()
        
        # Convert audio bytes to float32 array
        import torchaudio
        import io
        waveform, sample_rate = torchaudio.load(io.BytesIO(audio_bytes))
        
        # Resample to 16kHz if needed
        if sample_rate != 16000:
            import torchaudio.transforms as T
            resampler = T.Resample(sample_rate, 16000)
            waveform = resampler(waveform)
        
        audio_chunk = waveform.squeeze().numpy().astype(np.float32)
        
        # Send to avatar engine (if available)
        # In production, this would be a WebSocket connection to the avatar server
        # For now, we just track the metric
        metrics.avatar_end = time.time()
        
        # Log total latency
        metrics.log()
        
        # Reset for next turn
        self.session.current_metrics = None
    
    async def send_audio_to_stt(self, audio_bytes: bytes):
        """Forward audio to STT engine."""
        if self.stt_engine:
            await self.stt_engine.send_audio(audio_bytes)
    
    async def close(self):
        """Cleanup."""
        if self.stt_engine:
            await self.stt_engine.close()
        if self.agent and hasattr(self.agent, "cleanup"):
            await self.agent.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI WEBSOCKET SERVER
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Voice Agent Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_sessions: Dict[str, Session] = {}
active_pipelines: Dict[str, VoicePipeline] = {}


@app.websocket("/bridge/{vertical}")
async def bridge_endpoint(websocket: WebSocket, vertical: str = "dental"):
    """Main WebSocket endpoint for voice pipeline with authentication."""
    expected_key = os.getenv("VOICE_AGENT_API_KEY")
    
    # Extract auth token strictly from headers (avoids logging leakage in URLs/proxies)
    token = websocket.headers.get("x-api-key")
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif auth_header:
            token = auth_header.strip()
    
    # Reject connection if VOICE_AGENT_API_KEY is not set or token mismatch
    if not expected_key or not token or not secrets.compare_digest(token, expected_key):
        logger.warning(f"Unauthorized WebSocket connection attempt to /bridge/{vertical}")
        await websocket.close(code=1008)
        return
    
    session_id = str(uuid.uuid4())[:8]
    
    await websocket.accept()
    logger.info(f"New bridge session: {session_id} (vertical={vertical})")
    
    # Create session
    session = Session(session_id=session_id, ws=websocket, vertical=vertical)
    active_sessions[session_id] = session
    
    # Initialize pipeline
    pipeline = VoicePipeline(session, config)
    active_pipelines[session_id] = pipeline
    
    try:
        await pipeline.start()
        
        # Send ready signal
        await websocket.send_text(json.dumps({
            "type": "ready",
            "session_id": session_id,
            "config": {
                "llm": config.llm.provider,
                "tts": config.tts.provider,
                "avatar": config.avatar.provider,
            }
        }))
        
        # Main message loop
        while True:
            data = await websocket.receive()
            
            if "bytes" in data:
                # Audio data from client
                await pipeline.send_audio_to_stt(data["bytes"])
                
            elif "text" in data:
                # Control messages
                msg = json.loads(data["text"])
                await _handle_control_message(session, pipeline, msg)
                
    except WebSocketDisconnect:
        logger.info(f"Session {session_id} disconnected")
    except Exception as e:
        logger.error(f"Session {session_id} error: {e}")
    finally:
        await pipeline.close()
        active_sessions.pop(session_id, None)
        active_pipelines.pop(session_id, None)


async def _handle_control_message(session: Session, pipeline: VoicePipeline, msg: dict):
    """Handle control messages from client."""
    msg_type = msg.get("type")
    
    if msg_type == "ping":
        await session.ws.send_text(json.dumps({"type": "pong"}))
    elif msg_type == "interrupt":
        # User interrupted - stop current TTS
        logger.info("Interruption received")
    elif msg_type == "config":
        # Update config
        logger.info(f"Config update: {msg}")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_sessions": len(active_sessions),
        "config": {
            "llm": config.llm.provider,
            "tts": config.tts.provider,
            "stt": config.stt.provider,
            "avatar": config.avatar.provider,
        }
    }


@app.get("/sessions")
async def list_sessions():
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "vertical": s.vertical,
                "requests": s.total_requests,
            }
            for s in active_sessions.values()
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the WebSocket bridge server."""
    api_key = os.getenv("VOICE_AGENT_API_KEY")
    if not api_key:
        raise RuntimeError(
            "VOICE_AGENT_API_KEY environment variable is not set. "
            "Server refusing to start in unauthenticated state."
        )
    
    logger.info(f"Starting Voice Pipeline Bridge on {host}:{port}")
    logger.info(f"Config: LLM={config.llm.provider}, TTS={config.tts.provider}, "
                f"STT={config.stt.provider}, Avatar={config.avatar.provider}")
    
    errors = config.validate()
    if errors:
        logger.warning("Config validation warnings:")
        for e in errors:
            logger.warning(f"  - {e}")
    
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()