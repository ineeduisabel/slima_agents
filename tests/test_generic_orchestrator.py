"""Integration tests for the GenericOrchestrator with mocked agents."""

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
from slima_agents.progress import ProgressEmitter
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
                "token": "bk_pipeline_test",
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


def _make_agent_result(summary="Done", session_id=""):
    return AgentResult(
        summary=summary, full_output=summary, duration_s=1.0, session_id=session_id
    )


def _make_plan(**overrides) -> PipelinePlan:
    """Create a minimal valid PipelinePlan."""
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


# --- Tests ---


@pytest.mark.asyncio
async def test_orchestrator_runs_full_pipeline_with_external_plan(mock_slima):
    """Orchestrator should execute all stages when given an external plan."""
    plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=_make_agent_result())
        mock_instance.name = "WriterAgent[test]"
        MockWriter.return_value = mock_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        token = await orch.run("Write a mystery", external_plan=plan)

    assert token == "bk_pipeline_test"
    # Should have been called for each stage (2 stages)
    assert MockWriter.call_count == 2
    # Should create book
    mock_slima.create_book.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_runs_planning_when_no_external_plan(mock_slima):
    """Without external_plan, orchestrator should run GenericPlannerAgent."""
    plan = _make_plan()
    plan_json = plan.model_dump_json()

    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner, \
         patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:

        # Configure planner mock
        planner_instance = MagicMock()
        planner_instance.plan = plan
        planner_instance.run = AsyncMock(return_value=_make_agent_result())
        MockPlanner.return_value = planner_instance

        # Configure writer mock
        writer_instance = MagicMock()
        writer_instance.run = AsyncMock(return_value=_make_agent_result())
        writer_instance.name = "WriterAgent[test]"
        MockWriter.return_value = writer_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        token = await orch.run("Write a mystery")

    assert token == "bk_pipeline_test"
    MockPlanner.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_raises_on_empty_plan(mock_slima):
    """Should raise RuntimeError if planner produces no plan."""
    with patch("slima_agents.pipeline.orchestrator.GenericPlannerAgent") as MockPlanner:
        planner_instance = MagicMock()
        planner_instance.plan = None  # No plan produced
        planner_instance.run = AsyncMock(return_value=_make_agent_result())
        MockPlanner.return_value = planner_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        with pytest.raises(RuntimeError, match="failed to produce"):
            await orch.run("Write something")


@pytest.mark.asyncio
async def test_orchestrator_executes_stages_in_order(mock_slima):
    """Stages should execute in number order."""
    plan = _make_plan(
        stages=[
            StageDefinition(
                number=5, name="stage_c", display_name="C",
                instructions="I", initial_message="M",
            ),
            StageDefinition(
                number=3, name="stage_a", display_name="A",
                instructions="I", initial_message="M",
            ),
            StageDefinition(
                number=4, name="stage_b", display_name="B",
                instructions="I", initial_message="M",
            ),
        ]
    )

    call_order = []

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:

        def track_call(**kwargs):
            mock = MagicMock()
            mock.run = AsyncMock(return_value=_make_agent_result())
            mock.name = f"WriterAgent[{kwargs['stage_name']}]"
            call_order.append(kwargs["stage_name"])
            return mock

        MockWriter.side_effect = track_call

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        await orch.run("Test", external_plan=plan)

    assert call_order == ["stage_a", "stage_b", "stage_c"]


@pytest.mark.asyncio
async def test_orchestrator_runs_validation_with_session_chaining(mock_slima):
    """Validation R2 should use R1's session_id for session chaining."""
    plan = _make_plan(
        validation=ValidationDefinition(
            number=10,
            r1_instructions="Check consistency",
            r1_initial_message="Validate '{book_token}'",
            r2_instructions="Verify fixes",
            r2_initial_message="Verify '{book_token}'",
        )
    )

    writer_calls = []

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:

        def track_call(**kwargs):
            mock = MagicMock()
            session_id = "sess_r1_abc" if kwargs["stage_name"] == "validation_r1" else ""
            mock.run = AsyncMock(
                return_value=_make_agent_result(session_id=session_id)
            )
            mock.name = f"WriterAgent[{kwargs['stage_name']}]"
            writer_calls.append(kwargs)
            return mock

        MockWriter.side_effect = track_call

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        await orch.run("Test", external_plan=plan)

    # Find the validation calls
    val_calls = [c for c in writer_calls if "validation" in c["stage_name"]]
    assert len(val_calls) == 2

    r1_call = next(c for c in val_calls if c["stage_name"] == "validation_r1")
    r2_call = next(c for c in val_calls if c["stage_name"] == "validation_r2")

    # R2 should chain from R1's session
    assert r2_call.get("resume_session") == "sess_r1_abc"
    # R1 should not have resume_session
    assert not r1_call.get("resume_session")


@pytest.mark.asyncio
async def test_orchestrator_runs_polish_stage(mock_slima):
    """Polish stage should run after main stages."""
    plan = _make_plan(
        polish_stage=StageDefinition(
            number=11,
            name="polish",
            display_name="Polish",
            instructions="Polish everything",
            initial_message="Polish '{book_token}'",
        )
    )

    stage_names = []

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:

        def track_call(**kwargs):
            mock = MagicMock()
            mock.run = AsyncMock(return_value=_make_agent_result())
            mock.name = f"WriterAgent[{kwargs['stage_name']}]"
            stage_names.append(kwargs["stage_name"])
            return mock

        MockWriter.side_effect = track_call

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        await orch.run("Test", external_plan=plan)

    # Polish should be last
    assert stage_names[-1] == "polish"


@pytest.mark.asyncio
async def test_orchestrator_saves_plan_to_book(mock_slima):
    """Orchestrator should save pipeline-plan.json to the book."""
    plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=_make_agent_result())
        mock_instance.name = "WriterAgent[test]"
        MockWriter.return_value = mock_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        await orch.run("Test", external_plan=plan)

    # Find the create_file call for pipeline-plan.json
    plan_calls = [
        c
        for c in mock_slima.create_file.call_args_list
        if "pipeline-plan.json" in str(c)
    ]
    assert len(plan_calls) == 1


@pytest.mark.asyncio
async def test_orchestrator_saves_context_snapshots(mock_slima):
    """Orchestrator should save context snapshot after each stage."""
    plan = _make_plan()

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=_make_agent_result())
        mock_instance.name = "WriterAgent[test]"
        MockWriter.return_value = mock_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        await orch.run("Test", external_plan=plan)

    # write_file should be called for context snapshots + tracker
    snapshot_calls = [
        c
        for c in mock_slima.write_file.call_args_list
        if "context-snapshot.json" in str(c)
    ]
    # 2 stages = 2 snapshots
    assert len(snapshot_calls) == 2


@pytest.mark.asyncio
async def test_orchestrator_chapter_summarization(mock_slima):
    """Stages with summarize_chapters should trigger chapter summary."""
    plan = _make_plan(
        context_sections=["concept", "crime_design", "characters", "act1_summary"],
        stages=[
            StageDefinition(
                number=3,
                name="act1_writing",
                display_name="Act 1",
                instructions="Write act 1",
                initial_message="Write in '{book_token}'",
                summarize_chapters=True,
                summary_section="act1_summary",
            ),
        ],
        file_paths={"chapters_prefix": "chapters"},
    )

    # Set up book structure with chapters
    mock_slima.get_book_structure = AsyncMock(
        return_value=[
            {
                "name": "chapters",
                "kind": "folder",
                "position": 0,
                "children": [
                    {"name": "01.md", "kind": "file", "position": 0},
                    {"name": "02.md", "kind": "file", "position": 1},
                ],
            }
        ]
    )
    mock_slima.read_file = AsyncMock(
        return_value=MagicMock(content="Chapter content here...")
    )

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=_make_agent_result())
        mock_instance.name = "WriterAgent[test]"
        MockWriter.return_value = mock_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        await orch.run("Test", external_plan=plan)

    # Context should have act1_summary populated
    result = await orch.context.read("act1_summary")
    assert "chapters/01.md" in result or "Chapter content" in result


@pytest.mark.asyncio
async def test_orchestrator_resume_mode(mock_slima):
    """Resume mode should skip completed stages and continue."""
    plan = _make_plan()

    # Set up progress.md for resume (stages 1-3 done, resume from 4)
    progress_md = """# Pipeline Progress

- **Pipeline**: mystery
- **Status**: running
- **Started**: 2024-01-01T00:00:00Z
- **Prompt**: Test

## Stages

| # | Stage | Status | Started | Completed | Duration | Notes |
|---|-------|--------|---------|-----------|----------|-------|
| 1 | planning | completed | 00:00:00 | 00:01:00 | 60.0s |  |
| 2 | book_setup | completed | 00:01:00 | 00:01:30 | 30.0s |  |
| 3 | crime_design | completed | 00:01:30 | 00:05:00 | 210.0s |  |
| 4 | characters | pending | — | — | — |  |

## Resume Info

Last completed stage: 3
Next stage to run: 4"""

    # Mock read_file to return appropriate content based on path
    async def mock_read_file(book_token, path):
        if path == "agent-log/progress.md":
            return MagicMock(content=progress_md)
        elif path == "agent-log/pipeline-plan.json":
            return MagicMock(content=plan.model_dump_json())
        elif path == "agent-log/context-snapshot.json":
            snapshot = {
                "_allowed_sections": ["concept", "crime_design", "characters", "book_structure"],
                "user_prompt": "Test",
                "concept": "The crime...",
                "crime_design": "Crime design details...",
            }
            return MagicMock(content=json.dumps(snapshot))
        return MagicMock(content="")

    mock_slima.read_file = AsyncMock(side_effect=mock_read_file)

    stage_names = []

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:

        def track_call(**kwargs):
            mock = MagicMock()
            mock.run = AsyncMock(return_value=_make_agent_result())
            mock.name = f"WriterAgent[{kwargs['stage_name']}]"
            stage_names.append(kwargs["stage_name"])
            return mock

        MockWriter.side_effect = track_call

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        token = await orch.run("Test", resume_book="bk_resume_test")

    assert token == "bk_resume_test"
    # Should only run stage 4 (characters), not stage 3 (crime_design)
    assert "characters" in stage_names
    assert "crime_design" not in stage_names
    # Should not create a new book
    mock_slima.create_book.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_resume_all_done(mock_slima):
    """Resume should return immediately if all stages are completed."""
    progress_md = """# Pipeline Progress

- **Pipeline**: mystery
- **Status**: completed
- **Started**: 2024-01-01T00:00:00Z
- **Prompt**: Test

## Stages

| # | Stage | Status | Started | Completed | Duration | Notes |
|---|-------|--------|---------|-----------|----------|-------|
| 1 | planning | completed | 00:00:00 | 00:01:00 | 60.0s |  |
| 2 | book_setup | completed | 00:01:00 | 00:01:30 | 30.0s |  |
| 3 | crime_design | completed | 00:01:30 | 00:05:00 | 210.0s |  |

## Resume Info

Last completed stage: 3
Next stage to run: -1"""

    mock_slima.read_file = AsyncMock(
        return_value=MagicMock(content=progress_md)
    )

    orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
    token = await orch.run("Test", resume_book="bk_done")

    assert token == "bk_done"
    mock_slima.create_book.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_creates_tracker_from_plan(mock_slima):
    """Tracker should include all stages from the plan."""
    plan = _make_plan(
        stages=[
            StageDefinition(
                number=3, name="s1", display_name="S1",
                instructions="I", initial_message="M",
            ),
            StageDefinition(
                number=4, name="s2", display_name="S2",
                instructions="I", initial_message="M",
            ),
        ],
        validation=ValidationDefinition(
            number=5,
            r1_instructions="R1",
            r1_initial_message="R1 go",
            r2_instructions="R2",
            r2_initial_message="R2 go",
        ),
        polish_stage=StageDefinition(
            number=6, name="polish", display_name="Polish",
            instructions="P", initial_message="M",
        ),
    )

    with patch("slima_agents.pipeline.orchestrator.WriterAgent") as MockWriter:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=_make_agent_result())
        mock_instance.name = "WriterAgent[test]"
        MockWriter.return_value = mock_instance

        orch = GenericOrchestrator(slima_client=mock_slima, console=MagicMock())
        await orch.run("Test", external_plan=plan)

    # Verify tracker was written (write_file calls for progress.md)
    progress_calls = [
        c for c in mock_slima.write_file.call_args_list
        if "progress.md" in str(c)
    ]
    assert len(progress_calls) > 0
