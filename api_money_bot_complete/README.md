# API Money Bot v3.0 — Complete Package

## 📦 Package Contents

```
api_money_bot_complete/
├── src/
│   └── api_money_bot_v3.py          # Main payment automation bot (34 platforms)
├── api_key_harvester/
│   ├── main.py                        # API key harvester orchestrator
│   ├── create_zip.py                  # Packaging script
│   ├── requirements.txt               # All dependencies
│   ├── .env.example                   # Complete environment template
│   ├── utils/
│   │   ├── browser.py                 # Stealth browser factory (Playwright)
│   │   ├── captcha.py                 # 2Captcha solver integration
│   │   ├── fingerprint.py             # Browser fingerprint randomization
│   │   └── helpers.py                 # Key masking, extraction helpers
│   ├── strategies/
│   │   ├── base.py                    # Abstract strategy base
│   │   ├── binance.py                 # Binance API key harvester
│   │   ├── coinbase.py                # Coinbase API key harvester
│   │   ├── kucoin.py                  # KuCoin API key harvester
│   │   ├── bybit.py                   # Bybit API key harvester
│   │   ├── okx.py                     # OKX API key harvester
│   │   ├── github.py                  # GitHub token harvester
│   │   ├── upwork.py                  # Upwork OAuth harvester
│   │   ├── gumroad.py                 # Gumroad token harvester
│   │   ├── stripe.py                  # Stripe key harvester
│   │   ├── openai.py                  # OpenAI key harvester
│   │   ├── shutterstock.py            # Shutterstock token harvester
│   │   ├── adobestock.py              # Adobe Stock key harvester
│   │   ├── pond5.py                   # Pond5 key harvester
│   │   ├── etsy.py                    # Etsy key harvester
│   │   ├── ebay.py                    # eBay key harvester
│   │   ├── shopify.py                 # Shopify token harvester
│   │   ├── printful.py                # Printful key harvester
│   │   ├── printify.py                # Printify key harvester
│   │   ├── medium.py                  # Medium token harvester
│   │   ├── patreon.py                 # Patreon token harvester
│   │   ├── substack.py                # Substack key harvester
│   │   ├── reddit.py                  # Reddit app credentials harvester
│   │   ├── twitter.py                 # Twitter/X key harvester
│   │   ├── anthropic.py               # Anthropic key harvester
│   │   ├── replicate.py               # Replicate token harvester
│   │   ├── rapidapi.py                # RapidAPI key harvester
│   │   ├── razorpay.py                # Razorpay key harvester
│   │   ├── wise.py                    # Wise key harvester
│   │   ├── paypal.py                  # PayPal app credentials harvester
│   │   ├── toloka.py                  # Toloka key harvester
│   │   ├── clickworker.py             # Clickworker key harvester
│   │   └── remotasks.py               # Remotasks key harvester
├── .env.example                       # Master environment template
├── run_bot.bat                        # Windows launcher (menu-driven)
├── run_bot.sh                         # Linux/Mac launcher (menu-driven)
└── README.md                          # This file
```

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r api_key_harvester/requirements.txt
playwright install chromium
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your platform credentials
```

### 3. Run API Key Harvester
```bash
# Harvest ALL platform keys
python api_key_harvester/main.py

# Harvest specific platforms
python api_key_harvester/main.py --platforms binance coinbase github

# Show harvested keys
python api_key_harvester/main.py --show
```

### 4. Run Money Bot (Safe Mode)
```bash
# Health check (read-only, validates credentials)
python src/api_money_bot_v3.py --health

# Safe monitoring run (no money moves)
python src/api_money_bot_v3.py

# Revenue summary
python src/api_money_bot_v3.py --summary
```

### 5. Run Money Bot (Windows/Linux Menu)
```bash
# Windows
run_bot.bat

# Linux/Mac
./run_bot.sh
```

---

## 🛡️ Safety Architecture

| Layer | Control | Default |
|-------|---------|---------|
| **Master Switch** | `LIVE_MODE` | `false` |
| **Category Gates** | `TRADING_ENABLED`, `AUTO_WITHDRAW`, etc. | `false` |
| **Spending Caps** | `MAX_TRADE_USD`, `MAX_BID_USD`, etc. | Hardcoded |
| **Symbol Allowlist** | `ALLOWED_PAIRS` | `BTCUSDT,ETHUSDT` |
| **Testnet Default** | `BINANCE_TESTNET`, `BYBIT_TESTNET` | `true` |
| **Audit Trail** | `payment_audit.json` + `revenue_log.json` | Always on |

**NO MONEY MOVES unless you explicitly set `LIVE_MODE=true`.**

---

## 📋 Platform Coverage (34 Platforms)

### 🔴 Tier 1 — Financial (Highest Security)
- **Crypto**: Binance, Coinbase, KuCoin, Bybit, OKX
- **Payments**: Stripe, Razorpay, PayPal, Wise, Payoneer

### 🟠 Tier 2 — High-Value Automation
- **Freelancing**: Upwork, Freelancer.com

### 🟡 Tier 3 — Commerce & Media
- **Stock Media**: Shutterstock, Adobe Stock, Pond5
- **Digital Products**: Gumroad, Etsy, eBay
- **E-commerce**: Shopify, Printful, Printify

### 🟢 Tier 4 — Content, Social, AI, Microtasks
- **Content**: YouTube, Medium, Patreon, Substack
- **Social**: Reddit, Twitter/X, GitHub
- **AI**: OpenAI, Anthropic, Replicate, RapidAPI
- **Microtasks**: Toloka, Clickworker, Remotasks

---

## 🔧 Advanced Usage

### Execute Single Action (requires LIVE_MODE=true)
```bash
# Paper trade on Binance testnet
LIVE_MODE=true TRADING_ENABLED=true python src/api_money_bot_v3.py --action Binance execute_trade '{"symbol":"BTCUSDT","side":"BUY","quantity":0.001}'

# Upload photo to Shutterstock
python src/api_money_bot_v3.py --upload-photo shutterstock ./photo.jpg "My Title"

# Create Gumroad product
python src/api_money_bot_v3.py --create-product gumroad "My eBook" 999
```

### Run Single Platform
```bash
python src/api_money_bot_v3.py --platform Binance
python src/api_money_bot_v3.py --platform Upwork
```

### Parallel Execution
```bash
python src/api_money_bot_v3.py --parallel
```

---

## 🔐 Security Features

### Stealth Browser Automation
- **Playwright + playwright-stealth** for anti-detection
- **Random fingerprint rotation** per session (viewport, timezone, user-agent, WebGL)
- **Proxy support** for IP rotation
- **Session persistence** to avoid re-logging

### Captcha Solving
- **2Captcha integration** for reCAPTCHA v2/v3 and hCaptcha
- **Automatic injection** of solved tokens into pages
- **Configurable timeout** and retry logic

### Key Management
- **Automatic harvesting** from platform dashboards
- **Masked display** in logs (never expose full keys)
- **JSON export** to `harvested_keys.json`
- **Session caching** to reduce login frequency

---

## ⚠️ Legal & Ethical Notice

This tool is for **authorized security testing and personal account management only**. Unauthorized access or harvesting of third-party API keys violates Terms of Service and may be illegal. Always obtain permission before automating any login.

---

## 📊 Audit & Logging

All actions are logged to:
- `api_money_bot.log` — General operation log
- `payment_audit.json` — Every financial action (immutable)
- `revenue_log.json` — Revenue tracking & daily summaries
- `harvested_keys.json` — API key harvest results

---

*Package generated for API Money Bot v3.0 | Security-First Architecture*
