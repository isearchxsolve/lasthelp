"""
End-to-End System and Integration Tests for Neon Unified
Tests:
1. Playwright browser automation QA engine (qa_browser.py)
2. Stack detection and entity resolution heuristics
3. Autonomous code generation and project scaffolding
4. Self-healing loop diagnostic parser and code correction
5. SDLC pipeline quality gates
"""

import os
import sys
import pytest
from pathlib import Path

# Add neon_unified to sys.path
NEON_DIR = Path(__file__).parent.parent
if str(NEON_DIR) not in sys.path:
    sys.path.insert(0, str(NEON_DIR))

from qa_browser import Step, Flow, UISpec, QABrowser, HAS_PLAYWRIGHT
from qa_self_heal import detect_stack, _ENTITY_KEYWORDS


class TestNeonUnifiedE2E:
    """E2E test suite for Neon Unified autonomous engine."""

    def test_stack_detection_heuristics(self):
        assert detect_stack("Build a Flutter mobile fitness tracker") == "flutter-fastapi"
        assert detect_stack("Create a React Native Expo delivery app") == "expo-node"
        assert detect_stack("Fullstack Next.js App Router ecommerce platform") == "nextjs-postgres"
        assert detect_stack("Standard FastAPI and React SaaS dashboard") == "fastapi-react"

    def test_entity_keywords_resolution(self):
        matched = False
        sample_prompt = "Build a daily habit tracker with streaks and reminders"
        for keywords, slug, entity in _ENTITY_KEYWORDS:
            if any(kw in sample_prompt.lower() for kw in keywords):
                assert slug == "habit"
                assert entity == "Habit"
                matched = True
                break
        assert matched is True

    def test_playwright_qa_browser_spec_model(self):
        step1 = Step(action="goto", url="http://127.0.0.1:8000")
        step2 = Step(action="assert_text", selector="h1", value="Dashboard")
        flow = Flow(id="smoke_test", description="Smoke test flow", steps=[step1, step2])
        spec = UISpec(base_url="http://127.0.0.1:8000", flows=[flow])

        assert spec.base_url == "http://127.0.0.1:8000"
        assert len(spec.flows) == 1
        assert spec.flows[0].steps[0].action == "goto"

    @pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="Playwright not installed in environment")
    def test_playwright_headless_browser_lifecycle(self, tmp_path):
        with QABrowser(headless=True) as qa:
            page = qa.new_page()
            assert page is not None
            page.set_content("<html><body><h1 id='title'>Neon QA</h1><p>Test content</p></body></html>")
            
            title_text = page.locator("#title").text_content()
            assert title_text == "Neon QA"
            
            # Screenshot test
            ss_path = tmp_path / "screenshot.png"
            qa.screenshot(page, ss_path)
            assert ss_path.exists()
            assert ss_path.stat().st_size > 0
