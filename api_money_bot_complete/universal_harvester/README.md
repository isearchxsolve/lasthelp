# Reference: Multimodal Browser Automation Stack

## Free-Tier Limits (June 2026)

| Component | Limit | Cost |
|-----------|-------|------|
| Gemini 3.5 Flash (AI Studio) | 15 RPM / 1,500 RPD | Free |
| OpenAI Whisper (local) | Unlimited | Free (compute only) |
| Bright Data Web Unlocker | 5,000 requests/month | Free (no CC) |
| CloakBrowser | License required | Separate purchase |

## Known Hard Limits

1. **Invisible/behavioral checks** (reCAPTCHA v3, DataDome): No visual puzzle.
   CloakBrowser's behavioral simulation is the only mechanism; LLM is not invoked.

2. **Adversarial MLLM-targeted CAPTCHAs**: Research demonstrates 0% success
   on challenges designed to exploit transformer perceptual blind spots.

3. **Hardware attestation / biometric**: Outside browser automation scope entirely.

## Installation

```bash
pip install -r requirements.txt
playwright install
```

## Usage

Replace `YOUR_GOOGLE_AI_STUDIO_API_KEY` in `stealth_stack.py` and run:

```bash
python stealth_stack.py
```