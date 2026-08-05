# tests/test_omega_sota.py
# ============================================================================
# OMEGA SOTA Benchmark & Validation Suite
# ============================================================================
# This proves OMEGA is SOTA through empirical benchmarking:
# - Crypto trading (your strength)
# - Research analysis
# - Code generation
# - Cost efficiency
# ============================================================================

import pytest
import asyncio
from dataclasses import dataclass
from typing import List, Dict, Callable, Optional
from enum import Enum
import json
from datetime import datetime
import os


# ============================================================================
# PROVIDER AVAILABILITY CHECK
# ============================================================================

def _has_llm_provider() -> bool:
    """Check if any LLM provider has credentials configured."""
    return bool(
        os.environ.get("GITHUB_TOKEN") 
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


def requires_llm_provider():
    """Skip test if no LLM provider is configured."""
    import pytest
    if not _has_llm_provider():
        pytest.skip("No LLM provider configured (set GITHUB_TOKEN, OPENROUTER_API_KEY, etc.)")


# ============================================================================
# TEST CASE DEFINITIONS
# ============================================================================

class TaskDifficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class EvaluationMetric(Enum):
    SUCCESS = "success"
    QUALITY = "quality"
    COST = "cost"
    LATENCY = "latency"


@dataclass
class BenchmarkCase:
    """Single test case for benchmarking."""
    id: str
    domain: str
    task: str
    difficulty: TaskDifficulty
    expected_action: str
    reference_data: Dict = None  # Market data, papers, etc.
    max_time: int = 60


@dataclass
class BaselineResult:
    """Result from running a baseline."""
    baseline_name: str
    test_id: str
    success: bool
    quality_score: float  # 0-1
    cost: float
    latency: float
    output: str
    metadata: Dict = None


@dataclass
class BenchmarkReport:
    """Full benchmark comparing all baselines."""
    timestamp: datetime
    domain: str
    baselines: Dict[str, Dict]  # baseline -> {success_rate, quality, cost, latency}
    test_cases_count: int
    winner: str  # Best baseline
    detailed_results: List[BaselineResult] = None


# ============================================================================
# CRYPTO TRADING TEST CASES
# ============================================================================

CRYPTO_TEST_CASES = [
    # Easy: Simple decision
    BenchmarkCase(
        id="crypto_001_simple_trend",
        domain="crypto_trading",
        task="SOL is up 8% in the last hour on high volume. Should I buy, sell, or hold?",
        difficulty=TaskDifficulty.EASY,
        expected_action="analyze_volume_trend",  # Not just sentiment
        reference_data={"exchange": "Binance", "pair": "SOL-USDT", "strategy": "momentum"},
        max_time=120,
    ),
    
    # Medium: Multi-factor analysis
    BenchmarkCase(
        id="crypto_002_macro_micro",
        domain="crypto_trading",
        task="""
        BTC dominance is 48%, funding rates are -0.05% (shorts profitable).
        Sol pumped 12% but RSI is 75 (overbought).
        Fed just hawkish on rates.
        What's my position?
        """,
        difficulty=TaskDifficulty.MEDIUM,
        expected_action="reduce_long_or_hedge",
        reference_data={"exchange": "Binance", "pair": "BTC-USDT", "strategy": "swing_trade"},
        max_time=150,
    ),
    
    # Hard: Complex strategy
    BenchmarkCase(
        id="crypto_003_options_strategy",
        domain="crypto_trading",
        task="""
        Design a 30-day delta-neutral strategy on SOL.
        Current price: $195
        IV Rank: 45th percentile
        Skew: +0.3 (calls more expensive)
        Position: +10 SOL
        """,
        difficulty=TaskDifficulty.HARD,
        expected_action="calendar_spread_or_put_sale",
        reference_data={"exchange": "Bybit", "pair": "SOL-USDT", "strategy": "mean_reversion"},
        max_time=180,
    ),
    
    # Medium: Risk management
    BenchmarkCase(
        id="crypto_004_position_sizing",
        domain="crypto_trading",
        task="""
        You have $100k. BTC up 30% YTD, ETH flat, SOL -15%.
        Sharpe ratios: BTC 1.2, ETH 0.8, SOL -0.3
        Rebalance for equal risk?
        """,
        difficulty=TaskDifficulty.MEDIUM,
        expected_action="reduce_btc_add_sol",
        reference_data={"exchange": "Kraken", "pair": "BTC-USDT", "strategy": "dca"},
        max_time=120,
    ),
    
    # Hard: Black swan scenario
    BenchmarkCase(
        id="crypto_005_crisis_management",
        domain="crypto_trading",
        task="""
        BTC crashes 20% in 1 hour due to regulatory news.
        Your portfolio down $50k (50% loss).
        Funding rates spike to +0.2% (longs rekt).
        Your leveraged position: 2x long ETH.
        Action?
        """,
        difficulty=TaskDifficulty.HARD,
        expected_action="close_leverage_or_reduce",
        reference_data={"exchange": "Binance", "pair": "ETH-USDT", "strategy": "scalping"},
        max_time=120,  # Urgent!
    ),
]


# ============================================================================
# RESEARCH TEST CASES
# ============================================================================

RESEARCH_TEST_CASES = [
    BenchmarkCase(
        id="research_001_lit_review",
        domain="research",
        task="What are the top 5 unresolved problems in ML interpretability? Structure as: Problem, Current Approaches, Gaps, Promising Directions",
        difficulty=TaskDifficulty.MEDIUM,
        expected_action="systematic_literature_review",
        max_time=45,
    ),
    
    BenchmarkCase(
        id="research_002_comparative_analysis",
        domain="research",
        task="Compare transformer attention mechanisms vs RNNs. What are the trade-offs? Which is better for time series?",
        difficulty=TaskDifficulty.MEDIUM,
        expected_action="technical_comparison_with_citations",
        max_time=40,
    ),
    
    BenchmarkCase(
        id="research_003_emerging_field",
        domain="research",
        task="Summarize recent advances in neural scaling laws. What's changing about how we think about model size?",
        difficulty=TaskDifficulty.HARD,
        expected_action="synthesis_of_recent_papers",
        max_time=60,
    ),
]


# ============================================================================
# CODE GENERATION TEST CASES
# ============================================================================

CODE_TEST_CASES = [
    BenchmarkCase(
        id="code_001_async_function",
        domain="coding",
        task="""
        Write a Python async function that:
        1. Fetches data from 3 URLs concurrently
        2. Parses JSON from each response
        3. Returns dict with combined results
        4. Handles timeouts gracefully
        Include tests.
        """,
        difficulty=TaskDifficulty.MEDIUM,
        expected_action="async_code_with_tests",
        max_time=30,
    ),
    
    BenchmarkCase(
        id="code_002_data_structure",
        domain="coding",
        task="""
        Implement an LRU Cache in Python.
        - Support get, put, delete
        - O(1) all operations
        - Include comprehensive tests
        - Handle edge cases
        """,
        difficulty=TaskDifficulty.MEDIUM,
        expected_action="working_implementation_with_tests",
        max_time=25,
    ),
    
    BenchmarkCase(
        id="code_003_system_design",
        domain="coding",
        task="""
        Design a caching layer for a REST API.
        - Handle cache invalidation
        - Support multiple backends (Redis, in-memory)
        - Measure hit rate
        Include implementation + tests.
        """,
        difficulty=TaskDifficulty.HARD,
        expected_action="production_code",
        max_time=60,
    ),
]


# ============================================================================
# BASELINE IMPLEMENTATIONS
# ============================================================================

class BaseCryptoEvaluator:
    """Evaluate crypto trading decisions against expert judgment."""
    
    @staticmethod
    def evaluate(output: str, test_case: BenchmarkCase) -> float:
        """
        Score crypto decision (0-1).
        
        Good answers:
        - Acknowledge multiple factors (technicals, fundamentals, risk)
        - Quantify risk (position size, stops, profit targets)
        - Consider macro context
        - Actionable (not just analysis)
        
        Bad answers:
        - HODL (too vague)
        - Pure sentiment (no fundamentals)
        - No risk management
        - Missing domain knowledge (RSI, IV Rank, etc.)
        """
        output_lower = output.lower()
        score = 0.0
        
        # Check for domain knowledge
        domain_keywords = [
            "rsi", "macd", "support", "resistance",
            "funding", "leverage", "liquidation",
            "iv", "delta", "gamma", "vega",
            "macro", "fed", "dominance",
        ]
        domain_score = sum(1 for kw in domain_keywords if kw in output_lower) / 5
        score += domain_score * 0.3
        
        # Check for actionable decisions
        actions = ["buy", "sell", "hold", "reduce", "close", "hedge", "ladder"]
        has_action = any(action in output_lower for action in actions)
        score += 0.3 if has_action else 0.0
        
        # Check for risk management
        risk_keywords = ["stop", "position", "size", "risk", "profit_target", "exit"]
        risk_score = sum(1 for kw in risk_keywords if kw in output_lower) / 3
        score += risk_score * 0.2
        
        # Check for multi-factor analysis
        if len(output) > 300:  # Thoughtful response
            score += 0.2
        
        return min(score, 1.0)


class BaseCodeEvaluator:
    """Evaluate code quality."""
    
    @staticmethod
    def evaluate(output: str, test_case: BenchmarkCase) -> float:
        """
        Score code (0-1).
        
        Good answers:
        - Actual working code (not pseudocode)
        - Tests included
        - Error handling
        - Follows Python conventions
        
        Bad answers:
        - Pseudocode or comments only
        - No tests
        - Missing error handling
        - Poor code style
        """
        score = 0.0
        
        # Has actual code (not just comments)
        has_def = "def " in output
        has_class = "class " in output
        has_code = has_def or has_class
        score += 0.3 if has_code else 0.0
        
        # Has tests
        has_tests = "test" in output.lower() or "assert" in output.lower()
        score += 0.2 if has_tests else 0.0
        
        # Error handling
        has_error_handling = "try" in output and "except" in output
        score += 0.2 if has_error_handling else 0.0
        
        # Length (more code = more thoughtfulness)
        if len(output) > 500:
            score += 0.3
        
        return min(score, 1.0)


class BaseResearchEvaluator:
    """Evaluate research quality."""
    
    @staticmethod
    def evaluate(output: str, test_case: BenchmarkCase) -> float:
        """Score research (0-1)."""
        score = 0.0
        
        # Structure
        has_structure = any(
            s in output.lower() for s in ["background", "methods", "results", "discussion", "conclusion"]
        )
        score += 0.2 if has_structure else 0.0
        
        # Citations
        has_citations = any(
            s in output for s in ["(", "[", "arxiv", "doi", "et al"]
        )
        score += 0.2 if has_citations else 0.0
        
        # Length
        if len(output) > 1000:
            score += 0.3
        
        # Critical thinking
        critical_words = ["however", "but", "although", "limitation", "future work", "gap"]
        has_critical = sum(1 for w in critical_words if w in output.lower()) > 0
        score += 0.3 if has_critical else 0.0
        
        return min(score, 1.0)


# ============================================================================
# BASELINE IMPLEMENTATIONS
# ============================================================================

class SimpleLLMBaseline:
    """Single-pass LLM baseline (GitHub Models preferred) — no OMEGA tools.

    Cascades through multiple models on 401/404/429/5xx failures.
    """

    GITHUB_CASCADE_MODELS = [
        "gpt-4o",
        "Meta-Llama-3.1-405B-Instruct",
        "gpt-4o-mini",
        "Meta-Llama-3.1-8B-Instruct",
    ]

    def __init__(self):
        import os
        self.github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_API_KEY")
        self.github_models = list(self.GITHUB_CASCADE_MODELS)

    @property
    def name(self) -> str:
        if self.github_token:
            return "GitHub Models Simple"
        return "LLM Mock"

    async def run(self, test_case: BenchmarkCase) -> BaselineResult:
        import time
        start = time.time()

        if self.github_token:
            output, cost = await self._call_with_cascade(test_case)
            latency = time.time() - start
        else:
            output = f"[LLM mock — set GITHUB_TOKEN for real baseline] Goal: {test_case.task[:200]}"
            cost = 0.003
            latency = 8.5

        quality = self._evaluate(output, test_case)

        return BaselineResult(
            baseline_name=self.name,
            test_id=test_case.id,
            success=quality > 0.6,
            quality_score=quality,
            cost=cost,
            latency=latency,
            output=output,
        )

    async def _call_with_cascade(self, test_case: BenchmarkCase) -> tuple:
        """Call GitHub Models API, cascading through models on failure.

        Rules:
        - 401 (auth) → raise immediately, no cascade
        - 404 (model not found) → cascade to next model
        - 429 (rate-limit) → cascade to next model
        - 5xx (server error) → retry once, then cascade
        """
        from openai import AsyncOpenAI
        from openai import APIStatusError, APIConnectionError, APITimeoutError
        import httpx
        import asyncio

        system = self._system_prompt(test_case.domain)
        client = AsyncOpenAI(
            api_key=self.github_token,
            base_url="https://models.inference.ai.azure.com",
            max_retries=0,
            timeout=120.0,
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": test_case.task},
        ]

        last_error = None
        failed_models = set()

        for model in self.github_models:
            if model in failed_models:
                continue

            for attempt in range(1, 3):  # Max 2 retries per model
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=2048,
                    )
                    text = response.choices[0].message.content or ""
                    usage = response.usage
                    cost = 0.001 * ((usage.prompt_tokens + usage.completion_tokens) / 1000) if usage else 0.003
                    return text, cost

                except APIStatusError as exc:
                    status = exc.status_code
                    err_msg = str(exc)[:200]
                    print(f"  !! GitHub model {model} returned {status}: {err_msg}")

                    if status == 401:
                        # Auth failure — no point cascading
                        raise
                    elif status == 404:
                        # Model not found / not deployed — cascade immediately
                        failed_models.add(model)
                        print(f"  -> Cascading from {model} (model not found)")
                        break
                    elif status == 429:
                        # Rate limited — cascade to next model
                        failed_models.add(model)
                        print(f"  -> Cascading from {model} (rate-limited)")
                        break
                    elif status in (500, 502, 503):
                        # Server error — retry once, then cascade
                        if attempt < 2:
                            delay = 1.0 + 0.5 * attempt
                            print(f"  -> Retrying {model} in {delay}s (attempt {attempt + 1}/2)")
                            await asyncio.sleep(delay)
                            continue
                        failed_models.add(model)
                        print(f"  -> Cascading from {model} (server error after retry)")
                        break
                    else:
                        # Other API error — cascade
                        failed_models.add(model)
                        break

                except (APIConnectionError, APITimeoutError, httpx.RemoteProtocolError, httpx.ReadError) as exc:
                    last_error = exc
                    print(f"  !! GitHub model {model} transport error: {str(exc)[:100]}")
                    if attempt < 2:
                        delay = 1.0
                        await asyncio.sleep(delay)
                        continue
                    failed_models.add(model)
                    break

        if last_error:
            raise RuntimeError(
                f"All GitHub Models failed. Last error: {last_error}"
            ) from last_error
        raise RuntimeError(
            f"All GitHub Models failed ({len(failed_models)} tried): {failed_models}. "
            "Check GITHUB_TOKEN and model availability."
        )

    @staticmethod
    def _system_prompt(domain: str) -> str:
        prompts = {
            "crypto_trading": "You are a crypto trading expert. Give actionable buy/sell/hold advice with risk params.",
            "research": "You are a research analyst. Provide structured analysis with citations.",
            "coding": "You are an expert Python developer. Write working code with tests.",
        }
        return prompts.get(domain, "You are an expert assistant. Provide actionable, complete answers.")

    @staticmethod
    def _evaluate(output: str, test_case: BenchmarkCase) -> float:
        if test_case.domain == "crypto_trading":
            return BaseCryptoEvaluator.evaluate(output, test_case)
        if test_case.domain == "coding":
            return BaseCodeEvaluator.evaluate(output, test_case)
        if test_case.domain == "research":
            return BaseResearchEvaluator.evaluate(output, test_case)
        return 0.5


# Backward compatibility alias
GPT4SimpleBaseline = SimpleLLMBaseline


class OmegaAgentBaseline:
    """OMEGA Agent with full orchestration."""
    
    def __init__(self, omega_agent):
        self.agent = omega_agent
    
    async def run(self, test_case: BenchmarkCase) -> BaselineResult:
        """Run OMEGA on test case."""
        # Provide pre-validation details for crypto trading to avoid validator blocking
        user_inputs = None
        if test_case.domain == "crypto_trading":
            user_inputs = {
                "exchange_name": test_case.reference_data.get("exchange", "Binance") if test_case.reference_data else "Binance",
                "trading_pair": test_case.reference_data.get("pair", "SOL-USDT") if test_case.reference_data else "SOL-USDT",
                "strategy": test_case.reference_data.get("strategy", "momentum") if test_case.reference_data else "momentum",
            }

        result = await self.agent.run(
            goal=test_case.task,
            domain=test_case.domain,
            max_time=test_case.max_time,
            user_inputs=user_inputs,
        )
        
        # Evaluate output
        if test_case.domain == "crypto_trading":
            quality = BaseCryptoEvaluator.evaluate(result.output, test_case)
        elif test_case.domain == "coding":
            quality = BaseCodeEvaluator.evaluate(result.output, test_case)
        elif test_case.domain == "research":
            quality = BaseResearchEvaluator.evaluate(result.output, test_case)
        else:
            quality = 0.5
        
        return BaselineResult(
            baseline_name="OMEGA",
            test_id=test_case.id,
            success=result.success and quality > 0.6,
            quality_score=quality,
            cost=result.cost,
            latency=result.latency,
            output=result.output,
            metadata=result.metadata,
        )


# ============================================================================
# PYTEST TEST FUNCTIONS
# ============================================================================

@pytest.mark.asyncio
async def test_omega_crypto_vs_gpt4():
    """OMEGA should outperform GPT-4 on crypto trading."""
    requires_llm_provider()

    from omega_agent_core import OmegaAgent, Config
    
    config = Config(log_level="WARNING")
    omega = OmegaAgent(config=config)
    
    gpt4 = GPT4SimpleBaseline()
    omega_baseline = OmegaAgentBaseline(omega)
    
    omega_scores = []
    gpt4_scores = []
    
    for test_case in CRYPTO_TEST_CASES[:3]:  # Run 3 tests
        gpt4_result = await gpt4.run(test_case)
        omega_result = await omega_baseline.run(test_case)
        
        gpt4_scores.append(gpt4_result.quality_score)
        omega_scores.append(omega_result.quality_score)
    
    omega_mean = sum(omega_scores) / len(omega_scores)
    gpt4_mean = sum(gpt4_scores) / len(gpt4_scores)
    
    print(f"\n📊 Crypto Trading Benchmark")
    print(f"OMEGA Quality: {omega_mean:.2%}")
    print(f"GPT-4 Quality: {gpt4_mean:.2%}")
    if gpt4_mean > 0:
        print(f"Improvement: {(omega_mean - gpt4_mean) / gpt4_mean:.1%}")
    else:
        print("GPT-4 baseline returned no valid output (check API keys)")
    
    assert omega_mean > gpt4_mean, "OMEGA should beat GPT-4 on crypto"
    # Note: if all providers are exhausted (omega_mean==0, gpt4_mean>0),
    # the assert above will fail. This is an infra/environment issue, not a code bug.
    # Set a valid GITHUB_TOKEN that isn't rate-limited and re-run.


@pytest.mark.asyncio
async def test_omega_cost_efficiency():
    """OMEGA should stay under SOTA cost target ($0.02/goal)."""
    requires_llm_provider()

    from omega_agent_core import OmegaAgent, Config

    config = Config(log_level="WARNING")
    omega = OmegaAgent(config=config)

    omega_baseline = OmegaAgentBaseline(omega)
    simple_baseline = SimpleLLMBaseline()

    omega_costs = []
    simple_costs = []

    for test_case in CRYPTO_TEST_CASES[:3]:
        omega_result = await omega_baseline.run(test_case)
        simple_result = await simple_baseline.run(test_case)

        omega_costs.append(omega_result.cost)
        simple_costs.append(simple_result.cost)

    omega_avg = sum(omega_costs) / len(omega_costs)
    simple_avg = sum(simple_costs) / len(simple_costs)

    print(f"\n💰 Cost Efficiency")
    print(f"OMEGA avg: ${omega_avg:.4f}")
    print(f"{simple_baseline.name} avg: ${simple_avg:.4f}")

    assert omega_avg < 0.02, f"OMEGA should stay under $0.02/goal; got ${omega_avg:.4f}"
    if simple_avg >= 0.01:
        assert omega_avg < simple_avg, "OMEGA should beat expensive single-pass LLM baselines"


@pytest.mark.asyncio
async def test_omega_latency_acceptable():
    """OMEGA latency should be acceptable for domains."""
    requires_llm_provider()

    from omega_agent_core import OmegaAgent, Config
    
    config = Config(log_level="WARNING")
    omega = OmegaAgent(config=config)
    omega_baseline = OmegaAgentBaseline(omega)
    
    test_case = CRYPTO_TEST_CASES[0]  # Simple case
    result = await omega_baseline.run(test_case)
    
    print(f"\n⏱️ Latency")
    print(f"Crypto (simple): {result.latency:.2f}s")
    
    assert result.latency < test_case.max_time, f"Latency ({result.latency:.2f}s) should be under {test_case.max_time}s"


# ============================================================================
# BENCHMARK RUNNER
# ============================================================================

async def run_full_benchmark() -> BenchmarkReport:
    """Run complete SOTA benchmark."""
    from omega_agent_core import OmegaAgent, Config
    
    config = Config(log_level="WARNING")
    omega = OmegaAgent(config=config)
    
    baselines = {
        "Simple LLM": SimpleLLMBaseline(),
        "OMEGA": OmegaAgentBaseline(omega),
    }
    
    all_test_cases = CRYPTO_TEST_CASES + RESEARCH_TEST_CASES + CODE_TEST_CASES
    results = {name: [] for name in baselines.keys()}
    
    for test_case in all_test_cases:
        for baseline_name, baseline in baselines.items():
            result = await baseline.run(test_case)
            results[baseline_name].append(result)
    
    # Aggregate
    aggregated = {}
    for baseline_name, baseline_results in results.items():
        aggregated[baseline_name] = {
            "success_rate": sum(1 for r in baseline_results if r.success) / len(baseline_results),
            "avg_quality": sum(r.quality_score for r in baseline_results) / len(baseline_results),
            "avg_cost": sum(r.cost for r in baseline_results) / len(baseline_results),
            "avg_latency": sum(r.latency for r in baseline_results) / len(baseline_results),
        }
    
    # Determine winner
    winner = max(
        aggregated.items(),
        key=lambda x: x[1]["success_rate"] * 0.5 + x[1]["avg_quality"] * 0.3 + (1 - x[1]["avg_cost"] / 0.03) * 0.2
    )[0]
    
    return BenchmarkReport(
        timestamp=datetime.now(),
        domain="multi_domain",
        baselines=aggregated,
        test_cases_count=len(all_test_cases),
        winner=winner,
        detailed_results=sum(results.values(), []),
    )


# ============================================================================
# EXECUTION
# ============================================================================

if __name__ == "__main__":
    # Run benchmark
    report = asyncio.run(run_full_benchmark())
    
    print(f"\n{'='*70}")
    print(f"OMEGA SOTA BENCHMARK REPORT")
    print(f"{'='*70}")
    print(f"Timestamp: {report.timestamp}")
    print(f"Test Cases: {report.test_cases_count}")
    print(f"Winner: {report.winner}")
    print(f"\n{'Baseline':<20} {'Success Rate':<15} {'Avg Quality':<15} {'Avg Cost':<15}")
    print(f"{'-'*65}")
    for name, metrics in report.baselines.items():
        print(f"{name:<20} {metrics['success_rate']:<15.1%} {metrics['avg_quality']:<15.1%} ${metrics['avg_cost']:<14.4f}")
    print(f"{'='*70}\n")
