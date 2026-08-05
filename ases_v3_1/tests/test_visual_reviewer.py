"""
ASES — Visual Reviewer Unit Tests
==================================
Dedicated unit tests for visual_reviewer.py covering:
  - _has_frontend() stack + file-extension detection
  - _should_run_visual() last-mile gate heuristic
  - _visual_skip() return shape
  - _parse_json_safe() tolerant JSON extraction
  - _read_sandbox_file_b64() docker cp wrapper
  - visual_reviewer() full flow with mocked sandbox + OpenAI vision
  - visual_reviewer() skip paths (last-mile, screenshot fail, LLM fail, parse fail)

All Docker, subprocess, and OpenAI dependencies are mocked.
"""

import base64
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_SERVICE = os.path.join(ROOT, "agent_service")
sys.path.insert(0, AGENT_SERVICE)

import visual_reviewer as vr


# ---------------------------------------------------------------------------
# _has_frontend()
# ---------------------------------------------------------------------------

class TestHasFrontend:
    def test_detects_react_stack(self):
        assert vr._has_frontend("React", [{"path": "index.js"}]) is True

    def test_detects_nextjs_stack(self):
        assert vr._has_frontend("Next.js + TypeScript", [{"path": "api.ts"}]) is True

    def test_detects_vue_stack(self):
        assert vr._has_frontend("Vue", [{"path": "main.js"}]) is True

    def test_detects_html_stack(self):
        assert vr._has_frontend("HTML", [{"path": "style.css"}]) is True

    def test_detects_frontend_via_file_extension_jsx(self):
        assert vr._has_frontend("Node.js", [{"path": "App.jsx"}]) is True

    def test_detects_frontend_via_file_extension_tsx(self):
        assert vr._has_frontend("Python", [{"path": "Dashboard.tsx"}]) is True

    def test_detects_frontend_via_file_extension_html(self):
        assert vr._has_frontend("Node.js", [{"path": "page.html"}]) is True

    def test_returns_false_for_pure_backend(self):
        assert vr._has_frontend("Node.js + Express", [{"path": "server.js"}]) is False

    def test_returns_false_for_python_backend(self):
        assert vr._has_frontend("Python + FastAPI", [{"path": "main.py"}]) is False

    def test_strips_plus_in_stack(self):
        # "React + Express" → stack_key "react" → frontend
        assert vr._has_frontend("React + Express", [{"path": "server.js"}]) is True


# ---------------------------------------------------------------------------
# _should_run_visual() — last-mile gate heuristic
# ---------------------------------------------------------------------------

class TestShouldRunVisual:
    def test_skips_when_not_last_mile(self):
        """Iteration 1 of 5 → 4 remaining > reserve 2 → skip."""
        should_run, reason = vr._should_run_visual(
            iteration=1, max_iterations=5, previous_errors="",
        )
        assert should_run is False
        assert "Not last-mile" in reason

    def test_skips_when_rich_error_feedback_exists(self):
        """Last-mile BUT errors > 200 chars → skip (coder has text feedback)."""
        long_errors = "x" * 300
        should_run, reason = vr._should_run_visual(
            iteration=4, max_iterations=5, previous_errors=long_errors,
        )
        assert should_run is False
        assert "Rich text feedback" in reason

    def test_runs_on_last_mile_with_short_errors(self):
        """Iteration 4 of 5 + short errors → run."""
        should_run, reason = vr._should_run_visual(
            iteration=4, max_iterations=5, previous_errors="minor",
        )
        assert should_run is True
        assert reason == ""

    def test_runs_on_final_iteration(self):
        """Iteration 5 of 5 → 0 remaining ≤ 2 → run (if errors short)."""
        should_run, reason = vr._should_run_visual(
            iteration=5, max_iterations=5, previous_errors="",
        )
        assert should_run is True

    def test_runs_at_boundary_reserve_equals_remaining(self):
        """Iteration 3 of 5 → 2 remaining == reserve 2 → run (boundary)."""
        should_run, reason = vr._should_run_visual(
            iteration=3, max_iterations=5, previous_errors="",
        )
        assert should_run is True

    def test_skip_reason_empty_string_when_running(self):
        """When should_run is True, skip_reason must be empty string."""
        should_run, reason = vr._should_run_visual(
            iteration=5, max_iterations=5, previous_errors="",
        )
        assert should_run is True
        assert reason == ""


# ---------------------------------------------------------------------------
# _visual_skip()
# ---------------------------------------------------------------------------

class TestVisualSkip:
    def test_returns_approved_true(self):
        """Skip always returns approved=True (fail-open for visual)."""
        result = vr._visual_skip("some reason")
        assert result["approved"] is True

    def test_returns_empty_issues(self):
        result = vr._visual_skip("reason")
        assert result["issues"] == []
        assert result["issues_text"] == ""

    def test_returns_none_screenshot(self):
        result = vr._visual_skip("reason")
        assert result["screenshot_b64"] is None

    def test_returns_zero_tokens(self):
        result = vr._visual_skip("reason")
        assert result["tokens"] == 0


# ---------------------------------------------------------------------------
# _parse_json_safe()
# ---------------------------------------------------------------------------

class TestParseJsonSafe:
    def test_parses_plain_json(self):
        raw = '{"approved": false, "issues": []}'
        result = vr._parse_json_safe(raw)
        assert result["approved"] is False
        assert result["issues"] == []

    def test_parses_json_in_code_fence(self):
        raw = '```json\n{"approved": true, "summary": "ok"}\n```'
        result = vr._parse_json_safe(raw)
        assert result["approved"] is True
        assert result["summary"] == "ok"

    def test_parses_json_with_surrounding_text(self):
        raw = 'Here is the review:\n```json\n{"approved": false}\n```\nDone.'
        result = vr._parse_json_safe(raw)
        assert result["approved"] is False

    def test_returns_empty_dict_on_invalid_json(self):
        result = vr._parse_json_safe("not json at all")
        assert result == {}

    def test_returns_empty_dict_on_malformed_code_fence(self):
        raw = '```json\n{not valid json}\n```'
        result = vr._parse_json_safe(raw)
        assert result == {}

    def test_handles_nested_json(self):
        raw = '{"approved": false, "issues": [{"severity": "high", "description": "blank page"}]}'
        result = vr._parse_json_safe(raw)
        assert len(result["issues"]) == 1
        assert result["issues"][0]["severity"] == "high"


# ---------------------------------------------------------------------------
# _read_sandbox_file_b64()
# ---------------------------------------------------------------------------

class TestReadSandboxFileB64:
    def test_returns_base64_on_success(self):
        """docker cp success → base64-encoded file contents."""
        file_bytes = b"PNG_FAKE_DATA"
        expected_b64 = base64.b64encode(file_bytes).decode()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=file_bytes)
            result = vr._read_sandbox_file_b64("sandbox-1", "/workspace/shot.png")

        assert result == expected_b64
        mock_run.assert_called_once()
        args = mock_run.call_args.args[0]
        assert args[0] == "docker"
        assert "cp" in args
        assert "sandbox-1:/workspace/shot.png" in args

    def test_returns_none_on_nonzero_returncode(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=b"")
            result = vr._read_sandbox_file_b64("sandbox-1", "/path")

        assert result is None

    def test_returns_none_on_empty_stdout(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"")
            result = vr._read_sandbox_file_b64("sandbox-1", "/path")

        assert result is None

    def test_returns_none_on_subprocess_exception(self):
        with patch("subprocess.run", side_effect=RuntimeError("timeout")):
            result = vr._read_sandbox_file_b64("sandbox-1", "/path")

        assert result is None


# ---------------------------------------------------------------------------
# visual_reviewer() — full async flow with mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sandbox_deps():
    """Patch sandbox.run_command and sandbox.write_file for the duration."""
    run_cmd = AsyncMock()
    write_file = MagicMock()
    with patch("sandbox.run_command", run_cmd), \
         patch("sandbox.write_file", write_file):
        yield {"run_command": run_cmd, "write_file": write_file}


def _successful_screenshot():
    """Helper: run_command side_effect that returns success for any command."""
    def side_effect(sandbox_id, cmd, timeout=None):
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
    return side_effect


class TestVisualReviewerFullFlow:
    @pytest.mark.asyncio
    async def test_skips_when_not_last_mile(self, mock_sandbox_deps):
        """Iteration 1 of 5 → last-mile gate skips before any sandbox calls."""
        result = await vr.visual_reviewer(
            sandbox_id="sb-1",
            task="Build dashboard",
            tech_stack="React",
            files=[{"path": "App.jsx"}],
            config=MagicMock(),
            execution_id="exec-v1",
            iteration=1,
            max_iterations=5,
            previous_errors="",
        )

        assert result["approved"] is True
        assert result["tokens"] == 0
        # No sandbox calls should fire when skipped
        mock_sandbox_deps["run_command"].assert_not_awaited()
        mock_sandbox_deps["write_file"].assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_rich_errors_present(self, mock_sandbox_deps):
        """Last-mile but rich errors → skip."""
        result = await vr.visual_reviewer(
            sandbox_id="sb-1",
            task="Build app",
            tech_stack="React",
            files=[{"path": "App.jsx"}],
            config=MagicMock(),
            execution_id="exec-v2",
            iteration=4,
            max_iterations=5,
            previous_errors="x" * 300,
        )

        assert result["approved"] is True
        assert result["tokens"] == 0

    @pytest.mark.asyncio
    async def test_skips_screenshot_failure(self, mock_sandbox_deps):
        """Screenshot capture fails → skip with reason."""
        mock_sandbox_deps["run_command"].side_effect = _successful_screenshot()
        # Override: screenshot capture returns failure
        fail_result = {"success": False, "stdout": "", "stderr": "playwright not installed", "returncode": 1}
        mock_sandbox_deps["run_command"].side_effect = [
            {"success": True, "stdout": "", "stderr": "", "returncode": 0},  # dev server
            fail_result,  # screenshot capture
        ]

        with patch("visual_reviewer._read_sandbox_file_b64", return_value=None):
            result = await vr.visual_reviewer(
                sandbox_id="sb-1",
                task="Build app",
                tech_stack="React",
                files=[{"path": "App.jsx"}],
                config=MagicMock(),
                execution_id="exec-v3",
                iteration=5,
                max_iterations=5,
                previous_errors="",
            )

        assert result["approved"] is True  # fail-open
        assert result["tokens"] == 0

    @pytest.mark.asyncio
    async def test_skips_when_screenshot_file_not_found(self, mock_sandbox_deps):
        """Screenshot captures but file read returns None → skip."""
        mock_sandbox_deps["run_command"].side_effect = _successful_screenshot()

        with patch("visual_reviewer._read_sandbox_file_b64", return_value=None):
            result = await vr.visual_reviewer(
                sandbox_id="sb-1",
                task="Build app",
                tech_stack="React",
                files=[{"path": "App.jsx"}],
                config=MagicMock(),
                execution_id="exec-v4",
                iteration=5,
                max_iterations=5,
                previous_errors="",
            )

        assert result["approved"] is True
        assert result["tokens"] == 0

    @pytest.mark.asyncio
    async def test_approves_when_vision_says_approved(self, mock_sandbox_deps):
        """Vision returns approved=True → result approved with tokens counted."""
        mock_sandbox_deps["run_command"].side_effect = _successful_screenshot()

        fake_b64 = "iVBORw0KGgoAAAANS"  # minimal base64
        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(
            content='{"approved": true, "issues": [], "summary": "looks good"}'
        ))]
        fake_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("visual_reviewer._read_sandbox_file_b64", return_value=fake_b64), \
             patch("openai.AsyncOpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_openai_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
                result = await vr.visual_reviewer(
                    sandbox_id="sb-1",
                    task="Build dashboard",
                    tech_stack="React",
                    files=[{"path": "App.jsx"}],
                    config=MagicMock(),
                    execution_id="exec-v5",
                    iteration=5,
                    max_iterations=5,
                    previous_errors="",
                )

        assert result["approved"] is True
        assert result["tokens"] == 150  # 100 + 50
        assert result["screenshot_b64"] == fake_b64
        mock_client.chat.completions.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejects_when_vision_finds_issues(self, mock_sandbox_deps):
        import json
        """Vision returns approved=False with issues → issues_text populated."""
        mock_sandbox_deps["run_command"].side_effect = _successful_screenshot()

        fake_b64 = "iVBORw0KGgo="
        issues = [
            {"severity": "high", "description": "Page is white"},
            {"severity": "medium", "description": "Contrast 3:1"},
        ]
        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(
            content=json.dumps({"approved": False, "issues": issues, "summary": "fail"})
        ))]
        fake_response.usage = MagicMock(prompt_tokens=200, completion_tokens=80)

        with patch("visual_reviewer._read_sandbox_file_b64", return_value=fake_b64), \
             patch("openai.AsyncOpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_openai_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
                result = await vr.visual_reviewer(
                    sandbox_id="sb-1",
                    task="Build app",
                    tech_stack="React",
                    files=[{"path": "App.jsx"}],
                    config=MagicMock(),
                    execution_id="exec-v6",
                    iteration=5,
                    max_iterations=5,
                    previous_errors="",
                )

        assert result["approved"] is False
        assert len(result["issues"]) == 2
        assert "VISUAL REVIEW FAILED" in result["issues_text"]
        assert "Page is white" in result["issues_text"]
        assert "[HIGH]" in result["issues_text"]

    @pytest.mark.asyncio
    async def test_skips_on_llm_exception(self, mock_sandbox_deps):
        """OpenAI call throws → fail-open skip."""
        mock_sandbox_deps["run_command"].side_effect = _successful_screenshot()

        with patch("visual_reviewer._read_sandbox_file_b64", return_value="fakeb64"), \
             patch("openai.AsyncOpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=RuntimeError("API key invalid")
            )
            mock_openai_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-bad"}):
                result = await vr.visual_reviewer(
                    sandbox_id="sb-1",
                    task="Build app",
                    tech_stack="React",
                    files=[{"path": "App.jsx"}],
                    config=MagicMock(),
                    execution_id="exec-v7",
                    iteration=5,
                    max_iterations=5,
                    previous_errors="",
                )

        assert result["approved"] is True  # fail-open
        assert result["tokens"] == 0

    @pytest.mark.asyncio
    async def test_skips_on_unparseable_vision_response(self, mock_sandbox_deps):
        """Vision returns garbage JSON → skip (can't parse)."""
        mock_sandbox_deps["run_command"].side_effect = _successful_screenshot()

        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content="not json"))]
        fake_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        with patch("visual_reviewer._read_sandbox_file_b64", return_value="b64"), \
             patch("openai.AsyncOpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_openai_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
                result = await vr.visual_reviewer(
                    sandbox_id="sb-1",
                    task="Build app",
                    tech_stack="React",
                    files=[{"path": "App.jsx"}],
                    config=MagicMock(),
                    execution_id="exec-v8",
                    iteration=5,
                    max_iterations=5,
                    previous_errors="",
                )

        assert result["approved"] is True  # parse fail → skip → fail-open

    @pytest.mark.asyncio
    async def test_html_stack_skips_dev_server(self, mock_sandbox_deps):
        """HTML stack has dev_cmd=None → no dev server start, direct screenshot."""
        # Only the screenshot run_command should fire (not dev server)
        shot_result = {"success": True, "stdout": "", "stderr": "", "returncode": 0}
        mock_sandbox_deps["run_command"].return_value = shot_result

        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(
            content='{"approved": true, "issues": [], "summary": "ok"}'
        ))]
        fake_response.usage = MagicMock(prompt_tokens=50, completion_tokens=20)

        with patch("visual_reviewer._read_sandbox_file_b64", return_value="b64"), \
             patch("openai.AsyncOpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_openai_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
                result = await vr.visual_reviewer(
                    sandbox_id="sb-1",
                    task="Build landing page",
                    tech_stack="HTML",
                    files=[{"path": "index.html"}],
                    config=MagicMock(),
                    execution_id="exec-v9",
                    iteration=5,
                    max_iterations=5,
                    previous_errors="",
                )

        # Only 1 run_command call (screenshot), no dev server
        assert mock_sandbox_deps["run_command"].await_count == 1
        assert result["approved"] is True

    @pytest.mark.asyncio
    async def test_vision_prompt_includes_task_and_stack(self, mock_sandbox_deps):
        """The vision review prompt must mention the task and tech stack."""
        mock_sandbox_deps["run_command"].side_effect = _successful_screenshot()

        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(
            content='{"approved": true, "issues": [], "summary": "ok"}'
        ))]
        fake_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        with patch("visual_reviewer._read_sandbox_file_b64", return_value="b64"), \
             patch("openai.AsyncOpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_openai_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
                await vr.visual_reviewer(
                    sandbox_id="sb-1",
                    task="Build a TodoMVC app",
                    tech_stack="React",
                    files=[{"path": "App.jsx"}],
                    config=MagicMock(),
                    execution_id="exec-v10",
                    iteration=5,
                    max_iterations=5,
                    previous_errors="",
                )

        sent_messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        prompt_text = sent_messages[0]["content"][0]["text"]
        assert "TodoMVC" in prompt_text
        assert "React" in prompt_text
        assert "WCAG" in prompt_text  # accessibility check present
