"""Tests for all specialist agents (worldbuild + mystery).

Verifies each agent's name, system_prompt content, initial_message,
and allowed_tools without needing to run ClaudeRunner.
"""

from __future__ import annotations

import pytest

from slima_agents.agents.context import WorldContext
from slima_agents.agents.tools import SLIMA_MCP_TOOLS
from slima_agents.mystery.context import MysteryContext

# Worldbuild agents
from slima_agents.worldbuild.research import ResearchAgent
from slima_agents.worldbuild.validator import ValidationAgent
from slima_agents.worldbuild.specialists.cosmology import CosmologyAgent
from slima_agents.worldbuild.specialists.geography import GeographyAgent
from slima_agents.worldbuild.specialists.history import HistoryAgent
from slima_agents.worldbuild.specialists.peoples import PeoplesAgent
from slima_agents.worldbuild.specialists.cultures import CulturesAgent
from slima_agents.worldbuild.specialists.power_structures import PowerStructuresAgent
from slima_agents.worldbuild.specialists.characters import CharactersAgent
from slima_agents.worldbuild.specialists.items import ItemsAgent
from slima_agents.worldbuild.specialists.bestiary import BestiaryAgent
from slima_agents.worldbuild.specialists.narrative import NarrativeAgent

# Mystery agents
from slima_agents.mystery.planner import PlannerAgent as MysteryPlannerAgent
from slima_agents.mystery.validator import MysteryValidationAgent
from slima_agents.mystery.specialists.crime_design import CrimeDesignAgent
from slima_agents.mystery.specialists.characters import MysteryCharactersAgent
from slima_agents.mystery.specialists.plot_architecture import PlotArchitectureAgent
from slima_agents.mystery.specialists.setting import SettingAgent
from slima_agents.mystery.specialists.act1_writer import Act1WriterAgent
from slima_agents.mystery.specialists.act2_writer import Act2WriterAgent
from slima_agents.mystery.specialists.act3_writer import Act3WriterAgent
from slima_agents.mystery.specialists.polish import PolishAgent


# ============================================================
# Helpers
# ============================================================


def _world_ctx() -> WorldContext:
    return WorldContext()


def _mystery_ctx() -> MysteryContext:
    return MysteryContext()


# ============================================================
# Worldbuild Specialists
# ============================================================


class TestResearchAgent:
    def test_name(self):
        agent = ResearchAgent(context=_world_ctx(), prompt="test")
        assert agent.name == "ResearchAgent"

    def test_no_tools(self):
        agent = ResearchAgent(context=_world_ctx(), prompt="test")
        assert agent.allowed_tools() == []

    def test_system_prompt_nonempty(self):
        agent = ResearchAgent(context=_world_ctx(), prompt="build a world")
        sp = agent.system_prompt()
        assert len(sp) > 100

    def test_initial_message_contains_prompt(self):
        agent = ResearchAgent(context=_world_ctx(), prompt="dragon world")
        msg = agent.initial_message()
        assert "dragon world" in msg


class TestCosmologyAgent:
    def test_name(self):
        agent = CosmologyAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "CosmologyAgent"

    def test_has_write_tools(self):
        agent = CosmologyAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS

    def test_system_prompt_contains_book_token(self):
        agent = CosmologyAgent(context=_world_ctx(), book_token="bk_abc")
        assert "bk_abc" in agent.system_prompt()

    def test_initial_message_contains_book_token(self):
        agent = CosmologyAgent(context=_world_ctx(), book_token="bk_abc")
        assert "bk_abc" in agent.initial_message()


class TestGeographyAgent:
    def test_name(self):
        agent = GeographyAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "GeographyAgent"

    def test_has_write_tools(self):
        agent = GeographyAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestHistoryAgent:
    def test_name(self):
        agent = HistoryAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "HistoryAgent"

    def test_has_write_tools(self):
        agent = HistoryAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestPeoplesAgent:
    def test_name(self):
        agent = PeoplesAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "PeoplesAgent"

    def test_has_write_tools(self):
        agent = PeoplesAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestCulturesAgent:
    def test_name(self):
        agent = CulturesAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "CulturesAgent"

    def test_has_write_tools(self):
        agent = CulturesAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestPowerStructuresAgent:
    def test_name(self):
        agent = PowerStructuresAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "PowerStructuresAgent"

    def test_has_write_tools(self):
        agent = PowerStructuresAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestCharactersAgent:
    def test_name(self):
        agent = CharactersAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "CharactersAgent"

    def test_has_write_tools(self):
        agent = CharactersAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS

    def test_initial_message_mentions_characters(self):
        agent = CharactersAgent(context=_world_ctx(), book_token="bk_test")
        msg = agent.initial_message().lower()
        assert "character" in msg


class TestItemsAgent:
    def test_name(self):
        agent = ItemsAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "ItemsAgent"

    def test_has_write_tools(self):
        agent = ItemsAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestBestiaryAgent:
    def test_name(self):
        agent = BestiaryAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "BestiaryAgent"

    def test_has_write_tools(self):
        agent = BestiaryAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestNarrativeAgent:
    def test_name(self):
        agent = NarrativeAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "NarrativeAgent"

    def test_has_write_tools(self):
        agent = NarrativeAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestValidationAgent:
    def test_name_r1(self):
        agent = ValidationAgent(context=_world_ctx(), book_token="bk_test", validation_round=1)
        assert agent.name == "ValidationAgent-R1"

    def test_name_r2(self):
        agent = ValidationAgent(context=_world_ctx(), book_token="bk_test", validation_round=2)
        assert agent.name == "ValidationAgent-R2"

    def test_default_round(self):
        agent = ValidationAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.name == "ValidationAgent-R1"

    def test_has_write_tools(self):
        agent = ValidationAgent(context=_world_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS

    def test_r1_system_prompt_differs_from_r2(self):
        r1 = ValidationAgent(context=_world_ctx(), book_token="bk_x", validation_round=1)
        r2 = ValidationAgent(context=_world_ctx(), book_token="bk_x", validation_round=2)
        assert r1.system_prompt() != r2.system_prompt()


# ============================================================
# Mystery Specialists
# ============================================================


class TestMysteryPlannerAgent:
    def test_name(self):
        agent = MysteryPlannerAgent(context=_mystery_ctx(), prompt="test crime")
        assert agent.name == "PlannerAgent"

    def test_no_tools(self):
        agent = MysteryPlannerAgent(context=_mystery_ctx(), prompt="test")
        assert agent.allowed_tools() == []

    def test_system_prompt_nonempty(self):
        agent = MysteryPlannerAgent(context=_mystery_ctx(), prompt="locked room")
        sp = agent.system_prompt()
        assert len(sp) > 100

    def test_initial_message_contains_prompt(self):
        agent = MysteryPlannerAgent(context=_mystery_ctx(), prompt="locked room")
        msg = agent.initial_message()
        assert "locked room" in msg


class TestCrimeDesignAgent:
    def test_name(self):
        agent = CrimeDesignAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.name == "CrimeDesignAgent"

    def test_has_write_tools(self):
        agent = CrimeDesignAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS

    def test_system_prompt_contains_book_token(self):
        agent = CrimeDesignAgent(context=_mystery_ctx(), book_token="bk_xyz")
        assert "bk_xyz" in agent.system_prompt()


class TestMysteryCharactersAgent:
    def test_name(self):
        agent = MysteryCharactersAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.name == "MysteryCharactersAgent"

    def test_has_write_tools(self):
        agent = MysteryCharactersAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestPlotArchitectureAgent:
    def test_name(self):
        agent = PlotArchitectureAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.name == "PlotArchitectureAgent"

    def test_has_write_tools(self):
        agent = PlotArchitectureAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestSettingAgent:
    def test_name(self):
        agent = SettingAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.name == "SettingAgent"

    def test_has_write_tools(self):
        agent = SettingAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestAct1WriterAgent:
    def test_name(self):
        agent = Act1WriterAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.name == "Act1WriterAgent"

    def test_has_write_tools(self):
        agent = Act1WriterAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS

    def test_initial_message_mentions_chapters(self):
        agent = Act1WriterAgent(context=_mystery_ctx(), book_token="bk_test")
        msg = agent.initial_message().lower()
        assert "chapter" in msg or "ch" in msg or "1" in msg


class TestAct2WriterAgent:
    def test_name(self):
        agent = Act2WriterAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.name == "Act2WriterAgent"

    def test_has_write_tools(self):
        agent = Act2WriterAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestAct3WriterAgent:
    def test_name(self):
        agent = Act3WriterAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.name == "Act3WriterAgent"

    def test_has_write_tools(self):
        agent = Act3WriterAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS


class TestMysteryValidationAgent:
    def test_name_r1(self):
        agent = MysteryValidationAgent(context=_mystery_ctx(), book_token="bk_test", validation_round=1)
        assert agent.name == "MysteryValidationAgent-R1"

    def test_name_r2(self):
        agent = MysteryValidationAgent(context=_mystery_ctx(), book_token="bk_test", validation_round=2)
        assert agent.name == "MysteryValidationAgent-R2"

    def test_has_write_tools(self):
        agent = MysteryValidationAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS

    def test_r1_system_prompt_differs_from_r2(self):
        r1 = MysteryValidationAgent(context=_mystery_ctx(), book_token="bk_x", validation_round=1)
        r2 = MysteryValidationAgent(context=_mystery_ctx(), book_token="bk_x", validation_round=2)
        assert r1.system_prompt() != r2.system_prompt()


class TestPolishAgent:
    def test_name(self):
        agent = PolishAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.name == "PolishAgent"

    def test_has_write_tools(self):
        agent = PolishAgent(context=_mystery_ctx(), book_token="bk_test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS

    def test_initial_message_mentions_index(self):
        agent = PolishAgent(context=_mystery_ctx(), book_token="bk_test")
        msg = agent.initial_message().lower()
        assert "index" in msg or "readme" in msg or "summar" in msg


# ============================================================
# Cross-cutting: all agents with MCP should include book_token
# ============================================================


_WORLDBUILD_AGENTS = [
    (CosmologyAgent, _world_ctx),
    (GeographyAgent, _world_ctx),
    (HistoryAgent, _world_ctx),
    (PeoplesAgent, _world_ctx),
    (CulturesAgent, _world_ctx),
    (PowerStructuresAgent, _world_ctx),
    (CharactersAgent, _world_ctx),
    (ItemsAgent, _world_ctx),
    (BestiaryAgent, _world_ctx),
    (NarrativeAgent, _world_ctx),
]

_MYSTERY_AGENTS = [
    (CrimeDesignAgent, _mystery_ctx),
    (MysteryCharactersAgent, _mystery_ctx),
    (PlotArchitectureAgent, _mystery_ctx),
    (SettingAgent, _mystery_ctx),
    (Act1WriterAgent, _mystery_ctx),
    (Act2WriterAgent, _mystery_ctx),
    (Act3WriterAgent, _mystery_ctx),
    (PolishAgent, _mystery_ctx),
]


@pytest.mark.parametrize(
    "agent_cls, ctx_fn",
    _WORLDBUILD_AGENTS + _MYSTERY_AGENTS,
    ids=[cls.__name__ for cls, _ in _WORLDBUILD_AGENTS + _MYSTERY_AGENTS],
)
def test_mcp_agent_system_prompt_has_book_token(agent_cls, ctx_fn):
    """All MCP agents should include book_token in system_prompt."""
    agent = agent_cls(context=ctx_fn(), book_token="bk_unique_42")
    assert "bk_unique_42" in agent.system_prompt()


@pytest.mark.parametrize(
    "agent_cls, ctx_fn",
    _WORLDBUILD_AGENTS + _MYSTERY_AGENTS,
    ids=[cls.__name__ for cls, _ in _WORLDBUILD_AGENTS + _MYSTERY_AGENTS],
)
def test_mcp_agent_initial_message_has_book_token(agent_cls, ctx_fn):
    """All MCP agents should include book_token in initial_message."""
    agent = agent_cls(context=ctx_fn(), book_token="bk_unique_42")
    assert "bk_unique_42" in agent.initial_message()
