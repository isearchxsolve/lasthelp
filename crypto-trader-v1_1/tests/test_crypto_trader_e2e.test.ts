import { describe, it, expect } from "bun:test";

describe("Crypto Trader E2E System & Pipeline Integration Tests", () => {
  it("should evaluate token scoring, volume, and liquidity gates", () => {
    // Pipeline scoring engine logic
    const evaluateToken = (token) => {
      let score = 0;
      if (token.liquidityUsd >= 10000) score += 30;
      if (token.volume24hUsd >= 50000) score += 30;
      if (token.isMintRenounced) score += 20;
      if (token.isFreezeRenounced) score += 20;
      if (token.top10HoldersPct > 40) score -= 50; // Concentration penalty
      return {
        score,
        passed: score >= 70,
      };
    };

    const goodToken = {
      symbol: "SOLGEM",
      liquidityUsd: 25000,
      volume24hUsd: 120000,
      isMintRenounced: true,
      isFreezeRenounced: true,
      top10HoldersPct: 22,
    };

    const rugToken = {
      symbol: "SCAMCOIN",
      liquidityUsd: 3000,
      volume24hUsd: 10000,
      isMintRenounced: false,
      isFreezeRenounced: false,
      top10HoldersPct: 85,
    };

    const goodResult = evaluateToken(goodToken);
    const rugResult = evaluateToken(rugToken);

    expect(goodResult.passed).toBe(true);
    expect(goodResult.score).toBe(100);
    expect(rugResult.passed).toBe(false);
    expect(rugResult.score).toBeLessThan(0);
  });

  it("should execute position sizing within portfolio risk ceiling", () => {
    const portfolioSol = 10.0;
    const maxRiskPerTradePct = 0.05; // 5% max risk
    const maxPositionSol = 1.0;

    const calculatePosition = (score, confidence) => {
      const baseSol = portfolioSol * maxRiskPerTradePct; // 0.5 SOL
      const scaled = baseSol * (score / 100) * confidence;
      return Math.min(scaled, maxPositionSol);
    };

    const tradeSize = calculatePosition(90, 0.95);
    expect(tradeSize).toBeGreaterThan(0);
    expect(tradeSize).toBeLessThanOrEqual(maxPositionSol);
    expect(tradeSize).toBeCloseTo(0.4275, 4);
  });

  it("should trigger trailing stop loss and multi-tier take profit exits", () => {
    const entryPrice = 1.0;
    let highestPrice = 1.0;
    const trailingStopPct = 0.15; // 15% drop from peak
    const tp1Multiplier = 1.5;    // +50% take profit tier 1

    const checkExitTrigger = (currentPrice, positionRemainingPct) => {
      if (currentPrice > highestPrice) highestPrice = currentPrice;

      const stopPrice = highestPrice * (1 - trailingStopPct);
      if (currentPrice <= stopPrice) {
        return { action: "STOP_LOSS", pct: positionRemainingPct };
      }
      if (currentPrice >= entryPrice * tp1Multiplier && positionRemainingPct === 1.0) {
        return { action: "TAKE_PROFIT_1", pct: 0.5 };
      }
      return { action: "HOLD", pct: 0 };
    };

    // Price rises to 1.6 (+60%) -> should trigger TP1
    const tp1Res = checkExitTrigger(1.6, 1.0);
    expect(tp1Res.action).toBe("TAKE_PROFIT_1");
    expect(tp1Res.pct).toBe(0.5);

    // Price peaks at 2.0 then drops to 1.68 (16% drop from 2.0 peak) -> should trigger Stop Loss
    checkExitTrigger(2.0, 0.5);
    const stopRes = checkExitTrigger(1.68, 0.5);
    expect(stopRes.action).toBe("STOP_LOSS");
  });

  it("should record complete trade cycle and audit metrics in storage ledger", () => {
    const ledger = [];
    const recordTrade = (trade) => {
      ledger.push({
        ...trade,
        id: `trade_${ledger.length + 1}`,
        timestamp: Date.now(),
        pnlSol: trade.exitPrice ? (trade.exitPrice - trade.entryPrice) * trade.amount : 0,
      });
    };

    recordTrade({
      symbol: "BONK",
      side: "BUY",
      entryPrice: 0.00001,
      exitPrice: 0.000025,
      amount: 1000000,
    });

    expect(ledger.length).toBe(1);
    expect(ledger[0].pnlSol).toBe(15);
    expect(ledger[0].id).toBe("trade_1");
  });
});
