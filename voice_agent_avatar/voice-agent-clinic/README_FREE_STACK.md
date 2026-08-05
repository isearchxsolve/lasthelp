# Voice Agent Clinic - Free SOTA Stack

**Cost: $0/month** • Runs entirely on **Kaggle Free Tier** (30hrs GPU/week + 20hrs CPU/week)

---

## 🏗️ Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│  WebSocket  │────▶│   Deepgram  │────▶│   Gemini    │────▶│   Kokoro    │
│  (WebRTC)   │     │   Bridge    │     │    STT      │     │   3.5 Flash │     │    TTS      │
└─────────────┘     │  (port 8000)│     │  (Free 200  │     │  (Free 1500 │     │  (Free CPU) │
                    └─────────────┘     │   min/mo)   │     │   req/day)  │     └──────┬──────┘
                          │             └─────────────┘     └──────┬──────┘            │
                          ▼                                        ▼                   ▼
                   ┌─────────────┐                         ┌─────────────┐     ┌─────────────┐
                   │  LiveKit    │                         │  Function   │     │ LivePortrait│
                   │  (Signaling)│                         │  Calling    │     │  (Free GPU) │
                   └─────────────┘                         └─────────────┘     │  (port 7860)│
                          │                                                         └──────┬──────┘
                          ▼                                                                ▼
                   ┌─────────────┐                                                ┌─────────────┐
                   │  Calendar   │                                                │   Browser   │
                   │  (Cal.com)  │                                                │  (Video)    │
                   └─────────────┘                                                └─────────────┘
```

---

## 📦 Components

| Component | Free Tier | Kaggle Notebook |
|-----------|-----------|-----------------|
| **LLM** | Gemini 3.5 Flash (1500 req/day) | `voice_agent_kaggle.ipynb` |
| **TTS** | Kokoro (CPU, 82 voices) | `voice_agent_kaggle.ipynb` |
| **STT** | Deepgram Nova-2 (200 min/mo) | `voice_agent_kaggle.ipynb` |
| **Avatar** | LivePortrait (GPU T4) | `liveportrait_avatar_kaggle.ipynb` |
| **Bridge** | FastAPI + WebSockets | `websocket_bridge.py` |
| **Calendar** | Cal.com (Free) | Built-in |
| **CRM** | Your webhook | Built-in |
| **SMS** | Twilio (Free tier) | Built-in |
| **Email** | SendGrid (Free tier) | Built-in |

---

## 🚀 Quick Start

### 1. Prerequisites

- Kaggle account (free): https://www.kaggle.com
- LiveKit Cloud account (free tier): https://livekit.io
- Deepgram API key (free 200 min/mo): https://console.deepgram.com
- Google AI Studio API key (free): https://aistudio.google.com/apikey
- Cal.com account (free): https://cal.com

### 2. Deploy Voice Agent (Notebook 1)

1. Open `kaggle/voice_agent_kaggle.ipynb` on Kaggle
2. Settings → Accelerator → **GPU T4 x2**
3. Settings → Internet → **On**
4. Settings → Secrets → Add:
   ```
   GEMINI_API_KEY=your_gemini_key
   DEEPGRAM_API_KEY=your_deepgram_key
   LIVEKIT_API_KEY=your_livekit_key
   LIVEKIT_API_SECRET=your_livekit_secret
   LIVEKIT_URL=wss://your-project.livekit.cloud
   CALCOM_API_KEY=your_calcom_key
   CRM_WEBHOOK_URL=https://your-crm.com/webhook
   CRM_API_KEY=your_crm_key
   TWILIO_ACCOUNT_SID=your_twilio_sid
   TWILIO_AUTH_TOKEN=your_twilio_token
   SENDGRID_API_KEY=your_sendgrid_key
   ONCALL_PHONE=+15551234567
   CLINIC_TIMEZONE=America/New_York
   CALCOM_EVENT_TYPE_ID=12345
   ```
5. Run all cells

### 3. Deploy Avatar (Notebook 2)

1. Open `kaggle/liveportrait_avatar_kaggle.ipynb` on Kaggle
2. Settings → Accelerator → **GPU T4 x2** (REQUIRED)
3. Settings → Internet → **On**
3. Settings → Secrets → Add:
   ```
   LIVEPORTRAIT_REF_IMAGE_URL=https://your-cdn.com/doctor.jpg
   LIVEKIT_API_KEY=your_livekit_key
   LIVEKIT_API_SECRET=your_livekit_secret
   LIVEKIT_URL=wss://your-project.livekit.cloud
   ```
4. Run all cells
5. Test UI at: `https://<kaggle-url>:7861`

### 4. Deploy Bridge (Optional - for custom frontend)

```bash
pip install -r requirements_bridge.txt
python websocket_bridge.py
```

Connect your frontend to `ws://localhost:8000/bridge/dental`

---

## 🔧 Configuration

Edit `config_free.py` to swap providers instantly:

```python
from config_free import config

# Switch LLM
config.LLM_PROVIDER = "gemini"   # or "groq" or "ollama"

# Switch TTS
config.TTS_PROVIDER = "kokoro"   # or "f5_tts" or "xtts"

# Switch Avatar
config.AVATAR_PROVIDER = "liveportrait"  # or "sonic" or "none"

config.print_summary()
```

### Provider Comparison

| Provider | Cost | Quality | Speed | Best For |
|----------|------|---------|-------|----------|
| **Gemini 3.5 Flash** | Free (1500/day) | ⭐⭐⭐⭐⭐ | 2-3s | Production |
| **Groq Llama 3.3** | Free (144k/day) | ⭐⭐⭐⭐ | 0.5s | Speed |
| **Ollama (self-host)** | $0 (your GPU) | ⭐⭐⭐⭐ | 2-5s | Privacy |
| **Kokoro TTS** | Free (CPU) | ⭐⭐⭐⭐ | 50x RT | Quick deploy |
| **F5-TTS** | Free (GPU) | ⭐⭐⭐⭐⭐ | 10x RT | Voice cloning |
| **LivePortrait** | Free (GPU) | ⭐⭐⭐⭐⭐ | 30 FPS | Best quality |

---

## 📁 File Structure

```
voice-agent-clinic/
├── config_free.py              # Master configuration
├── websocket_bridge.py         # STT→LLM→TTS→Avatar bridge
├── requirements_bridge.txt     # Bridge dependencies
├── kaggle/
│   ├── voice_agent_kaggle.ipynb      # Main voice agent (GPU)
│   └── liveportrait_avatar_kaggle.ipynb  # Avatar server (GPU)
├── agent/                      # Original LiveKit agent (paid stack)
└── kaggle/                     # Free stack notebooks
```

---

## 💰 Cost Breakdown

| Component | Paid Stack | Free Stack | Savings |
|-----------|------------|------------|---------|
| LLM | GPT-4o $0.06/min | Gemini $0 | $200-500/mo |
| TTS | ElevenLabs $0.30/1k | Kokoro $0 | $150-400/mo |
| STT | Deepgram $0.004/min | Deepgram Free 200min | $50-100/mo |
| Avatar | HeyGen $3/min | LivePortrait $0 | $500-2000/mo |
| **Total** | **~$900-3000/mo** | **$0/mo** | **99.6%** |

---

## 🎯 Production Scaling

When you outgrow free tiers (100+ calls/day):

```bash
# Option 1: Hetzner AX102 (€118/mo)
# 128GB RAM + 2x RTX 4090
# Run Ollama 70B + F5-TTS + LivePortrait
# Unlimited inference for $118/mo

# Option 2: RunPod / Lambda Labs
# Pay-per-second GPU rental
# ~$0.50/hr for A100
```

**10-client deployment:**
- Paid stack: $9,000-30,000/month
- Self-hosted: $118/month
- **Margin: 99.6%**

---

## 🔗 Integration

### Frontend (React/Vue)

```javascript
const ws = new WebSocket('wss://your-kaggle-url:8000/bridge/dental');

ws.onopen = () => {
  // Start recording audio
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = e => {
        if (e.data.size > 0) ws.send(e.data);
      };
      mediaRecorder.start(100); // 100ms chunks
    });
};

ws.onmessage = (event) => {
  if (event.data instanceof Blob) {
    // Audio response - play it
    const audio = new Audio(URL.createObjectURL(event.data));
    audio.play();
  } else {
    // Control messages
    const msg = JSON.parse(event.data);
  }
};
```

### LiveKit Room Metadata

When creating a room, set metadata for vertical:

```python
from livekit import api

room = await api.LiveRoomService().create_room(
    api.CreateRoomRequest(
        name="clinic-call-123",
        metadata=json.dumps({"vertical": "dental"})  # or medical, hvac, legal, real_estate
    )
)
```

---

## 🐛 Troubleshooting

### "Model not found" errors
- Ensure GPU is enabled in Kaggle settings
- Check `/kaggle/working/models/` exists for Kokoro
- Check `/kaggle/working/LivePortrait/checkpoints/` for LivePortrait

### High latency (>1s)
- Use `gemini-3.5-flash` (not pro)
- Reduce `max_tokens` to 128
- Enable `interim_results=true` in Deepgram

### Avatar not syncing
- Reference image must be 512x512, clear face
- Check WebRTC signaling on port 7860
- Verify LiveKit video track publishing

### Out of memory (OOM)
- Kaggle T4 has 16GB VRAM
- Close other notebooks
- Use `torch.cuda.empty_cache()` between requests

---

## 📜 License

MIT License - Use freely for commercial or personal projects.

---

## 🙏 Credits

- **LivePortrait**: Kwai-Kolors (https://github.com/Kwai-Kolors/LivePortrait)
- **Kokoro TTS**: remsky (https://github.com/remsky/Kokoro-FastAPI)
- **Gemini**: Google AI Studio
- **Deepgram**: Free tier STT
- **LiveKit**: Real-time audio/video infrastructure