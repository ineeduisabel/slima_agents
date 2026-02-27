"""Tests for GenericPlannerAgent upgrade: source_book + revise()."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.base import AgentResult
from slima_agents.agents.tools import SLIMA_MCP_ALL_READ_TOOLS
from slima_agents.pipeline.context import DynamicContext
from slima_agents.pipeline.planner import GenericPlannerAgent, _parse_plan


# --- Helpers ---


def _make_plan_json(**overrides) -> str:
    defaults = dict(
        title="密室殺人事件",
        description="A locked-room mystery",
        genre="mystery",
        language="zh",
        concept_summary="The victim was found...",
        context_sections=["concept", "crime_design", "characters"],
        stages=[
            dict(
                number=1,
                name="crime_design",
                display_name="犯罪設計",
                instructions="Design the crime in detail.",
                initial_message="Create files in book '{book_token}'.",
            ),
        ],
        file_paths={"planning_prefix": "規劃"},
    )
    defaults.update(overrides)
    return json.dumps(defaults, ensure_ascii=False)


def _make_context() -> DynamicContext:
    return DynamicContext(allowed_sections=["concept"])


def _mock_run_output(text: str, session_id: str = "sess_123"):
    from slima_agents.agents.claude_runner import RunOutput
    return RunOutput(text=text, num_turns=1, cost_usd=0.01, session_id=session_id)


# --- source_book param ---


def test_planner_no_source_book_no_tools():
    """Without source_book, planner should have no MCP tools."""
    agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
    assert agent.allowed_tools() == []


def test_planner_with_source_book_has_read_tools():
    """With source_book, planner should get SLIMA_MCP_ALL_READ_TOOLS."""
    agent = GenericPlannerAgent(
        context=_make_context(), prompt="Test", source_book="bk_abc123"
    )
    assert agent.allowed_tools() == SLIMA_MCP_ALL_READ_TOOLS


def test_planner_source_book_stored():
    """source_book param should be stored on the agent."""
    agent = GenericPlannerAgent(
        context=_make_context(), prompt="Test", source_book="bk_xyz"
    )
    assert agent.source_book == "bk_xyz"


def test_planner_source_book_default_empty():
    """source_book should default to empty string."""
    agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
    assert agent.source_book == ""


# --- system prompt with source book ---


def test_planner_system_prompt_no_source_book():
    """Without source_book, system prompt should not contain source book token."""
    agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
    prompt = agent.system_prompt()
    assert "read-only MCP access to book" not in prompt


def test_planner_system_prompt_with_source_book():
    """With source_book, system prompt should include Source Book section."""
    agent = GenericPlannerAgent(
        context=_make_context(), prompt="Test", source_book="bk_abc123"
    )
    prompt = agent.system_prompt()
    assert "## Source Book" in prompt
    assert "bk_abc123" in prompt
    assert "get_book_structure" in prompt
    assert "read_file" in prompt


# --- initial_message ---


def test_planner_initial_message_standard():
    """Standard mode should include the user prompt."""
    agent = GenericPlannerAgent(context=_make_context(), prompt="寫密室推理")
    msg = agent.initial_message()
    assert "寫密室推理" in msg
    assert "PipelinePlan" in msg


# --- revise() ---


@pytest.mark.asyncio
async def test_planner_revise_uses_session_chaining():
    """revise() should set resume_session before calling run."""
    plan_json = _make_plan_json()
    mock_output = _mock_run_output(plan_json, session_id="sess_v2")

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
        result = await agent.revise("請加入更多角色", session_id="sess_v1")

        # Should have called runner with resume_session
        call_kwargs = MockRunner.run.call_args.kwargs
        assert call_kwargs.get("resume_session") == "sess_v1"


@pytest.mark.asyncio
async def test_planner_revise_parses_revised_plan():
    """revise() should parse the revised plan output."""
    plan_json = _make_plan_json(title="修改版密室殺人")
    mock_output = _mock_run_output(plan_json, session_id="sess_v2")

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
        result = await agent.revise("請修改標題", session_id="sess_v1")

        assert agent.plan is not None
        assert agent.plan.title == "修改版密室殺人"
        assert result.session_id == "sess_v2"


@pytest.mark.asyncio
async def test_planner_revise_initial_message_contains_feedback():
    """During revision, initial_message should include the feedback."""
    plan_json = _make_plan_json()
    mock_output = _mock_run_output(plan_json)

    captured_prompts = []

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        async def capture_run(**kwargs):
            captured_prompts.append(kwargs.get("prompt", ""))
            return mock_output

        MockRunner.run = AsyncMock(side_effect=capture_run)

        agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
        await agent.revise("請加入更多角色", session_id="sess_v1")

        assert len(captured_prompts) == 1
        assert "請加入更多角色" in captured_prompts[0]


@pytest.mark.asyncio
async def test_planner_revise_handles_unparseable():
    """If revision output is not valid JSON, plan should be None."""
    mock_output = _mock_run_output("I couldn't do it", session_id="sess_v2")

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
        result = await agent.revise("Change stuff", session_id="sess_v1")

        assert agent.plan is None


@pytest.mark.asyncio
async def test_planner_revise_with_source_book():
    """revise() should work with source_book set."""
    plan_json = _make_plan_json(source_book="bk_abc123", action_type="rewrite")
    mock_output = _mock_run_output(plan_json, session_id="sess_v2")

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = GenericPlannerAgent(
            context=_make_context(), prompt="重寫", source_book="bk_abc123"
        )
        result = await agent.revise("多加點懸念", session_id="sess_v1")

        assert agent.plan is not None
        assert agent.plan.source_book == "bk_abc123"


# --- run() still works ---


@pytest.mark.asyncio
async def test_planner_run_still_works():
    """Standard run() should still work as before."""
    plan_json = _make_plan_json()
    mock_output = _mock_run_output(plan_json)

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = GenericPlannerAgent(context=_make_context(), prompt="寫密室推理")
        result = await agent.run()

        assert agent.plan is not None
        assert agent.plan.title == "密室殺人事件"
        assert isinstance(result, AgentResult)


@pytest.mark.asyncio
async def test_planner_run_with_source_book():
    """run() with source_book should pass read tools."""
    plan_json = _make_plan_json()
    mock_output = _mock_run_output(plan_json)

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = GenericPlannerAgent(
            context=_make_context(), prompt="重寫這本書",
            source_book="bk_abc123",
        )
        result = await agent.run()

        call_kwargs = MockRunner.run.call_args.kwargs
        assert any("read_file" in t for t in call_kwargs.get("allowed_tools", []))
