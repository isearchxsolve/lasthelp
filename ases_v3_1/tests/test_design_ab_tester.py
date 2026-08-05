import pytest
import sys
import os
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from design_ab_tester import (
    DesignVariant,
    DesignABTester,
    select_design_spec_with_ab_test,
    select_best_fallback_spec,
)

def test_design_variant():
    v = DesignVariant(
        spec_id="1",
        spec_json={"has_design": True},
        similarity=0.9,
        hit_count=10,
        pass_count=6,
        fail_count=4,
        last_used=datetime.now()
    )
    assert v.pass_rate == 0.6
    
    # Untested variant prior
    v_new = DesignVariant(
        spec_id="2",
        spec_json={"has_design": True},
        similarity=0.9,
        hit_count=0,
        pass_count=0,
        fail_count=0,
        last_used=None
    )
    assert v_new.pass_rate == 0.5

def test_get_current_epsilon():
    tester = DesignABTester(epsilon=0.3, epsilon_decay=0.9, min_epsilon=0.05)
    variants = [
        DesignVariant("1", {}, 0.9, 10, 5, 5, None),
        DesignVariant("2", {}, 0.8, 10, 5, 5, None),
    ]
    # total trials = 20. decay exponent = 20/10 = 2.0.
    # decayed epsilon = 0.3 * (0.9 ** 2) = 0.3 * 0.81 = 0.243
    epsilon = tester._get_current_epsilon(variants)
    assert pytest.approx(epsilon) == 0.243

    # Check min_epsilon bounding
    tester_min = DesignABTester(epsilon=0.3, epsilon_decay=0.1, min_epsilon=0.1)
    epsilon_min = tester_min._get_current_epsilon(variants)
    assert epsilon_min == 0.1

@pytest.mark.asyncio
async def test_select_variant_bandit():
    # Epsilon = 0 -> exploit (highest pass rate)
    tester = DesignABTester(epsilon=0.0)
    mock_pool = AsyncMock()
    
    variants = [
        DesignVariant("1", {"spec_name": "v1"}, 0.9, 10, 8, 2, None), # pass_rate = 0.8
        DesignVariant("2", {"spec_name": "v2"}, 0.8, 10, 9, 1, None), # pass_rate = 0.9
    ]
    
    with patch.object(tester, "_load_variants", return_value=variants):
        spec, spec_id = await tester.select_variant(
            mock_pool, "tenant-1", "Build Form", "React", "exec-123"
        )
        assert spec_id == "2"
        assert spec["spec_name"] == "v2"

@pytest.mark.asyncio
async def test_record_result():
    tester = DesignABTester()
    mock_pool = AsyncMock()
    
    await tester.record_result(mock_pool, "123", passed=True, execution_id="exec-123")
    mock_pool.execute.assert_called_once()
    args = mock_pool.execute.call_args[0]
    assert 123 in args # spec_id as int

@pytest.mark.asyncio
async def test_load_variants():
    tester = DesignABTester()
    mock_pool = AsyncMock()
    
    mock_row = MagicMock()
    row_data = {
        "id": 456,
        "spec_json": '{"has_design": true}',
        "similarity": 0.85,
        "hit_count": 5,
        "pass_count": 3,
        "fail_count": 2,
        "last_used": None
    }
    mock_row.__getitem__.side_effect = lambda key: row_data[key]
    mock_row.get.side_effect = lambda key, default=None: row_data.get(key, default)
    mock_pool.fetch.return_value = [mock_row]
    
    with patch("vector_memory._embed", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = [0.1, 0.2, 0.3]
        variants = await tester._load_variants(mock_pool, "tenant-1", "task", "React")
        assert len(variants) == 1
        assert variants[0].spec_id == "456"
        assert variants[0].spec_json == {"has_design": True}
        assert variants[0].similarity == 0.85

@pytest.mark.asyncio
async def test_select_best_fallback_spec():
    mock_pool = AsyncMock()
    
    mock_row1 = MagicMock()
    row_data1 = {
        "id": 789,
        "spec_json": '{"fallback": true}',
        "similarity": 0.95,
        "hit_count": 10,
        "pass_count": 9,
        "fail_count": 1,
        "last_used": None
    }
    mock_row1.__getitem__.side_effect = lambda key: row_data1[key]
    mock_row1.get.side_effect = lambda key, default=None: row_data1.get(key, default)
    
    mock_pool.fetch.return_value = [mock_row1]

    with patch("vector_memory._embed", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = [0.1]
        spec, spec_id = await select_best_fallback_spec(mock_pool, "tenant-1", "task", "React", "exec-123")
        assert spec_id == "789"
        assert spec == {"fallback": True}
