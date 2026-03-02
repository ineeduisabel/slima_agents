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


# ---------- help ----------


def test_main_help(runner):
    """Main group should show help."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "task" in result.output
    assert "task-pipeline" in result.output
    assert "status" in result.output


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


# ---------- plan-build ----------


def test_plan_build_help(runner):
    """plan-build --help should show options."""
    result = runner.invoke(main, ["plan-build", "--help"])
    assert result.exit_code == 0
    assert "--model" in result.output
    assert "--json-progress" in result.output
    assert "--timeout" in result.output
    assert "PROMPT" in result.output


def test_plan_build_in_main_help(runner):
    """plan-build should appear in main --help."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "plan-build" in result.output


def _make_agent_result(full_output: str, **kw):
    """Create a mock AgentResult."""
    from slima_agents.agents.base import AgentResult
    return AgentResult(
        summary=full_output[:200],
        full_output=full_output,
        session_id=kw.get("session_id", "sess_test"),
        num_turns=kw.get("num_turns", 3),
        cost_usd=kw.get("cost_usd", 0.05),
        duration_s=kw.get("duration_s", 10.0),
    )


def test_plan_build_outputs_json(runner):
    """plan-build should output validated TaskPlan JSON to stdout."""
    plan = {
        "stages": [{"number": 1, "name": "research", "prompt": "Do research"}]
    }
    agent_output = f'```json\n{json.dumps(plan)}\n```'
    mock_result = _make_agent_result(agent_output)

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=MagicMock(
            text=agent_output, num_turns=3, cost_usd=0.05, session_id="sess_test"
        ))
        with patch("slima_agents.agents.task.TaskAgent.run", new_callable=AsyncMock, return_value=mock_result):
            result = runner.invoke(main, ["plan-build", "build a fantasy world"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "stages" in output
    assert output["stages"][0]["name"] == "research"


def test_plan_build_with_stdin(runner):
    """plan-build should accept existing plan via stdin and include it in prompt."""
    existing_plan = '{"stages":[{"number":1,"name":"old","prompt":"old task"}]}'
    new_plan = {
        "stages": [
            {"number": 1, "name": "old", "prompt": "old task"},
            {"number": 2, "name": "new", "prompt": "new task"},
        ]
    }
    agent_output = f'```json\n{json.dumps(new_plan)}\n```'
    mock_result = _make_agent_result(agent_output)

    with patch("slima_agents.agents.task.TaskAgent.run", new_callable=AsyncMock, return_value=mock_result) as mock_run:
        result = runner.invoke(
            main, ["plan-build", "add a new stage"], input=existing_plan
        )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert len(output["stages"]) == 2


def test_plan_build_invalid_output(runner):
    """plan-build should exit 1 when agent returns non-JSON."""
    mock_result = _make_agent_result("This is not JSON at all, just text.")

    with patch("slima_agents.agents.task.TaskAgent.run", new_callable=AsyncMock, return_value=mock_result):
        result = runner.invoke(main, ["plan-build", "build something"])

    assert result.exit_code == 1
    assert "JSON extraction error:" in result.output


def test_plan_build_json_progress(runner):
    """plan-build --json-progress should emit plan_build_result NDJSON event."""
    plan = {
        "stages": [{"number": 1, "name": "research", "prompt": "Do research"}]
    }
    agent_output = f'```json\n{json.dumps(plan)}\n```'
    mock_result = _make_agent_result(agent_output)

    with patch("slima_agents.agents.task.TaskAgent.run", new_callable=AsyncMock, return_value=mock_result):
        result = runner.invoke(main, ["plan-build", "--json-progress", "build a world"])

    assert result.exit_code == 0
    # stdout should contain NDJSON event(s)
    lines = [l for l in result.output.strip().split("\n") if l.strip()]
    # Find the plan_build_result event
    found = False
    for line in lines:
        event = json.loads(line)
        if event.get("event") == "plan_build_result":
            found = True
            assert "plan_json" in event
            assert "session_id" in event
            # plan_json should be valid JSON
            parsed = json.loads(event["plan_json"])
            assert "stages" in parsed
            break
    assert found, f"No plan_build_result event found in output: {result.output}"


def test_plan_build_empty_stages_validation_error(runner):
    """plan-build should exit 1 when stages array is empty."""
    bad_plan = '{"stages": []}'
    agent_output = f'```json\n{bad_plan}\n```'
    mock_result = _make_agent_result(agent_output)

    with patch("slima_agents.agents.task.TaskAgent.run", new_callable=AsyncMock, return_value=mock_result):
        result = runner.invoke(main, ["plan-build", "build something"])

    assert result.exit_code == 1
    assert "Validation error:" in result.output


def test_plan_build_validation_error(runner):
    """plan-build should exit 1 when JSON doesn't match TaskPlan schema."""
    # Valid JSON but no 'stages' field (required)
    bad_plan = '{"title": "test"}'
    agent_output = f'```json\n{bad_plan}\n```'
    mock_result = _make_agent_result(agent_output)

    with patch("slima_agents.agents.task.TaskAgent.run", new_callable=AsyncMock, return_value=mock_result):
        result = runner.invoke(main, ["plan-build", "build something"])

    assert result.exit_code == 1
    assert "Validation error:" in result.output


# ---------- verbose flag ----------


def test_verbose_flag(runner):
    """--verbose should not crash (logging config)."""
    with patch("slima_agents.cli.Config.load", side_effect=ConfigError("no token")):
        result = runner.invoke(main, ["-v", "task-pipeline"], input='{}')
    assert result.exit_code == 1  # ConfigError or plan error, but -v didn't crash
