"""Tests for the generic WriterAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.base import AgentResult
from slima_agents.agents.tools import SLIMA_MCP_READ_TOOLS, SLIMA_MCP_TOOLS
from slima_agents.pipeline.context import DynamicContext
from slima_agents.pipeline.writer_agent import WriterAgent
from slima_agents.worldbuild.templates import LANGUAGE_RULE


# --- Helpers ---


def _make_context() -> DynamicContext:
    ctx = DynamicContext(allowed_sections=["concept", "characters"])
    ctx.user_prompt = "寫密室推理"
    return ctx


def _make_writer(
    tool_set="write", quality_standard="", instructions="Do the work", **kwargs
) -> WriterAgent:
    ctx = _make_context()
    defaults = dict(
        context=ctx,
        book_token="bk_test",
        stage_name="crime_design",
        stage_instructions=instructions,
        stage_initial_message="Create files in book '{book_token}'.",
        tool_set=tool_set,
        quality_standard=quality_standard,
    )
    defaults.update(kwargs)
    return WriterAgent(**defaults)


# --- name ---


def test_name_includes_stage():
    """Name should include the stage name for logging."""
    agent = _make_writer(stage_name="crime_design")
    assert agent.name == "WriterAgent[crime_design]"


# --- system_prompt ---


def test_system_prompt_contains_language_rule():
    """System prompt should always start with LANGUAGE_RULE."""
    agent = _make_writer()
    prompt = agent.system_prompt()
    assert prompt.startswith(LANGUAGE_RULE)


def test_system_prompt_contains_instructions():
    """System prompt should include stage instructions."""
    agent = _make_writer(instructions="Design the crime in detail")
    prompt = agent.system_prompt()
    assert "Design the crime in detail" in prompt


def test_system_prompt_contains_quality_standard():
    """System prompt should include quality standard when provided."""
    agent = _make_writer(quality_standard="**Quality:** Write 1000+ words.")
    prompt = agent.system_prompt()
    assert "**Quality:** Write 1000+ words." in prompt


def test_system_prompt_omits_quality_when_empty():
    """System prompt should not contain an empty quality standard block."""
    agent = _make_writer(quality_standard="")
    prompt = agent.system_prompt()
    # Should have instructions directly followed by book token section
    assert "Do the work\n\n# Target Book" in prompt


def test_system_prompt_contains_book_token():
    """System prompt should include the book_token."""
    agent = _make_writer()
    prompt = agent.system_prompt()
    assert "book_token: bk_test" in prompt


def test_system_prompt_contains_context():
    """System prompt should include serialized context."""
    agent = _make_writer()
    prompt = agent.system_prompt()
    assert "## User Request" in prompt
    assert "寫密室推理" in prompt


# --- initial_message ---


def test_initial_message_replaces_book_token():
    """Initial message should replace {book_token} placeholder."""
    agent = _make_writer()
    msg = agent.initial_message()
    assert "bk_test" in msg
    assert "{book_token}" not in msg


def test_initial_message_multiple_placeholders():
    """Should replace all occurrences of {book_token}."""
    ctx = _make_context()
    agent = WriterAgent(
        context=ctx,
        book_token="bk_abc",
        stage_name="test",
        stage_instructions="I",
        stage_initial_message="Read '{book_token}' then write to '{book_token}'.",
    )
    msg = agent.initial_message()
    assert msg == "Read 'bk_abc' then write to 'bk_abc'."


# --- allowed_tools ---


def test_tools_write():
    """tool_set='write' should return full SLIMA_MCP_TOOLS."""
    agent = _make_writer(tool_set="write")
    assert agent.allowed_tools() == SLIMA_MCP_TOOLS


def test_tools_read():
    """tool_set='read' should return SLIMA_MCP_READ_TOOLS."""
    agent = _make_writer(tool_set="read")
    assert agent.allowed_tools() == SLIMA_MCP_READ_TOOLS


def test_tools_none():
    """tool_set='none' should return empty list."""
    agent = _make_writer(tool_set="none")
    assert agent.allowed_tools() == []


def test_tools_unknown_falls_back_to_write():
    """Unknown tool_set should fall back to write tools."""
    agent = _make_writer(tool_set="unknown")
    assert agent.allowed_tools() == SLIMA_MCP_TOOLS


# --- BaseAgent integration ---


@pytest.mark.asyncio
async def test_run_calls_claude_runner():
    """WriterAgent.run() should invoke ClaudeRunner like any BaseAgent."""
    from slima_agents.agents.claude_runner import RunOutput

    mock_output = RunOutput(
        text="Done writing files",
        num_turns=5,
        cost_usd=0.01,
        session_id="sess_123",
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = _make_writer()
        result = await agent.run()

        assert isinstance(result, AgentResult)
        assert result.full_output == "Done writing files"
        assert result.session_id == "sess_123"
        MockRunner.run.assert_called_once()

        # Verify the prompt passed to ClaudeRunner
        call_kwargs = MockRunner.run.call_args
        assert "bk_test" in call_kwargs.kwargs.get("prompt", call_kwargs.args[0] if call_kwargs.args else "")
