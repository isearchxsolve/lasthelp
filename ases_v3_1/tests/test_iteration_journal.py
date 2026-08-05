import pytest
import sys
import os
from unittest.mock import AsyncMock, patch

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

# Pre-import agent_loop so it is in sys.modules
import agent_loop

from iteration_journal import (
    ScoredConstraint,
    IterationRecord,
    IterationJournal,
    CONFIRM_WEIGHT,
    VIOLATE_PENALTY,
    MAX_INJECT,
    MIN_SCORE,
)
from models import TenantConfig

def test_scored_constraint_init():
    sc = ScoredConstraint(text="Use React hooks")
    assert sc.text == "Use React hooks"
    assert sc.confirmed == 1
    assert sc.violated == 0
    assert sc.score == 1.0
    assert sc.key == "use react hooks"

@pytest.mark.asyncio
async def test_iteration_journal_record_and_update():
    journal = IterationJournal(task="Build API", tech_stack="FastAPI")
    assert journal.task == "Build API"
    assert journal.tech_stack == "FastAPI"
    assert len(journal.records) == 0

    config = TenantConfig(tenant_id="test-tenant")
    
    # Mock call_model for _extract_decisions from agent_loop
    with patch("agent_loop.call_model", new_callable=AsyncMock) as mock_call_model:
        mock_call_model.return_value = ('["use fastapi", "use jwt"]', 0, 0)
        
        files = [{"path": "main.py", "content": "import fastapi"}]
        test_results = {"success": True}
        
        await journal.record(
            iteration=1,
            files=files,
            test_results=test_results,
            config=config,
            execution_id="exec-123",
            static_result={"approved": True},
            review_result={"review": {"approved": True}}
        )
        
        assert len(journal.records) == 1
        assert journal.records[0].iteration == 1
        assert journal.records[0].test_passed is True
        
        # Check that constraints were created/updated
        assert "use fastapi" in journal._constraints
        assert journal._constraints["use fastapi"].confirmed == 1
        assert journal._constraints["use fastapi"].score == CONFIRM_WEIGHT

        # Let's test penalise_violated
        journal.penalise_violated(["use fastapi failed"])
        # "use fastapi" has 2 words intersection with "use fastapi failed" -> "use", "fastapi"
        # So it should be penalized
        assert journal._constraints["use fastapi"].violated == 1
        assert journal._constraints["use fastapi"].score == CONFIRM_WEIGHT - VIOLATE_PENALTY

        # Check build_context_block
        context_block = journal.build_context_block()
        assert "ARCHITECTURAL JOURNAL" in context_block
        assert "use fastapi" in context_block.lower()

        # Check detect_regressions
        current_files = [{"path": "main.py", "content": "import fastapi\n# modified"}]
        regressions = journal.detect_regressions(current_files, True)
        assert regressions == ["main.py"]

def test_extract_design_decisions():
    journal = IterationJournal(task="Build API", tech_stack="FastAPI")
    spec = {
        "design_system": {
            "colors": {
                "primary": "#ff0000",
                "background": "#ffffff"
            },
            "typography": {
                "font_family": "Roboto",
                "body_size": "16px"
            }
        },
        "layout": {
            "grid_columns": 12,
            "max_width": "1200px"
        },
        "components": [
            {
                "name": "Header",
                "states": ["sticky", "scrolled"],
                "interaction_rules": ["click logo to scroll to top"]
            }
        ]
    }
    decisions = journal._extract_design_decisions(spec)
    assert any("Color system: primary=#ff0000" in d for d in decisions)
    assert any("Typography: Roboto" in d for d in decisions)
    assert any("Header states: sticky, scrolled" in d for d in decisions)

def test_penalise_design_failure():
    journal = IterationJournal(task="Build API", tech_stack="FastAPI")
    journal._design_constraints["header states: sticky, scrolled"] = ScoredConstraint(
        text="Header states: sticky, scrolled",
        confirmed=1,
        violated=0,
        score=1.0,
        key="header states: sticky, scrolled",
        category="design"
    )

    # Penalize design failure
    components = [
        {
            "name": "Header",
            "states": ["sticky", "scrolled"]
        }
    ]
    journal.penalise_design_failure(components, failure_type="visual")
    # Score should be -4.0, which is below MIN_SCORE (-3.0), so it gets pruned.
    assert "header states: sticky, scrolled" not in journal._design_constraints
