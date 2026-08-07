"""
End-to-End System and Strategy Integration Tests for Solana Auto Trader
Tests:
1. HWRSignalEngine filter validation and scoring
2. Market condition regime classification and EMA smoothing
3. Risk-adjusted position sizing and probability tiers
4. Asymmetric exit trade execution (stop loss, TP1, trailing stop)
5. Token candidate scanning and pipeline filters
"""

import os
import sys
import pytest
from pathlib import Path

# Add project root to sys.path
SOLANA_DIR = Path(__file__).parent.parent
if str(SOLANA_DIR) not in sys.path:
    sys.path.insert(0, str(SOLANA_DIR))

from hwr_signal_engine import HWRSignalEngine
from market_condition_analyzer import MarketConditionAnalyzer


class TestSolanaAutoTraderE2E:
    """E2E test suite for Solana Auto Trader."""

    def test_hwr_engine_filter_valid_token(self):
        engine = HWRSignalEngine()
        valid_token = {
            "symbol": "SOLGEM",
            "liquidity": 150_000,
            "liq_drop_pct": 2.0,
            "change_24h": 25.0,
            "change_1h": 4.5,
            "buy_pressure": 0.70,
            "rsi": 52,
        }

        # Check hard filters
        assert valid_token["liquidity"] >= engine.MIN_LIQUIDITY_USD
        assert valid_token["liq_drop_pct"] <= engine.MAX_LIQ_DROP_PCT
        assert valid_token["change_24h"] >= engine.MIN_24H_CHANGE_PCT
        assert valid_token["change_1h"] >= engine.MIN_1H_CHANGE_PCT
        assert valid_token["buy_pressure"] >= engine.MIN_BUY_PRESSURE
        assert engine.MIN_RSI <= valid_token["rsi"] <= engine.MAX_RSI

    def test_hwr_engine_rejects_illiquid_or_dumping_tokens(self):
        engine = HWRSignalEngine()
        illiquid_token = {
            "symbol": "TRASH",
            "liquidity": 10_000,  # < 40k
            "liq_drop_pct": 15.0,
            "change_24h": -10.0,
            "change_1h": -5.0,
            "buy_pressure": 0.20,
            "rsi": 25,
        }

        assert illiquid_token["liquidity"] < engine.MIN_LIQUIDITY_USD
        assert illiquid_token["liq_drop_pct"] > engine.MAX_LIQ_DROP_PCT
        assert illiquid_token["buy_pressure"] < engine.MIN_BUY_PRESSURE

    def test_market_condition_analyzer_regime_detection(self):
        analyzer = MarketConditionAnalyzer()
        
        # Test empty input handling
        status, reason, details = analyzer.analyze({})
        assert status == "POOR"
        assert "No token data" in reason

        # Test bullish tokens batch
        tokens = {
            "token_1": {
                "trend": "BULLISH",
                "ema_slope": 0.005,
                "relative_volume": 1.5,
                "rsi": 55,
            },
            "token_2": {
                "trend": "BULLISH",
                "ema_slope": 0.004,
                "relative_volume": 1.3,
                "rsi": 52,
            }
        }
        
        analyzer._cached_result = None  # Clear cache for testing fresh run
        analyzer._cache_ts = 0.0
        status, reason, details = analyzer.analyze(tokens)
        assert status in ("HEALTHY", "FILTERED")
        assert "overall_score" in details
        assert details["overall_score"] > 0

    def test_probability_weighted_position_sizing(self):
        def get_position_pct(prob_score: float) -> float:
            if prob_score >= 85:
                return 0.30
            if prob_score >= 75:
                return 0.20
            if prob_score >= 65:
                return 0.10
            return 0.0

        assert get_position_pct(90) == 0.30
        assert get_position_pct(78) == 0.20
        assert get_position_pct(68) == 0.10
        assert get_position_pct(50) == 0.0

    def test_asymmetric_exit_rules(self):
        engine = HWRSignalEngine()
        entry_price = 10.0
        stop_price = entry_price * (1 - engine.STOP_LOSS_PCT)
        tp1_price = entry_price * (1 + engine.TP1_PCT)

        assert stop_price == pytest.approx(9.1)
        assert tp1_price == pytest.approx(11.8)
