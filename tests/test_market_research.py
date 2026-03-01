"""Tests for MarketResearchAgent and the `research` CLI command.

Covers:
- Agent unit tests: name, tools, system_prompt, initial_message
- CLI tests: help, config error, integration with mocked agent
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from slima_agents.agents.base import AgentResult
from slima_agents.agents.claude_runner import RunOutput
from slima_agents.agents.context import WorldContext
from slima_agents.agents.research import MarketResearchAgent
from slima_agents.agents.tools import SLIMA_MCP_TOOLS
from slima_agents.cli import main
from slima_agents.config import ConfigError


# ============================================================
# Helpers
# ============================================================


def _run_output(text: str = "Done", num_turns: int = 1, cost_usd: float = 0.01) -> RunOutput:
    return RunOutput(text=text, num_turns=num_turns, cost_usd=cost_usd)


def _mock_config(**overrides):
    cfg = MagicMock()
    cfg.slima_api_token = overrides.get("token", "tok_test_12345678")
    cfg.slima_base_url = overrides.get("base_url", "https://api.slima.ai")
    cfg.model = overrides.get("model", "claude-opus-4-6")
    return cfg


@pytest.fixture
def runner():
    return CliRunner()


# ============================================================
# Agent Unit Tests
# ============================================================


class TestMarketResearchAgentName:
    def test_name(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="test")
        assert agent.name == "MarketResearchAgent"


class TestMarketResearchAgentTools:
    def test_has_write_tools(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="test")
        assert agent.allowed_tools() == SLIMA_MCP_TOOLS

    def test_includes_create_and_write(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="test")
        tools = agent.allowed_tools()
        assert "mcp__slima__create_file" in tools
        assert "mcp__slima__write_file" in tools


class TestMarketResearchAgentSystemPrompt:
    def test_contains_book_token(self):
        agent = MarketResearchAgent(
            context=WorldContext(), book_token="bk_test99", prompt="AI market"
        )
        sp = agent.system_prompt()
        assert "bk_test99" in sp

    def test_mentions_market_research(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="test")
        sp = agent.system_prompt()
        assert "market research" in sp.lower()

    def test_mentions_report_structure(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="test")
        sp = agent.system_prompt()
        assert "executive-summary" in sp
        assert "market-analysis" in sp
        assert "recommendations" in sp

    def test_nonempty(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="test")
        assert len(agent.system_prompt()) > 100


class TestMarketResearchAgentInitialMessage:
    def test_contains_prompt(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="AI coding tools")
        msg = agent.initial_message()
        assert "AI coding tools" in msg

    def test_contains_book_token(self):
        agent = MarketResearchAgent(
            context=WorldContext(), book_token="bk_abc", prompt="test"
        )
        msg = agent.initial_message()
        assert "bk_abc" in msg

    def test_without_book_token(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="test")
        msg = agent.initial_message()
        assert "Book:" not in msg


class TestMarketResearchAgentTimeout:
    def test_default_timeout(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="test")
        assert agent.timeout == 600

    def test_custom_timeout(self):
        agent = MarketResearchAgent(context=WorldContext(), prompt="test", timeout=300)
        assert agent.timeout == 300


class TestMarketResearchAgentRun:
    @pytest.mark.asyncio
    async def test_run_returns_agent_result(self):
        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(
                return_value=_run_output("Market report complete.", num_turns=3)
            )

            agent = MarketResearchAgent(
                context=WorldContext(), book_token="bk_test", prompt="AI market"
            )
            result = await agent.run()

            assert isinstance(result, AgentResult)
            assert "Market report complete" in result.full_output
            assert result.num_turns == 3
            MockRunner.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_passes_tools(self):
        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=_run_output("Done"))

            agent = MarketResearchAgent(
                context=WorldContext(), book_token="bk_test", prompt="test"
            )
            await agent.run()

            call_kwargs = MockRunner.run.call_args.kwargs
            assert call_kwargs["allowed_tools"] == SLIMA_MCP_TOOLS

    @pytest.mark.asyncio
    async def test_run_passes_system_prompt(self):
        with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=_run_output("Done"))

            agent = MarketResearchAgent(
                context=WorldContext(), book_token="bk_xyz", prompt="SaaS"
            )
            await agent.run()

            call_kwargs = MockRunner.run.call_args.kwargs
            assert "bk_xyz" in call_kwargs["system_prompt"]
            assert "market research" in call_kwargs["system_prompt"].lower()


# ============================================================
# CLI Tests
# ============================================================


class TestResearchCLIHelp:
    def test_help(self, runner):
        result = runner.invoke(main, ["research", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.output
        assert "--book" in result.output
        assert "--json-progress" in result.output
        assert "market research" in result.output.lower()

    def test_appears_in_main_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "research" in result.output


class TestResearchCLIConfigError:
    def test_config_error_exits_1(self, runner):
        with patch("slima_agents.cli.Config.load", side_effect=ConfigError("no token")):
            result = runner.invoke(main, ["research", "test prompt"])
        assert result.exit_code == 1
        assert "Config error:" in result.output


class TestResearchCLIIntegration:
    def test_creates_book_and_runs_agent(self, runner):
        """Full flow: Config → SlimaClient → create_book → agent → done."""
        mock_cfg = _mock_config()
        mock_book = MagicMock()
        mock_book.token = "bk_new123"
        mock_book.title = "Market Research: AI tools"

        with patch("slima_agents.cli.Config.load", return_value=mock_cfg):
            with patch("slima_agents.cli.SlimaClient") as MockClient:
                ctx = AsyncMock()
                ctx.create_book = AsyncMock(return_value=mock_book)
                MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
                    MockRunner.run = AsyncMock(
                        return_value=_run_output("Report done.", num_turns=2, cost_usd=0.05)
                    )
                    result = runner.invoke(main, ["research", "AI tools market"])

        assert result.exit_code == 0
        assert "bk_new123" in result.output
        assert "Done!" in result.output
        ctx.create_book.assert_called_once()

    def test_uses_existing_book(self, runner):
        """--book flag should skip book creation."""
        mock_cfg = _mock_config()

        with patch("slima_agents.cli.Config.load", return_value=mock_cfg):
            with patch("slima_agents.cli.SlimaClient") as MockClient:
                ctx = AsyncMock()
                MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
                    MockRunner.run = AsyncMock(
                        return_value=_run_output("Report done.")
                    )
                    result = runner.invoke(
                        main, ["research", "--book", "bk_existing", "competitor analysis"]
                    )

        assert result.exit_code == 0
        assert "Done!" in result.output
        # Should NOT call create_book
        ctx.create_book.assert_not_called()

    def test_json_progress_emits_events(self, runner):
        """--json-progress should emit NDJSON events to stdout."""
        mock_cfg = _mock_config()
        mock_book = MagicMock()
        mock_book.token = "bk_json_test"
        mock_book.title = "Market Research: test"

        with patch("slima_agents.cli.Config.load", return_value=mock_cfg):
            with patch("slima_agents.cli.SlimaClient") as MockClient:
                ctx = AsyncMock()
                ctx.create_book = AsyncMock(return_value=mock_book)
                MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
                    MockRunner.run = AsyncMock(
                        return_value=_run_output("Done.")
                    )
                    result = runner.invoke(
                        main, ["research", "--json-progress", "test"]
                    )

        assert result.exit_code == 0
        # NDJSON events should be in stdout
        assert "pipeline_start" in result.output
        assert "stage_start" in result.output
        assert "agent_complete" in result.output
        assert "pipeline_complete" in result.output
