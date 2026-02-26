"""Tests for AskAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.ask import AskAgent
from slima_agents.agents.base import AgentResult
from slima_agents.agents.claude_runner import RunOutput  # used by _run_output helper
from slima_agents.agents.context import WorldContext
from slima_agents.agents.tools import SLIMA_MCP_ALL_READ_TOOLS, SLIMA_MCP_TOOLS


def _run_output(text: str = "Done", num_turns: int = 1, cost_usd: float = 0.01) -> RunOutput:
    return RunOutput(text=text, num_turns=num_turns, cost_usd=cost_usd)


@pytest.mark.asyncio
async def test_ask_agent_returns_result():
    """AskAgent calls ClaudeRunner and returns AgentResult; name is 'AskAgent'."""
    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output("Here are your books."))

        agent = AskAgent(context=WorldContext(), prompt="列出我所有的書")
        result = await agent.run()

        assert isinstance(result, AgentResult)
        assert agent.name == "AskAgent"
        assert "Here are your books" in result.full_output
        assert result.num_turns == 1
        MockRunner.run.assert_called_once()


def test_ask_agent_readonly_tools():
    """Default allowed_tools should be SLIMA_MCP_ALL_READ_TOOLS."""
    agent = AskAgent(context=WorldContext(), prompt="test")
    assert agent.allowed_tools() == SLIMA_MCP_ALL_READ_TOOLS
    # Should not contain any write/create tools
    for tool in agent.allowed_tools():
        assert "create" not in tool
        assert "write" not in tool
        assert "edit" not in tool


def test_ask_agent_writable_tools():
    """writable=True should return SLIMA_MCP_TOOLS (includes write tools)."""
    agent = AskAgent(context=WorldContext(), prompt="test", writable=True)
    assert agent.allowed_tools() == SLIMA_MCP_TOOLS
    tool_names = agent.allowed_tools()
    assert "mcp__slima__create_file" in tool_names
    assert "mcp__slima__write_file" in tool_names


def test_ask_agent_with_book_token():
    """system_prompt should include book_token when provided."""
    agent = AskAgent(context=WorldContext(), book_token="bk_abc123", prompt="test")
    sp = agent.system_prompt()
    assert "bk_abc123" in sp
    assert "Target book token" in sp


def test_ask_agent_without_book_token():
    """system_prompt should not mention book token when not provided."""
    agent = AskAgent(context=WorldContext(), prompt="test")
    sp = agent.system_prompt()
    assert "Target book token" not in sp


def test_ask_agent_timeout_default():
    """Default timeout should be 300s."""
    agent = AskAgent(context=WorldContext(), prompt="test")
    assert agent.timeout == 300


def test_ask_agent_timeout_override():
    """Timeout can be overridden via kwargs."""
    agent = AskAgent(context=WorldContext(), prompt="test", timeout=600)
    assert agent.timeout == 600


def test_ask_agent_initial_message():
    """initial_message should return the prompt as-is."""
    agent = AskAgent(context=WorldContext(), prompt="搜尋所有提到龍的段落")
    assert agent.initial_message() == "搜尋所有提到龍的段落"
