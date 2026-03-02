"""Tests for TaskAgent — configurable general-purpose agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slima_agents.agents.context import WorldContext
from slima_agents.agents.task import (
    TaskAgent,
    _DEFAULT_SYSTEM_PROMPT,
    _PLAN_FIRST_GUIDANCE,
    _TOOL_SETS,
)
from slima_agents.agents.tools import (
    SLIMA_MCP_ALL_READ_TOOLS,
    SLIMA_MCP_ALL_TOOLS,
    SLIMA_MCP_TOOLS,
    WEB_TOOLS,
)
from slima_agents.templates import LANGUAGE_RULE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(**kwargs) -> TaskAgent:
    """Create a TaskAgent with sensible defaults."""
    kwargs.setdefault("context", WorldContext())
    return TaskAgent(**kwargs)


def _make_run_output(text: str = "done", **overrides):
    """Create a mock RunOutput."""
    out = MagicMock()
    out.text = text
    out.num_turns = overrides.get("num_turns", 1)
    out.cost_usd = overrides.get("cost_usd", 0.01)
    out.session_id = overrides.get("session_id", "sess_task_1")
    return out


# ---------------------------------------------------------------------------
# name
# ---------------------------------------------------------------------------

class TestName:
    def test_name_is_task_agent(self):
        agent = _make_agent()
        assert agent.name == "TaskAgent"


# ---------------------------------------------------------------------------
# initial_message
# ---------------------------------------------------------------------------

class TestInitialMessage:
    def test_returns_prompt_as_is(self):
        agent = _make_agent(prompt="Do something cool")
        assert agent.initial_message() == "Do something cool"

    def test_empty_prompt(self):
        agent = _make_agent(prompt="")
        assert agent.initial_message() == ""

    def test_unicode_prompt(self):
        agent = _make_agent(prompt="寫一個短篇故事")
        assert agent.initial_message() == "寫一個短篇故事"


# ---------------------------------------------------------------------------
# system_prompt — building blocks
# ---------------------------------------------------------------------------

class TestSystemPromptDefault:
    def test_default_system_prompt(self):
        agent = _make_agent()
        sp = agent.system_prompt()
        assert _DEFAULT_SYSTEM_PROMPT in sp

    def test_language_rule_always_included(self):
        agent = _make_agent()
        sp = agent.system_prompt()
        assert "CRITICAL — Language Rule" in sp

    def test_no_plan_first_by_default(self):
        agent = _make_agent()
        sp = agent.system_prompt()
        assert "Planning Mode" not in sp

    def test_no_book_token_by_default(self):
        agent = _make_agent()
        sp = agent.system_prompt()
        assert "Target Book" not in sp

    def test_no_context_when_empty(self):
        agent = _make_agent()
        sp = agent.system_prompt()
        assert "Current Context" not in sp


class TestSystemPromptCustom:
    def test_custom_replaces_default(self):
        agent = _make_agent(system_prompt_text="You are a pirate.")
        sp = agent.system_prompt()
        assert "You are a pirate." in sp
        assert _DEFAULT_SYSTEM_PROMPT not in sp

    def test_plan_first(self):
        agent = _make_agent(plan_first=True)
        sp = agent.system_prompt()
        assert "Planning Mode" in sp
        assert "Analyze the request" in sp

    def test_book_token(self):
        agent = _make_agent(book_token="bk_test123")
        sp = agent.system_prompt()
        assert "# Target Book" in sp
        assert "bk_test123" in sp

    def test_context_included_when_non_empty(self):
        ctx = WorldContext()
        ctx.overview = "A fantasy world with dragons."
        agent = _make_agent(context=ctx)
        sp = agent.system_prompt()
        assert "# Current Context" in sp
        assert "A fantasy world with dragons." in sp


class TestSystemPromptCombinations:
    def test_all_options_enabled(self):
        ctx = WorldContext()
        ctx.overview = "Some overview."
        agent = _make_agent(
            system_prompt_text="Custom instructions here.",
            plan_first=True,
            book_token="bk_combo",
            context=ctx,
        )
        sp = agent.system_prompt()
        # Check ordering: language_rule → custom → plan_first → book → context
        lr_pos = sp.index("CRITICAL — Language Rule")
        custom_pos = sp.index("Custom instructions here.")
        plan_pos = sp.index("Planning Mode")
        book_pos = sp.index("# Target Book")
        ctx_pos = sp.index("# Current Context")
        assert lr_pos < custom_pos < plan_pos < book_pos < ctx_pos

    def test_plan_first_with_book_no_context(self):
        agent = _make_agent(plan_first=True, book_token="bk_abc")
        sp = agent.system_prompt()
        assert "Planning Mode" in sp
        assert "bk_abc" in sp
        assert "Current Context" not in sp


# ---------------------------------------------------------------------------
# allowed_tools — 4 tool_set values
# ---------------------------------------------------------------------------

class TestAllowedTools:
    def test_write_tool_set(self):
        agent = _make_agent(tool_set="write")
        tools = agent.allowed_tools()
        assert tools == _TOOL_SETS["write"]
        # Should include MCP write tools + web
        assert any("create_file" in t for t in tools)
        assert "WebSearch" in tools

    def test_read_tool_set(self):
        agent = _make_agent(tool_set="read")
        tools = agent.allowed_tools()
        assert tools == _TOOL_SETS["read"]
        assert any("read_file" in t for t in tools)
        assert "WebSearch" in tools
        # Should NOT include write tools
        assert not any("create_file" in t for t in tools)

    def test_all_tool_set(self):
        agent = _make_agent(tool_set="all")
        tools = agent.allowed_tools()
        assert tools == _TOOL_SETS["all"]
        assert any("create_book" in t for t in tools)
        assert any("delete_file" in t for t in tools)
        assert "WebFetch" in tools

    def test_none_tool_set(self):
        agent = _make_agent(tool_set="none")
        tools = agent.allowed_tools()
        assert tools == _TOOL_SETS["none"]
        assert tools == [*WEB_TOOLS]
        assert len(tools) == 2

    def test_unknown_falls_back_to_read(self):
        agent = _make_agent(tool_set="unknown_value")
        tools = agent.allowed_tools()
        assert tools == _TOOL_SETS["read"]

    def test_default_is_read(self):
        agent = _make_agent()
        tools = agent.allowed_tools()
        assert tools == _TOOL_SETS["read"]

    def test_no_bash_in_any_tool_set(self):
        """No tool set should ever include Bash."""
        for ts_name in ("write", "read", "all", "none"):
            agent = _make_agent(tool_set=ts_name)
            tools = agent.allowed_tools()
            assert "Bash" not in tools, f"tool_set={ts_name} should not include Bash"

    def test_web_tools_in_all_sets(self):
        """WebSearch and WebFetch should be in every tool set."""
        for ts_name in ("write", "read", "all", "none"):
            agent = _make_agent(tool_set=ts_name)
            tools = agent.allowed_tools()
            assert "WebSearch" in tools, f"tool_set={ts_name} missing WebSearch"
            assert "WebFetch" in tools, f"tool_set={ts_name} missing WebFetch"


# ---------------------------------------------------------------------------
# _has_write_tools
# ---------------------------------------------------------------------------

class TestHasWriteTools:
    def test_write_has_write_tools(self):
        agent = _make_agent(tool_set="write")
        assert agent._has_write_tools() is True

    def test_all_has_write_tools(self):
        agent = _make_agent(tool_set="all")
        assert agent._has_write_tools() is True

    def test_read_no_write_tools(self):
        agent = _make_agent(tool_set="read")
        assert agent._has_write_tools() is False

    def test_none_no_write_tools(self):
        agent = _make_agent(tool_set="none")
        assert agent._has_write_tools() is False


# ---------------------------------------------------------------------------
# run() — ClaudeRunner mock
# ---------------------------------------------------------------------------

class TestRun:
    @pytest.mark.asyncio
    async def test_run_passes_tools(self):
        agent = _make_agent(prompt="hello", tool_set="write")
        output = _make_run_output()

        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=output)
            result = await agent.run()

        call_kwargs = MockRunner.run.call_args.kwargs
        assert call_kwargs["allowed_tools"] == _TOOL_SETS["write"]

    @pytest.mark.asyncio
    async def test_run_passes_resume_session(self):
        agent = _make_agent(prompt="continue", resume_session="sess_prev")
        output = _make_run_output()

        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=output)
            result = await agent.run()

        call_kwargs = MockRunner.run.call_args.kwargs
        assert call_kwargs["resume_session"] == "sess_prev"

    @pytest.mark.asyncio
    async def test_run_passes_on_event(self):
        callback = MagicMock()
        agent = _make_agent(prompt="go", on_event=callback)
        output = _make_run_output()

        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=output)
            result = await agent.run()

        call_kwargs = MockRunner.run.call_args.kwargs
        assert call_kwargs["on_event"] is callback

    @pytest.mark.asyncio
    async def test_run_returns_agent_result(self):
        agent = _make_agent(prompt="test")
        output = _make_run_output(text="result text", session_id="sess_42")

        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=output)
            result = await agent.run()

        assert result.session_id == "sess_42"
        assert result.full_output == "result text"

    @pytest.mark.asyncio
    async def test_run_default_timeout(self):
        agent = _make_agent(prompt="hi")
        assert agent.timeout == 3600

    @pytest.mark.asyncio
    async def test_run_custom_timeout(self):
        agent = _make_agent(prompt="hi", timeout=600)
        assert agent.timeout == 600
