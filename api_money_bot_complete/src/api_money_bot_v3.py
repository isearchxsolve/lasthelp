#!/usr/bin/env python3
"""
API Money Bot v3.0 --- Payment Automation Edition
================================================
Transforms monitoring into action: actually places trades, submits proposals,
uploads content, fulfills orders, creates payouts, and withdraws earnings.

SAFETY ARCHITECTURE:
  • LIVE_MODE master switch (default FALSE) --- no money moves unless True
  • Per-category confirmation flags (TRADING_ENABLED, AUTO_PROPOSE, etc.)
  • Hardcoded spending/withdrawal caps enforced in code
  • Testnet/paper trading remains default for all exchanges
  • Full audit trail written to revenue_log.json + payment_audit.json

Usage:
  python api_money_bot.py --health                          # credential check
  python api_money_bot.py                                   # safe monitoring run
  LIVE_MODE=true python api_money_bot.py --action execute   # live action run
  python api_money_bot.py --platform Binance --action trade # single platform
  python api_money_bot.py --upload-photo shutterstock ./img.jpg "Title"
  python api_money_bot.py --create-product gumroad "eBook" 999
  python api_money_bot.py --summary                         # revenue report

Install:
  pip install python-binance coinbase-advanced-py python-dotenv requests
"""

import argparse
import base64
import functools
import hashlib
import hmac
import json
import logging
import os
import random
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# ─────────── optional heavy deps ───────────
try:
    from binance.client import Client as BinanceClient
    _BINANCE_OK = True
except ImportError:
    _BINANCE_OK = False

try:
    from coinbaseadvanced.client import CoinbaseAdvancedClient
    _COINBASE_OK = True
except ImportError:
    _COINBASE_OK = False

try:
    import praw
    _REDDIT_OK = True
except ImportError:
    _REDDIT_OK = False

load_dotenv()

# ═══════════════════════════════════════════════════════════════
#  SAFETY CONFIG  ---  master & per-category kill switches
# ═══════════════════════════════════════════════════════════════

class SafetyConfig:
    """All payment-action gates.  Set env vars to TRUE only when you want money to move."""
    LIVE_MODE: bool = os.getenv("LIVE_MODE", "false").lower() == "true"

    # Category flags
    TRADING_ENABLED: bool     = os.getenv("TRADING_ENABLED", "false").lower() == "true"
    AUTO_PROPOSE: bool        = os.getenv("AUTO_PROPOSE", "false").lower() == "true"
    AUTO_PUBLISH: bool        = os.getenv("AUTO_PUBLISH", "false").lower() == "true"
    AUTO_FULFILL: bool        = os.getenv("AUTO_FULFILL", "false").lower() == "true"
    AUTO_LIST: bool           = os.getenv("AUTO_LIST", "false").lower() == "true"
    AUTO_WITHDRAW: bool       = os.getenv("AUTO_WITHDRAW", "false").lower() == "true"
    AUTO_DELIVER: bool        = os.getenv("AUTO_DELIVER", "false").lower() == "true"
    MICROTASK_AUTO: bool      = os.getenv("MICROTASK_AUTO", "false").lower() == "true"

    # Spending / withdrawal caps
    MAX_TRADE_USD: float      = float(os.getenv("MAX_TRADE_USD", "100.0"))
    MAX_BID_USD: float        = float(os.getenv("MAX_BID_USD", "500.0"))
    MAX_WITHDRAW_USD: float   = float(os.getenv("MAX_WITHDRAW_USD", "1000.0"))
    MAX_LISTING_PRICE: float  = float(os.getenv("MAX_LISTING_PRICE", "500.0"))

    # Allowed trading universe
    ALLOWED_PAIRS: List[str]  = os.getenv("ALLOWED_PAIRS", "BTCUSDT,ETHUSDT").split(",")

    # Payment destinations
    UPI_ID: str               = os.getenv("UPI_ID", "")
    BANK_ACCOUNT: str         = os.getenv("BANK_ACCOUNT", "")
    IFSC_CODE: str            = os.getenv("IFSC_CODE", "")
    WITHDRAW_DESTINATION: str = os.getenv("WITHDRAW_DESTINATION", "")


# ═══════════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-18s | %(message)s",
    handlers=[
        logging.FileHandler("api_money_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("MoneyBot")

# ── audit logger (separate file for every money action) ──
audit_handler = logging.FileHandler("payment_audit.json", encoding="utf-8")
audit_handler.setFormatter(logging.Formatter("%(message)s"))
audit_log = logging.getLogger("audit")
audit_log.addHandler(audit_handler)
audit_log.setLevel(logging.INFO)


# ═══════════════════════════════════════════════════════════════
#  DECORATORS  ---  safety gates + resilience
# ═══════════════════════════════════════════════════════════════

def require_live_mode(fn: Callable) -> Callable:
    """Blocks execution unless LIVE_MODE=True."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not SafetyConfig.LIVE_MODE:
            log.warning(f"[BLOCKED] {fn.__qualname__}: LIVE_MODE=False --- no money moved.")
            return {"status": "blocked", "reason": "LIVE_MODE=False"}
        return fn(*args, **kwargs)
    return wrapper

def require_confirmation(flag_name: str):
    """Requires a specific SafetyConfig flag to be True."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not getattr(SafetyConfig, flag_name, False):
                log.warning(f"[BLOCKED] {fn.__qualname__}: {flag_name}=False")
                return {"status": "blocked", "reason": f"{flag_name}=False"}
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def retry(max_attempts: int = 3, base_delay: float = 2.0):
    """Exponential-backoff retry decorator."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_attempts:
                        raise
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    log.warning(f"[{fn.__qualname__}] attempt {attempt} failed ({exc}). Retrying in {delay:.1f}s…")
                    time.sleep(delay)
        return wrapper
    return decorator


class RateLimiter:
    """Token-bucket rate limiter (thread-safe)."""
    def __init__(self, calls_per_minute: int):
        self._interval = 60.0 / max(calls_per_minute, 1)
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        with self._lock:
            elapsed = time.time() - self._last
            if elapsed < self._interval:
                time.sleep(self._interval - elapsed)
            self._last = time.time()


# ── helpers ──────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)

def _hmac_sha256_b64(secret: str, message: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()).decode()

def _hmac_sha256_hex(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def _now_ms() -> str:
    return str(int(time.time() * 1000))

def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ═══════════════════════════════════════════════════════════════
#  REVENUE & AUDIT TRACKER
# ═══════════════════════════════════════════════════════════════
class RevenueTracker:
    FILE = "revenue_log.json"

    def __init__(self):
        self._records: List[Dict] = []
        self._load()

    def _load(self):
        if Path(self.FILE).exists():
            try:
                with open(self.FILE, encoding="utf-8") as f:
                    self._records = json.load(f)
            except Exception:
                self._records = []

    def _save(self):
        with open(self.FILE, "w", encoding="utf-8") as f:
            json.dump(self._records, f, indent=2, default=str)

    def record(self, platform: str, event: str, amount_usd: float = 0.0, meta: Dict = None):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "platform": platform,
            "event": event,
            "amount_usd": round(amount_usd, 6),
            "live_mode": SafetyConfig.LIVE_MODE,
            "meta": meta or {},
        }
        self._records.append(entry)
        self._save()
        audit_log.info(json.dumps(entry, default=str))
        if amount_usd:
            log.info(f"[Revenue] {platform} | {event} | ${amount_usd:.4f}")

    def daily_summary(self) -> Dict[str, float]:
        today = datetime.now().date().isoformat()
        totals: Dict[str, float] = defaultdict(float)
        for r in self._records:
            if r["ts"].startswith(today):
                totals[r["platform"]] += r["amount_usd"]
        return dict(totals)

    def total_earned(self) -> float:
        return round(sum(r["amount_usd"] for r in self._records), 4)


tracker = RevenueTracker()


# ═══════════════════════════════════════════════════════════════
#  CONFIG  --- all credentials pulled from .env
# ═══════════════════════════════════════════════════════════════

@dataclass
class Config:
    # ── Identity ──────────────────────────────────
    UPI_ID: str = field(default_factory=lambda: _env("UPI_ID", "kunal.colab-1@okicici"))

    # ── Crypto: Binance ───────────────────────────
    BINANCE_API_KEY: str    = field(default_factory=lambda: _env("BINANCE_API_KEY"))
    BINANCE_API_SECRET: str = field(default_factory=lambda: _env("BINANCE_API_SECRET"))
    BINANCE_TESTNET: bool   = field(default_factory=lambda: _env("BINANCE_TESTNET", "true") == "true")

    # ── Crypto: Coinbase ──────────────────────────
    COINBASE_API_KEY: str    = field(default_factory=lambda: _env("COINBASE_API_KEY"))
    COINBASE_API_SECRET: str = field(default_factory=lambda: _env("COINBASE_API_SECRET"))

    # ── Crypto: KuCoin ────────────────────────────
    KUCOIN_API_KEY: str    = field(default_factory=lambda: _env("KUCOIN_API_KEY"))
    KUCOIN_API_SECRET: str = field(default_factory=lambda: _env("KUCOIN_API_SECRET"))
    KUCOIN_PASSPHRASE: str = field(default_factory=lambda: _env("KUCOIN_PASSPHRASE"))

    # ── Crypto: Bybit ─────────────────────────────
    BYBIT_API_KEY: str    = field(default_factory=lambda: _env("BYBIT_API_KEY"))
    BYBIT_API_SECRET: str = field(default_factory=lambda: _env("BYBIT_API_SECRET"))
    BYBIT_TESTNET: bool   = field(default_factory=lambda: _env("BYBIT_TESTNET", "true") == "true")

    # ── Crypto: OKX ───────────────────────────────
    OKX_API_KEY: str    = field(default_factory=lambda: _env("OKX_API_KEY"))
    OKX_API_SECRET: str = field(default_factory=lambda: _env("OKX_API_SECRET"))
    OKX_PASSPHRASE: str = field(default_factory=lambda: _env("OKX_PASSPHRASE"))

    # ── Stock Media ───────────────────────────────
    SHUTTERSTOCK_TOKEN: str       = field(default_factory=lambda: _env("SHUTTERSTOCK_TOKEN"))
    ADOBE_STOCK_API_KEY: str      = field(default_factory=lambda: _env("ADOBE_STOCK_API_KEY"))
    ADOBE_STOCK_ACCESS_TOKEN: str = field(default_factory=lambda: _env("ADOBE_STOCK_ACCESS_TOKEN"))
    POND5_API_KEY: str            = field(default_factory=lambda: _env("POND5_API_KEY"))

    # ── Freelancing ───────────────────────────────
    UPWORK_TOKEN: str      = field(default_factory=lambda: _env("UPWORK_TOKEN"))
    FREELANCER_TOKEN: str  = field(default_factory=lambda: _env("FREELANCER_TOKEN"))

    # ── Digital Products ──────────────────────────
    GUMROAD_ACCESS_TOKEN: str = field(default_factory=lambda: _env("GUMROAD_ACCESS_TOKEN"))
    ETSY_API_KEY: str         = field(default_factory=lambda: _env("ETSY_API_KEY"))
    ETSY_ACCESS_TOKEN: str    = field(default_factory=lambda: _env("ETSY_ACCESS_TOKEN"))
    EBAY_TOKEN: str           = field(default_factory=lambda: _env("EBAY_TOKEN"))
    STRIPE_SECRET_KEY: str    = field(default_factory=lambda: _env("STRIPE_SECRET_KEY"))

    # ── Content ───────────────────────────────────
    YOUTUBE_API_KEY: str    = field(default_factory=lambda: _env("YOUTUBE_API_KEY"))
    YOUTUBE_CHANNEL_ID: str = field(default_factory=lambda: _env("YOUTUBE_CHANNEL_ID"))
    MEDIUM_API_KEY: str     = field(default_factory=lambda: _env("MEDIUM_API_KEY"))
    MEDIUM_USER_ID: str     = field(default_factory=lambda: _env("MEDIUM_USER_ID"))
    PATREON_ACCESS_TOKEN: str = field(default_factory=lambda: _env("PATREON_ACCESS_TOKEN"))
    SUBSTACK_API_KEY: str   = field(default_factory=lambda: _env("SUBSTACK_API_KEY"))

    # ── E-commerce / POD ────────────────────────────
    SHOPIFY_STORE: str        = field(default_factory=lambda: _env("SHOPIFY_STORE"))
    SHOPIFY_ACCESS_TOKEN: str = field(default_factory=lambda: _env("SHOPIFY_ACCESS_TOKEN"))
    PRINTFUL_API_KEY: str     = field(default_factory=lambda: _env("PRINTFUL_API_KEY"))
    PRINTIFY_API_KEY: str     = field(default_factory=lambda: _env("PRINTIFY_API_KEY"))
    PRINTIFY_SHOP_ID: str     = field(default_factory=lambda: _env("PRINTIFY_SHOP_ID"))

    # ── Social / Gig Hunting ──────────────────────
    REDDIT_CLIENT_ID: str     = field(default_factory=lambda: _env("REDDIT_CLIENT_ID"))
    REDDIT_CLIENT_SECRET: str = field(default_factory=lambda: _env("REDDIT_CLIENT_SECRET"))
    REDDIT_USER_AGENT: str    = field(default_factory=lambda: _env("REDDIT_USER_AGENT", "MoneyBot/3.0"))
    TWITTER_BEARER_TOKEN: str = field(default_factory=lambda: _env("TWITTER_BEARER_TOKEN"))
    GITHUB_TOKEN: str         = field(default_factory=lambda: _env("GITHUB_TOKEN"))

    # ── AI Services ───────────────────────────────
    OPENAI_API_KEY: str    = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    ANTHROPIC_API_KEY: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    REPLICATE_API_KEY: str = field(default_factory=lambda: _env("REPLICATE_API_KEY"))
    RAPIDAPI_KEY: str      = field(default_factory=lambda: _env("RAPIDAPI_KEY"))

    # ── Payment / Withdrawal ──────────────────────
    RAZORPAY_KEY_ID: str     = field(default_factory=lambda: _env("RAZORPAY_KEY_ID"))
    RAZORPAY_KEY_SECRET: str = field(default_factory=lambda: _env("RAZORPAY_KEY_SECRET"))
    WISE_API_KEY: str        = field(default_factory=lambda: _env("WISE_API_KEY"))
    PAYONEER_API_KEY: str    = field(default_factory=lambda: _env("PAYONEER_API_KEY"))
    PAYPAL_CLIENT_ID: str    = field(default_factory=lambda: _env("PAYPAL_CLIENT_ID"))
    PAYPAL_CLIENT_SECRET: str= field(default_factory=lambda: _env("PAYPAL_CLIENT_SECRET"))

    # ── Microtasks ────────────────────────────────
    CLICKWORKER_API_KEY: str = field(default_factory=lambda: _env("CLICKWORKER_API_KEY"))
    TOLOKA_API_KEY: str      = field(default_factory=lambda: _env("TOLOKA_API_KEY"))
    REMOTASKS_API_KEY: str   = field(default_factory=lambda: _env("REMOTASKS_API_KEY"))


cfg = Config()


# ═══════════════════════════════════════════════════════════════
#  BASE PLATFORM
# ═══════════════════════════════════════════════════════════════
class Platform:
    NAME = "base"
    _limiter: Optional[RateLimiter] = None

    def __init__(self):
        self.log = logging.getLogger(f"Bot.{self.NAME}")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MoneyBot/3.0"})

    def _rl(self):
        if self._limiter:
            self._limiter.wait()
        else:
            time.sleep(random.uniform(0.3, 1.0))

    def health_check(self) -> bool:
        raise NotImplementedError

    def run(self):
        """Default monitoring run. Override in subclasses."""
        raise NotImplementedError

    def _safe_request(self, method: str, url: str, **kwargs) -> Optional[Dict]:
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json() if response.text else {}
        except Exception as e:
            self.log.error(f"Request failed: {url} --- {e}")
            return None

    def _audit(self, action: str, details: Dict):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "platform": self.NAME,
            "action": action,
            "live_mode": SafetyConfig.LIVE_MODE,
            "details": details,
        }
        audit_log.info(json.dumps(entry, default=str))
        self.log.info(f"[ACTION] {self.NAME}.{action}: {details}")
        return entry


# ═══════════════════════════════════════════════════════════════
#  CRYPTO PLATFORMS  ---  now with live order execution
# ═══════════════════════════════════════════════════════════════

class BinancePlatform(Platform):
    NAME = "Binance"
    _limiter = RateLimiter(20)

    SYMBOL = "BTCUSDT"
    ORDER_USDT = 10.0
    TAKE_PROFIT_PCT = 1.0
    STOP_LOSS_PCT   = 0.4

    def __init__(self):
        super().__init__()
        self._client: Optional["BinanceClient"] = None

    def _cli(self) -> Optional["BinanceClient"]:
        if not (cfg.BINANCE_API_KEY and cfg.BINANCE_API_SECRET and _BINANCE_OK):
            return None
        if not self._client:
            self._client = BinanceClient(
                cfg.BINANCE_API_KEY, cfg.BINANCE_API_SECRET,
                testnet=cfg.BINANCE_TESTNET,
            )
        return self._client

    def health_check(self) -> bool:
        c = self._cli()
        if not c:
            return False
        try:
            c.ping()
            return True
        except Exception:
            return False

    @retry()
    def get_price(self, symbol: str = "") -> float:
        self._rl()
        t = self._cli().get_symbol_ticker(symbol=symbol or self.SYMBOL)
        return float(t["price"])

    @retry()
    def get_balances(self) -> Dict[str, float]:
        self._rl()
        info = self._cli().get_account()
        return {b["asset"]: float(b["free"]) for b in info["balances"] if float(b["free"]) > 0}

    # ── ACTION: execute live trade ────────────────────────────────────────
    @require_live_mode
    @require_confirmation("TRADING_ENABLED")
    def execute_trade(self, symbol: str, side: str, quantity: float) -> Dict:
        """Place a live market order. side = BUY or SELL."""
        if symbol not in SafetyConfig.ALLOWED_PAIRS:
            return self._audit("trade_blocked", {"reason": "symbol not allowed", "symbol": symbol})
        price = self.get_price(symbol)
        value = price * quantity
        if value > SafetyConfig.MAX_TRADE_USD:
            return self._audit("trade_blocked", {
                "reason": "exceeds MAX_TRADE_USD", "value": value, "max": SafetyConfig.MAX_TRADE_USD
            })
        if cfg.BINANCE_TESTNET:
            self.log.info(f"[TESTNET] {side} {quantity} {symbol} @ ${price:,.2f}")
            result = {"status": "TESTNET", "side": side, "qty": quantity, "symbol": symbol, "price": price}
        else:
            if side.upper() == "BUY":
                result = self._cli().order_market_buy(symbol=symbol, quantity=quantity)
            else:
                result = self._cli().order_market_sell(symbol=symbol, quantity=quantity)
        self._audit("trade_executed", result)
        tracker.record("Binance", f"trade_{side.lower()}", amount_usd=value, meta=result)
        return result

    def run(self):
        if not self._cli():
            self.log.warning("Binance credentials or library missing")
            return
        balances = self.get_balances()
        price = self.get_price()
        self.log.info(f"Balances: {balances}")
        self.log.info(f"{self.SYMBOL}: ${price:,.2f}")
        tracker.record("Binance", "price_check", meta={"price": price})


class CoinbasePlatform(Platform):
    NAME = "Coinbase"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.COINBASE_API_KEY and cfg.COINBASE_API_SECRET and _COINBASE_OK)

    @retry()
    def run(self):
        if not self.health_check():
            self.log.warning("Coinbase credentials/library missing")
            return
        self._rl()
        client = CoinbaseAdvancedClient(cfg.COINBASE_API_KEY, cfg.COINBASE_API_SECRET)
        accounts = client.get_accounts()
        self.log.info(f"{len(accounts)} accounts retrieved")
        for a in accounts:
            bal = a.get("available_balance", {})
            if float(bal.get("value", 0)) > 0:
                self.log.info(f"  {a.get('name')}: {bal.get('value')} {bal.get('currency')}")
        tracker.record("Coinbase", "account_check")

    @require_live_mode
    @require_confirmation("TRADING_ENABLED")
    def execute_trade(self, product_id: str = "BTC-USD", side: str = "BUY", funds: float = 10.0) -> Dict:
        if funds > SafetyConfig.MAX_TRADE_USD:
            return self._audit("trade_blocked", {"reason": "exceeds MAX_TRADE_USD", "funds": funds})
        if not self.health_check():
            return {"status": "error", "reason": "not configured"}
        client = CoinbaseAdvancedClient(cfg.COINBASE_API_KEY, cfg.COINBASE_API_SECRET)
        try:
            order = client.create_order(
                product_id=product_id, side=side.lower(),
                order_configuration={"market_market_ioc": {"quote_size": str(funds) if side.upper()=="BUY" else str(funds)}}
            )
            self._audit("trade_executed", {"product_id": product_id, "side": side, "funds": funds, "order": order})
            tracker.record("Coinbase", f"trade_{side.lower()}", amount_usd=funds, meta=order)
            return order
        except Exception as e:
            self.log.error(f"Coinbase trade error: {e}")
            return {"status": "error", "error": str(e)}


class KuCoinPlatform(Platform):
    NAME = "KuCoin"
    BASE = "https://api.kucoin.com"
    _limiter = RateLimiter(30)

    def health_check(self) -> bool:
        return bool(cfg.KUCOIN_API_KEY and cfg.KUCOIN_API_SECRET and cfg.KUCOIN_PASSPHRASE)

    def _auth(self, ts: str, method: str, endpoint: str, body: str = "") -> Dict[str, str]:
        payload = f"{ts}{method.upper()}{endpoint}{body}"
        sig = _hmac_sha256_b64(cfg.KUCOIN_API_SECRET, payload)
        pp  = _hmac_sha256_b64(cfg.KUCOIN_API_SECRET, cfg.KUCOIN_PASSPHRASE)
        return {
            "KC-API-KEY": cfg.KUCOIN_API_KEY,
            "KC-API-SIGN": sig,
            "KC-API-TIMESTAMP": ts,
            "KC-API-PASSPHRASE": pp,
            "KC-API-KEY-VERSION": "2",
        }

    def _get(self, endpoint: str) -> Optional[Dict]:
        self._rl()
        ts = _now_ms()
        resp = self.session.get(f"{self.BASE}{endpoint}", headers=self._auth(ts, "GET", endpoint))
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, body: Dict) -> Optional[Dict]:
        self._rl()
        ts = _now_ms()
        b = json.dumps(body)
        resp = self.session.post(f"{self.BASE}{endpoint}", headers={**self._auth(ts, "POST", endpoint, b), "Content-Type": "application/json"}, data=b)
        resp.raise_for_status()
        return resp.json()

    @retry()
    def get_accounts(self) -> List[Dict]:
        data = self._get("/api/v1/accounts")
        return data.get("data", []) if data else []

    @retry()
    def get_ticker(self, symbol: str = "BTC-USDT") -> Optional[Dict]:
        data = self._get(f"/api/v1/market/orderbook/level1?symbol={symbol}")
        return data.get("data") if data else None

    @require_live_mode
    @require_confirmation("TRADING_ENABLED")
    def execute_trade(self, symbol: str, side: str, size: float, price: float = None) -> Dict:
        if symbol.replace("-", "") not in [p.replace("-", "") for p in SafetyConfig.ALLOWED_PAIRS]:
            return self._audit("trade_blocked", {"reason": "symbol not allowed", "symbol": symbol})
        value = (price or float(self.get_ticker(symbol).get("price", 0))) * size
        if value > SafetyConfig.MAX_TRADE_USD:
            return self._audit("trade_blocked", {"reason": "exceeds cap", "value": value})
        try:
            result = self._post("/api/v1/orders", {
                "clientOid": str(int(time.time())),
                "side": side.lower(),
                "symbol": symbol,
                "type": "market",
                "size": str(size),
            })
            self._audit("trade_executed", {"symbol": symbol, "side": side, "size": size, "result": result})
            tracker.record("KuCoin", f"trade_{side.lower()}", amount_usd=value, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("KuCoin credentials missing")
            return
        accts = self.get_accounts()
        non_zero = [a for a in accts if float(a.get("balance", 0)) > 0]
        self.log.info(f"{len(non_zero)} non-zero accounts")
        ticker = self.get_ticker()
        if ticker:
            self.log.info(f"BTC-USDT: ${float(ticker.get('price', 0)):,.2f}")
        tracker.record("KuCoin", "account_check")


class BybitPlatform(Platform):
    NAME = "Bybit"
    BASE_MAIN = "https://api.bybit.com"
    BASE_TEST = "https://api-testnet.bybit.com"
    _limiter = RateLimiter(20)

    @property
    def _base(self) -> str:
        return self.BASE_TEST if cfg.BYBIT_TESTNET else self.BASE_MAIN

    def health_check(self) -> bool:
        return bool(cfg.BYBIT_API_KEY and cfg.BYBIT_API_SECRET)

    def _sign(self, ts: str, recv_win: str, params_str: str) -> str:
        payload = f"{ts}{cfg.BYBIT_API_KEY}{recv_win}{params_str}"
        return _hmac_sha256_hex(cfg.BYBIT_API_SECRET, payload)

    def _get(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        self._rl()
        params = params or {}
        ts, rw = _now_ms(), "5000"
        p_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        headers = {
            "X-BAPI-API-KEY": cfg.BYBIT_API_KEY,
            "X-BAPI-SIGN": self._sign(ts, rw, p_str),
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": rw,
        }
        resp = self.session.get(f"{self._base}{endpoint}", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, body: Dict) -> Optional[Dict]:
        self._rl()
        ts, rw = _now_ms(), "5000"
        b = json.dumps(body)
        headers = {
            "X-BAPI-API-KEY": cfg.BYBIT_API_KEY,
            "X-BAPI-SIGN": self._sign(ts, rw, b),
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": rw,
            "Content-Type": "application/json",
        }
        resp = self.session.post(f"{self._base}{endpoint}", headers=headers, data=b)
        resp.raise_for_status()
        return resp.json()

    @retry()
    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Optional[Dict]:
        d = self._get("/v5/account/wallet-balance", {"accountType": account_type})
        return d.get("result") if d else None

    @retry()
    def get_ticker(self, symbol: str = "BTCUSDT", category: str = "spot") -> Optional[Dict]:
        d = self._get("/v5/market/tickers", {"category": category, "symbol": symbol})
        items = d.get("result", {}).get("list", []) if d else []
        return items[0] if items else None

    @require_live_mode
    @require_confirmation("TRADING_ENABLED")
    def execute_trade(self, symbol: str, side: str, qty: float, category: str = "spot") -> Dict:
        if symbol not in SafetyConfig.ALLOWED_PAIRS:
            return self._audit("trade_blocked", {"reason": "symbol not allowed", "symbol": symbol})
        price = float(self.get_ticker(symbol, category).get("lastPrice", 0))
        if price * qty > SafetyConfig.MAX_TRADE_USD:
            return self._audit("trade_blocked", {"reason": "exceeds cap", "value": price*qty})
        try:
            result = self._post("/v5/order/create", {
                "category": category,
                "symbol": symbol,
                "side": side.capitalize(),
                "orderType": "Market",
                "qty": str(qty),
            })
            self._audit("trade_executed", {"symbol": symbol, "side": side, "qty": qty, "result": result})
            tracker.record("Bybit", f"trade_{side.lower()}", amount_usd=price*qty, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Bybit credentials missing")
            return
        wallet = self.get_wallet_balance()
        if wallet:
            coins = wallet.get("list", [{}])[0].get("coin", [])
            non_zero = [c for c in coins if float(c.get("walletBalance", 0)) > 0]
            for c in non_zero:
                self.log.info(f"  {c.get('coin')}: {c.get('walletBalance')} (unrealised PnL: {c.get('unrealisedPnl', 0)})")
        ticker = self.get_ticker()
        if ticker:
            self.log.info(f"BTCUSDT: ${float(ticker.get('lastPrice', 0)):,.2f}")
        tracker.record("Bybit", "balance_check")


class OKXPlatform(Platform):
    NAME = "OKX"
    BASE = "https://www.okx.com"
    _limiter = RateLimiter(20)

    def health_check(self) -> bool:
        return bool(cfg.OKX_API_KEY and cfg.OKX_API_SECRET and cfg.OKX_PASSPHRASE)

    def _headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        ts = _utc_iso()
        sig = _hmac_sha256_b64(cfg.OKX_API_SECRET, f"{ts}{method.upper()}{path}{body}")
        return {
            "OK-ACCESS-KEY": cfg.OKX_API_KEY,
            "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": cfg.OKX_PASSPHRASE,
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> Optional[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}{path}", headers=self._headers("GET", path))
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: Dict) -> Optional[Dict]:
        self._rl()
        b = json.dumps(body)
        resp = self.session.post(f"{self.BASE}{path}", headers=self._headers("POST", path, b), data=b)
        resp.raise_for_status()
        return resp.json()

    @retry()
    def get_balance(self) -> Optional[Dict]:
        d = self._get("/api/v5/account/balance")
        items = d.get("data", []) if d else []
        return items[0] if items else None

    @retry()
    def get_ticker(self, inst_id: str = "BTC-USDT") -> Optional[Dict]:
        d = self._get(f"/api/v5/market/ticker?instId={inst_id}")
        items = d.get("data", []) if d else []
        return items[0] if items else None

    @require_live_mode
    @require_confirmation("TRADING_ENABLED")
    def execute_trade(self, inst_id: str, side: str, sz: float) -> Dict:
        if inst_id.replace("-", "") not in [p.replace("-", "") for p in SafetyConfig.ALLOWED_PAIRS]:
            return self._audit("trade_blocked", {"reason": "symbol not allowed", "inst_id": inst_id})
        price = float(self.get_ticker(inst_id).get("last", 0))
        if price * sz > SafetyConfig.MAX_TRADE_USD:
            return self._audit("trade_blocked", {"reason": "exceeds cap", "value": price*sz})
        try:
            result = self._post("/api/v5/trade/order", {
                "instId": inst_id,
                "tdMode": "cash",
                "side": side.lower(),
                "ordType": "market",
                "sz": str(sz),
            })
            self._audit("trade_executed", {"inst_id": inst_id, "side": side, "sz": sz, "result": result})
            tracker.record("OKX", f"trade_{side.lower()}", amount_usd=price*sz, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("OKX credentials missing")
            return
        bal = self.get_balance()
        if bal:
            non_zero = [d for d in bal.get("details", []) if float(d.get("cashBal", 0)) > 0]
            self.log.info(f"{len(non_zero)} currencies with balance")
        ticker = self.get_ticker()
        if ticker:
            self.log.info(f"BTC-USDT: ${float(ticker.get('last', 0)):,.2f}")
        tracker.record("OKX", "balance_check")


# ═══════════════════════════════════════════════════════════════
#  STOCK MEDIA PLATFORMS  ---  upload actions
# ═══════════════════════════════════════════════════════════════

class ShutterstockPlatform(Platform):
    NAME = "Shutterstock"
    BASE = "https://api.shutterstock.com/v2"
    _limiter = RateLimiter(5)

    def health_check(self) -> bool:
        return bool(cfg.SHUTTERSTOCK_TOKEN)

    def _auth(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {cfg.SHUTTERSTOCK_TOKEN}"}

    @retry(2)
    def get_earnings(self) -> Optional[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/user/earnings-summary", headers=self._auth())
        return resp.json() if resp.status_code == 200 else None

    @retry(2)
    def get_portfolio(self, page: int = 1, per_page: int = 50) -> List[Dict]:
        self._rl()
        resp = self.session.get(
            f"{self.BASE}/images",
            headers=self._auth(),
            params={"added_date_start": "2020-01-01", "page": page, "per_page": per_page},
        )
        return resp.json().get("data", []) if resp.status_code == 200 else []

    @retry(2)
    def upload_photo(self, photo_path: str, title: str, description: str,
                     keywords: List[str] = None, category_id: int = 1) -> Optional[str]:
        self._rl()
        if not Path(photo_path).exists():
            self.log.error(f"File not found: {photo_path}")
            return None
        headers = self._auth()
        with open(photo_path, "rb") as f:
            resp = self.session.post(
                f"{self.BASE}/images",
                headers=headers,
                files={"file": f},
                data={
                    "title": title,
                    "description": description,
                    "keywords": ",".join(keywords or []),
                    "categories": json.dumps([{"id": category_id}]),
                },
            )
        if resp.status_code in (200, 201):
            asset_id = resp.json().get("id")
            self.log.info(f"Uploaded: {asset_id} --- {title}")
            tracker.record("Shutterstock", "upload", meta={"title": title, "id": asset_id})
            return asset_id
        self.log.error(f"Upload failed {resp.status_code}: {resp.text[:200]}")
        return None

    def run(self):
        if not self.health_check():
            self.log.warning("Shutterstock token missing")
            return
        earnings = self.get_earnings()
        if earnings:
            monthly = earnings.get("total_month_earnings", {})
            amount = float(monthly.get("amount", 0))
            self.log.info(f"Monthly earnings: ${amount:.2f}")
            tracker.record("Shutterstock", "earnings", amount_usd=amount, meta={"currency": monthly.get("currency")})
        portfolio = self.get_portfolio()
        self.log.info(f"Portfolio: {len(portfolio)} image(s)")


class AdobeStockPlatform(Platform):
    NAME = "AdobeStock"
    BASE = "https://stock.adobe.io"
    _limiter = RateLimiter(5)

    def health_check(self) -> bool:
        return bool(cfg.ADOBE_STOCK_API_KEY and cfg.ADOBE_STOCK_ACCESS_TOKEN)

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": cfg.ADOBE_STOCK_API_KEY,
            "X-Product": "MoneyBot/3.0",
            "Authorization": f"Bearer {cfg.ADOBE_STOCK_ACCESS_TOKEN}",
        }

    @retry(2)
    def list_assets(self, limit: int = 100) -> List[Dict]:
        self._rl()
        resp = self.session.get(
            f"{self.BASE}/Rest/Media/1/Files",
            headers=self._headers(),
            params={"locale": "en_US", "search_parameters[limit]": limit},
        )
        return resp.json().get("files", []) if resp.status_code == 200 else []

    @retry(2)
    def upload_asset(self, file_path: str, title: str, category: int = 990) -> bool:
        self._rl()
        if not Path(file_path).exists():
            self.log.error(f"File not found: {file_path}")
            return False
        headers = {**self._headers(), "Content-Type": "image/jpeg"}
        with open(file_path, "rb") as f:
            resp = self.session.post(
                f"{self.BASE}/Rest/Media/1/Files",
                headers=headers,
                params={"title": title, "category": category},
                data=f.read(),
            )
        ok = resp.status_code in (200, 201)
        if ok:
            tracker.record("AdobeStock", "upload", meta={"title": title})
        self.log.info(f"Upload {'OK' if ok else 'FAILED'}: {title}")
        return ok

    def run(self):
        if not self.health_check():
            self.log.warning("Adobe Stock credentials missing")
            return
        assets = self.list_assets()
        self.log.info(f"Portfolio: {len(assets)} asset(s)")
        tracker.record("AdobeStock", "portfolio_check", meta={"count": len(assets)})


class Pond5Platform(Platform):
    NAME = "Pond5"
    BASE = "https://api.pond5.com"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.POND5_API_KEY)

    def _auth(self) -> Dict[str, str]:
        return {"Authorization": f"Token {cfg.POND5_API_KEY}"}

    @retry(2)
    def get_portfolio(self) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/contributor/assets/", headers=self._auth())
        return resp.json().get("results", []) if resp.status_code == 200 else []

    @retry(2)
    def get_earnings(self) -> Optional[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/contributor/earnings/", headers=self._auth())
        return resp.json() if resp.status_code == 200 else None

    @retry(2)
    def upload_clip(self, file_path: str, title: str, description: str,
                    tags: List[str] = None, media_type: str = "footage") -> Optional[str]:
        self._rl()
        if not Path(file_path).exists():
            self.log.error(f"File not found: {file_path}")
            return None
        with open(file_path, "rb") as f:
            resp = self.session.post(
                f"{self.BASE}/contributor/assets/",
                headers=self._auth(),
                files={"file": f},
                data={
                    "title": title,
                    "description": description,
                    "tags": ",".join(tags or []),
                    "media_type": media_type,
                },
            )
        if resp.status_code in (200, 201):
            asset_id = str(resp.json().get("id"))
            tracker.record("Pond5", "upload", meta={"title": title, "id": asset_id})
            self.log.info(f"Uploaded clip: {asset_id}")
            return asset_id
        self.log.error(f"Pond5 upload failed {resp.status_code}")
        return None

    def run(self):
        if not self.health_check():
            self.log.warning("Pond5 API key missing")
            return
        portfolio = self.get_portfolio()
        self.log.info(f"Portfolio: {len(portfolio)} asset(s)")
        earnings = self.get_earnings()
        if earnings:
            total = float(earnings.get("total_earnings", 0))
            self.log.info(f"Total earnings: ${total:.2f}")
            tracker.record("Pond5", "earnings", amount_usd=total)


# ═══════════════════════════════════════════════════════════════
#  FREELANCING PLATFORMS  ---  auto-proposal / bid actions
# ═══════════════════════════════════════════════════════════════

class UpworkPlatform(Platform):
    NAME = "Upwork"
    GQL = "https://api.upwork.com/graphql"
    _limiter = RateLimiter(5)

    def health_check(self) -> bool:
        return bool(cfg.UPWORK_TOKEN)

    def _gql(self, query: str, variables: Dict = None) -> Optional[Dict]:
        self._rl()
        resp = self.session.post(
            self.GQL,
            headers={"Authorization": f"Bearer {cfg.UPWORK_TOKEN}", "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
        )
        resp.raise_for_status()
        return resp.json()

    @retry(2)
    def search_jobs(self, keyword: str, limit: int = 10) -> List[Dict]:
        q = """
        query SearchJobs($query: String!, $limit: Int!) {
            searchJobs(query: $query, limit: $limit) {
                items { id title engagement budget { amount currencyCode } category2 { name } skills { name } }
            }
        }"""
        d = self._gql(q, {"query": keyword, "limit": limit})
        return (d or {}).get("data", {}).get("searchJobs", {}).get("items", [])

    @retry(2)
    def get_active_contracts(self) -> List[Dict]:
        q = "query { currentUserContracts(status: ACTIVE) { items { id title status hourlyPayRate { amount currencyCode } } } }"
        d = self._gql(q)
        return (d or {}).get("data", {}).get("currentUserContracts", {}).get("items", [])

    @retry(2)
    def get_weekly_earnings(self) -> Optional[Dict]:
        q = "query { weeklyEarnings { earnedAmount { amount currencyCode } hoursWorked } }"
        d = self._gql(q)
        return (d or {}).get("data", {}).get("weeklyEarnings")

    @require_live_mode
    @require_confirmation("AUTO_PROPOSE")
    def submit_proposal(self, job_id: str, cover_letter: str, bid_amount: float) -> Dict:
        if bid_amount > SafetyConfig.MAX_BID_USD:
            return self._audit("proposal_blocked", {"reason": "exceeds MAX_BID_USD", "bid": bid_amount})
        try:
            mutation = """
            mutation SubmitProposal($jobId: ID!, $coverLetter: String!, $bidAmount: MoneyInput!) {
                submitProposal(input: {jobId: $jobId, coverLetter: $coverLetter, bidAmount: $bidAmount}) {
                    proposal { id status }
                    errors { message }
                }
            }"""
            variables = {
                "jobId": job_id,
                "coverLetter": cover_letter,
                "bidAmount": {"amount": str(bid_amount), "currency": "USD"}
            }
            resp = self.session.post(
                self.GQL,
                headers={"Authorization": f"Bearer {cfg.UPWORK_TOKEN}", "Content-Type": "application/json"},
                json={"query": mutation, "variables": variables}
            )
            result = resp.json() if resp.status_code == 200 else {"status": resp.status_code}
            self._audit("proposal_submitted", {"job_id": job_id, "bid": bid_amount, "result": result})
            tracker.record("Upwork", "proposal_submitted", amount_usd=bid_amount, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Upwork token missing")
            return
        jobs = self.search_jobs("python AI automation developer", limit=10)
        self.log.info(f"Found {len(jobs)} matching jobs")
        for j in jobs[:3]:
            b = j.get("budget", {})
            self.log.info(f"  [{j.get('id')}] {j.get('title', '')[:55]} | ${b.get('amount', '?')} {j.get('engagement', '')}")
        contracts = self.get_active_contracts()
        self.log.info(f"Active contracts: {len(contracts)}")
        earnings = self.get_weekly_earnings()
        if earnings:
            amt = earnings.get("earnedAmount", {})
            self.log.info(f"Weekly earnings: ${amt.get('amount', 0)} {amt.get('currencyCode')}")
            tracker.record("Upwork", "weekly_earnings", amount_usd=float(amt.get("amount", 0)))
        tracker.record("Upwork", "job_search", meta={"count": len(jobs)})


class FreelancerPlatform(Platform):
    NAME = "Freelancer"
    BASE = "https://www.freelancer.com/api"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.FREELANCER_TOKEN)

    def _h(self) -> Dict[str, str]:
        return {"freelancer-oauth-v1": cfg.FREELANCER_TOKEN, "Content-Type": "application/json"}

    @retry(3)
    def search_projects(self, query: str = "python developer", limit: int = 10) -> List[Dict]:
        self._rl()
        resp = self.session.get(
            f"{self.BASE}/projects/0.1/projects/active/",
            headers=self._h(),
            params={"query": query, "limit": limit, "full_description": True, "job_details": True},
        )
        if resp.status_code == 200:
            return resp.json().get("result", {}).get("projects", [])
        self.log.warning(f"Search failed: {resp.status_code}")
        return []

    @retry(2)
    def get_self_info(self) -> Optional[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/users/0.1/self/", headers=self._h())
        return resp.json().get("result") if resp.status_code == 200 else None

    @retry(2)
    def get_active_bids(self) -> List[Dict]:
        self._rl()
        resp = self.session.get(
            f"{self.BASE}/projects/0.1/bids/",
            headers=self._h(),
            params={"bidder_id": "self", "bid_statuses[]": ["pending", "awarded"]},
        )
        return resp.json().get("result", {}).get("bids", []) if resp.status_code == 200 else []

    @require_live_mode
    @require_confirmation("AUTO_PROPOSE")
    def submit_bid(self, project_id: int, bid_amount: float, proposal: str, duration_days: int = 7) -> Dict:
        if bid_amount > SafetyConfig.MAX_BID_USD:
            return self._audit("bid_blocked", {"reason": "exceeds MAX_BID_USD", "bid": bid_amount})
        try:
            url = f"{self.BASE}/projects/0.1/bids/"
            data = {
                "project_id": project_id,
                "bidder_id": cfg.MEDIUM_USER_ID or "self",
                "amount": bid_amount,
                "period": duration_days,
                "proposal": proposal,
                "milestone_percentage": 100,
            }
            resp = self.session.post(url, headers=self._h(), json=data)
            result = resp.json() if resp.status_code == 200 else {"status": resp.status_code}
            self._audit("bid_submitted", {"project_id": project_id, "amount": bid_amount, "result": result})
            tracker.record("Freelancer", "bid_submitted", amount_usd=bid_amount, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Freelancer token missing")
            return
        me = self.get_self_info()
        if me:
            rep = me.get("reputation", {}).get("entire_history", {}).get("overall", "?")
            self.log.info(f"User: {me.get('username')} | Rating: {rep}/5.0")
        projects = self.search_projects("python AI automation", 10)
        self.log.info(f"Found {len(projects)} project(s)")
        for p in projects[:3]:
            b = p.get("budget", {})
            self.log.info(f"  [{p.get('id')}] {p.get('title', '')[:55]} | ${b.get('minimum', 0)}--${b.get('maximum', 0)}")
        bids = self.get_active_bids()
        self.log.info(f"Active bids: {len(bids)}")
        tracker.record("Freelancer", "project_search", meta={"count": len(projects)})


# ═══════════════════════════════════════════════════════════════
#  SOCIAL / GIG HUNTING  ---  Reddit auto-reply
# ═══════════════════════════════════════════════════════════════

class RedditPlatform(Platform):
    NAME = "Reddit"
    _limiter = RateLimiter(10)

    def __init__(self):
        super().__init__()
        self._reddit = None
        if all([cfg.REDDIT_CLIENT_ID, cfg.REDDIT_CLIENT_SECRET]) and _REDDIT_OK:
            try:
                self._reddit = praw.Reddit(
                    client_id=cfg.REDDIT_CLIENT_ID,
                    client_secret=cfg.REDDIT_CLIENT_SECRET,
                    user_agent=cfg.REDDIT_USER_AGENT,
                )
                self.log.info("Reddit: Initialized")
            except Exception as e:
                self.log.warning(f"Reddit init failed: {e}")

    def health_check(self) -> bool:
        return self._reddit is not None

    @retry(2)
    def hunt_gigs(self, subreddits: List[str] = None, limit: int = 10) -> List[Dict]:
        if not self._reddit:
            return []
        if subreddits is None:
            subreddits = ["slavelabour", "forhire", "jobbit", "WorkOnline"]
        gigs = []
        for sub_name in subreddits:
            try:
                subreddit = self._reddit.subreddit(sub_name)
                for post in subreddit.new(limit=limit):
                    title_lower = post.title.lower()
                    if any(k in title_lower for k in ["hiring", "paid", "$", "budget", "freelance"]):
                        gigs.append({"id": post.id, "title": post.title, "url": post.url, "subreddit": sub_name})
            except Exception as e:
                self.log.warning(f"Reddit r/{sub_name}: {e}")
        return gigs

    @require_live_mode
    @require_confirmation("AUTO_PROPOSE")
    def submit_reply(self, submission_id: str, reply_text: str) -> Dict:
        if not self._reddit:
            return {"status": "error", "reason": "not initialized"}
        try:
            submission = self._reddit.submission(id=submission_id)
            comment = submission.reply(reply_text)
            self._audit("gig_reply_sent", {"submission_id": submission_id, "comment_id": comment.id})
            tracker.record("Reddit", "gig_reply", meta={"submission_id": submission_id})
            return {"status": "ok", "comment_id": comment.id}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Reddit not initialized")
            return
        gigs = self.hunt_gigs()
        self.log.info(f"Found {len(gigs)} gig post(s)")
        for g in gigs[:5]:
            self.log.info(f"  r/{g['subreddit']}: {g['title'][:60]}")
        tracker.record("Reddit", "gig_hunt", meta={"count": len(gigs)})


# ═══════════════════════════════════════════════════════════════
#  DIGITAL PRODUCTS & E-COMMERCE  ---  create / fulfill actions
# ═══════════════════════════════════════════════════════════════

class GumroadPlatform(Platform):
    NAME = "Gumroad"
    BASE = "https://api.gumroad.com/v2"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.GUMROAD_ACCESS_TOKEN)

    def _p(self, **kwargs) -> Dict:
        return {"access_token": cfg.GUMROAD_ACCESS_TOKEN, **kwargs}

    @retry(2)
    def get_products(self) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/products", params=self._p())
        return resp.json().get("products", []) if resp.status_code == 200 else []

    @retry(2)
    def get_sales(self, after: str = None) -> List[Dict]:
        self._rl()
        params = self._p()
        if after:
            params["after"] = after
        resp = self.session.get(f"{self.BASE}/sales", params=params)
        return resp.json().get("sales", []) if resp.status_code == 200 else []

    @retry(2)
    def create_product(self, name: str, price_cents: int, description: str = "", file_url: str = None) -> Optional[Dict]:
        self._rl()
        data = self._p(name=name, price=price_cents, description=description)
        if file_url:
            data["url"] = file_url
        resp = self.session.post(f"{self.BASE}/products", data=data)
        if resp.status_code in (200, 201):
            product = resp.json().get("product", {})
            self.log.info(f"Created product: {product.get('id')} --- {name} @ ${price_cents/100:.2f}")
            tracker.record("Gumroad", "product_created", meta={"name": name, "price_cents": price_cents})
            return product
        self.log.error(f"Create failed {resp.status_code}: {resp.text[:200]}")
        return None

    @retry(2)
    def enable_product(self, product_id: str) -> bool:
        self._rl()
        resp = self.session.put(f"{self.BASE}/products/{product_id}/enable", params=self._p())
        return resp.status_code == 200

    def run(self):
        if not self.health_check():
            self.log.warning("Gumroad token missing")
            return
        products = self.get_products()
        total_rev = 0.0
        for p in products:
            rev = float(p.get("sales_revenue", 0)) / 100
            total_rev += rev
            self.log.info(f"  [{p.get('id')}] {p.get('name', '')[:45]} | ${int(p.get('price',0))/100:.2f} | {p.get('sales_count',0)} sales | Rev: ${rev:.2f}")
        self.log.info(f"Total revenue: ${total_rev:.2f}")
        tracker.record("Gumroad", "revenue_check", amount_usd=total_rev)


class EtsyPlatform(Platform):
    NAME = "Etsy"
    BASE = "https://openapi.etsy.com/v3/application"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.ETSY_ACCESS_TOKEN)

    def _h(self) -> Dict[str, str]:
        return {"x-api-key": cfg.ETSY_API_KEY, "Authorization": f"Bearer {cfg.ETSY_ACCESS_TOKEN}"}

    @retry(2)
    def get_shops(self) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/users/me/shops", headers=self._h())
        return resp.json().get("results", []) if resp.status_code == 200 else []

    @retry(2)
    def get_listings(self, shop_id: str, state: str = "active") -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/shops/{shop_id}/listings", headers=self._h(), params={"state": state, "limit": 100})
        return resp.json().get("results", []) if resp.status_code == 200 else []

    @retry(2)
    def get_receipts(self, shop_id: str) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/shops/{shop_id}/receipts", headers=self._h(), params={"was_paid": "true", "limit": 25})
        return resp.json().get("results", []) if resp.status_code == 200 else []

    @require_live_mode
    @require_confirmation("AUTO_LIST")
    def create_listing(self, shop_id: str, title: str, description: str, price: float, quantity: int = 1, tags: List[str] = None) -> Dict:
        if price > SafetyConfig.MAX_LISTING_PRICE:
            return self._audit("listing_blocked", {"reason": "exceeds MAX_LISTING_PRICE", "price": price})
        try:
            data = {
                "title": title,
                "description": description,
                "price": price,
                "quantity": quantity,
                "tags": tags or ["handmade", "digital"],
                "who_made": "i_did",
                "when_made": "made_to_order",
                "taxonomy_id": 1,
                "type": "physical",
            }
            resp = self.session.post(f"{self.BASE}/shops/{shop_id}/listings", headers=self._h(), json=data)
            result = resp.json() if resp.status_code == 200 else {"status": resp.status_code}
            self._audit("listing_created", {"shop_id": shop_id, "title": title, "price": price, "result": result})
            tracker.record("Etsy", "listing_created", amount_usd=price, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Etsy token missing")
            return
        shops = self.get_shops()
        for shop in shops:
            sid = str(shop.get("shop_id"))
            listings = self.get_listings(sid)
            receipts = self.get_receipts(sid)
            rev = sum(float(r.get("total_price", {}).get("amount", 0)) / 100 for r in receipts)
            self.log.info(f"  '{shop.get('shop_name')}' --- {len(listings)} listings | {len(receipts)} orders | Rev: ${rev:.2f}")
            tracker.record("Etsy", "revenue_check", amount_usd=rev, meta={"shop": shop.get("shop_name")})


class EbayPlatform(Platform):
    NAME = "eBay"
    BASE = "https://api.ebay.com"
    _limiter = RateLimiter(5)

    def health_check(self) -> bool:
        return bool(cfg.EBAY_TOKEN)

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {cfg.EBAY_TOKEN}", "Content-Type": "application/json", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}

    @retry(2)
    def search_items(self, query: str, limit: int = 10) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/buy/browse/v1/item_summary/search", headers=self._h(), params={"q": query, "limit": limit})
        return resp.json().get("itemSummaries", []) if resp.status_code == 200 else []

    @retry(2)
    def get_inventory_items(self) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/sell/inventory/v1/inventory_item", headers=self._h(), params={"limit": 100})
        return resp.json().get("inventoryItems", []) if resp.status_code == 200 else []

    def run(self):
        if not self.health_check():
            self.log.warning("eBay token missing")
            return
        results = self.search_items("digital art printable", limit=5)
        self.log.info(f"Market comp: {len(results)} similar listing(s)")
        inventory = self.get_inventory_items()
        self.log.info(f"Your inventory: {len(inventory)} item(s)")
        tracker.record("eBay", "market_check", meta={"comps": len(results)})


class StripePlatform(Platform):
    NAME = "Stripe"
    BASE = "https://api.stripe.com/v1"
    _limiter = RateLimiter(20)

    def health_check(self) -> bool:
        return bool(cfg.STRIPE_SECRET_KEY)

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {cfg.STRIPE_SECRET_KEY}"}

    @retry(2)
    def get_balance(self) -> Optional[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/balance", headers=self._h())
        return resp.json() if resp.status_code == 200 else None

    @retry(2)
    def get_recent_charges(self, limit: int = 10) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/charges", headers=self._h(), params={"limit": limit})
        return resp.json().get("data", []) if resp.status_code == 200 else []

    @retry(2)
    def get_payouts(self, limit: int = 5) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/payouts", headers=self._h(), params={"limit": limit, "status": "paid"})
        return resp.json().get("data", []) if resp.status_code == 200 else []

    @require_live_mode
    @require_confirmation("AUTO_WITHDRAW")
    def create_payout(self, amount_usd: float, destination_bank: str = None) -> Dict:
        if amount_usd > SafetyConfig.MAX_WITHDRAW_USD:
            return self._audit("payout_blocked", {"reason": "exceeds MAX_WITHDRAW_USD", "amount": amount_usd})
        try:
            data = {"amount": int(amount_usd * 100), "currency": "usd", "method": "standard"}
            if destination_bank:
                data["destination"] = destination_bank
            resp = self.session.post(f"{self.BASE}/payouts", headers=self._h(), data=data)
            result = resp.json() if resp.status_code == 200 else {"status": resp.status_code}
            self._audit("payout_created", {"amount_usd": amount_usd, "result": result})
            tracker.record("Stripe", "payout_created", amount_usd=amount_usd, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Stripe key missing")
            return
        bal = self.get_balance()
        if bal:
            avail = sum(b["amount"] for b in bal.get("available", []) if b["currency"] == "usd") / 100
            pending = sum(b["amount"] for b in bal.get("pending", []) if b["currency"] == "usd") / 100
            self.log.info(f"Balance --- Available: ${avail:.2f} | Pending: ${pending:.2f}")
            tracker.record("Stripe", "balance", amount_usd=avail + pending)
        charges = self.get_recent_charges()
        paid_total = sum(c["amount"] for c in charges if c.get("paid")) / 100
        self.log.info(f"Recent {len(charges)} charge(s) --- Total: ${paid_total:.2f}")


class ShopifyPlatform(Platform):
    NAME = "Shopify"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.SHOPIFY_STORE and cfg.SHOPIFY_ACCESS_TOKEN)

    def _base(self) -> str:
        return f"https://{cfg.SHOPIFY_STORE}.myshopify.com/admin/api/2024-01"

    def _h(self) -> Dict[str, str]:
        return {"X-Shopify-Access-Token": cfg.SHOPIFY_ACCESS_TOKEN}

    @retry(2)
    def get_orders(self, limit: int = 10) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self._base()}/orders.json", headers=self._h(), params={"limit": limit, "status": "any"})
        return resp.json().get("orders", []) if resp.status_code == 200 else []

    @require_live_mode
    @require_confirmation("AUTO_FULFILL")
    def fulfill_order(self, order_id: str, tracking_number: str = None, carrier: str = "UPS") -> Dict:
        try:
            order = self._safe_request("GET", f"{self._base()}/orders/{order_id}.json", headers=self._h())
            if not order or not order.get("order"):
                return {"status": "error", "reason": "order not found"}
            fulfillment = {
                "fulfillment": {
                    "location_id": order["order"]["location_id"],
                    "tracking_number": tracking_number or f"AUTO{random.randint(10000,99999)}",
                    "carrier": carrier,
                    "notify_customer": True,
                }
            }
            result = self._safe_request("POST", f"{self._base()}/orders/{order_id}/fulfillments.json", headers=self._h(), json=fulfillment)
            self._audit("order_fulfilled", {"order_id": order_id, "tracking": fulfillment["fulfillment"]["tracking_number"], "result": result})
            tracker.record("Shopify", "order_fulfilled", meta={"order_id": order_id})
            return result or {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Shopify credentials missing")
            return
        orders = self.get_orders()
        revenue = sum(float(o.get("total_price", 0)) for o in orders)
        self.log.info(f"{len(orders)} orders | Revenue: ${revenue:.2f}")
        tracker.record("Shopify", "revenue_check", amount_usd=revenue, meta={"orders": len(orders)})


class PrintfulPlatform(Platform):
    NAME = "Printful"
    BASE = "https://api.printful.com"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.PRINTFUL_API_KEY)

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {cfg.PRINTFUL_API_KEY}"}

    @retry(2)
    def get_orders(self) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/orders", headers=self._h())
        return resp.json().get("result", []) if resp.status_code == 200 else []

    def run(self):
        if not self.health_check():
            self.log.warning("Printful key missing")
            return
        orders = self.get_orders()
        self.log.info(f"Printful: {len(orders)} orders")
        tracker.record("Printful", "orders_check", meta={"count": len(orders)})


class PrintifyPlatform(Platform):
    NAME = "Printify"
    BASE = "https://api.printify.com/v1"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.PRINTIFY_API_KEY and cfg.PRINTIFY_SHOP_ID)

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {cfg.PRINTIFY_API_KEY}"}

    @retry(2)
    def get_products(self) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/shops/{cfg.PRINTIFY_SHOP_ID}/products.json", headers=self._h())
        return resp.json().get("data", []) if resp.status_code == 200 else []

    @require_live_mode
    @require_confirmation("AUTO_LIST")
    def create_product(self, title: str, blueprint_id: int, print_provider_id: int,
                       variant_ids: List[int], price: float, image_url: str) -> Dict:
        try:
            variants = [{"id": v_id, "price": int(price * 100), "is_enabled": True} for v_id in variant_ids]
            data = {
                "title": title,
                "description": f"Auto-generated: {title}",
                "blueprint_id": blueprint_id,
                "print_provider_id": print_provider_id,
                "variants": variants,
                "print_areas": [{"variant_ids": variant_ids, "placeholders": [{"position": "front", "images": [{"id": image_url, "x": 0.5, "y": 0.5, "scale": 1.0}]}]}]
            }
            resp = self.session.post(f"{self.BASE}/shops/{cfg.PRINTIFY_SHOP_ID}/products.json", headers=self._h(), json=data)
            result = resp.json() if resp.status_code == 200 else {"status": resp.status_code}
            self._audit("product_created", {"title": title, "price": price, "result": result})
            tracker.record("Printify", "product_created", amount_usd=price, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Printify credentials missing")
            return
        products = self.get_products()
        self.log.info(f"Printify: {len(products)} products")
        tracker.record("Printify", "products_check", meta={"count": len(products)})


# ═══════════════════════════════════════════════════════════════
#  CONTENT PLATFORM
# ═══════════════════════════════════════════════════════════════

class YouTubePlatform(Platform):
    NAME = "YouTube"
    BASE = "https://www.googleapis.com/youtube/v3"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.YOUTUBE_API_KEY and cfg.YOUTUBE_CHANNEL_ID)

    def _p(self, **kwargs) -> Dict:
        return {"key": cfg.YOUTUBE_API_KEY, **kwargs}

    @retry(2)
    def get_channel_stats(self) -> Optional[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/channels", params=self._p(part="statistics,snippet", id=cfg.YOUTUBE_CHANNEL_ID))
        items = resp.json().get("items", []) if resp.status_code == 200 else []
        return items[0] if items else None

    def run(self):
        if not self.health_check():
            self.log.warning("YouTube credentials missing")
            return
        ch = self.get_channel_stats()
        if ch:
            s = ch.get("statistics", {})
            self.log.info(f"Channel: {ch.get('snippet',{}).get('title')} | Subs: {int(s.get('subscriberCount',0)):,} | Views: {int(s.get('viewCount',0)):,}")
        tracker.record("YouTube", "analytics_check")


class MediumPlatform(Platform):
    NAME = "Medium"
    BASE = "https://api.medium.com/v1"
    _limiter = RateLimiter(5)

    def health_check(self) -> bool:
        return bool(cfg.MEDIUM_API_KEY and cfg.MEDIUM_USER_ID)

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {cfg.MEDIUM_API_KEY}", "Content-Type": "application/json"}

    @retry(2)
    def get_user(self) -> Optional[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/me", headers=self._h())
        return resp.json().get("data") if resp.status_code == 200 else None

    @require_live_mode
    @require_confirmation("AUTO_PUBLISH")
    def publish_post(self, title: str, content: str, tags: List[str] = None, publish_status: str = "public") -> Dict:
        try:
            data = {
                "title": title,
                "contentFormat": "html",
                "content": f"<h1>{title}</h1>{content}",
                "tags": tags or ["automation", "tech"],
                "publishStatus": publish_status,
            }
            resp = self.session.post(f"{self.BASE}/users/{cfg.MEDIUM_USER_ID}/posts", headers=self._h(), json=data)
            result = resp.json() if resp.status_code == 200 else {"status": resp.status_code}
            self._audit("post_published", {"title": title, "result": result})
            tracker.record("Medium", "post_published", meta={"title": title})
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Medium credentials missing")
            return
        user = self.get_user()
        if user:
            self.log.info(f"Medium user: {user.get('username')}")
        tracker.record("Medium", "user_check")


# ═══════════════════════════════════════════════════════════════
#  AI SERVICE PLATFORMS  ---  generate + deliver
# ═══════════════════════════════════════════════════════════════

class OpenAIPlatform(Platform):
    NAME = "OpenAI"
    BASE = "https://api.openai.com/v1"
    _limiter = RateLimiter(20)

    def health_check(self) -> bool:
        return bool(cfg.OPENAI_API_KEY)

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {cfg.OPENAI_API_KEY}", "Content-Type": "application/json"}

    @retry(2)
    def generate(self, prompt: str, model: str = "gpt-4o-mini", max_tokens: int = 2000) -> Optional[str]:
        self._rl()
        data = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
        resp = self.session.post(f"{self.BASE}/chat/completions", headers=self._h(), json=data)
        if resp.status_code == 200:
            return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return None

    @require_live_mode
    @require_confirmation("AUTO_DELIVER")
    def generate_and_deliver(self, client_email: str, prompt: str) -> Dict:
        content = self.generate(prompt)
        if not content:
            return {"status": "error", "reason": "generation failed"}
        # Delivery is simulated; integrate SendGrid/AWS SES in production
        self._audit("content_delivered", {
            "client": client_email,
            "prompt_preview": prompt[:50],
            "content_length": len(content),
            "delivery_status": "simulated",
        })
        tracker.record("OpenAI", "content_delivered", meta={"client": client_email, "length": len(content)})
        return {"status": "delivered", "content_length": len(content)}

    def run(self):
        if not self.health_check():
            self.log.warning("OpenAI key missing")
            return
        self.log.info("OpenAI: Ready for generation")
        tracker.record("OpenAI", "health_check")


class AnthropicPlatform(Platform):
    NAME = "Anthropic"
    BASE = "https://api.anthropic.com/v1"
    _limiter = RateLimiter(20)

    def health_check(self) -> bool:
        return bool(cfg.ANTHROPIC_API_KEY)

    def _h(self) -> Dict[str, str]:
        return {"x-api-key": cfg.ANTHROPIC_API_KEY, "Content-Type": "application/json", "anthropic-version": "2023-06-01"}

    @retry(2)
    def generate(self, prompt: str, model: str = "claude-3-haiku-20240307", max_tokens: int = 2000) -> Optional[str]:
        self._rl()
        data = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        resp = self.session.post(f"{self.BASE}/messages", headers=self._h(), json=data)
        if resp.status_code == 200:
            return resp.json().get("content", [{}])[0].get("text", "")
        return None

    def run(self):
        if not self.health_check():
            self.log.warning("Anthropic key missing")
            return
        self.log.info("Anthropic: Ready")
        tracker.record("Anthropic", "health_check")


class ReplicatePlatform(Platform):
    NAME = "Replicate"
    BASE = "https://api.replicate.com/v1"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.REPLICATE_API_KEY)

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Token {cfg.REPLICATE_API_KEY}"}

    @retry(2)
    def list_models(self) -> List[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/models", headers=self._h())
        return resp.json().get("results", []) if resp.status_code == 200 else []

    def run(self):
        if not self.health_check():
            self.log.warning("Replicate key missing")
            return
        models = self.list_models()
        self.log.info(f"Replicate: {len(models)} models accessible")
        tracker.record("Replicate", "models_check", meta={"count": len(models)})


# ═══════════════════════════════════════════════════════════════
#  PAYMENT / WITHDRAWAL PLATFORMS
# ═══════════════════════════════════════════════════════════════

class RazorpayPlatform(Platform):
    NAME = "Razorpay"
    BASE = "https://api.razorpay.com/v1"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.RAZORPAY_KEY_ID and cfg.RAZORPAY_KEY_SECRET)

    def _auth(self) -> Tuple[str, str]:
        return (cfg.RAZORPAY_KEY_ID, cfg.RAZORPAY_KEY_SECRET)

    @require_live_mode
    @require_confirmation("AUTO_WITHDRAW")
    def create_payout(self, amount_inr: float, account_number: str = None, ifsc: str = None, mode: str = "IMPS") -> Dict:
        if amount_inr / 85.0 > SafetyConfig.MAX_WITHDRAW_USD:  # rough USD cap
            return self._audit("payout_blocked", {"reason": "exceeds cap", "amount_inr": amount_inr})
        try:
            data = {
                "account_number": "2323230029292929",  # Razorpay virtual account
                "amount": int(amount_inr * 100),
                "currency": "INR",
                "mode": mode,
                "purpose": "payout",
                "fund_account": {
                    "account_type": "bank_account",
                    "bank_account": {
                        "name": "Account Holder",
                        "ifsc": ifsc or SafetyConfig.IFSC_CODE or "HDFC0000000",
                        "account_number": account_number or SafetyConfig.BANK_ACCOUNT or "0000000000",
                    }
                }
            }
            resp = self.session.post(f"{self.BASE}/payouts", auth=self._auth(), json=data)
            result = resp.json() if resp.status_code == 200 else {"status": resp.status_code}
            self._audit("payout_initiated", {"amount_inr": amount_inr, "mode": mode, "result": result})
            tracker.record("Razorpay", "payout", amount_usd=amount_inr/85.0, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Razorpay credentials missing")
            return
        self.log.info("Razorpay: Ready for payouts")
        tracker.record("Razorpay", "health_check")


class WisePlatform(Platform):
    NAME = "Wise"
    BASE = "https://api.wise.com"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.WISE_API_KEY)

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {cfg.WISE_API_KEY}"}

    @retry(2)
    def get_profile(self) -> Optional[Dict]:
        self._rl()
        resp = self.session.get(f"{self.BASE}/v1/profiles", headers=self._h())
        profiles = resp.json() if resp.status_code == 200 else []
        return profiles[0] if profiles else None

    @require_live_mode
    @require_confirmation("AUTO_WITHDRAW")
    def create_transfer_quote(self, source: str = "USD", target: str = "INR", amount: float = 100.0) -> Dict:
        try:
            profile = self.get_profile()
            pid = profile.get("id") if profile else None
            data = {"sourceCurrency": source, "targetCurrency": target, "sourceAmount": amount, "profile": pid}
            resp = self.session.post(f"{self.BASE}/v2/quotes", headers=self._h(), json=data)
            result = resp.json() if resp.status_code == 200 else {"status": resp.status_code}
            self._audit("transfer_quoted", {"source": source, "target": target, "amount": amount, "result": result})
            tracker.record("Wise", "transfer_quote", amount_usd=amount, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Wise key missing")
            return
        self.log.info("Wise: Ready")
        tracker.record("Wise", "health_check")


class PayPalPlatform(Platform):
    NAME = "PayPal"
    BASE = "https://api.paypal.com"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.PAYPAL_CLIENT_ID and cfg.PAYPAL_CLIENT_SECRET)

    def _token(self) -> Optional[str]:
        auth = base64.b64encode(f"{cfg.PAYPAL_CLIENT_ID}:{cfg.PAYPAL_CLIENT_SECRET}".encode()).decode()
        resp = self.session.post(
            f"{self.BASE}/v1/oauth2/token",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"}
        )
        return resp.json().get("access_token") if resp.status_code == 200 else None

    @require_live_mode
    @require_confirmation("AUTO_WITHDRAW")
    def create_payout(self, amount: float, recipient_email: str, currency: str = "USD") -> Dict:
        try:
            token = self._token()
            if not token:
                return {"status": "error", "reason": "auth failed"}
            data = {
                "sender_batch_header": {"sender_batch_id": f"batch_{int(time.time())}", "email_subject": "Payout"},
                "items": [{"recipient_type": "EMAIL", "amount": {"value": str(amount), "currency": currency},
                            "receiver": recipient_email, "sender_item_id": f"item_{int(time.time())}"}]
            }
            resp = self.session.post(
                f"{self.BASE}/v1/payments/payouts",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=data
            )
            result = resp.json() if resp.status_code in (200, 201) else {"status": resp.status_code}
            self._audit("payout_created", {"amount": amount, "recipient": recipient_email, "result": result})
            tracker.record("PayPal", "payout", amount_usd=amount, meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("PayPal credentials missing")
            return
        self.log.info("PayPal: Ready")
        tracker.record("PayPal", "health_check")


# ═══════════════════════════════════════════════════════════════
#  MICROTASK PLATFORMS
# ═══════════════════════════════════════════════════════════════

class TolokaPlatform(Platform):
    NAME = "Toloka"
    BASE = "https://toloka.dev/api/v1"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.TOLOKA_API_KEY)

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"OAuth {cfg.TOLOKA_API_KEY}"}

    @require_live_mode
    @require_confirmation("MICROTASK_AUTO")
    def accept_task_suite(self, task_suite_id: str) -> Dict:
        try:
            resp = self.session.post(f"{self.BASE}/task-suites/{task_suite_id}/assignments", headers=self._h(), json={"user_id": "me"})
            result = resp.json() if resp.status_code == 200 else {"status": resp.status_code}
            self._audit("task_accepted", {"task_suite_id": task_suite_id, "result": result})
            tracker.record("Toloka", "task_accepted", meta=result)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self):
        if not self.health_check():
            self.log.warning("Toloka key missing")
            return
        self.log.info("Toloka: Ready")
        tracker.record("Toloka", "health_check")


class ClickworkerPlatform(Platform):
    NAME = "Clickworker"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.CLICKWORKER_API_KEY)

    def run(self):
        if not self.health_check():
            self.log.warning("Clickworker key missing")
            return
        self.log.info("Clickworker: Ready")
        tracker.record("Clickworker", "health_check")


class RemotasksPlatform(Platform):
    NAME = "Remotasks"
    _limiter = RateLimiter(10)

    def health_check(self) -> bool:
        return bool(cfg.REMOTASKS_API_KEY)

    def run(self):
        if not self.health_check():
            self.log.warning("Remotasks key missing")
            return
        self.log.info("Remotasks: Ready")
        tracker.record("Remotasks", "health_check")


# ═══════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

class MoneyBotOrchestrator:
    def __init__(self):
        self.log = logging.getLogger("Orchestrator")
        self.platforms: List[Platform] = [
            # Crypto
            BinancePlatform(), CoinbasePlatform(), KuCoinPlatform(), BybitPlatform(), OKXPlatform(),
            # Stock Media
            ShutterstockPlatform(), AdobeStockPlatform(), Pond5Platform(),
            # Freelance
            UpworkPlatform(), FreelancerPlatform(),
            # Social
            RedditPlatform(),
            # Commerce
            GumroadPlatform(), EtsyPlatform(), EbayPlatform(), StripePlatform(),
            ShopifyPlatform(), PrintfulPlatform(), PrintifyPlatform(),
            # Content
            YouTubePlatform(), MediumPlatform(),
            # AI
            OpenAIPlatform(), AnthropicPlatform(), ReplicatePlatform(),
            # Payments
            RazorpayPlatform(), WisePlatform(), PayPalPlatform(),
            # Microtasks
            TolokaPlatform(), ClickworkerPlatform(), RemotasksPlatform(),
        ]

    def health_check_all(self) -> Dict[str, bool]:
        self.log.info("── Health Check ──────────────────────────────")
        results: Dict[str, bool] = {}
        for p in self.platforms:
            try:
                ok = p.health_check()
                results[p.NAME] = ok
                sym = "OK" if ok else "XX"
                self.log.info(f"  {sym} {p.NAME}")
            except Exception as e:
                results[p.NAME] = False
                self.log.error(f"  XX {p.NAME}: {e}")
        configured = sum(v for v in results.values())
        self.log.info(f"  {configured}/{len(self.platforms)} platforms configured")
        return results

    def _run_one(self, p: Platform):
        sep = "─" * 22
        self.log.info(f"{sep} {p.NAME} {sep}")
        try:
            p.run()
        except Exception as e:
            self.log.error(f"[{p.NAME}] Unhandled error: {e}", exc_info=True)

    def run_all(self, parallel: bool = False):
        start = datetime.now()
        self.log.info(f"🚀  API Money Bot v3.0  ---  {start:%Y-%m-%d %H:%M:%S}")
        self.log.info(f"LIVE_MODE={SafetyConfig.LIVE_MODE} | TRADING={SafetyConfig.TRADING_ENABLED} | PROPOSE={SafetyConfig.AUTO_PROPOSE} | WITHDRAW={SafetyConfig.AUTO_WITHDRAW}")

        health = self.health_check_all()
        active = [p for p in self.platforms if health.get(p.NAME)]

        if parallel:
            threads = [threading.Thread(target=self._run_one, args=(p,), name=p.NAME, daemon=True) for p in active]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        else:
            for p in active:
                self._run_one(p)
                time.sleep(random.uniform(0.5, 2.0))

        self._print_summary(start)

    def run_platform(self, name: str):
        match = next((p for p in self.platforms if p.NAME.lower() == name.lower()), None)
        if not match:
            names = ", ".join(p.NAME for p in self.platforms)
            self.log.error(f"Unknown platform '{name}'. Available: {names}")
            return
        self._run_one(match)

    def execute_action(self, platform_name: str, action: str, **kwargs):
        """Execute a specific action on a platform."""
        p = next((x for x in self.platforms if x.NAME.lower() == platform_name.lower()), None)
        if not p:
            self.log.error(f"Platform {platform_name} not found")
            return
        method = getattr(p, action, None)
        if not method:
            self.log.error(f"Action {action} not found on {platform_name}")
            return
        try:
            result = method(**kwargs)
            self.log.info(f"Action result: {result}")
            return result
        except Exception as e:
            self.log.error(f"Action failed: {e}")

    def _print_summary(self, start: datetime):
        summary = tracker.daily_summary()
        total = tracker.total_earned()
        self.log.info("\n" + "═" * 55)
        self.log.info(f"  📊  DAILY SUMMARY  ({datetime.now().date()})")
        self.log.info("═" * 55)
        if summary:
            for name, amt in sorted(summary.items(), key=lambda x: -x[1]):
                self.log.info(f"  {name:<22}: ${amt:.4f}")
        else:
            self.log.info("  No revenue events recorded today yet.")
        self.log.info("─" * 55)
        self.log.info(f"  {'All-time total':<22}: ${total:.4f}")
        self.log.info(f"  {'Run duration':<22}: {datetime.now() - start}")
        self.log.info("═" * 55)


# ═══════════════════════════════════════════════════════════════
#  EARNINGS ENGINE  ---  optional import
# ═══════════════════════════════════════════════════════════════

_HAS_EARNINGS_ENGINE = False
try:
    from earnings_engine import (EarningsMonitor, DepositPipeline,
                                  EarnFirstPriorityQueue, TradingBalanceTracker)
    _HAS_EARNINGS_ENGINE = True
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="API Money Bot v3.0 --- payment automation edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--platform", metavar="NAME", help="Run a single platform (e.g. KuCoin, Gumroad)")
    parser.add_argument("--health", action="store_true", help="Credential health-check and exit")
    parser.add_argument("--parallel", action="store_true", help="Run all platforms concurrently")
    parser.add_argument("--summary", action="store_true", help="Print revenue summary and exit")
    parser.add_argument("--action", nargs=3, metavar=("PLATFORM", "METHOD", "JSON_ARGS"),
                        help="Execute action: --action Binance execute_trade '{\"symbol\":\"BTCUSDT\",\"side\":\"BUY\",\"quantity\":0.001}'")
    # Quick-action shortcuts
    parser.add_argument("--upload-photo", nargs=3, metavar=("PLATFORM", "PATH", "TITLE"),
                        help="Upload photo: --upload-photo shutterstock ./img.jpg 'My Title'")
    parser.add_argument("--upload-clip", nargs=3, metavar=("PLATFORM", "PATH", "TITLE"),
                        help="Upload clip: --upload-clip pond5 ./clip.mp4 'My Clip'")
    parser.add_argument("--create-product", nargs=3, metavar=("PLATFORM", "NAME", "PRICE_CENTS"),
                        help="Create product: --create-product gumroad 'My eBook' 999")
    # Earnings engine actions
    parser.add_argument("--earnings", action="store_true",
                        help="Check earnings on all platforms and print summary")
    parser.add_argument("--priority", action="store_true",
                        help="Run earn-first priority queue: earners -> withdraw -> trade")
    parser.add_argument("--pipeline", action="store_true",
                        help="Run deposit pipeline: auto-withdraw earnings if threshold met")
    args = parser.parse_args()

    bot = MoneyBotOrchestrator()

    # ── Earnings Engine actions ──────────────────────────────
    if args.earnings or args.priority or args.pipeline:
        if not _HAS_EARNINGS_ENGINE:
            log.error("earnings_engine.py not available. Run: pip install -r requirements.txt")
            return
        from earnings_engine import EarningsMonitor, DepositPipeline, EarnFirstPriorityQueue, TradingBalanceTracker

        monitor = EarningsMonitor(bot.platforms)
        tracker = TradingBalanceTracker()
        pipeline = DepositPipeline(monitor, tracker)

        if args.earnings:
            monitor.check_all()
            monitor.print_summary()
            return

        if args.pipeline:
            result = pipeline.run(force_withdraw=False)
            log.info(f"Pipeline result: {json.dumps(result, indent=2, default=str)}")
            return

        if args.priority:
            queue = EarnFirstPriorityQueue(bot.platforms, pipeline, monitor)
            result = queue.run_all()
            log.info(f"Priority queue result: {json.dumps({k: v for k, v in result.items() if k != 'results'}, indent=2)}")
            return

    if args.summary:
        s = tracker.daily_summary()
        total = tracker.total_earned()
        print("\n" + "─" * 45)
        print(f"  📊  Revenue Summary  ({datetime.now().date()})")
        print("─" * 45)
        for name, amt in sorted(s.items(), key=lambda x: -x[1]):
            print(f"  {name:<22}: ${amt:.4f}")
        print("─" * 45)
        print(f"  {'All-time total':<22}: ${total:.4f}")
        print()
        return

    if args.health:
        bot.health_check_all()
        return

    if args.action:
        platform_name, method, json_args = args.action
        kwargs = json.loads(json_args)
        bot.execute_action(platform_name, method, **kwargs)
        return

    if args.upload_photo:
        platform_name, path, title = args.upload_photo
        p = next((x for x in bot.platforms if x.NAME.lower() == platform_name.lower()), None)
        if isinstance(p, ShutterstockPlatform):
            p.upload_photo(path, title, description="Uploaded via MoneyBot")
        elif isinstance(p, AdobeStockPlatform):
            p.upload_asset(path, title)
        else:
            print("--upload-photo supports: shutterstock, adobestock")
        return

    if args.upload_clip:
        platform_name, path, title = args.upload_clip
        p = next((x for x in bot.platforms if x.NAME.lower() == platform_name.lower()), None)
        if isinstance(p, Pond5Platform):
            p.upload_clip(path, title, description="Uploaded via MoneyBot")
        else:
            print("--upload-clip supports: pond5")
        return

    if args.create_product:
        platform_name, name, price_cents = args.create_product
        p = next((x for x in bot.platforms if x.NAME.lower() == platform_name.lower()), None)
        if isinstance(p, GumroadPlatform):
            p.create_product(name, int(price_cents))
        elif isinstance(p, EtsyPlatform):
            print("Etsy listing requires shop_id. Use --action instead.")
        elif isinstance(p, PrintifyPlatform):
            print("Printify requires blueprint_id. Use --action instead.")
        else:
            print("--create-product supports: gumroad")
        return

    if args.platform:
        bot.run_platform(args.platform)
    else:
        bot.run_all(parallel=args.parallel)


if __name__ == "__main__":
    main()
