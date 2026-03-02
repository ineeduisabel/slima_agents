"""Tests for NDJSON streaming architecture (Phases 1-4).

Phase 1: ClaudeRunner _read_stream on_event callback
Phase 2: ProgressEmitter tool_use, text_delta, ask_result, make_agent_callback
Phase 3: Orchestrator callback injection
Phase 4: AskAgent changes + CLI --json-progress
"""

from __future__ import annotations

import asyncio
import json
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slima_agents.agents.base import AgentResult, BaseAgent
from slima_agents.agents.claude_runner import RunOutput
from slima_agents.agents.context import WorldContext
from slima_agents.progress import ProgressEmitter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_output(text="Done", session_id="", **kw) -> RunOutput:
    return RunOutput(text=text, session_id=session_id, **kw)


def _make_emitter() -> tuple[ProgressEmitter, StringIO]:
    buf = StringIO()
    return ProgressEmitter(enabled=True, _stream=buf), buf


def _parse_events(buf: StringIO) -> list[dict]:
    buf.seek(0)
    return [json.loads(line) for line in buf if line.strip()]


class StubAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "StubAgent"

    def system_prompt(self) -> str:
        return "test"

    def initial_message(self) -> str:
        return "go"


def _make_agent_result(**kw) -> AgentResult:
    defaults = dict(summary="ok", full_output="ok", session_id="sess_1",
                    num_turns=1, cost_usd=0.01, duration_s=1.0)
    defaults.update(kw)
    return AgentResult(**defaults)


# ===========================================================================
# Phase 1: _read_stream on_event callback
# ===========================================================================

class TestReadStreamOnEvent:
    """_read_stream should call on_event for each parsed event."""

    @pytest.mark.asyncio
    async def test_on_event_called_for_each_event(self):
        """on_event callback receives every parsed JSON event."""
        from slima_agents.agents.claude_runner import _read_stream

        events_received: list[dict] = []
        stream_lines = [
            json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}),
            json.dumps({"type": "result", "result": "done", "num_turns": 1, "total_cost_usd": 0.01}),
        ]

        proc = MagicMock()
        proc.stdout = _async_line_iter(stream_lines)
        proc.stderr = MagicMock()
        proc.stderr.read = AsyncMock(return_value=b"")
        proc.wait = AsyncMock(return_value=0)

        text, turns, cost, timed_out, sess = await _read_stream(
            proc, timeout=10, on_event=lambda e: events_received.append(e)
        )

        assert len(events_received) == 3
        assert events_received[0]["type"] == "system"
        assert events_received[1]["type"] == "assistant"
        assert events_received[2]["type"] == "result"
        assert sess == "s1"
        assert text == "done"

    @pytest.mark.asyncio
    async def test_on_event_none_is_safe(self):
        """on_event=None should not cause errors."""
        from slima_agents.agents.claude_runner import _read_stream

        stream_lines = [
            json.dumps({"type": "result", "result": "ok", "num_turns": 1, "total_cost_usd": 0.0}),
        ]

        proc = MagicMock()
        proc.stdout = _async_line_iter(stream_lines)
        proc.stderr = MagicMock()
        proc.stderr.read = AsyncMock(return_value=b"")
        proc.wait = AsyncMock(return_value=0)

        text, _, _, _, _ = await _read_stream(proc, timeout=10, on_event=None)
        assert text == "ok"

    @pytest.mark.asyncio
    async def test_on_event_error_does_not_interrupt(self):
        """Errors in on_event callback are swallowed."""
        from slima_agents.agents.claude_runner import _read_stream

        def bad_callback(event):
            raise ValueError("boom")

        stream_lines = [
            json.dumps({"type": "result", "result": "ok", "num_turns": 1, "total_cost_usd": 0.0}),
        ]

        proc = MagicMock()
        proc.stdout = _async_line_iter(stream_lines)
        proc.stderr = MagicMock()
        proc.stderr.read = AsyncMock(return_value=b"")
        proc.wait = AsyncMock(return_value=0)

        text, _, _, _, _ = await _read_stream(proc, timeout=10, on_event=bad_callback)
        assert text == "ok"


class TestBaseAgentOnEvent:
    """BaseAgent should accept on_event and pass it to ClaudeRunner."""

    def test_on_event_stored(self):
        callback = lambda e: None
        agent = StubAgent(context=WorldContext(), on_event=callback)
        assert agent.on_event is callback

    def test_on_event_defaults_to_none(self):
        agent = StubAgent(context=WorldContext())
        assert agent.on_event is None

    @pytest.mark.asyncio
    async def test_on_event_passed_to_runner(self):
        callback = lambda e: None
        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=_run_output())
            agent = StubAgent(context=WorldContext(), on_event=callback)
            await agent.run()
            call_kwargs = MockRunner.run.call_args.kwargs
            assert call_kwargs["on_event"] is callback


# ===========================================================================
# Phase 2: ProgressEmitter new methods
# ===========================================================================

class TestEmitterToolUse:
    def test_tool_use_schema(self):
        emitter, buf = _make_emitter()
        emitter.tool_use("TestAgent", "mcp__slima__read_file", stage=3)
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "tool_use"
        assert ev["agent"] == "TestAgent"
        assert ev["tool_name"] == "mcp__slima__read_file"
        assert ev["stage"] == 3

    def test_tool_use_without_stage(self):
        emitter, buf = _make_emitter()
        emitter.tool_use("Agent", "some_tool")
        events = _parse_events(buf)
        assert "stage" not in events[0]


class TestEmitterTextDelta:
    def test_text_delta_schema(self):
        emitter, buf = _make_emitter()
        emitter.text_delta("Agent", "Hello world", stage=1)
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "text_delta"
        assert ev["agent"] == "Agent"
        assert ev["text"] == "Hello world"
        assert ev["stage"] == 1

    def test_text_delta_without_stage(self):
        emitter, buf = _make_emitter()
        emitter.text_delta("Agent", "text")
        events = _parse_events(buf)
        assert "stage" not in events[0]


class TestEmitterAskResult:
    def test_ask_result_schema(self):
        emitter, buf = _make_emitter()
        emitter.ask_result(
            session_id="sess_1", result="answer",
            num_turns=3, cost_usd=0.1234, duration_s=5.678,
        )
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "ask_result"
        assert ev["session_id"] == "sess_1"
        assert ev["result"] == "answer"
        assert ev["num_turns"] == 3
        assert ev["cost_usd"] == 0.1234
        assert ev["duration_s"] == 5.68

    def test_ask_result_defaults(self):
        emitter, buf = _make_emitter()
        emitter.ask_result(session_id="s", result="r")
        events = _parse_events(buf)
        ev = events[0]
        assert ev["num_turns"] == 0
        assert ev["cost_usd"] == 0.0
        assert ev["duration_s"] == 0.0


class TestEmitterDisabledStreaming:
    def test_disabled_emitter_no_output(self):
        buf = StringIO()
        emitter = ProgressEmitter(enabled=False, _stream=buf)
        emitter.tool_use("A", "t")
        emitter.text_delta("A", "text")
        emitter.ask_result("s", "r")
        assert buf.getvalue() == ""


class TestMakeAgentCallback:
    def test_callback_emits_tool_use(self):
        emitter, buf = _make_emitter()
        cb = emitter.make_agent_callback("TestAgent", stage=5)
        cb({
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "mcp__slima__read_file"}]
            },
        })
        events = _parse_events(buf)
        assert len(events) == 1
        assert events[0]["event"] == "tool_use"
        assert events[0]["tool_name"] == "mcp__slima__read_file"
        assert events[0]["agent"] == "TestAgent"
        assert events[0]["stage"] == 5

    def test_callback_emits_text_delta(self):
        emitter, buf = _make_emitter()
        cb = emitter.make_agent_callback("TestAgent", stage=2)
        cb({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Hello world"}]
            },
        })
        events = _parse_events(buf)
        assert len(events) == 1
        assert events[0]["event"] == "text_delta"
        assert events[0]["text"] == "Hello world"

    def test_callback_handles_multiple_blocks(self):
        emitter, buf = _make_emitter()
        cb = emitter.make_agent_callback("Agent")
        cb({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "thinking..."},
                    {"type": "tool_use", "name": "read_file"},
                    {"type": "text", "text": "more text"},
                ]
            },
        })
        events = _parse_events(buf)
        assert len(events) == 3
        assert events[0]["event"] == "text_delta"
        assert events[1]["event"] == "tool_use"
        assert events[2]["event"] == "text_delta"

    def test_callback_ignores_non_assistant_events(self):
        emitter, buf = _make_emitter()
        cb = emitter.make_agent_callback("Agent")
        cb({"type": "system", "subtype": "init"})
        cb({"type": "result", "result": "done"})
        assert buf.getvalue() == ""

    def test_callback_skips_empty_text(self):
        emitter, buf = _make_emitter()
        cb = emitter.make_agent_callback("Agent")
        cb({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": ""}]
            },
        })
        assert buf.getvalue() == ""

    def test_callback_error_does_not_raise(self):
        """Errors inside the callback should be swallowed."""
        emitter, buf = _make_emitter()
        # Force _emit to raise
        emitter._emit = MagicMock(side_effect=RuntimeError("boom"))
        cb = emitter.make_agent_callback("Agent")
        # Should not raise
        cb({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "hi"}]},
        })


# ===========================================================================
# Phase 3: Orchestrator callback injection
# ===========================================================================

class TestWorldbuildCallbackInjection:
    """worldbuild _run_phase should set agent.on_event before agent.run()."""

    @pytest.mark.asyncio
    async def test_run_phase_sets_on_event(self):
        from slima_agents.worldbuild.orchestrator import OrchestratorAgent

        emitter = ProgressEmitter(enabled=True, _stream=StringIO())

        mock_slima = AsyncMock()
        mock_slima.get_book_structure = AsyncMock(return_value=[])

        orch = OrchestratorAgent(
            slima_client=mock_slima,
            emitter=emitter,
            console=MagicMock(),
        )

        mock_agent = MagicMock()
        mock_agent.name = "TestAgent"
        mock_agent.on_event = None
        mock_agent.run = AsyncMock(return_value=_make_agent_result())

        await orch._run_phase(
            "Test Phase", [("TestAgent", mock_agent)],
            stage=1, book_token="bk_test",
        )

        # on_event should have been set to a callback
        assert mock_agent.on_event is not None
        assert callable(mock_agent.on_event)


class TestMysteryCallbackInjection:
    """mystery _run_stage should set agent.on_event before agent.run()."""

    @pytest.mark.asyncio
    async def test_run_stage_sets_on_event(self):
        from slima_agents.mystery.orchestrator import MysteryOrchestratorAgent

        emitter = ProgressEmitter(enabled=True, _stream=StringIO())

        mock_slima = AsyncMock()
        mock_slima.get_book_structure = AsyncMock(return_value=[])

        orch = MysteryOrchestratorAgent(
            slima_client=mock_slima,
            emitter=emitter,
            console=MagicMock(),
        )

        mock_agent = MagicMock()
        mock_agent.name = "TestAgent"
        mock_agent.on_event = None
        mock_agent.run = AsyncMock(return_value=_make_agent_result())

        await orch._run_stage(3, "Test", mock_agent, "bk_test")

        assert mock_agent.on_event is not None
        assert callable(mock_agent.on_event)


class TestPipelineCallbackInjection:
    """pipeline _run_writer_stage should set agent.on_event."""

    @pytest.mark.asyncio
    async def test_run_writer_stage_sets_on_event(self):
        from slima_agents.pipeline.models import StageDefinition
        from slima_agents.pipeline.orchestrator import GenericOrchestrator

        emitter = ProgressEmitter(enabled=True, _stream=StringIO())
        mock_slima = AsyncMock()
        mock_slima.get_book_structure = AsyncMock(return_value=[])

        orch = GenericOrchestrator(
            slima_client=mock_slima,
            emitter=emitter,
            console=MagicMock(),
        )
        # Set up context
        from slima_agents.pipeline.context import DynamicContext
        orch.context = DynamicContext(allowed_sections=["concept"])

        stage_def = StageDefinition(
            number=3, name="test_stage", display_name="Test Stage",
            instructions="write stuff", initial_message="go",
            tool_set="write",
        )

        on_event_set = []

        with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
            mock_instance = MagicMock()
            mock_instance.name = "WriterAgent[test_stage]"
            mock_instance.run = AsyncMock(return_value=_make_agent_result())

            def capture_on_event(**kw):
                return mock_instance

            MockWriter.side_effect = capture_on_event

            await orch._run_writer_stage(stage_def, "bk_test")

        # on_event should have been set
        assert mock_instance.on_event is not None


# ===========================================================================
# Phase 4: AskAgent changes
# ===========================================================================

class TestAskAgentChanges:
    def test_default_timeout_3600(self):
        from slima_agents.agents.ask import AskAgent
        agent = AskAgent(context=WorldContext(), prompt="test")
        assert agent.timeout == 3600

    def test_readonly_returns_ask_agent_tools(self):
        from slima_agents.agents.ask import AskAgent
        from slima_agents.agents.tools import ASK_AGENT_TOOLS
        agent = AskAgent(context=WorldContext(), prompt="test")
        assert agent.allowed_tools() == ASK_AGENT_TOOLS
        assert "Bash" not in agent.allowed_tools()

    def test_writable_returns_ask_agent_write_tools(self):
        from slima_agents.agents.ask import AskAgent
        from slima_agents.agents.tools import ASK_AGENT_WRITE_TOOLS
        agent = AskAgent(context=WorldContext(), prompt="test", writable=True)
        assert agent.allowed_tools() == ASK_AGENT_WRITE_TOOLS

    def test_has_write_tools_readonly(self):
        """Read-only AskAgent should not have write tools."""
        from slima_agents.agents.ask import AskAgent
        agent = AskAgent(context=WorldContext(), prompt="test")
        assert agent._has_write_tools() is False

    def test_has_write_tools_writable(self):
        """Writable AskAgent should have write tools."""
        from slima_agents.agents.ask import AskAgent
        agent = AskAgent(context=WorldContext(), prompt="test", writable=True)
        assert agent._has_write_tools() is True

    def test_on_event_accepted(self):
        from slima_agents.agents.ask import AskAgent
        cb = lambda e: None
        agent = AskAgent(context=WorldContext(), prompt="test", on_event=cb)
        assert agent.on_event is cb


class TestCliAskJsonProgress:
    """CLI ask --json-progress should emit NDJSON events."""

    def test_ask_help_shows_json_progress(self):
        from click.testing import CliRunner
        from slima_agents.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["ask", "--help"])
        assert "--json-progress" in result.output

    def test_plan_help_shows_json_progress(self):
        from click.testing import CliRunner
        from slima_agents.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["plan", "--help"])
        assert "--json-progress" in result.output


# ---------------------------------------------------------------------------
# Async line iterator helper for _read_stream tests
# ---------------------------------------------------------------------------

class _async_line_iter:
    """Fake async iterator that yields lines as bytes."""

    def __init__(self, lines: list[str]):
        self._lines = [f"{line}\n".encode() for line in lines]
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._index]
        self._index += 1
        return line

    async def read(self):
        return b""
