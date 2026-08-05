# Voice Agent Clinic

A **state-of-the-art (SOTA) real-time voice AI agent** with an animated avatar, designed for clinics, dental practices, medical offices, HVAC companies, law firms, and real estate brokerages.

## Features

- **Real-time voice conversations** via LiveKit + WebRTC
- **AI avatar** with HeyGen / D-ID streaming integration
- **Appointment scheduling** via Cal.com API
- **CRM integration** (webhook-based, HubSpot/Zoho compatible)
- **SMS & email notifications** via Twilio + SendGrid
- **Knowledge base** with RAG for FAQ answering
- **Multi-vertical support** (dental, medical, HVAC, legal, real estate)
- **Observability** with Prometheus metrics and structured JSON logging
- **Guardrails** for PII detection, input validation, and content safety
- **Embeddable web widget** (React component with Daily.co video)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        VOICE AGENT CLINIC                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│  │  Twilio SIP │───►│  LiveKit    │───►│  AI Agent   │       │
│  │  (Phone)    │    │  (WebRTC)   │    │  (Python)   │       │
│  └─────────────┘    └─────────────┘    └──────┬──────┘       │
│                                               │                │
│  ┌─────────────┐    ┌─────────────┐    ┌──────▼──────┐       │
│  │  Web Widget │◄───│  Daily.co   │◄───│  Avatar     │       │
│  │  (React)    │    │  (Video)    │    │  (HeyGen)   │       │
│  └─────────────┘    └─────────────┘    └─────────────┘       │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│  │  Cal.com    │    │  CRM        │    │  Twilio/    │       │
│  │  (Calendar) │    │  (Webhook)  │    │  SendGrid   │       │
│  └─────────────┘    └─────────────┘    └─────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Clone and setup

```bash
git clone <repo-url>
cd voice-agent-clinic/agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file:

```env
# LiveKit
LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# Speech (STT)
DEEPGRAM_API_KEY=your_deepgram_key

# LLM
OPENAI_API_KEY=your_openai_key

# Voice (TTS)
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL

# Calendar
CALCOM_API_KEY=your_calcom_key
CALCOM_EVENT_TYPE_ID=12345

# CRM
CRM_WEBHOOK_URL=https://hooks.zapier.com/hooks/catch/.../...
CRM_API_KEY=optional

# Avatar
HEYGEN_API_KEY=your_heygen_key
HEYGEN_AVATAR_ID=your_avatar_id
HEYGEN_VOICE_ID=your_voice_id

# Notifications
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
SENDGRID_API_KEY=your_sendgrid_key

# Clinic settings
CLINIC_TIMEZONE=America/New_York
ONCALL_PHONE=+1234567890
```

### 3. Run the agent

```bash
python main.py
```

### 4. Build and deploy the web widget

```bash
cd ../web-widget
npm install
npm run build
```

## Deployment

### Docker

```bash
docker build -t voice-agent:latest ./agent
docker run -p 8080:8080 --env-file .env voice-agent:latest
```

### Kubernetes

See `infra/kubernetes/` for manifests.

## Testing

```bash
cd tests
pip install pytest pytest-asyncio
pytest unit/test_agent.py -v
pytest integration/test_end_to_end.py -v
```

## Verticals

The agent supports multiple business verticals with tailored prompts and workflows:

| Vertical | Key Features | Compliance |
|----------|-------------|------------|
| Dental | Appointment booking, anxiety support, pricing disclaimers | Standard |
| Medical | Triage escalation, HIPAA guardrails, telehealth | HIPAA |
| HVAC | Emergency dispatch, maintenance plans, ballpark pricing | Standard |
| Legal | Intake screening, privilege disclaimers, conflict checks | Attorney-client privilege |
| Real Estate | Showing scheduling, Fair Housing compliance, CMA referrals | Fair Housing |

## License

MIT
