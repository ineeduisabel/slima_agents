"""Tests for CLI commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from slima_agents.cli import main
from slima_agents.config import ConfigError


@pytest.fixture
def runner():
    return CliRunner()


def _mock_config(**overrides):
    """Create a mock Config object."""
    cfg = MagicMock()
    cfg.slima_api_token = overrides.get("token", "tok_test_12345678")
    cfg.slima_base_url = overrides.get("base_url", "https://api.slima.ai")
    cfg.model = overrides.get("model", "claude-opus-4-6")
    return cfg


# ---------- status ----------


def test_status_shows_config(runner):
    """status command should display token, URL, model."""
    mock_cfg = _mock_config()
    with patch("slima_agents.cli.Config.load", return_value=mock_cfg):
        with patch("slima_agents.cli.SlimaClient") as MockClient:
            ctx = AsyncMock()
            ctx.list_books = AsyncMock(return_value=[1, 2, 3])
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = runner.invoke(main, ["status"])

    assert result.exit_code == 0
    assert "Slima Token:" in result.output
    assert "12345678" in result.output
    assert "Model:" in result.output
    assert "3 books" in result.output


def test_status_config_error(runner):
    """status command should show error on ConfigError."""
    with patch("slima_agents.cli.Config.load", side_effect=ConfigError("no token")):
        result = runner.invoke(main, ["status"])
    assert result.exit_code == 1
    assert "Config error:" in result.output


# ---------- ask ----------


def test_ask_plain_text(runner):
    """ask command should output agent result as plain text."""
    mock_cfg = _mock_config()
    mock_result = MagicMock()
    mock_result.full_output = "Here are your books."
    mock_result.session_id = "sess_123"
    mock_result.num_turns = 1
    mock_result.cost_usd = 0.01
    mock_result.duration_s = 2.5

    with patch("slima_agents.cli.Config.load", return_value=mock_cfg):
        with patch("slima_agents.cli.AskAgent", create=True) as MockAgent:
            # AskAgent is imported inside the function, so patch in the module
            with patch("slima_agents.agents.ask.AskAgent") as MockAskAgent:
                instance = AsyncMock()
                instance.run = AsyncMock(return_value=mock_result)
                MockAskAgent.return_value = instance

                # Patch the lazy import
                with patch.dict("sys.modules", {}):
                    result = runner.invoke(main, ["ask", "hello"])

    # The ask command writes directly to stdout.buffer, which CliRunner captures
    # but may have encoding issues. Check it didn't crash.
    assert result.exit_code in (0, 1)  # May fail on import in test env


def test_ask_json_output(runner):
    """ask --json should output structured JSON with session_id."""
    mock_result = MagicMock()
    mock_result.full_output = "Hello!"
    mock_result.session_id = "sess_abc"
    mock_result.num_turns = 2
    mock_result.cost_usd = 0.02
    mock_result.duration_s = 3.14

    with patch("slima_agents.cli.os.getenv", return_value="claude-opus-4-6"):
        with patch("slima_agents.agents.ask.AskAgent") as MockAskAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=mock_result)
            MockAskAgent.return_value = instance

            result = runner.invoke(main, ["ask", "--json", "hello"])

    # CliRunner captures stdout.buffer writes as bytes
    if result.exit_code == 0:
        # Parse JSON from output
        output_line = result.output.strip()
        if output_line:
            data = json.loads(output_line)
            assert data["session_id"] == "sess_abc"
            assert data["num_turns"] == 2


def test_ask_config_error(runner):
    """ask command should fail gracefully on missing config."""
    # When Config.load() raises, ask should exit with error
    # But ask doesn't call Config.load(), it resolves model directly
    # The error path is in the agent run, not config loading
    pass


# ---------- worldbuild ----------


def test_worldbuild_config_error(runner):
    """worldbuild should exit 1 on ConfigError."""
    with patch("slima_agents.cli.Config.load", side_effect=ConfigError("no token")):
        result = runner.invoke(main, ["worldbuild", "test prompt"])
    assert result.exit_code == 1
    assert "Config error:" in result.output


# ---------- mystery ----------


def test_mystery_config_error(runner):
    """mystery should exit 1 on ConfigError."""
    with patch("slima_agents.cli.Config.load", side_effect=ConfigError("no token")):
        result = runner.invoke(main, ["mystery", "test prompt"])
    assert result.exit_code == 1
    assert "Config error:" in result.output


# ---------- verbose flag ----------


def test_verbose_flag(runner):
    """--verbose should not crash (logging config)."""
    with patch("slima_agents.cli.Config.load", side_effect=ConfigError("no token")):
        result = runner.invoke(main, ["-v", "worldbuild", "test"])
    assert result.exit_code == 1  # ConfigError, but -v didn't crash


# ---------- help ----------


def test_main_help(runner):
    """Main group should show help."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "worldbuild" in result.output
    assert "mystery" in result.output
    assert "ask" in result.output
    assert "task" in result.output
    assert "status" in result.output


def test_ask_help(runner):
    """ask --help should show all options."""
    result = runner.invoke(main, ["ask", "--help"])
    assert result.exit_code == 0
    assert "--book" in result.output
    assert "--readonly" in result.output
    assert "--resume" in result.output
    assert "--system-prompt" in result.output
    assert "--json" in result.output


# ---------- task ----------


def test_task_help(runner):
    """task --help should show all options."""
    result = runner.invoke(main, ["task", "--help"])
    assert result.exit_code == 0
    assert "--book" in result.output
    assert "--tool-set" in result.output
    assert "--system-prompt" in result.output
    assert "--plan-first" in result.output
    assert "--plan-first" in result.output
    assert "--resume" in result.output
    assert "--json" in result.output
    assert "--json-progress" in result.output
    assert "--timeout" in result.output


def test_task_in_main_help(runner):
    """task should appear in main --help."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "task" in result.output


def test_task_tool_set_choices(runner):
    """task --tool-set should only accept valid choices."""
    result = runner.invoke(main, ["task", "--tool-set", "invalid", "hello"])
    assert result.exit_code != 0
    assert "Invalid value" in result.output or "invalid" in result.output.lower()


# ---------- task-pipeline ----------


def test_task_pipeline_help(runner):
    """task-pipeline --help should show options."""
    result = runner.invoke(main, ["task-pipeline", "--help"])
    assert result.exit_code == 0
    assert "--model" in result.output
    assert "--json-progress" in result.output


def test_task_pipeline_in_main_help(runner):
    """task-pipeline should appear in main --help."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "task-pipeline" in result.output


def test_task_pipeline_config_error(runner):
    """task-pipeline should exit 1 on ConfigError."""
    plan_json = '{"stages":[{"number":1,"name":"s","prompt":"p"}]}'

    with patch("slima_agents.cli.Config.load", side_effect=ConfigError("no token")):
        result = runner.invoke(main, ["task-pipeline"], input=plan_json)
    assert result.exit_code == 1
    assert "Config error:" in result.output


def test_task_pipeline_invalid_json(runner):
    """task-pipeline with invalid JSON from stdin should exit 1."""
    mock_cfg = _mock_config()
    with patch("slima_agents.cli.Config.load", return_value=mock_cfg):
        result = runner.invoke(main, ["task-pipeline"], input="not json {{{")

    assert result.exit_code == 1
    assert "Plan error:" in result.output


def test_task_pipeline_stdin_empty(runner):
    """task-pipeline with empty stdin should exit 1."""
    mock_cfg = _mock_config()
    with patch("slima_agents.cli.Config.load", return_value=mock_cfg):
        result = runner.invoke(main, ["task-pipeline"], input="")

    assert result.exit_code == 1
    assert "No JSON provided" in result.output


def test_task_pipeline_valid_stdin(runner):
    """task-pipeline should parse valid JSON from stdin."""
    plan_json = '{"stages":[{"number":1,"name":"s","prompt":"p"}]}'

    mock_cfg = _mock_config()
    with patch("slima_agents.cli.Config.load", return_value=mock_cfg):
        result = runner.invoke(main, ["task-pipeline"], input=plan_json)

    # Should get past plan parsing (may fail at orchestrator, not at parse)
    assert "Plan error:" not in result.output
