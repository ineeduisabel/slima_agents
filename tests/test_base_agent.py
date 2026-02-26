"""Tests for BaseAgent with mocked ClaudeRunner."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.base import BaseAgent, AgentResult
from slima_agents.agents.claude_runner import RunOutput
from slima_agents.agents.context import WorldContext
from slima_agents.worldbuild.research import ResearchAgent
from slima_agents.worldbuild.validator import ValidationAgent


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


@pytest.mark.asyncio
async def test_research_agent_parses_title():
    """ResearchAgent should extract suggested_title and suggested_description."""
    context = WorldContext()

    mock_output = (
        "## Title\n"
        "台灣百鬼錄\n"
        "\n"
        "## Description\n"
        "一本關於台灣鬼怪傳說的世界觀聖經，涵蓋民間信仰與超自然存在。\n"
        "\n"
        "## Overview\n"
        "This is the overview content.\n"
        "\n"
        "## Cosmology\n"
        "Cosmology content here.\n"
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output(mock_output))

        agent = ResearchAgent(context=context, prompt="台灣鬼怪故事")
        await agent.run()

        assert agent.suggested_title == "台灣百鬼錄"
        assert "台灣鬼怪傳說" in agent.suggested_description
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
        MockRunner.run = AsyncMock(return_value=_run_output(mock_output))

        agent = ResearchAgent(context=context, prompt="test world")
        await agent.run()

        assert agent.suggested_title == ""
        assert agent.suggested_description == ""
        overview = await context.read("overview")
        assert "without title" in overview


@pytest.mark.asyncio
async def test_research_agent_parses_description():
    """ResearchAgent should extract suggested_description from ## Description section."""
    context = WorldContext()

    mock_output = (
        "## Title\n"
        "The Dark Chronicles\n"
        "\n"
        "## Description\n"
        "A dark fantasy world where ancient gods wage war through mortal champions.\n"
        "\n"
        "## Overview\n"
        "Overview content here.\n"
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output(mock_output))

        agent = ResearchAgent(context=context, prompt="dark fantasy world")
        await agent.run()

        assert agent.suggested_title == "The Dark Chronicles"
        assert "ancient gods" in agent.suggested_description
        assert "mortal champions" in agent.suggested_description


@pytest.mark.asyncio
async def test_research_agent_description_without_title():
    """ResearchAgent should parse description even when title comes after it."""
    context = WorldContext()

    mock_output = (
        "## Description\n"
        "A world of shadows and light.\n"
        "\n"
        "## Title\n"
        "Shadow Codex\n"
        "\n"
        "## Overview\n"
        "Overview here.\n"
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output(mock_output))

        agent = ResearchAgent(context=context, prompt="shadow world")
        await agent.run()

        assert agent.suggested_description == "A world of shadows and light."
        assert agent.suggested_title == "Shadow Codex"


@pytest.mark.asyncio
async def test_validation_agent_round_parameter():
    """ValidationAgent should change name, prompt, and instructions based on round."""
    context = WorldContext()

    agent_r1 = ValidationAgent(
        context=context,
        book_token="bk_test",
        validation_round=1,
    )
    agent_r2 = ValidationAgent(
        context=context,
        book_token="bk_test",
        validation_round=2,
    )

    # Name reflects round
    assert agent_r1.name == "ValidationAgent-R1"
    assert agent_r2.name == "ValidationAgent-R2"

    # System prompts use different instructions
    sp_r1 = agent_r1.system_prompt()
    sp_r2 = agent_r2.system_prompt()
    assert "Round 1" in sp_r1
    assert "Round 2" in sp_r2
    assert "content completeness" in sp_r1
    assert "Verification Agent" in sp_r2

    # Initial messages differ
    msg_r1 = agent_r1.initial_message()
    msg_r2 = agent_r2.initial_message()
    assert "preliminary consistency report" in msg_r1
    assert "FINAL status report" in msg_r2


@pytest.mark.asyncio
async def test_validation_agent_default_round():
    """ValidationAgent defaults to round 1 when no round specified."""
    context = WorldContext()
    agent = ValidationAgent(context=context, book_token="bk_test")
    assert agent.validation_round == 1
    assert agent.name == "ValidationAgent-R1"
