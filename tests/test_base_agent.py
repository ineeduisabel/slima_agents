"""Tests for BaseAgent with mocked ClaudeRunner."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.base import BaseAgent, AgentResult
from slima_agents.agents.claude_runner import RunOutput
from slima_agents.agents.context import WorldContext


def _run_output(text: str = "Done", num_turns: int = 1, cost_usd: float = 0.01) -> RunOutput:
    """Helper to create a RunOutput for mocking."""
    return RunOutput(text=text, num_turns=num_turns, cost_usd=cost_usd)


class StubAgent(BaseAgent):
    """Minimal agent for testing."""

    @property
    def name(self) -> str:
        return "StubAgent"

    def system_prompt(self) -> str:
        return "You are a test agent."

    def initial_message(self) -> str:
        return "Do the thing."


@pytest.mark.asyncio
async def test_agent_returns_result():
    """Agent calls ClaudeRunner and returns AgentResult."""
    context = WorldContext()

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(
            return_value=_run_output("Task completed successfully. Created files.")
        )

        agent = StubAgent(
            context=context,
            book_token="bk_test",
        )

        result = await agent.run()
        assert isinstance(result, AgentResult)
        assert "Task completed" in result.summary
        assert result.full_output == "Task completed successfully. Created files."
        assert result.num_turns == 1
        assert result.cost_usd == 0.01
        assert result.duration_s > 0

        MockRunner.run.assert_called_once()
        call_kwargs = MockRunner.run.call_args
        assert call_kwargs.kwargs["prompt"] == "Do the thing."
        assert call_kwargs.kwargs["system_prompt"] == "You are a test agent."


@pytest.mark.asyncio
async def test_agent_passes_allowed_tools():
    """Agent passes allowed_tools to ClaudeRunner."""
    context = WorldContext()

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output())

        agent = StubAgent(
            context=context,
            book_token="bk_test",
        )

        await agent.run()

        call_kwargs = MockRunner.run.call_args
        tools = call_kwargs.kwargs["allowed_tools"]
        assert "mcp__slima__create_file" in tools
        assert "mcp__slima__write_file" in tools


@pytest.mark.asyncio
async def test_agent_passes_model():
    """Agent passes model to ClaudeRunner when specified."""
    context = WorldContext()

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output())

        agent = StubAgent(
            context=context,
            book_token="bk_test",
            model="claude-opus-4-6",
        )

        await agent.run()

        call_kwargs = MockRunner.run.call_args
        assert call_kwargs.kwargs["model"] == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_agent_summary_truncated():
    """Agent summary is truncated to 200 chars."""
    context = WorldContext()

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        long_output = "x" * 500
        MockRunner.run = AsyncMock(return_value=_run_output(long_output))

        agent = StubAgent(
            context=context,
            book_token="bk_test",
        )

        result = await agent.run()
        assert len(result.summary) == 200
        assert result.full_output == long_output
