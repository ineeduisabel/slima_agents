"""BDD tests for session resume feature (Phases 1-3a).

Phase 1: ClaudeRunner captures session_id from stream-json init event
Phase 2: BaseAgent passes resume_session to ClaudeRunner, AgentResult carries session_id
Phase 3a: Validation R1→R2 chains session in both orchestrators
"""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slima_agents.agents.base import AgentResult, BaseAgent
from slima_agents.agents.claude_runner import ClaudeRunner, RunOutput
from slima_agents.agents.context import WorldContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_output(text="Done", session_id="sess_abc123", **kw) -> RunOutput:
    """Helper to create a RunOutput with session_id."""
    return RunOutput(text=text, session_id=session_id, **kw)


class StubAgent(BaseAgent):
    """Minimal agent for testing."""

    @property
    def name(self) -> str:
        return "StubAgent"

    def system_prompt(self) -> str:
        return "You are a test agent."

    def initial_message(self) -> str:
        return "Do the thing."


# ===========================================================================
# Phase 1: ClaudeRunner session_id capture
# ===========================================================================

class TestClaudeRunnerSessionId:
    """ClaudeRunner should capture session_id from stream-json init event."""

    def test_run_output_has_session_id_field(self):
        """RunOutput dataclass should have a session_id field."""
        out = RunOutput(text="hi", session_id="sess_123")
        assert out.session_id == "sess_123"

    def test_run_output_session_id_defaults_empty(self):
        """RunOutput session_id should default to empty string."""
        out = RunOutput(text="hi")
        assert out.session_id == ""

    @pytest.mark.asyncio
    async def test_captures_session_id_from_init_event(self):
        """ClaudeRunner should extract session_id from system init event."""
        init_event = json.dumps({
            "type": "system",
            "subtype": "init",
            "session_id": "e2393023-f234-46fc-a341-693936cbcdb8",
        })
        result_event = json.dumps({
            "type": "result",
            "result": "Done",
            "session_id": "e2393023-f234-46fc-a341-693936cbcdb8",
            "num_turns": 1,
            "total_cost_usd": 0.01,
        })
        stdout_data = (init_event + "\n" + result_event + "\n").encode()

        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: _async_lines(stdout_data)
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        with patch("slima_agents.agents.claude_runner.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=mock_proc)
            mock_asyncio.timeout = _fake_timeout
            mock_asyncio.wait_for = AsyncMock(return_value=0)
            mock_asyncio.CancelledError = asyncio.CancelledError

            output = await ClaudeRunner.run(
                prompt="test",
                system_prompt="sys",
            )

        assert output.session_id == "e2393023-f234-46fc-a341-693936cbcdb8"
        assert output.text == "Done"

    @pytest.mark.asyncio
    async def test_session_id_empty_when_no_init_event(self):
        """session_id should be empty when no init event is received."""
        result_event = json.dumps({
            "type": "result",
            "result": "Done",
            "num_turns": 1,
            "total_cost_usd": 0.01,
        })
        stdout_data = (result_event + "\n").encode()

        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: _async_lines(stdout_data)
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        with patch("slima_agents.agents.claude_runner.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=mock_proc)
            mock_asyncio.timeout = _fake_timeout
            mock_asyncio.wait_for = AsyncMock(return_value=0)
            mock_asyncio.CancelledError = asyncio.CancelledError

            output = await ClaudeRunner.run(
                prompt="test",
                system_prompt="sys",
            )

        assert output.session_id == ""

    def test_run_output_supports_resume_session_param(self):
        """ClaudeRunner.run() should accept resume_session parameter."""
        import inspect
        sig = inspect.signature(ClaudeRunner.run)
        assert "resume_session" in sig.parameters

    @pytest.mark.asyncio
    async def test_resume_session_adds_resume_flag(self):
        """When resume_session is provided, --resume flag should be in the command."""
        result_event = json.dumps({
            "type": "result",
            "result": "Continued",
            "num_turns": 2,
            "total_cost_usd": 0.02,
        })
        stdout_data = (result_event + "\n").encode()

        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: _async_lines(stdout_data)
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        captured_cmd = None

        async def capture_exec(*args, **kwargs):
            nonlocal captured_cmd
            captured_cmd = args
            return mock_proc

        with patch("slima_agents.agents.claude_runner.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = capture_exec
            mock_asyncio.timeout = _fake_timeout
            mock_asyncio.wait_for = AsyncMock(return_value=0)
            mock_asyncio.CancelledError = asyncio.CancelledError

            await ClaudeRunner.run(
                prompt="continue",
                system_prompt="sys",
                resume_session="sess_abc123",
            )

        assert captured_cmd is not None
        assert "--resume" in captured_cmd
        assert "sess_abc123" in captured_cmd


# ===========================================================================
# Phase 2: BaseAgent + AgentResult session support
# ===========================================================================

class TestBaseAgentSessionSupport:
    """BaseAgent should pass resume_session to ClaudeRunner and expose session_id."""

    @pytest.mark.asyncio
    async def test_agent_result_has_session_id(self):
        """AgentResult should carry session_id from RunOutput."""
        ctx = WorldContext()
        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=_run_output("Done", "sess_xyz"))
            agent = StubAgent(context=ctx, book_token="bk_test")
            result = await agent.run()

        assert result.session_id == "sess_xyz"

    @pytest.mark.asyncio
    async def test_agent_passes_resume_session_to_runner(self):
        """BaseAgent should forward resume_session to ClaudeRunner.run()."""
        ctx = WorldContext()
        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=_run_output("Continued"))
            agent = StubAgent(
                context=ctx,
                book_token="bk_test",
                resume_session="sess_prev",
            )
            await agent.run()

            call_kwargs = MockRunner.run.call_args.kwargs
            assert call_kwargs["resume_session"] == "sess_prev"

    @pytest.mark.asyncio
    async def test_agent_default_no_resume(self):
        """BaseAgent should not pass resume_session by default."""
        ctx = WorldContext()
        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=_run_output("Done"))
            agent = StubAgent(context=ctx, book_token="bk_test")
            await agent.run()

            call_kwargs = MockRunner.run.call_args.kwargs
            assert call_kwargs["resume_session"] == ""


# ===========================================================================
# Phase 3a: Validation R1→R2 session chain (Worldbuild)
# ===========================================================================

class TestWorldbuildValidationSessionChain:
    """Worldbuild orchestrator should chain Validation R1→R2 via session resume."""

    @pytest.mark.asyncio
    async def test_validation_r2_receives_r1_session_id(self):
        """Orchestrator should pass R1's session_id to R2 as resume_session."""
        from slima_agents.slima.types import Book
        from slima_agents.worldbuild.orchestrator import OrchestratorAgent

        mock_slima = AsyncMock()
        mock_slima._base_url = "https://test.slima.app"
        mock_slima.create_book = AsyncMock(
            return_value=Book.model_validate({
                "token": "bk_test", "title": "T",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
            })
        )
        mock_slima.create_file = AsyncMock()
        mock_slima.write_file = AsyncMock()
        mock_slima.get_book_structure = AsyncMock(return_value=[])

        with patch("slima_agents.worldbuild.orchestrator.ResearchAgent") as MockResearch, \
             patch("slima_agents.worldbuild.orchestrator.CosmologyAgent") as MockCosmo, \
             patch("slima_agents.worldbuild.orchestrator.GeographyAgent") as MockGeo, \
             patch("slima_agents.worldbuild.orchestrator.HistoryAgent") as MockHist, \
             patch("slima_agents.worldbuild.orchestrator.PeoplesAgent") as MockPeoples, \
             patch("slima_agents.worldbuild.orchestrator.CulturesAgent") as MockCultures, \
             patch("slima_agents.worldbuild.orchestrator.PowerStructuresAgent") as MockPower, \
             patch("slima_agents.worldbuild.orchestrator.CharactersAgent") as MockChars, \
             patch("slima_agents.worldbuild.orchestrator.ItemsAgent") as MockItems, \
             patch("slima_agents.worldbuild.orchestrator.BestiaryAgent") as MockBestiary, \
             patch("slima_agents.worldbuild.orchestrator.NarrativeAgent") as MockNarr, \
             patch("slima_agents.worldbuild.orchestrator.ValidationAgent") as MockValid:

            # Setup non-validation agents
            for MockCls in [MockResearch, MockCosmo, MockGeo, MockHist, MockPeoples,
                            MockCultures, MockPower, MockChars, MockItems, MockBestiary,
                            MockNarr]:
                inst = AsyncMock()
                inst.run = AsyncMock(return_value=AgentResult(
                    summary="Done", full_output="Done", duration_s=1.0,
                ))
                MockCls.return_value = inst

            MockResearch.return_value.suggested_title = "Test"
            MockResearch.return_value.suggested_description = "Test"

            # Track validation construction kwargs
            valid_kwargs_list = []

            def make_valid(**kwargs):
                valid_kwargs_list.append(kwargs)
                inst = AsyncMock()
                # R1 returns a session_id; R2 does not need to
                r = kwargs.get("validation_round", 1)
                session_id = "sess_r1_abc" if r == 1 else ""
                inst.run = AsyncMock(return_value=AgentResult(
                    summary="Done", full_output="Done", duration_s=1.0,
                    session_id=session_id,
                ))
                return inst

            MockValid.side_effect = make_valid

            orch = OrchestratorAgent(slima_client=mock_slima)
            await orch.run("Test")

            # R1 should NOT have resume_session
            assert valid_kwargs_list[0].get("resume_session", "") == ""
            # R2 should have R1's session_id as resume_session
            assert valid_kwargs_list[1].get("resume_session") == "sess_r1_abc"


# ===========================================================================
# Phase 3a: Validation R1→R2 session chain (Mystery)
# ===========================================================================

class TestMysteryValidationSessionChain:
    """Mystery orchestrator should chain Validation R1→R2 via session resume."""

    @pytest.mark.asyncio
    async def test_mystery_validation_r2_receives_r1_session_id(self):
        """Mystery orchestrator should pass R1's session_id to R2."""
        from slima_agents.slima.types import Book
        from slima_agents.mystery.orchestrator import MysteryOrchestratorAgent

        mock_slima = AsyncMock()
        mock_slima._base_url = "https://test.slima.app"
        mock_slima.create_book = AsyncMock(
            return_value=Book.model_validate({
                "token": "bk_mtest", "title": "M",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
            })
        )
        mock_slima.create_file = AsyncMock()
        mock_slima.write_file = AsyncMock()
        mock_slima.read_file = AsyncMock(
            return_value=MagicMock(content="mock content")
        )
        mock_slima.get_book_structure = AsyncMock(return_value=[])

        with patch("slima_agents.mystery.orchestrator.PlannerAgent") as MockPlanner, \
             patch("slima_agents.mystery.orchestrator.CrimeDesignAgent") as MockCrime, \
             patch("slima_agents.mystery.orchestrator.MysteryCharactersAgent") as MockChars, \
             patch("slima_agents.mystery.orchestrator.PlotArchitectureAgent") as MockPlot, \
             patch("slima_agents.mystery.orchestrator.SettingAgent") as MockSetting, \
             patch("slima_agents.mystery.orchestrator.Act1WriterAgent") as MockAct1, \
             patch("slima_agents.mystery.orchestrator.Act2WriterAgent") as MockAct2, \
             patch("slima_agents.mystery.orchestrator.Act3WriterAgent") as MockAct3, \
             patch("slima_agents.mystery.orchestrator.MysteryValidationAgent") as MockValid, \
             patch("slima_agents.mystery.orchestrator.PolishAgent") as MockPolish:

            for MockCls in [MockPlanner, MockCrime, MockChars, MockPlot, MockSetting,
                            MockAct1, MockAct2, MockAct3, MockPolish]:
                inst = AsyncMock()
                inst.run = AsyncMock(return_value=AgentResult(
                    summary="Done", full_output="Done", duration_s=1.0,
                ))
                inst.name = "MockAgent"
                MockCls.return_value = inst

            MockPlanner.return_value.suggested_title = "Test"
            MockPlanner.return_value.suggested_description = "Test"

            valid_kwargs_list = []

            def make_valid(**kwargs):
                valid_kwargs_list.append(kwargs)
                inst = AsyncMock()
                r = kwargs.get("validation_round", 1)
                session_id = "sess_mr1_xyz" if r == 1 else ""
                inst.run = AsyncMock(return_value=AgentResult(
                    summary="Done", full_output="Done", duration_s=1.0,
                    session_id=session_id,
                ))
                inst.name = f"MysteryValidationAgent-R{r}"
                return inst

            MockValid.side_effect = make_valid

            orch = MysteryOrchestratorAgent(slima_client=mock_slima)
            await orch.run("Test mystery")

            # R1 should NOT have resume_session
            assert valid_kwargs_list[0].get("resume_session", "") == ""
            # R2 should have R1's session_id
            assert valid_kwargs_list[1].get("resume_session") == "sess_mr1_xyz"


# ===========================================================================
# Async test helpers
# ===========================================================================

import asyncio


async def _async_lines(data: bytes):
    """Yield lines from bytes data as an async iterator."""
    for line in data.split(b"\n"):
        if line:
            yield line


class _fake_timeout:
    """Fake asyncio.timeout context manager for testing."""

    def __init__(self, seconds):
        self.seconds = seconds

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False
