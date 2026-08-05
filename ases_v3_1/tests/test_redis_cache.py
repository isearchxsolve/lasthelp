import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from redis_cache import (
    _make_key,
    cache_get,
    cache_set,
    DEFAULT_TTL_SECONDS,
)

def test_make_key():
    messages = [{"role": "user", "content": "hello"}]
    key1 = _make_key("gpt-4o", messages, 0.7)
    key2 = _make_key("gpt-4o", messages, 0.7)
    assert key1 == key2
    
    # Order of messages or content change should change key
    key3 = _make_key("gpt-4o", [{"role": "user", "content": "hello2"}], 0.7)
    assert key1 != key3

def test_cache_get_miss():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    
    with patch("redis_cache._get_redis", return_value=mock_redis):
        res = cache_get("gpt-4o", [{"role": "user", "content": "hello"}], 0.7)
        assert res is None
        mock_redis.get.assert_called_once()

def test_cache_get_hit():
    mock_redis = MagicMock()
    payload = json.dumps({
        "content": "cached response",
        "input_tokens": 10,
        "output_tokens": 20
    })
    mock_redis.get.return_value = payload
    
    with patch("redis_cache._get_redis", return_value=mock_redis):
        res = cache_get("gpt-4o", [{"role": "user", "content": "hello"}], 0.7)
        assert res == ("cached response", 0, 0)  # Always returns (content, 0, 0) for cached hits
        mock_redis.get.assert_called_once()

def test_cache_set():
    mock_redis = MagicMock()
    
    with patch("redis_cache._get_redis", return_value=mock_redis):
        cache_set(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.7,
            content="response",
            input_tokens=10,
            output_tokens=20,
            call_type="planner"
        )
        
        # Verify setex was called with proper key, ttl (86400 for planner), and serialized payload
        mock_redis.setex.assert_called_once()
        args, kwargs = mock_redis.setex.call_args
        key, ttl, value = args
        assert key.startswith("ases:prompt_cache:")
        assert ttl == DEFAULT_TTL_SECONDS["planner"]
        parsed = json.loads(value)
        assert parsed["content"] == "response"
        assert parsed["input_tokens"] == 10
        assert parsed["output_tokens"] == 20
