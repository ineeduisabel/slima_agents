"""Tests for the GenericPlannerAgent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.base import AgentResult
from slima_agents.pipeline.context import DynamicContext
from slima_agents.pipeline.models import PipelinePlan, StageDefinition, ValidationDefinition
from slima_agents.pipeline.planner import GenericPlannerAgent, _parse_plan


# --- Helpers ---


def _make_plan_json(**overrides) -> str:
    """Create a valid PipelinePlan JSON string."""
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


# --- _parse_plan ---


def test_parse_plan_raw_json():
    """Should parse raw JSON without fences."""
    plan = _parse_plan(_make_plan_json())
    assert plan is not None
    assert plan.title == "密室殺人事件"
    assert plan.genre == "mystery"


def test_parse_plan_fenced_json():
    """Should parse JSON inside ```json ... ``` fences."""
    fenced = f"```json\n{_make_plan_json()}\n```"
    plan = _parse_plan(fenced)
    assert plan is not None
    assert plan.title == "密室殺人事件"


def test_parse_plan_fenced_no_lang():
    """Should parse JSON inside ``` ... ``` fences without language tag."""
    fenced = f"```\n{_make_plan_json()}\n```"
    plan = _parse_plan(fenced)
    assert plan is not None


def test_parse_plan_with_surrounding_text():
    """Should extract JSON from text with leading/trailing content."""
    text = f"Here is the plan:\n\n{_make_plan_json()}\n\nThat's it."
    plan = _parse_plan(text)
    assert plan is not None
    assert plan.title == "密室殺人事件"


def test_parse_plan_empty_text():
    """Should return None for empty text."""
    assert _parse_plan("") is None
    assert _parse_plan("   ") is None


def test_parse_plan_invalid_json():
    """Should return None for invalid JSON."""
    assert _parse_plan("not json at all") is None


def test_parse_plan_valid_json_but_wrong_schema():
    """Should return None for valid JSON that doesn't match PipelinePlan."""
    assert _parse_plan('{"foo": "bar"}') is None


def test_parse_plan_with_validation():
    """Should parse plan with validation definition."""
    plan_json = _make_plan_json(
        validation=dict(
            number=10,
            r1_instructions="Check",
            r1_initial_message="R1 go",
            r2_instructions="Verify",
            r2_initial_message="R2 go",
        )
    )
    plan = _parse_plan(plan_json)
    assert plan is not None
    assert plan.validation is not None
    assert plan.validation.number == 10


def test_parse_plan_with_polish():
    """Should parse plan with polish stage."""
    plan_json = _make_plan_json(
        polish_stage=dict(
            number=11,
            name="polish",
            display_name="Polish",
            instructions="Polish everything",
            initial_message="Polish '{book_token}'",
        )
    )
    plan = _parse_plan(plan_json)
    assert plan is not None
    assert plan.polish_stage is not None


# --- GenericPlannerAgent ---


def test_planner_name():
    agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
    assert agent.name == "GenericPlannerAgent"


def test_planner_no_tools():
    agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
    assert agent.allowed_tools() == []


def test_planner_system_prompt_contains_schema():
    """System prompt should include the PipelinePlan JSON schema."""
    agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
    prompt = agent.system_prompt()
    assert "PipelinePlan" in prompt
    assert "StageDefinition" in prompt or "stages" in prompt


def test_planner_initial_message_contains_prompt():
    agent = GenericPlannerAgent(context=_make_context(), prompt="寫密室推理")
    msg = agent.initial_message()
    assert "寫密室推理" in msg


@pytest.mark.asyncio
async def test_planner_run_parses_plan():
    """After run(), planner.plan should be populated."""
    from slima_agents.agents.claude_runner import RunOutput

    plan_json = _make_plan_json()
    mock_output = RunOutput(text=plan_json, num_turns=1, cost_usd=0.01, session_id="s1")

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = GenericPlannerAgent(context=_make_context(), prompt="寫密室推理")
        result = await agent.run()

        assert agent.plan is not None
        assert agent.plan.title == "密室殺人事件"
        assert isinstance(result, AgentResult)


@pytest.mark.asyncio
async def test_planner_run_handles_unparseable():
    """If output is not valid JSON, plan should be None."""
    from slima_agents.agents.claude_runner import RunOutput

    mock_output = RunOutput(text="I can't produce JSON sorry", num_turns=1, cost_usd=0.01)

    with patch("slima_agents.agents.base.ClaudeRunner") as MockRunner:
        MockRunner.run = AsyncMock(return_value=mock_output)

        agent = GenericPlannerAgent(context=_make_context(), prompt="Test")
        await agent.run()

        assert agent.plan is None
