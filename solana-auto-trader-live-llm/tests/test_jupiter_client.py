from __future__ import annotations

from unittest.mock import Mock, call, patch

import requests

from solana_trading_agent import JupiterClient, TOKENS, TradingMode


def test_live_quote_retries_transient_http_failures() -> None:
    failed = Mock()
    failed.raise_for_status.side_effect = requests.HTTPError("temporary failure")
    succeeded = Mock()
    succeeded.raise_for_status.return_value = None
    succeeded.json.return_value = {"outAmount": "123", "routePlan": []}
    client = JupiterClient(TradingMode.LIVE)

    with patch("solana_trading_agent.requests.get", side_effect=[failed, succeeded]) as get, patch(
        "solana_trading_agent.time.sleep"
    ):
        quote = client.get_quote(TOKENS["SOL"], TOKENS["USDC"], 1_000_000)

    assert quote == {"outAmount": "123", "routePlan": []}
    assert get.call_count == 2
    assert get.call_args_list[0] == call(
        client.QUOTE_URL,
        params={
            "inputMint": TOKENS["SOL"],
            "outputMint": TOKENS["USDC"],
            "amount": 1_000_000,
            "slippageBps": 100,
            "onlyDirectRoutes": False,
        },
        timeout=10,
        headers=None,
    )


def test_price_request_uses_retry_helper_with_headers() -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "pairs": [{"chainId": "solana", "priceUsd": "2.50"}]
    }
    client = JupiterClient(TradingMode.PAPER)

    with patch("solana_trading_agent.requests.get", return_value=response) as get:
        price = client.get_token_price(TOKENS["JUP"])

    assert 2.4975 <= price <= 2.5025
    get.assert_called_once_with(
        f"https://api.dexscreener.com/latest/dex/tokens/{TOKENS['JUP']}",
        params=None,
        timeout=6,
        headers={"User-Agent": "Mozilla/5.0"},
    )
