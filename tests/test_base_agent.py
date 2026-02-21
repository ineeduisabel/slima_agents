"""Tests for BaseAgent with mocked ClaudeRunner."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.base import BaseAgent, AgentResult
from slima_agents.agents.context import WorldContext
from slima_agents.worldbuild.research import ResearchAgent


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
        MockRunner.run = AsyncMock(return_value="Task completed successfully. Created files.")

        agent = StubAgent(
            context=context,
            book_token="bk_test",
        )

        result = await agent.run()
        assert isinstance(result, AgentResult)
        assert "Task completed" in result.summary
        assert result.full_output == "Task completed successfully. Created files."

        MockRunner.run.assert_called_once()
        call_kwargs = MockRunner.run.call_args
        assert call_kwargs.kwargs["prompt"] == "Do the thing."
        assert call_kwargs.kwargs["system_prompt"] == "You are a test agent."


@pytest.mark.asyncio
async def test_agent_passes_allowed_tools():
    """Agent passes allowed_tools to ClaudeRunner."""
    context = WorldContext()

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value="Done")

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
        MockRunner.run = AsyncMock(return_value="Done")

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
        MockRunner.run = AsyncMock(return_value=long_output)

        agent = StubAgent(
            context=context,
            book_token="bk_test",
        )

        result = await agent.run()
        assert len(result.summary) == 200
        assert result.full_output == long_output


@pytest.mark.asyncio
async def test_research_agent_parses_title():
    """ResearchAgent should extract suggested_title from ## Title section."""
    context = WorldContext()

    mock_output = (
        "## Title\n"
        "台灣百鬼錄\n"
        "\n"
        "## Overview\n"
        "This is the overview content.\n"
        "\n"
        "## Cosmology\n"
        "Cosmology content here.\n"
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = ResearchAgent(context=context, prompt="台灣鬼怪故事")
        await agent.run()

        assert agent.suggested_title == "台灣百鬼錄"
        overview = await context.read("overview")
        assert "overview content" in overview


@pytest.mark.asyncio
async def test_research_agent_fallback_without_title():
    """ResearchAgent should have empty suggested_title if ## Title is missing."""
    context = WorldContext()

    mock_output = (
        "## Overview\n"
        "Overview without title section.\n"
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = ResearchAgent(context=context, prompt="test world")
        await agent.run()

        assert agent.suggested_title == ""
        overview = await context.read("overview")
        assert "without title" in overview
