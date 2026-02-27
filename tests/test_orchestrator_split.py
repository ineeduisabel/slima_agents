"""Tests for GenericOrchestrator split: plan() / revise_plan() / execute()."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slima_agents.agents.base import AgentResult
from slima_agents.pipeline.context import DynamicContext
from slima_agents.pipeline.models import (
    PipelinePlan,
    StageDefinition,
    ValidationDefinition,
)
from slima_agents.pipeline.orchestrator import GenericOrchestrator
from slima_agents.slima.client import SlimaClient
from slima_agents.slima.types import Book


# --- Fixtures ---


@pytest.fixture
def mock_slima():
    slima = AsyncMock(spec=SlimaClient)
    slima._base_url = "https://test.slima.app"
    slima.create_book = AsyncMock(
        return_value=Book.model_validate(
            {
                "token": "bk_split_test",
                "title": "Test Book",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
            }
        )
    )
    slima.create_file = AsyncMock()
    slima.write_file = AsyncMock()
    slima.read_file = AsyncMock(
        return_value=MagicMock(content="mock file content")
    )
    slima.get_book_structure = AsyncMock(
        return_value=[
            {
                "name": "planning",
                "kind": "folder",
                "position": 0,
                "children": [
                    {"name": "concept-overview.md", "kind": "file", "position": 0}
                ],
            }
        ]
    )
    return slima


def _make_agent_result(summary="Done", session_id="sess_abc"):
    return AgentResult(
        summary=summary, full_output=summary, duration_s=1.0, session_id=session_id
    )


def _make_plan(**overrides) -> PipelinePlan:
    defaults = dict(
        title="Test Book",
        description="A test",
        genre="mystery",
        language="zh",
        concept_summary="The crime concept...",
        context_sections=["concept", "crime_design", "characters"],
        stages=[
            StageDefinition(
                number=3,
                name="crime_design",
                display_name="Crime Design",
                instructions="Design the crime",
                initial_message="Create files in '{book_token}'.",
            ),
            StageDefinition(
                number=4,
                name="characters",
                display_name="Characters",
                instructions="Design characters",
                initial_message="Create character files in '{book_token}'.",
            ),
        ],
        file_paths={"planning_prefix": "planning", "chapters_prefix": "chapters"},
    )
    defaults.update(overrides)
    return PipelinePlan(**defaults)


# --- plan() ---


@pytest.mark.asyncio
async def test_plan_returns_plan_and_session_id(mock_slima):
    """plan() should return (PipelinePlan, session_id)."""
    expected_plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner:
        planner_instance = MagicMock()
        planner_instance.plan = expected_plan
        planner_instance.run = AsyncMock(
            return_value=_make_agent_result(session_id="sess_plan_1")
        )
        MockPlanner.return_value = planner_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        plan, session_id = await orch.plan("寫密室推理")

    assert plan.title == "Test Book"
    assert session_id == "sess_plan_1"


@pytest.mark.asyncio
async def test_plan_with_source_book(mock_slima):
    """plan() with source_book should pass it to GenericPlannerAgent."""
    expected_plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner:
        planner_instance = MagicMock()
        planner_instance.plan = expected_plan
        planner_instance.run = AsyncMock(
            return_value=_make_agent_result(session_id="sess_plan_sb")
        )
        MockPlanner.return_value = planner_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        plan, session_id = await orch.plan("重寫這本書", source_book="bk_source")

    # Verify source_book was passed to the planner constructor
    call_kwargs = MockPlanner.call_args.kwargs
    assert call_kwargs.get("source_book") == "bk_source"


@pytest.mark.asyncio
async def test_plan_raises_on_failure(mock_slima):
    """plan() should raise RuntimeError if planner produces no plan."""
    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner:
        planner_instance = MagicMock()
        planner_instance.plan = None
        planner_instance.run = AsyncMock(return_value=_make_agent_result())
        MockPlanner.return_value = planner_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        with pytest.raises(RuntimeError, match="failed to produce"):
            await orch.plan("Bad prompt")


# --- revise_plan() ---


@pytest.mark.asyncio
async def test_revise_plan_returns_revised_plan(mock_slima):
    """revise_plan() should return a revised plan and new session_id."""
    revised_plan = _make_plan(title="Revised Book")

    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner:
        planner_instance = MagicMock()
        planner_instance.plan = revised_plan
        planner_instance.revise = AsyncMock(
            return_value=_make_agent_result(session_id="sess_v2")
        )
        MockPlanner.return_value = planner_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        plan, session_id = await orch.revise_plan(
            prompt="寫密室推理",
            feedback="加入更多角色",
            session_id="sess_v1",
        )

    assert plan.title == "Revised Book"
    assert session_id == "sess_v2"


@pytest.mark.asyncio
async def test_revise_plan_passes_feedback_and_session(mock_slima):
    """revise_plan() should pass feedback and session_id to planner.revise()."""
    revised_plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner:
        planner_instance = MagicMock()
        planner_instance.plan = revised_plan
        planner_instance.revise = AsyncMock(
            return_value=_make_agent_result(session_id="sess_v2")
        )
        MockPlanner.return_value = planner_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        await orch.revise_plan(
            prompt="Test",
            feedback="More characters",
            session_id="sess_v1",
        )

    planner_instance.revise.assert_called_once_with("More characters", "sess_v1")


@pytest.mark.asyncio
async def test_revise_plan_with_source_book(mock_slima):
    """revise_plan() with source_book should pass it to planner."""
    revised_plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner:
        planner_instance = MagicMock()
        planner_instance.plan = revised_plan
        planner_instance.revise = AsyncMock(
            return_value=_make_agent_result(session_id="sess_v2")
        )
        MockPlanner.return_value = planner_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        await orch.revise_plan(
            prompt="重寫",
            feedback="More",
            session_id="sess_v1",
            source_book="bk_src",
        )

    call_kwargs = MockPlanner.call_args.kwargs
    assert call_kwargs.get("source_book") == "bk_src"


@pytest.mark.asyncio
async def test_revise_plan_raises_on_failure(mock_slima):
    """revise_plan() should raise if revision fails to produce plan."""
    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner:
        planner_instance = MagicMock()
        planner_instance.plan = None
        planner_instance.revise = AsyncMock(return_value=_make_agent_result())
        MockPlanner.return_value = planner_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        with pytest.raises(RuntimeError, match="failed to produce"):
            await orch.revise_plan(
                prompt="Test",
                feedback="Revise",
                session_id="sess_v1",
            )


# --- execute() ---


@pytest.mark.asyncio
async def test_execute_runs_all_stages(mock_slima):
    """execute() should run all stages from the plan."""
    plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=_make_agent_result())
        mock_instance.name = "WriterAgent[test]"
        MockWriter.return_value = mock_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        token = await orch.execute("Test", plan)

    assert token == "bk_split_test"
    assert MockWriter.call_count == 2
    mock_slima.create_book.assert_called_once()


@pytest.mark.asyncio
async def test_execute_skips_book_creation_on_resume(mock_slima):
    """execute() with resume_book should not create a new book."""
    plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=_make_agent_result())
        mock_instance.name = "WriterAgent[test]"
        MockWriter.return_value = mock_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        token = await orch.execute("Test", plan, resume_book="bk_existing")

    assert token == "bk_existing"
    mock_slima.create_book.assert_not_called()


@pytest.mark.asyncio
async def test_execute_with_validation(mock_slima):
    """execute() should run validation stages."""
    plan = _make_plan(
        validation=ValidationDefinition(
            number=10,
            r1_instructions="Check",
            r1_initial_message="R1",
            r2_instructions="Verify",
            r2_initial_message="R2",
        )
    )

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
        def make_writer(**kwargs):
            mock = MagicMock()
            sid = "sess_r1" if kwargs.get("stage_name") == "validation_r1" else ""
            mock.run = AsyncMock(return_value=_make_agent_result(session_id=sid))
            mock.name = f"WriterAgent[{kwargs['stage_name']}]"
            return mock

        MockWriter.side_effect = make_writer

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        token = await orch.execute("Test", plan)

    assert token == "bk_split_test"
    # 2 stages + 2 validation = 4 WriterAgent calls
    assert MockWriter.call_count == 4


# --- run() backward compat ---


@pytest.mark.asyncio
async def test_run_still_works_with_external_plan(mock_slima):
    """run() with external_plan should still work."""
    plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=_make_agent_result())
        mock_instance.name = "WriterAgent[test]"
        MockWriter.return_value = mock_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        token = await orch.run("Test", external_plan=plan)

    assert token == "bk_split_test"


@pytest.mark.asyncio
async def test_run_plans_then_executes(mock_slima):
    """run() without external_plan should plan first then execute."""
    plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner, \
         patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:

        planner_instance = MagicMock()
        planner_instance.plan = plan
        planner_instance.run = AsyncMock(
            return_value=_make_agent_result(session_id="sess_plan")
        )
        MockPlanner.return_value = planner_instance

        writer_instance = MagicMock()
        writer_instance.run = AsyncMock(return_value=_make_agent_result())
        writer_instance.name = "WriterAgent[test]"
        MockWriter.return_value = writer_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        token = await orch.run("Write a mystery")

    assert token == "bk_split_test"
    MockPlanner.assert_called_once()


@pytest.mark.asyncio
async def test_run_with_source_book(mock_slima):
    """run() with source_book should pass it to planning."""
    plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner, \
         patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:

        planner_instance = MagicMock()
        planner_instance.plan = plan
        planner_instance.run = AsyncMock(
            return_value=_make_agent_result(session_id="sess_plan")
        )
        MockPlanner.return_value = planner_instance

        writer_instance = MagicMock()
        writer_instance.run = AsyncMock(return_value=_make_agent_result())
        writer_instance.name = "WriterAgent[test]"
        MockWriter.return_value = writer_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        token = await orch.run("重寫", source_book="bk_src")

    call_kwargs = MockPlanner.call_args.kwargs
    assert call_kwargs.get("source_book") == "bk_src"
