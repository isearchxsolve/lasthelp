# Universal Harvester - Integration Documentation

## Overview

This document describes the integration of CloakBrowser and the stealth_stack.py multimodal browser automation stack into the Universal Harvester project.

## Architecture

The Universal Harvester now uses two parallel architectures:

### 1. **CloakBrowser + stealth_stack.py** (DEFAULT)
- Provides comprehensive anti-detection and captcha solving capabilities
- Uses Gemini 3.5 Flash for visual captcha solving
- Uses Whisper for audio captcha transcription
- Uses Bright Data Web Unlocker for obscure challenge types
- Implemented through the `ResearchOrchestrator` class

### 2. **Standard Playwright + utils.captcha.py** (Fallback)
- Uses 2Captcha API for reCAPTCHA solving
- Simpler setup but less comprehensive
- Retained for backward compatibility

## Environment Configuration

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
# Edit .env with your API keys
```

### Required API Keys

1. **Gemini API Key** (`GEMINI_API_KEY`)
   - Get from [Google AI Studio](https://aistudio.google.com/app/apikey)
   - Free tier: 15 RPM / 1,500 RPD

2. **Bright Data Token** (`BRIGHTDATA_TOKEN`, `BRIGHTDATA_ZONE`)
   - Free tier: 5,000 requests/month
   - Get from [Bright Data](https://brightdata.com)

### Optional API Keys

1. **2Captcha API Key** (`CAPTCHA_API_KEY`)
   - Required only if using legacy captcha solving

## Installation

1. Install required dependencies:

```bash
pip install -r requirements.txt
cd crawlee-engine && npm install
cd .. && chmod +x main.py
```

2. Get API keys and configure `.env`:

```bash
# Gemini 3.5 Flash API key
GEMINI_API_KEY=your_key_here

# Bright Data Web Unlocker token
BRIGHTDATA_TOKEN=your_token
BRIGHTDATA_ZONE=web_unlocker
```

## Usage

### Local Mode (Default) - Uses CloakBrowser + stealth_stack.py

```bash
python main.py --email your@email.com --password YourPassword123
```

Features:
- CloakBrowser for stealth browsing
- Gemini 3.5 Flash for visual captcha solving
- Whisper for audio captcha solving
- Bright Data fallback for obscure challenges
- Fingerprint randomization

### Crawlee Mode - Uses Node.js engine

```bash
python main.py --crawlee --email your@email.com --password YourPassword123
```

Features:
- Remote Crawlee engine with Playwright
- Built-in stealth with fingerprinting
- Session persistence
- Parallel processing

### Batch Mode

```bash
python main.py --crawlee --batch-size 4 --email your@email.com --password YourPassword123
```

Processes multiple platforms concurrently.

## Architecture Details

### CloakBrowser Integration

`main.py` now uses `create_stealth_browser` from `stealth_stack.py`:

```python
from stealth_stack import create_stealth_browser, safe_goto, pre_challenge_warming, ResearchOrchestrator
from utils.fingerprint import Fingerprint

# Launch CloakBrowser with fingerprint seed
fingerprint_seed = f"moneybot_{int(time.time())}"
browser = create_stealth_browser(
    proxy_url=None,
    fingerprint_seed=fingerprint_seed,
    headless=self.headless,
)

# Inject fingerprint randomization
fingerprint = Fingerprint(seed=fingerprint_seed)
fingerprint.inject_into_page(page)
```

### Captcha Solving Architecture

The `ResearchOrchestrator` from `stealth_stack.py` provides a 7-layer solution:

1. **CloakBrowser** - Stealth browser runtime
2. **GeminiVisionSolver** - Visual captcha solving via Google AI Studio
3. **LocalAudioSolver** - Audio captcha transcription using Whisper
4. **ChallengeDetector** - DOM-based challenge classification
5. **BrightDataFallback** - Proxy-based unlocker for obscure challenges
6. **SmartRouter** - Challenge classification and routing logic
7. **ResearchOrchestrator** - State-machine execution with retry logic

### Layer-by-Layer Processing

1. **Detection**: Identifies challenge type (reCAPTCHA, hCaptcha, slider, text, audio)
2. **Classification**: Routes to appropriate solver based on challenge characteristics
3. **Solving**: Uses Gemini for visual/audio/text, local Whisper for speech
4. **Fallback**: Routes obscure challenges to Bright Data Web Unlocker
5. **Execution**: Performs human-like interactions with retries and identity rotation

## Configuration

### Environment Variables

```bash
# Required for stealth_stack.py
GEMINI_API_KEY=your_gemini_key
genai_api_key=your_gemini_key  # Alternative environment variable name
BRIGHTDATA_TOKEN=your_brightdata_token

# Optional for legacy 2Captcha solving
CAPTCHA_API_KEY=your_2captcha_key

# Environment selection
ENVIRONMENT=stealth  # Use stealth_stack.py
# ENVIRONMENT=standard  # Use utils.captcha.py (legacy)
```

### Platform Configuration

Each platform in `config/platforms.py` can be configured with:

```python
"platform_name": {
    "signup": "https://platform.com/sign-up",
    "signin": "https://platform.com/log-in", 
    "api": "https://platform.com/api/keys",
    "email_platform": "gmail",
    "selectors": {...},  # Optional custom selectors
}
```

## Advanced Configuration

### CloakBrowser Customization

The `create_stealth_browser` function accepts:

```python
browser = create_stealth_browser(
    proxy_url="http://proxy:8080",           # Optional proxy
    fingerprint_seed="custom_seed",         # Custom fingerprint seed
    headless=false,                         # Headed mode for debugging
)
```

### ResearchOrchestrator Customization

```python
from stealth_stack import ResearchOrchestrator

orchestrator = ResearchOrchestrator(
    gemini_api_key="your_gemini_key",
    proxy="http://proxy:8080",              # Optional proxy
    whisper_model="base",                  # Whisper model size
    brightdata_token="your_brightdata_token",  # Optional
    brightdata_zone="web_unlocker",        # Bright Data zone
)
```

## Troubleshooting

### Common Issues

1. **API Key Errors**
   - Check that GEMINI_API_KEY and BRIGHTDATA_TOKEN are correctly set
   - Verify API keys are active and not expired

2. **CloakBrowser Not Launching**
   - Ensure CloakBrowser is installed: `pip install cloakbrowser`
   - Check for missing dependencies: `pip install google-generativeai openai-whisper pillow numpy playwright`

3. **Captcha Solving Failures**
   - Check that all required API keys are configured
   - Verify CAPTCHA_API_KEY if using legacy captcha solving

4. **Network Timeouts**
   - Check internet connectivity
   - Verify Bright Data or Gemini service status

### Debug Mode

Enable debug mode for verbose logging:

```bash
# In your environment or code
DEBUG_MODE=true
```

## Migration Guide

### From Legacy Mode to Stealth Mode

1. **Update dependencies**: `pip install cloakbrowser google-generativeai openai-whisper pillow numpy playwright`
2. **Configure API keys**: Get Gemini and Bright Data tokens
3. **Update environment**: Set GEMINI_API_KEY, BRIGHTDATA_TOKEN in `.env`
4. **Run tests**: Ensure all tests pass with the new architecture

### Environment Selection

The environment can be configured via the `ENVIRONMENT` variable:

```bash
ENVIRONMENT=stealth  # Use stealth_stack.py (recommended)
ENVIRONMENT=standard # Use utils.captcha.py (legacy)
```

## Performance Considerations

### Resource Requirements

1. **CPU**: For Gemini AI inference and Whisper transcription
2. **Memory**: 4GB+ recommended for simultaneous processing
3. **Network**: Gemini (15 RPM), Whisper (unlimited local), Bright Data (5K RPM free)

### Scaling

For large-scale operations:
1. Use Crawlee mode for parallel processing
2. Configure batch processing with multiple platforms
3. Monitor API usage to stay within free tier limits

## Compatibility

### System Requirements

- Python 3.8+
- Windows, macOS, or Linux
- Chrome/Chromium browser for tests

### Node.js Requirements

- Node.js 18+
- npm 8+

## Support

### Issues and Bug Reports

For bugs and issues:
1. Check the GitHub repository issues
2. Verify your environment configuration
3. Test with specific platforms

### Feature Requests

Feature requests are welcome. Please submit via the GitHub repository.

## Future Enhancements

1. **Multi-LLM Support**: Integration with other AI providers
2. **Cloud Whitelist**: Support for specific regions or networks
3. **Advanced Fingerprinting**: More sophisticated user agent and browser fingerprinting
4. **Real-time Analytics**: Monitoring and optimization of captcha solving performance

---

**License**: Proprietary (Educational and Research Use Only)

**Version**: 2.0

**Last Updated**: June 17, 2026