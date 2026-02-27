"""Tests for PlannerAgent with mocked ClaudeRunner."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.claude_runner import RunOutput
from slima_agents.mystery.context import MysteryContext
from slima_agents.mystery.planner import PlannerAgent
from slima_agents.mystery.validator import MysteryValidationAgent


def _run_output(text: str = "Done", num_turns: int = 1, cost_usd: float = 0.01) -> RunOutput:
    return RunOutput(text=text, num_turns=num_turns, cost_usd=cost_usd)


@pytest.mark.asyncio
async def test_planner_parses_title():
    """PlannerAgent should extract suggested_title and suggested_description."""
    context = MysteryContext()

    mock_output = (
        "## Title\n"
        "維多利亞莊園之謎\n"
        "\n"
        "## Description\n"
        "一座與世隔絕的維多利亞莊園中，賓客接連遇害的密室殺人事件。\n"
        "\n"
        "## Concept\n"
        "This is a locked-room mystery set in Victorian England.\n"
        "\n"
        "## The Crime\n"
        "The butler did it with poison.\n"
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output(mock_output))

        agent = PlannerAgent(context=context, prompt="維多利亞莊園密室殺人")
        await agent.run()

        assert agent.suggested_title == "維多利亞莊園之謎"
        assert "維多利亞莊園" in agent.suggested_description

        concept = await context.read("concept")
        assert "locked-room" in concept

        crime = await context.read("crime_design")
        assert "butler" in crime


@pytest.mark.asyncio
async def test_planner_fallback_without_title():
    """PlannerAgent should have empty suggested_title if ## Title is missing."""
    context = MysteryContext()

    mock_output = (
        "## Concept\n"
        "A murder mystery without a title section.\n"
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output(mock_output))

        agent = PlannerAgent(context=context, prompt="test mystery")
        await agent.run()

        assert agent.suggested_title == ""
        assert agent.suggested_description == ""
        concept = await context.read("concept")
        assert "murder mystery" in concept


@pytest.mark.asyncio
async def test_planner_parses_all_sections():
    """PlannerAgent should populate concept, crime_design, characters, plot_architecture."""
    context = MysteryContext()

    mock_output = (
        "## Title\n"
        "The Missing Heir\n"
        "\n"
        "## Description\n"
        "A wealthy heir vanishes from a locked study.\n"
        "\n"
        "## Concept\n"
        "Classic whodunit in a country estate.\n"
        "\n"
        "## The Crime\n"
        "The heir was poisoned by the gardener.\n"
        "\n"
        "## The False Story\n"
        "It appeared to be a kidnapping.\n"
        "\n"
        "## Evidence Chain\n"
        "1. Poison bottle in the greenhouse.\n"
        "\n"
        "## Red Herrings\n"
        "The ransom note was a decoy.\n"
        "\n"
        "## Character Sketches\n"
        "Detective: Inspector Holmes.\nVictim: Lord Ashford.\n"
        "\n"
        "## Act Structure\n"
        "Act 1: Discovery of disappearance.\n"
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output(mock_output))

        agent = PlannerAgent(context=context, prompt="country estate mystery")
        await agent.run()

        assert agent.suggested_title == "The Missing Heir"
        concept = await context.read("concept")
        assert "whodunit" in concept

        crime = await context.read("crime_design")
        assert "poisoned" in crime
        assert "kidnapping" in crime  # false story appended
        assert "Poison bottle" in crime  # evidence chain appended
        assert "ransom" in crime  # red herrings appended

        chars = await context.read("characters")
        assert "Inspector Holmes" in chars

        plot = await context.read("plot_architecture")
        assert "Discovery" in plot


@pytest.mark.asyncio
async def test_planner_description_before_title():
    """PlannerAgent should parse description even when it comes before title."""
    context = MysteryContext()

    mock_output = (
        "## Description\n"
        "A noir detective story in 1940s Shanghai.\n"
        "\n"
        "## Title\n"
        "Shanghai Shadows\n"
        "\n"
        "## Concept\n"
        "Hardboiled noir.\n"
    )

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=_run_output(mock_output))

        agent = PlannerAgent(context=context, prompt="noir mystery")
        await agent.run()

        assert agent.suggested_description == "A noir detective story in 1940s Shanghai."
        assert agent.suggested_title == "Shanghai Shadows"


@pytest.mark.asyncio
async def test_mystery_validation_agent_rounds():
    """MysteryValidationAgent should change based on round."""
    context = MysteryContext()

    agent_r1 = MysteryValidationAgent(
        context=context, book_token="bk_test", validation_round=1,
    )
    agent_r2 = MysteryValidationAgent(
        context=context, book_token="bk_test", validation_round=2,
    )

    assert agent_r1.name == "MysteryValidationAgent-R1"
    assert agent_r2.name == "MysteryValidationAgent-R2"

    sp_r1 = agent_r1.system_prompt()
    sp_r2 = agent_r2.system_prompt()
    assert "Round 1" in sp_r1
    assert "Round 2" in sp_r2

    msg_r1 = agent_r1.initial_message()
    msg_r2 = agent_r2.initial_message()
    assert "preliminary validation report" in msg_r1
    assert "FINAL status report" in msg_r2
