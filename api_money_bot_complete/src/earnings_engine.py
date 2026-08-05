"""
Earnings Engine --- Balance Monitor, Withdrawal Pipeline & Earn-First Priority Queue
==================================================================================

Provides:
  • EarningsMonitor  --- check earnings/balance on every platform, aggregate & report
  • DepositPipeline  --- auto-withdraw earnings when threshold is met, track virtual trading balance
  • EarnFirstPriorityQueue  --- process earning platforms first, switch to trading after threshold

Integration:
  from earnings_engine import EarningsMonitor, DepositPipeline, EarnFirstPriorityQueue
  monitor = EarningsMonitor(platforms)
  monitor.check_all()
  pipeline = DepositPipeline(monitor)
  pipeline.run(threshold=50.0)
  queue = EarnFirstPriorityQueue(platforms, pipeline)
  queue.run_all()
"""

import json
import logging
import os
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("EarningsEngine")

# ═══════════════════════════════════════════════════════════════
#  CONFIG  ---  earnings-specific settings
# ═══════════════════════════════════════════════════════════════

class EarningsConfig:
    """Earnings engine thresholds. Override via .env."""
    # Minimum total earnings (USD) before withdrawals are triggered
    MIN_WITHDRAWAL_THRESHOLD: float = float(os.getenv("MIN_WITHDRAWAL_THRESHOLD", "20.0"))
    # Minimum available trading balance before trades execute
    MIN_TRADE_BALANCE: float = float(os.getenv("MIN_TRADE_BALANCE", "50.0"))
    # Minimum earnings before trading platforms are activated
    EARNINGS_TRADE_THRESHOLD: float = float(os.getenv("EARNINGS_TRADE_THRESHOLD", "100.0"))
    # Auto-withdraw destination preference: "stripe", "paypal", "wise", "razorpay", or "any"
    WITHDRAW_PREFERENCE: str = os.getenv("WITHDRAW_PREFERENCE", "any")
    # Withdrawal destination details
    WITHDRAW_BANK_ACCOUNT: str = os.getenv("BANK_ACCOUNT", "")
    WITHDRAW_IFSC: str = os.getenv("IFSC_CODE", "")
    WITHDRAW_UPI: str = os.getenv("UPI_ID", "")
    WITHDRAW_EMAIL: str = os.getenv("WITHDRAW_DESTINATION", "")


# ═══════════════════════════════════════════════════════════════
#  DATA --- standardized earnings report
# ═══════════════════════════════════════════════════════════════

@dataclass
class EarningsReport:
    platform: str
    total_usd: float = 0.0
    available_usd: float = 0.0
    pending_usd: float = 0.0
    currency: str = "USD"
    status: str = "ok"  # ok, not_available, error
    error: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __bool__(self):
        return self.status == "ok"


EARNINGS_FILE = "earnings_report.json"
TRADE_BALANCE_FILE = "trading_balance.json"


# ═══════════════════════════════════════════════════════════════
#  PLATFORM ADAPTERS  ---  extract earnings from any platform object
# ═══════════════════════════════════════════════════════════════

def get_platform_earnings(platform) -> EarningsReport:
    """
    Extract a standard EarningsReport from any platform object.
    Tries, in order:
      1. get_earnings() method if available
      2. get_balance() method if available
      3. get_weekly_earnings() method if available
      4. Known revenue computations from run() data
    """
    name = platform.NAME
    p = platform

    # ── Stock Media ────────────────────────────────────────────
    if name == "Shutterstock":
        try:
            data = p.get_earnings()
            if data:
                monthly = data.get("total_month_earnings", {})
                amount = float(monthly.get("amount", 0))
                return EarningsReport(name, total_usd=amount, available_usd=amount,
                                      currency=monthly.get("currency", "USD"), raw=data)
            return EarningsReport(name, status="not_available")
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    if name == "Pond5":
        try:
            data = p.get_earnings()
            if data:
                total = float(data.get("total_earnings", 0))
                return EarningsReport(name, total_usd=total, available_usd=total, raw=data)
            return EarningsReport(name, status="not_available")
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    if name == "AdobeStock":
        try:
            assets = p.list_assets()
            # Adobe Stock contributor API doesn't expose earnings directly via this endpoint
            return EarningsReport(name, status="not_available",
                                  error="Adobe Stock earnings require contributor API scrape")
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    # ── Freelancing ────────────────────────────────────────────
    if name == "Upwork":
        try:
            data = p.get_weekly_earnings()
            if data:
                amt = data.get("earnedAmount", {})
                amount = float(amt.get("amount", 0))
                return EarningsReport(name, total_usd=amount, available_usd=amount,
                                      currency=amt.get("currencyCode", "USD"), raw=data)
            return EarningsReport(name, status="not_available")
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    if name == "Freelancer":
        return EarningsReport(name, status="not_available",
                              error="Freelancer balance not exposed by API")

    # ── Digital Products ────────────────────────────────────────
    if name == "Gumroad":
        try:
            products = p.get_products()
            total_rev = sum(float(prod.get("sales_revenue", 0)) / 100 for prod in products)
            return EarningsReport(name, total_usd=total_rev, available_usd=total_rev, raw={"products": products})
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    if name == "Etsy":
        try:
            shops = p.get_shops()
            total_rev = 0.0
            raw_data = {"shops": []}
            for shop in shops:
                sid = str(shop.get("shop_id"))
                receipts = p.get_receipts(sid)
                rev = sum(float(r.get("total_price", {}).get("amount", 0)) / 100 for r in receipts)
                total_rev += rev
                raw_data["shops"].append({"shop_name": shop.get("shop_name"), "revenue": rev, "receipts": receipts})
            return EarningsReport(name, total_usd=total_rev, available_usd=total_rev, raw=raw_data)
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    if name == "eBay":
        return EarningsReport(name, status="not_available",
                              error="eBay earnings require Finance API (not implemented)")

    # ── E-commerce ──────────────────────────────────────────────
    if name == "Shopify":
        try:
            orders = p.get_orders()
            revenue = sum(float(o.get("total_price", 0)) for o in orders)
            return EarningsReport(name, total_usd=revenue, available_usd=revenue, raw={"orders": orders})
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    if name == "Printful":
        try:
            orders = p.get_orders()
            return EarningsReport(name, status="not_available",
                                  error="Printful revenue not exposed by API")
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    if name == "Printify":
        try:
            products = p.get_products()
            return EarningsReport(name, status="not_available",
                                  error="Printify revenue not exposed by API")
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    # ── Content ─────────────────────────────────────────────────
    if name == "YouTube":
        return EarningsReport(name, status="not_available",
                              error="YouTube earnings require AdSense API (not implemented)")

    if name == "Medium":
        return EarningsReport(name, status="not_available",
                              error="Medium earnings require Medium Partner Program API (not implemented)")

    # ── Payments (already have balance, not earnings) ──────────
    if name == "Stripe":
        try:
            data = p.get_balance()
            if data:
                avail = sum(b["amount"] for b in data.get("available", []) if b["currency"] == "usd") / 100
                pending = sum(b["amount"] for b in data.get("pending", []) if b["currency"] == "usd") / 100
                return EarningsReport(name, total_usd=avail + pending, available_usd=avail,
                                      pending_usd=pending, raw=data)
            return EarningsReport(name, status="not_available")
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    if name == "Razorpay":
        return EarningsReport(name, status="not_available",
                              error="Razorpay balance API not implemented")

    if name == "Wise":
        return EarningsReport(name, status="not_available",
                              error="Wise balance API not implemented")

    if name == "PayPal":
        return EarningsReport(name, status="not_available",
                              error="PayPal balance requires additional scopes")

    # ── Microtasks ──────────────────────────────────────────────
    if name == "Toloka":
        return EarningsReport(name, status="not_available",
                              error="Toloka earnings not exposed via API")

    if name == "Clickworker":
        return EarningsReport(name, status="not_available",
                              error="Clickworker earnings not exposed via API")

    if name == "Remotasks":
        return EarningsReport(name, status="not_available",
                              error="Remotasks earnings not exposed via API")

    # ── Social / API (no earnings) ──────────────────────────────
    if name in ("Reddit", "Twitter", "GitHub"):
        return EarningsReport(name, status="not_available", error="Not an earning platform")

    # ── Crypto / Trading platforms (have wallet balance, not earnings) ──
    if name == "Binance":
        try:
            bals = p.get_balances()
            total_usd = 0.0
            for asset, qty in bals.items():
                if asset in ("USDT", "USDC", "BUSD", "USDD"):
                    total_usd += qty
                elif asset == "BTC":
                    total_usd += qty * 60000
                elif asset == "ETH":
                    total_usd += qty * 3000
            return EarningsReport(name, total_usd=total_usd, available_usd=total_usd, raw=bals)
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))
    if name == "Coinbase":
        return EarningsReport(name, status="not_available",
                              error="Coinbase balance via API not implemented")
    if name == "KuCoin":
        try:
            accts = p.get_accounts()
            total_usd = 0.0
            for a in accts:
                bal = float(a.get("balance", 0))
                if bal > 0:
                    curr = a.get("currency", "")
                    if curr in ("USDT", "USDC", "BUSD"):
                        total_usd += bal
                    elif curr == "BTC":
                        total_usd += bal * 60000
                    elif curr == "ETH":
                        total_usd += bal * 3000
            return EarningsReport(name, total_usd=total_usd, available_usd=total_usd, raw=accts)
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))
    if name == "Bybit":
        try:
            wallet = p.get_wallet_balance()
            total_usd = 0.0
            if wallet:
                coins = wallet.get("list", [{}])[0].get("coin", [])
                for c in coins:
                    bal = float(c.get("walletBalance", 0))
                    curr = c.get("coin", "")
                    if curr in ("USDT", "USDC", "BUSD"):
                        total_usd += bal
                    elif curr == "BTC":
                        total_usd += bal * 60000
                    elif curr == "ETH":
                        total_usd += bal * 3000
            return EarningsReport(name, total_usd=total_usd, available_usd=total_usd, raw=wallet)
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))
    if name == "OKX":
        try:
            bal_data = p.get_balance()
            total_usd = 0.0
            if bal_data:
                details = bal_data.get("details", [])
                for d in details:
                    bal = float(d.get("cashBal", 0))
                    curr = d.get("ccy", "")
                    if curr in ("USDT", "USDC", "BUSD"):
                        total_usd += bal
                    elif curr == "BTC":
                        total_usd += bal * 60000
                    elif curr == "ETH":
                        total_usd += bal * 3000
            return EarningsReport(name, total_usd=total_usd, available_usd=total_usd, raw=bal_data)
        except Exception as e:
            return EarningsReport(name, status="error", error=str(e))

    # ── Fallback ────────────────────────────────────────────────
    return EarningsReport(name, status="not_available",
                          error=f"No earnings adapter for {name}")


# ═══════════════════════════════════════════════════════════════
#  EARNINGS MONITOR
# ═══════════════════════════════════════════════════════════════

class EarningsMonitor:
    """Check earnings/balance on every platform and produce a consolidated report."""

    EARNING_PLATFORM_NAMES = {
        # Pure earning platforms (generate revenue directly)
        "Shutterstock", "AdobeStock", "Pond5",          # Stock media
        "Upwork", "Freelancer",                           # Freelancing
        "Gumroad", "Etsy", "eBay",                        # Digital products / e-commerce
        "Shopify", "Printful", "Printify",                # E-commerce / POD
        "YouTube", "Medium",                               # Content
        "Toloka", "Clickworker", "Remotasks",              # Microtasks
    }

    WITHDRAWAL_PLATFORM_NAMES = {
        "Stripe", "Razorpay", "Wise", "PayPal",
    }

    TRADING_PLATFORM_NAMES = {
        "Binance", "Coinbase", "KuCoin", "Bybit", "OKX",
    }

    def __init__(self, platforms: List):
        self.platforms = {p.NAME: p for p in platforms}
        self.reports: Dict[str, EarningsReport] = {}

    def check_all(self) -> List[EarningsReport]:
        """Check earnings on every available platform."""
        reports = []
        for name in sorted(self.platforms):
            platform = self.platforms[name]
            try:
                report = get_platform_earnings(platform)
            except Exception as e:
                report = EarningsReport(name, status="error", error=str(e))
            self.reports[name] = report
            reports.append(report)
            if report.status == "ok":
                log.info(f"  {name:<22} ${report.total_usd:>8.2f}  "
                         f"(avail: ${report.available_usd:.2f}, pend: ${report.pending_usd:.2f})")
            elif report.status == "not_available":
                log.info(f"  {name:<22} --- no earnings API available")
            else:
                log.warning(f"  {name:<22} ERROR: {report.error}")
        self._save_report()
        return reports

    def check_platform(self, name: str) -> Optional[EarningsReport]:
        """Check a single platform's earnings."""
        platform = self.platforms.get(name)
        if not platform:
            return None
        try:
            report = get_platform_earnings(platform)
        except Exception as e:
            report = EarningsReport(name, status="error", error=str(e))
        self.reports[name] = report
        return report

    def total_earned(self) -> float:
        """Sum of all earnings across all platforms."""
        return sum(r.total_usd for r in self.reports.values() if r.status == "ok")

    def total_available(self) -> float:
        """Sum of available (not pending) earnings."""
        return sum(r.available_usd for r in self.reports.values() if r.status == "ok")

    def total_pending(self) -> float:
        """Sum of pending earnings."""
        return sum(r.pending_usd for r in self.reports.values() if r.status == "ok")

    def earning_platforms_earnings(self) -> Dict[str, EarningsReport]:
        """Earnings from pure earning platforms (stock media, freelance, ecommerce, content, microtasks)."""
        return {n: r for n, r in self.reports.items()
                if n in self.EARNING_PLATFORM_NAMES and r.status == "ok"}

    def withdrawal_platform_balances(self) -> Dict[str, EarningsReport]:
        """Balances from payment/withdrawal platforms."""
        return {n: r for n, r in self.reports.items()
                if n in self.WITHDRAWAL_PLATFORM_NAMES and r.status == "ok"}

    def trading_platform_balances(self) -> Dict[str, EarningsReport]:
        """Balances from trading platforms."""
        return {n: r for n, r in self.reports.items()
                if n in self.TRADING_PLATFORM_NAMES and r.status == "ok"}

    def summary(self) -> Dict[str, Any]:
        """Produce a summary dict."""
        earning_reports = self.earning_platforms_earnings()
        withdraw_reports = self.withdrawal_platform_balances()
        trade_reports = self.trading_platform_balances()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_earned_all": self.total_earned(),
            "total_available": self.total_available(),
            "total_pending": self.total_pending(),
            "earning_platforms": {
                "count": len(earning_reports),
                "total": sum(r.total_usd for r in earning_reports.values()),
                "available": sum(r.available_usd for r in earning_reports.values()),
                "platforms": {n: {"total_usd": r.total_usd, "available_usd": r.available_usd,
                                  "pending_usd": r.pending_usd} for n, r in earning_reports.items()},
            },
            "withdrawal_platforms": {
                "count": len(withdraw_reports),
                "total": sum(r.total_usd for r in withdraw_reports.values()),
                "available": sum(r.available_usd for r in withdraw_reports.values()),
                "platforms": {n: {"total_usd": r.total_usd, "available_usd": r.available_usd} for n, r in withdraw_reports.items()},
            },
            "trading_platforms": {
                "count": len(trade_reports),
                "total": sum(r.total_usd for r in trade_reports.values()),
                "platforms": {n: {"total_usd": r.total_usd} for n, r in trade_reports.items()},
            },
        }

    def print_summary(self):
        """Print a human-readable summary."""
        s = self.summary()
        sep = "─" * 50
        print(f"\n{sep}")
        print(f"  📊  EARNINGS SUMMARY  ({datetime.now().date()})")
        print(sep)
        print(f"  {'Total earned (all platforms):':<35} ${s['total_earned_all']:>8.2f}")
        print(f"  {'Available for withdrawal:':<35} ${s['total_available']:>8.2f}")
        print(f"  {'Pending:':<35} ${s['total_pending']:>8.2f}")
        print()
        print(f"  EARNING PLATFORMS ({s['earning_platforms']['count']}):")
        for name, r in sorted(s['earning_platforms']['platforms'].items()):
            print(f"    {name:<22}  ${r['total_usd']:>8.2f}  (avail: ${r['available_usd']:.2f})")
        print(f"    {'─' * 30}")
        print(f"    {'Total':<22}  ${s['earning_platforms']['total']:>8.2f}")
        print()
        print(f"  WITHDRAWAL PLATFORMS ({s['withdrawal_platforms']['count']}):")
        for name, r in sorted(s['withdrawal_platforms']['platforms'].items()):
            print(f"    {name:<22}  ${r['total_usd']:>8.2f}  (avail: ${r['available_usd']:.2f})")
        print()
        print(f"  TRADING PLATFORMS ({s['trading_platforms']['count']}):")
        for name, r in sorted(s['trading_platforms']['platforms'].items()):
            print(f"    {name:<22}  ${r['total_usd']:>8.2f}")
        print(sep)
        print(f"  {'Earnings (earners)':<35} ${s['earning_platforms']['total']:>8.2f}")
        print(f"  {'Available (withdrawal)':<35} ${s['withdrawal_platforms']['available']:>8.2f}")
        print(f"  {'Trading balance':<35} ${s['trading_platforms']['total']:>8.2f}")
        print(sep)

    def _save_report(self):
        """Save earnings report to JSON file."""
        data = {name: asdict(r) for name, r in self.reports.items()}
        with open(EARNINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.now(timezone.utc).isoformat(), "reports": data}, f, indent=2, default=str)
        log.info(f"Report saved to {EARNINGS_FILE}")


# ═══════════════════════════════════════════════════════════════
#  TRADING BALANCE TRACKER
# ═══════════════════════════════════════════════════════════════

class TradingBalanceTracker:
    """
    Tracks a virtual trading balance that grows as earnings are withdrawn
    and shrinks as trades are executed.
    """

    def __init__(self):
        self._balance = 0.0
        self._total_deposited = 0.0
        self._total_traded = 0.0
        self._load()

    def _load(self):
        if Path(TRADE_BALANCE_FILE).exists():
            try:
                with open(TRADE_BALANCE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                    self._balance = float(data.get("balance", 0))
                    self._total_deposited = float(data.get("total_deposited", 0))
                    self._total_traded = float(data.get("total_traded", 0))
            except Exception:
                pass

    def _save(self):
        with open(TRADE_BALANCE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "balance": self._balance,
                "total_deposited": self._total_deposited,
                "total_traded": self._total_traded,
                "updated": datetime.now(timezone.utc).isoformat(),
            }, f, indent=2)

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def total_deposited(self) -> float:
        return self._total_deposited

    @property
    def total_traded(self) -> float:
        return self._total_traded

    def deposit(self, amount: float):
        """Add funds to the trading balance (simulates bank deposit to exchange)."""
        self._balance += amount
        self._total_deposited += amount
        self._save()
        log.info(f"[TradingBalance] Deposited ${amount:.2f} --- balance: ${self._balance:.2f}")

    def withdraw_trade(self, amount: float):
        """Deduct funds (simulates trade execution spending)."""
        self._balance -= amount
        self._total_traded += amount
        self._save()
        log.info(f"[TradingBalance] Trade spent ${amount:.2f} --- balance: ${self._balance:.2f}")

    def has_sufficient_balance(self, min_balance: float = None) -> bool:
        threshold = min_balance if min_balance is not None else EarningsConfig.MIN_TRADE_BALANCE
        return self._balance >= threshold


# ═══════════════════════════════════════════════════════════════
#  DEPOSIT PIPELINE  ---  auto-withdraw earnings -> trading balance
# ═══════════════════════════════════════════════════════════════

class DepositPipeline:
    """
    Automated pipeline:
      1. Check earnings from all earning platforms
      2. If total >= MIN_WITHDRAWAL_THRESHOLD, initiate withdrawals
      3. Track withdrawn amounts in TradingBalanceTracker
      4. If trading balance >= MIN_TRADE_BALANCE, signal ready for trading
    """

    def __init__(self, monitor: EarningsMonitor, tracker: TradingBalanceTracker = None):
        self.monitor = monitor
        self.tracker = tracker or TradingBalanceTracker()
        self.log = logging.getLogger("DepositPipeline")

    def run(self, force_withdraw: bool = False) -> Dict[str, Any]:
        """
        Execute the deposit pipeline:
          - Check earnings
          - Auto-withdraw if threshold met
          - Return status
        """
        self.log.info("═══ Deposit Pipeline ═══")
        self.monitor.check_all()
        summary = self.monitor.summary()

        available = summary["withdrawal_platforms"]["available"]
        earning_available = summary["earning_platforms"]["available"]
        threshold = EarningsConfig.MIN_WITHDRAWAL_THRESHOLD

        self.log.info(f"Earning platforms available: ${earning_available:.2f}")
        self.log.info(f"Withdrawal platforms available: ${available:.2f}")
        self.log.info(f"Withdrawal threshold: ${threshold:.2f}")

        result = {
            "status": "idle",
            "total_available": available,
            "earning_available": earning_available,
            "threshold": threshold,
            "withdrawals": [],
        }

        # Try to withdraw from payment platforms if there's available balance
        if available >= threshold or force_withdraw:
            withdrawn = self._auto_withdraw()
            result["withdrawals"] = withdrawn
            if withdrawn:
                result["status"] = "withdrawn"
                total = sum(w["amount"] for w in withdrawn)
                deposit_amt = total * 0.2
                self.log.info(f"Withdrew ${total:.2f} --- crediting 20% (${deposit_amt:.2f}) to trading balance")
                self.tracker.deposit(deposit_amt)
        else:
            self.log.info(f"Available ${available:.2f} < threshold ${threshold:.2f} --- skipping withdrawal")

        # Report trading readiness
        trade_ready = self.tracker.has_sufficient_balance()
        result["trading_balance"] = self.tracker.balance
        result["trade_ready"] = trade_ready
        self.log.info(f"Trading balance: ${self.tracker.balance:.2f} {'OK READY' if trade_ready else 'XX below min'}")

        return result

    def _auto_withdraw(self) -> List[Dict]:
        """Attempt withdrawals from available payment platforms."""
        withdrawals = []
        preference = EarningsConfig.WITHDRAW_PREFERENCE

        # Priority order based on preference
        order = ["Stripe", "Razorpay", "Wise", "PayPal"]
        if preference != "any":
            order = [preference] + [p for p in order if p != preference]

        for name in order:
            platform = self.monitor.platforms.get(name)
            if not platform:
                continue
            report = self.monitor.reports.get(name)
            if not report or report.status != "ok" or report.available_usd < 5.0:
                continue

            try:
                wd = self._withdraw_from(platform, name, report.available_usd)
                if wd:
                    withdrawals.append(wd)
                    break  # Withdraw from one platform per run
            except Exception as e:
                self.log.error(f"Withdrawal from {name} failed: {e}")

        return withdrawals

    def _withdraw_from(self, platform, name: str, amount: float) -> Optional[Dict]:
        """Execute withdrawal on a specific payment platform."""
        amount = min(amount, float(os.getenv("MAX_WITHDRAW_USD", "1000.0")))

        self.log.info(f"Attempting withdrawal of ${amount:.2f} from {name}...")

        if name == "Stripe" and hasattr(platform, "create_payout"):
            destination = EarningsConfig.WITHDRAW_BANK_ACCOUNT or None
            result = platform.create_payout(amount, destination)
            self.log.info(f"Stripe payout: {result}")
            return {"platform": name, "amount": amount, "result": result}

        elif name == "Razorpay" and hasattr(platform, "create_payout"):
            amount_inr = amount * 85.0  # approximate USD->INR
            result = platform.create_payout(amount_inr)
            self.log.info(f"Razorpay payout: {result}")
            return {"platform": name, "amount": amount, "result": result}

        elif name == "Wise" and hasattr(platform, "create_transfer_quote"):
            result = platform.create_transfer_quote(source="USD", target="INR", amount=amount)
            self.log.info(f"Wise transfer: {result}")
            return {"platform": name, "amount": amount, "result": result}

        elif name == "PayPal" and hasattr(platform, "create_payout"):
            dest = EarningsConfig.WITHDRAW_EMAIL or "your@email.com"
            result = platform.create_payout(amount, dest)
            self.log.info(f"PayPal payout: {result}")
            return {"platform": name, "amount": amount, "result": result}

        self.log.warning(f"No withdrawal method available for {name}")
        return None


# ═══════════════════════════════════════════════════════════════
#  EARN-FIRST PRIORITY QUEUE
# ═══════════════════════════════════════════════════════════════

# Priority order: platforms processed in this order
EARN_FIRST_ORDER = [
    # PHASE 1: Pure Earning Platforms (quick wins first)
    "Shutterstock",              # Stock media --- upload once, earn forever
    "AdobeStock",                # Stock media
    "Pond5",                     # Stock media
    "Toloka",                    # Microtasks --- fast earnings
    "Clickworker",               # Microtasks
    "Remotasks",                 # Microtasks
    "Gumroad",                   # Digital products --- passive income
    "Etsy",                      # E-commerce
    "eBay",                      # Marketplace
    "Medium",                    # Content --- Partner Program
    "YouTube",                   # Content --- ad revenue
    "Printful",                  # Print-on-demand
    "Printify",                  # Print-on-demand
    "Shopify",                   # E-commerce store
    "Upwork",                    # Freelancing --- higher value
    "Freelancer",                # Freelancing
    "Reddit",                    # Gig hunting

    # PHASE 2: Withdrawal Platforms (consolidate earnings)
    "Stripe",
    "Razorpay",
    "Wise",
    "PayPal",

    # PHASE 3: Trading Platforms (only if earnings threshold met)
    "Binance",
    "Coinbase",
    "KuCoin",
    "Bybit",
    "OKX",

    # API / Social (no money, but API keys useful)
    "OpenAI",
    "Anthropic",
    "Replicate",
    "RapidAPI",
]


class EarnFirstPriorityQueue:
    """
    Processes platforms in priority order:
      1. All earning platforms first (Phase 1)
      2. If earnings >= EARNINGS_TRADE_THRESHOLD, process withdrawal platforms (Phase 2)
      3. If trading balance >= MIN_TRADE_BALANCE, process trading platforms (Phase 3)
      4. Finally, process API / social platforms
    """

    def __init__(self, platforms: List, pipeline: DepositPipeline = None, monitor: EarningsMonitor = None):
        self.platforms = {p.NAME: p for p in platforms}
        self.pipeline = pipeline
        self.monitor = monitor or EarningsMonitor(platforms)
        self.log = logging.getLogger("PriorityQueue")

    def run_all(self, force_earnings_check: bool = True) -> Dict[str, Any]:
        """Run all platforms in earn-first priority order."""
        start = datetime.now()
        self.log.info(f"═══ Earn-First Priority Queue ═══")
        self.log.info(f"Start: {start:%Y-%m-%d %H:%M:%S}")

        # Step 1: Check overall earnings
        if force_earnings_check:
            self.log.info("Phase 0: Checking earnings across all platforms...")
            self.monitor.check_all()
            self.monitor.print_summary()

        total_earnings = self.monitor.total_earned()
        total_available = self.monitor.total_available()
        earnings_threshold = EarningsConfig.EARNINGS_TRADE_THRESHOLD
        min_trade_balance = EarningsConfig.MIN_TRADE_BALANCE

        self.log.info(f"Total earnings: ${total_earnings:.2f}")
        self.log.info(f"Trade threshold: ${earnings_threshold:.2f}")
        self.log.info(f"Min trade balance: ${min_trade_balance:.2f}")

        trade_unlocked = total_earnings >= earnings_threshold

        # Step 2: Process platforms in priority order
        results = {}
        phase1_done = False
        phase2_done = False
        phase3_done = False

        for name in EARN_FIRST_ORDER:
            platform = self.platforms.get(name)
            if not platform:
                continue

            # Determine phase
            is_earning = name in EarningsMonitor.EARNING_PLATFORM_NAMES
            is_withdrawal = name in EarningsMonitor.WITHDRAWAL_PLATFORM_NAMES
            is_trading = name in EarningsMonitor.TRADING_PLATFORM_NAMES

            # Skip trading if threshold not met
            if is_trading and not trade_unlocked:
                self.log.info(f"  [{name}] SKIP --- earnings ${total_earnings:.2f} < threshold ${earnings_threshold:.2f}")
                results[name] = {"status": "skipped", "reason": "earnings threshold not met"}
                continue

            # Mark phases as we encounter them
            if is_earning and not phase1_done:
                self.log.info("── Phase 1: Earning Platforms ──")
                phase1_done = True
            elif is_withdrawal and not phase2_done:
                self.log.info("── Phase 2: Withdrawal Platforms ──")
                phase2_done = True
            elif is_trading and not phase3_done:
                self.log.info("── Phase 3: Trading Platforms ──")
                phase3_done = True

            # Run the platform
            self.log.info(f"  ▶ {name}")
            try:
                result = platform.run()
                results[name] = {"status": "ok", "result": str(result)[:200] if result else None}
            except Exception as e:
                self.log.error(f"  XX {name}: {e}")
                results[name] = {"status": "error", "error": str(e)}

            time.sleep(random.uniform(0.5, 2.0))

        # Step 3: Run deposit pipeline if applicable
        if self.pipeline:
            self.log.info("── Deposit Pipeline ──")
            pipeline_result = self.pipeline.run()
            results["__pipeline__"] = pipeline_result

        # Summary
        elapsed = datetime.now() - start
        self.log.info("═" * 50)
        ok_count = sum(1 for r in results.values() if isinstance(r, dict) and r.get("status") == "ok")
        error_count = sum(1 for r in results.values() if isinstance(r, dict) and r.get("status") == "error")
        self.log.info(f"Done in {elapsed}. {ok_count} OK, {error_count} errors.")

        return {
            "results": results,
            "total_earnings": total_earnings,
            "trade_unlocked": trade_unlocked,
            "elapsed_seconds": elapsed.total_seconds(),
        }


# ═══════════════════════════════════════════════════════════════
#  CONVENIENCE: standalone entry point
# ═══════════════════════════════════════════════════════════════

def run_standalone(platforms: List = None, action: str = "check"):
    """
    Run the earnings engine standalone (outside the MoneyBot orchestrator).

    Args:
        platforms: list of platform instances
        action: "check" | "withdraw" | "priority"
    """
    if not platforms:
        print("No platforms provided.")
        return

    monitor = EarningsMonitor(platforms)
    tracker = TradingBalanceTracker()
    pipeline = DepositPipeline(monitor, tracker)
    queue = EarnFirstPriorityQueue(platforms, pipeline, monitor)

    if action == "check":
        monitor.check_all()
        monitor.print_summary()
    elif action == "withdraw":
        result = pipeline.run(force_withdraw=True)
        print(f"Pipeline result: {json.dumps(result, indent=2, default=str)}")
    elif action == "priority":
        result = queue.run_all()
        print(f"Queue result: {json.dumps(result, indent=2, default=str)}")
    else:
        print(f"Unknown action: {action}. Use: check, withdraw, priority")
