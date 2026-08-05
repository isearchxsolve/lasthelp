import pytest
import sys
import os

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from tools import (
    calculate_cost,
    truncate_context,
)

def test_calculate_cost():
    # gpt-4o: input=0.0025/1k, output=0.01/1k.
    # tokens = 3000 -> 1000 input, 2000 output.
    # input cost: 1 * 0.0025 = 0.0025
    # output cost: 2 * 0.01 = 0.02
    # total: 0.0225
    assert calculate_cost(3000, "gpt-4o") == 0.0225

    # Unknown model defaults to gpt-4o-mini: input=0.00015/1k, output=0.0006/1k
    # tokens = 3000 -> 1000 input, 2000 output.
    # input cost: 1 * 0.00015 = 0.00015
    # output cost: 2 * 0.0006 = 0.0012
    # total: 0.00135 -> Python rounds to 0.0013
    assert calculate_cost(3000, "unknown-model") == 0.0013

def test_truncate_context():
    context = "abcdefghij" * 10  # 100 chars
    # Under limit
    assert truncate_context(context, max_chars=120) == context

    # Over limit
    # max_chars = 30 -> head = 10, tail = 10
    truncated = truncate_context(context, max_chars=30)
    assert len(truncated) == 20 + len("\n\n... [truncated] ...\n\n")
    assert truncated.startswith(context[:10])
    assert truncated.endswith(context[-10:])
