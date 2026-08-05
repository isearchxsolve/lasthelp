import pytest
import secrets
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

# Add agent_service to path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from auth import (
    _hash_key,
    _generate_key,
    bootstrap_tenant_key,
    require_auth,
    rotate_tenant_key,
    _get_tenant_key_hash,
    _set_tenant_key_hash,
)

def test_hash_key():
    key = "hello_world"
    hashed = _hash_key(key)
    assert len(hashed) == 64
    # Test idempotence
    assert hashed == _hash_key(key)
    assert hashed != _hash_key("hello_world2")

def test_generate_key():
    key1 = _generate_key()
    key2 = _generate_key()
    assert len(key1) == 43
    assert key1 != key2

@pytest.mark.asyncio
async def test_get_set_tenant_key_hash():
    mock_pool = AsyncMock()
    mock_pool.fetchval.return_value = "hashed_val"
    
    val = await _get_tenant_key_hash(mock_pool, "tenant-1")
    assert val == "hashed_val"
    mock_pool.fetchval.assert_called_once_with(
        "SELECT api_key_hash FROM tenants WHERE slug = $1 AND status = 'active'",
        "tenant-1"
    )

    await _set_tenant_key_hash(mock_pool, "tenant-1", "new_hash")
    mock_pool.execute.assert_called_once_with(
        "UPDATE tenants SET api_key_hash = $1 WHERE slug = $2",
        "new_hash",
        "tenant-1"
    )

@pytest.mark.asyncio
async def test_bootstrap_tenant_key():
    mock_pool = AsyncMock()
    
    with patch("auth._generate_key", return_value="plain_key"), \
         patch("auth._hash_key", return_value="hashed_key") as mock_hash:
        key = await bootstrap_tenant_key(mock_pool, "tenant-1")
        assert key == "plain_key"
        mock_hash.assert_called_once_with("plain_key")
        mock_pool.execute.assert_called_once_with(
            "UPDATE tenants SET api_key_hash = $1 WHERE slug = $2",
            "hashed_key",
            "tenant-1"
        )

@pytest.mark.asyncio
async def test_require_auth_missing_key():
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(x_tenant_id="tenant-1", x_api_key="")
    assert exc_info.value.status_code == 401
    assert "Missing x-api-key header" in exc_info.value.detail

@pytest.mark.asyncio
async def test_require_auth_bootstrap():
    mock_pool = AsyncMock()
    mock_pool.fetchval.return_value = None  # tenant exists but key is not set
    
    with patch("auth.get_db_pool", return_value=mock_pool), \
         patch("auth.bootstrap_tenant_key", return_value="bootstrapped_key") as mock_bootstrap:
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(x_tenant_id="tenant-1", x_api_key="incoming_key")
        assert exc_info.value.status_code == 401
        assert "Tenant key just initialised" in exc_info.value.detail
        mock_bootstrap.assert_called_once_with(mock_pool, "tenant-1")

@pytest.mark.asyncio
async def test_require_auth_invalid_key():
    mock_pool = AsyncMock()
    mock_pool.fetchval.return_value = _hash_key("correct_key")
    
    with patch("auth.get_db_pool", return_value=mock_pool):
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(x_tenant_id="tenant-1", x_api_key="wrong_key")
        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail

@pytest.mark.asyncio
async def test_require_auth_success():
    mock_pool = AsyncMock()
    mock_pool.fetchval.return_value = _hash_key("correct_key")
    
    with patch("auth.get_db_pool", return_value=mock_pool):
        result = await require_auth(x_tenant_id="tenant-1", x_api_key="correct_key")
        assert result == "tenant-1"

@pytest.mark.asyncio
async def test_rotate_tenant_key():
    mock_pool = AsyncMock()
    
    with patch("auth.get_db_pool", return_value=mock_pool), \
         patch("auth._generate_key", return_value="rotated_key"), \
         patch("auth._hash_key", return_value="rotated_hash"):
        key = await rotate_tenant_key("tenant-1")
        assert key == "rotated_key"
        mock_pool.execute.assert_called_once_with(
            "UPDATE tenants SET api_key_hash = $1 WHERE slug = $2",
            "rotated_hash",
            "tenant-1"
        )
