"""Integration tests for TaskOrchestrator with mocked TaskAgent + SlimaClient."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slima_agents.agents.base import AgentResult
from slima_agents.agents.task_models import TaskPlan, TaskStageDefinition
from slima_agents.agents.task_orchestrator import TaskOrchestrator
from slima_agents.agents.context import DynamicContext
from slima_agents.progress import ProgressEmitter
from slima_agents.slima.client import SlimaClient
from slima_agents.slima.types import Book


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_slima():
    slima = AsyncMock(spec=SlimaClient)
    slima._base_url = "https://test.slima.app"
    slima.create_book = AsyncMock(
        return_value=Book.model_validate({
            "token": "bk_task_test",
            "title": "Task Book",
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z",
        })
    )
    slima.create_file = AsyncMock()
    slima.write_file = AsyncMock()
    slima.read_file = AsyncMock(return_value=MagicMock(content="mock"))
    slima.get_book_structure = AsyncMock(return_value=[
        {"name": "agent-log", "kind": "folder", "position": 0, "children": [
            {"name": "task-plan.json", "kind": "file", "position": 0},
        ]},
    ])
    return slima


@pytest.fixture
def emitter():
    return ProgressEmitter(enabled=False)


def _result(summary: str = "Done", output: str = "", session_id: str = "sess_1") -> AgentResult:
    return AgentResult(
        summary=summary,
        full_output=output or summary,
        duration_s=1.0,
        session_id=session_id,
    )


def _plan(**overrides) -> TaskPlan:
    defaults = dict(
        title="Test Task",
        stages=[
            TaskStageDefinition(number=1, name="step1", prompt="do step 1", context_section="overview"),
            TaskStageDefinition(number=2, name="step2", prompt="do step 2", context_section="detail"),
            TaskStageDefinition(number=3, name="step3", prompt="do step 3"),
        ],
    )
    defaults.update(overrides)
    return TaskPlan(**defaults)


# ---------------------------------------------------------------------------
# Book setup
# ---------------------------------------------------------------------------


class TestBookSetup:
    @pytest.mark.asyncio
    async def test_creates_book_when_title_set(self, mock_slima, emitter):
        plan = _plan(title="New Book")
        orch = TaskOrchestrator(mock_slima, model="test-model", emitter=emitter)

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            book_token = await orch.run(plan)

        mock_slima.create_book.assert_awaited_once()
        assert book_token == "bk_task_test"

    @pytest.mark.asyncio
    async def test_uses_existing_book(self, mock_slima, emitter):
        plan = _plan(title="", book_token="bk_existing")
        orch = TaskOrchestrator(mock_slima, model="test-model", emitter=emitter)

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            book_token = await orch.run(plan)

        mock_slima.create_book.assert_not_awaited()
        assert book_token == "bk_existing"

    @pytest.mark.asyncio
    async def test_no_book_mode(self, mock_slima, emitter):
        plan = _plan(title="", book_token="")
        orch = TaskOrchestrator(mock_slima, model="test-model", emitter=emitter)

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            book_token = await orch.run(plan)

        mock_slima.create_book.assert_not_awaited()
        assert book_token == ""

    @pytest.mark.asyncio
    async def test_defers_when_creates_book_stage_exists(self, mock_slima, emitter):
        """Should NOT create book upfront when a creates_book stage exists."""
        plan = TaskPlan(
            title="My Book",
            stages=[
                TaskStageDefinition(number=1, name="brainstorm", prompt="think",
                                    tool_set="all", creates_book=True),
                TaskStageDefinition(number=2, name="write", prompt="write",
                                    tool_set="write"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result(
                output="I created the book: bk_new123 with title My Book",
                session_id="sess_1",
            ))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            book_token = await orch.run(plan)

        # Orchestrator should NOT have called create_book itself
        mock_slima.create_book.assert_not_awaited()
        # Should have captured the token from agent output
        assert book_token == "bk_new123"


# ---------------------------------------------------------------------------
# Sequential execution
# ---------------------------------------------------------------------------


class TestSequentialExecution:
    @pytest.mark.asyncio
    async def test_three_stages_run_sequentially(self, mock_slima, emitter):
        """Stages 1, 2, 3 should all execute in order."""
        call_order = []

        async def _run_side_effect():
            call_order.append(len(call_order) + 1)
            return _result(f"done-{len(call_order)}")

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(side_effect=_run_side_effect)
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test-model", emitter=emitter)
            await orch.run(_plan())

        assert len(call_order) == 3
        assert call_order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_agent_receives_correct_params(self, mock_slima, emitter):
        """TaskAgent should be created with stage-specific params."""
        created_kwargs = []

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            def _capture(**kwargs):
                inst = AsyncMock()
                inst.run = AsyncMock(return_value=_result())
                inst.name = "TaskAgent"
                created_kwargs.append(kwargs)
                return inst

            MockAgent.side_effect = _capture

            orch = TaskOrchestrator(mock_slima, model="test-model", emitter=emitter)
            await orch.run(_plan())

        assert len(created_kwargs) == 3
        assert created_kwargs[0]["prompt"] == "do step 1"
        assert created_kwargs[1]["prompt"] == "do step 2"


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


class TestParallelExecution:
    @pytest.mark.asyncio
    async def test_same_number_runs_in_parallel(self, mock_slima, emitter):
        """Stages with the same number should be gathered."""
        plan = TaskPlan(
            title="Parallel Test",
            stages=[
                TaskStageDefinition(number=1, name="research", prompt="research"),
                TaskStageDefinition(number=2, name="cosmology", prompt="cosmo", context_section="cosmo"),
                TaskStageDefinition(number=2, name="geography", prompt="geo", context_section="geo"),
                TaskStageDefinition(number=3, name="narrative", prompt="narrate"),
            ],
        )

        run_count = 0

        async def _run_side():
            nonlocal run_count
            run_count += 1
            return _result(f"result-{run_count}")

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(side_effect=_run_side)
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test-model", emitter=emitter)
            await orch.run(plan)

        # 4 stages total: 1 sequential + 2 parallel + 1 sequential
        assert run_count == 4


# ---------------------------------------------------------------------------
# Context accumulation
# ---------------------------------------------------------------------------


class TestContextAccumulation:
    @pytest.mark.asyncio
    async def test_context_section_written(self, mock_slima, emitter):
        """Stage output should be written to the configured context section."""
        plan = TaskPlan(
            title="Context Test",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p1", context_section="overview"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result("Stage 1 output", "Stage 1 full output"))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test-model", emitter=emitter)
            await orch.run(plan)

        # Context should have overview populated with structured handoff
        overview = await orch.context.read("overview")
        assert "Stage 1 full output" in overview
        assert "[Stage 1" in overview  # handoff header

    @pytest.mark.asyncio
    async def test_context_accumulates_across_stages(self, mock_slima, emitter):
        """Stage 2 should see stage 1's context."""
        plan = TaskPlan(
            title="Accum Test",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p1", context_section="overview"),
                TaskStageDefinition(number=2, name="s2", prompt="p2", context_section="detail"),
            ],
        )

        call_count = 0

        async def _run_side():
            nonlocal call_count
            call_count += 1
            return _result(f"output-{call_count}", f"full-output-{call_count}")

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(side_effect=_run_side)
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test-model", emitter=emitter)
            await orch.run(plan)

        overview = await orch.context.read("overview")
        assert "full-output-1" in overview
        assert "[Stage 1" in overview  # handoff header
        detail = await orch.context.read("detail")
        assert "full-output-2" in detail
        assert "[Stage 2" in detail  # handoff header

    @pytest.mark.asyncio
    async def test_no_context_section_skips_write(self, mock_slima, emitter):
        """Stage without context_section should not write to context."""
        plan = TaskPlan(
            title="No Context",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p1"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result("output"))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test-model", emitter=emitter)
            await orch.run(plan)

        # Context should be empty (only book_structure implicitly available)
        prompt_str = orch.context.serialize_for_prompt()
        assert "output" not in prompt_str or "Book Structure" in prompt_str


# ---------------------------------------------------------------------------
# NDJSON events
# ---------------------------------------------------------------------------


class TestNDJSONEvents:
    @pytest.mark.asyncio
    async def test_pipeline_start_emitted(self, mock_slima):
        emitter = MagicMock(spec=ProgressEmitter)
        emitter.make_agent_callback = MagicMock(return_value=None)

        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="s1", prompt="p1"),
        ])

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        emitter.pipeline_start.assert_called()

    @pytest.mark.asyncio
    async def test_pipeline_complete_emitted(self, mock_slima):
        emitter = MagicMock(spec=ProgressEmitter)
        emitter.make_agent_callback = MagicMock(return_value=None)

        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="s1", prompt="p1"),
        ])

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        emitter.pipeline_complete.assert_called_once()
        call_kwargs = emitter.pipeline_complete.call_args[1]
        assert call_kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_stage_events_emitted(self, mock_slima):
        emitter = MagicMock(spec=ProgressEmitter)
        emitter.make_agent_callback = MagicMock(return_value=None)

        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="research", prompt="p1"),
            TaskStageDefinition(number=2, name="writing", prompt="p2"),
        ])

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        # stage_start should be called for each unique number
        stage_start_calls = emitter.stage_start.call_args_list
        assert len(stage_start_calls) >= 2

    @pytest.mark.asyncio
    async def test_agent_events_emitted(self, mock_slima):
        emitter = MagicMock(spec=ProgressEmitter)
        emitter.make_agent_callback = MagicMock(return_value=None)

        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="s1", prompt="p1"),
        ])

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        emitter.agent_start.assert_called()
        emitter.agent_complete.assert_called()


# ---------------------------------------------------------------------------
# Book structure injection
# ---------------------------------------------------------------------------


class TestBookStructureInjection:
    @pytest.mark.asyncio
    async def test_structure_injected_after_group(self, mock_slima, emitter):
        """Book structure should be injected after each group when book exists."""
        plan = TaskPlan(
            title="Structure Test",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p"),
                TaskStageDefinition(number=2, name="s2", prompt="p"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        # get_book_structure called for injection + file path snapshots
        assert mock_slima.get_book_structure.await_count >= 2


# ---------------------------------------------------------------------------
# Context snapshot
# ---------------------------------------------------------------------------


class TestContextSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_saved_after_group(self, mock_slima, emitter):
        """Context snapshot should be saved after each group when book exists."""
        plan = TaskPlan(
            title="Snapshot Test",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p", context_section="overview"),
                TaskStageDefinition(number=2, name="s2", prompt="p"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        # write_file called for context snapshot (once per group with book)
        snapshot_calls = [
            c for c in mock_slima.write_file.call_args_list
            if "context-snapshot.json" in str(c)
        ]
        assert len(snapshot_calls) == 2  # 2 groups


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_agent_failure_propagates(self, mock_slima, emitter):
        """If an agent raises, the orchestrator should re-raise."""
        plan = TaskPlan(
            title="Error Test",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(side_effect=RuntimeError("agent crashed"))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            with pytest.raises(RuntimeError, match="agent crashed"):
                await orch.run(plan)

    @pytest.mark.asyncio
    async def test_error_emits_pipeline_complete_false(self, mock_slima):
        emitter = MagicMock(spec=ProgressEmitter)
        emitter.make_agent_callback = MagicMock(return_value=None)

        plan = TaskPlan(
            title="Error Test",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(side_effect=RuntimeError("boom"))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            with pytest.raises(RuntimeError):
                await orch.run(plan)

        emitter.pipeline_complete.assert_called_once()
        call_kwargs = emitter.pipeline_complete.call_args[1]
        assert call_kwargs["success"] is False


# ---------------------------------------------------------------------------
# Tracker integration
# ---------------------------------------------------------------------------


class TestTrackerIntegration:
    @pytest.mark.asyncio
    async def test_tracker_created_for_book(self, mock_slima, emitter):
        """PipelineTracker should be created when book exists."""
        plan = _plan(title="Tracker Test")

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            with patch("slima_agents.agents.task_orchestrator.PipelineTracker") as MockTracker:
                tracker_instance = AsyncMock()
                MockTracker.return_value = tracker_instance

                orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
                await orch.run(plan)

            MockTracker.assert_called_once()
            tracker_instance.start.assert_awaited_once()
            tracker_instance.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_tracker_without_book(self, mock_slima, emitter):
        """PipelineTracker should NOT be created when no book."""
        plan = _plan(title="", book_token="")

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            with patch("slima_agents.agents.task_orchestrator.PipelineTracker") as MockTracker:
                orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
                await orch.run(plan)

            MockTracker.assert_not_called()


# ---------------------------------------------------------------------------
# Group stages logic
# ---------------------------------------------------------------------------


class TestGroupStages:
    def test_groups_by_number(self):
        stages = [
            TaskStageDefinition(number=1, name="a", prompt="x"),
            TaskStageDefinition(number=2, name="b", prompt="x"),
            TaskStageDefinition(number=2, name="c", prompt="x"),
            TaskStageDefinition(number=3, name="d", prompt="x"),
        ]
        groups = TaskOrchestrator._group_stages(stages)
        assert sorted(groups.keys()) == [1, 2, 3]
        assert len(groups[1]) == 1
        assert len(groups[2]) == 2
        assert len(groups[3]) == 1

    def test_single_stage_per_group(self):
        stages = [
            TaskStageDefinition(number=1, name="a", prompt="x"),
            TaskStageDefinition(number=2, name="b", prompt="x"),
        ]
        groups = TaskOrchestrator._group_stages(stages)
        assert len(groups) == 2
        assert all(len(v) == 1 for v in groups.values())

    def test_all_same_number(self):
        stages = [
            TaskStageDefinition(number=1, name="a", prompt="x"),
            TaskStageDefinition(number=1, name="b", prompt="x"),
            TaskStageDefinition(number=1, name="c", prompt="x"),
        ]
        groups = TaskOrchestrator._group_stages(stages)
        assert len(groups) == 1
        assert len(groups[1]) == 3


# ---------------------------------------------------------------------------
# Pipeline metadata injection
# ---------------------------------------------------------------------------


class TestPipelineMetadata:
    @pytest.mark.asyncio
    async def test_pipeline_info_injected(self, mock_slima, emitter):
        """Context should contain _pipeline_info after run starts."""
        plan = TaskPlan(
            title="My Book",
            stages=[
                TaskStageDefinition(number=1, name="research", display_name="Research", prompt="p"),
                TaskStageDefinition(number=2, name="writing", display_name="Writing", prompt="p"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        info = await orch.context.read("_pipeline_info")
        assert "My Book" in info
        assert "bk_task_test" in info
        assert "Research" in info
        assert "Writing" in info
        assert "Total stages: 2" in info

    @pytest.mark.asyncio
    async def test_pipeline_info_no_book(self, mock_slima, emitter):
        """Pipeline info should show (no book) when no book created."""
        plan = TaskPlan(
            stages=[TaskStageDefinition(number=1, name="s1", prompt="p")],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result())
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        info = await orch.context.read("_pipeline_info")
        assert "(no book)" in info


# ---------------------------------------------------------------------------
# Structured handoff
# ---------------------------------------------------------------------------


class TestStructuredHandoff:
    @pytest.mark.asyncio
    async def test_handoff_has_stage_header(self, mock_slima, emitter):
        """Context section should contain stage header."""
        plan = TaskPlan(
            title="Handoff Test",
            stages=[
                TaskStageDefinition(number=1, name="research", display_name="Research", prompt="p", context_section="overview"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result("Done", "Full research output"))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        overview = await orch.context.read("overview")
        assert "[Stage 1 'Research' completed]" in overview
        assert "---" in overview
        assert "Full research output" in overview

    @pytest.mark.asyncio
    async def test_handoff_includes_new_files(self, mock_slima, emitter):
        """Handoff should list newly created files."""
        # Make get_book_structure return different results before/after
        call_count = 0

        async def _structure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                # Before stage
                return []
            else:
                # After stage: new file appeared
                return [{"name": "chapters", "kind": "folder", "position": 0, "children": [
                    {"name": "ch01.md", "kind": "file", "position": 0},
                ]}]

        mock_slima.get_book_structure = AsyncMock(side_effect=_structure)

        plan = TaskPlan(
            title="Files Test",
            stages=[
                TaskStageDefinition(number=1, name="writer", display_name="Writer", prompt="p", context_section="output", tool_set="write"),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result("Wrote chapter", "Chapter content"))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        output = await orch.context.read("output")
        assert "chapters/ch01.md" in output

    def test_build_handoff_static(self):
        """Unit test for _build_handoff."""
        stage_def = TaskStageDefinition(number=1, name="research", display_name="Research", prompt="p")
        result = _result("sum", "full output text")
        handoff = TaskOrchestrator._build_handoff(stage_def, result, {"file1.md", "file2.md"})
        assert "[Stage 1 'Research' completed]" in handoff
        assert "file1.md" in handoff
        assert "file2.md" in handoff
        assert "---" in handoff
        assert "full output text" in handoff

    def test_build_handoff_timed_out(self):
        """Handoff should note timed-out stages."""
        stage_def = TaskStageDefinition(number=1, name="s", prompt="p")
        result = AgentResult(summary="partial", full_output="partial output", duration_s=1.0, timed_out=True)
        handoff = TaskOrchestrator._build_handoff(stage_def, result, set())
        assert "timed out" in handoff

    def test_build_handoff_no_files(self):
        """Handoff without files should not include Files line."""
        stage_def = TaskStageDefinition(number=1, name="s", prompt="p")
        result = _result("done", "output")
        handoff = TaskOrchestrator._build_handoff(stage_def, result, set())
        assert "Files created" not in handoff


# ---------------------------------------------------------------------------
# Session chaining (chain_to_previous)
# ---------------------------------------------------------------------------


class TestSessionChaining:
    @pytest.mark.asyncio
    async def test_chain_passes_session_id(self, mock_slima, emitter):
        """Stage with chain_to_previous should receive previous session_id."""
        plan = TaskPlan(
            title="Chain Test",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p1"),
                TaskStageDefinition(number=2, name="s2", prompt="p2", chain_to_previous=True),
            ],
        )

        created_agents = []

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            def _make_instance(**kwargs):
                inst = AsyncMock()
                inst.run = AsyncMock(return_value=_result(session_id="sess_from_s1"))
                inst.name = "TaskAgent"
                created_agents.append(kwargs)
                return inst

            MockAgent.side_effect = _make_instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        # First agent: no resume session
        assert created_agents[0].get("resume_session", "") == ""
        # Second agent: should have session from first
        assert created_agents[1].get("resume_session") == "sess_from_s1"

    @pytest.mark.asyncio
    async def test_no_chain_gets_empty_session(self, mock_slima, emitter):
        """Stage without chain_to_previous should not get a session_id."""
        plan = TaskPlan(
            title="No Chain Test",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p1"),
                TaskStageDefinition(number=2, name="s2", prompt="p2", chain_to_previous=False),
            ],
        )

        created_agents = []

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            def _make_instance(**kwargs):
                inst = AsyncMock()
                inst.run = AsyncMock(return_value=_result(session_id="sess_abc"))
                inst.name = "TaskAgent"
                created_agents.append(kwargs)
                return inst

            MockAgent.side_effect = _make_instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        # Second agent should NOT get resume_session even though s1 produced one
        assert created_agents[1].get("resume_session", "") == ""

    @pytest.mark.asyncio
    async def test_chain_three_stages(self, mock_slima, emitter):
        """Session should chain across multiple stages."""
        plan = TaskPlan(
            title="Multi Chain",
            stages=[
                TaskStageDefinition(number=1, name="s1", prompt="p1"),
                TaskStageDefinition(number=2, name="s2", prompt="p2", chain_to_previous=True),
                TaskStageDefinition(number=3, name="s3", prompt="p3", chain_to_previous=True),
            ],
        )

        call_count = 0
        created_agents = []

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            def _make_instance(**kwargs):
                nonlocal call_count
                call_count += 1
                inst = AsyncMock()
                inst.run = AsyncMock(return_value=_result(session_id=f"sess_{call_count}"))
                inst.name = "TaskAgent"
                created_agents.append(kwargs)
                return inst

            MockAgent.side_effect = _make_instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            await orch.run(plan)

        assert created_agents[0].get("resume_session", "") == ""
        assert created_agents[1].get("resume_session") == "sess_1"
        assert created_agents[2].get("resume_session") == "sess_2"


# ---------------------------------------------------------------------------
# Deferred book creation (creates_book)
# ---------------------------------------------------------------------------


class TestCreatesBook:
    @pytest.mark.asyncio
    async def test_captures_book_token_from_output(self, mock_slima, emitter):
        """creates_book stage should extract bk_ token from agent output."""
        plan = TaskPlan(
            stages=[
                TaskStageDefinition(
                    number=1, name="brainstorm", prompt="brainstorm and create book",
                    tool_set="all", creates_book=True, context_section="brainstorm",
                ),
                TaskStageDefinition(
                    number=2, name="write", prompt="write chapter 1",
                    tool_set="write",
                ),
            ],
        )

        call_count = 0
        created_agents = []

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            def _make(**kwargs):
                nonlocal call_count
                call_count += 1
                inst = AsyncMock()
                if call_count == 1:
                    # Stage 1: agent creates a book via MCP
                    inst.run = AsyncMock(return_value=_result(
                        output="I've created the book 'Fantasy World' (bk_fantasy01). Let me outline the setting...",
                        session_id="sess_1",
                    ))
                else:
                    inst.run = AsyncMock(return_value=_result(
                        output="Chapter 1 written.",
                        session_id="sess_2",
                    ))
                inst.name = "TaskAgent"
                created_agents.append(kwargs)
                return inst

            MockAgent.side_effect = _make

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            book_token = await orch.run(plan)

        assert book_token == "bk_fantasy01"
        # Stage 2 should have received the captured book_token
        assert created_agents[1]["book_token"] == "bk_fantasy01"
        # Orchestrator should NOT have created a book itself
        mock_slima.create_book.assert_not_awaited()
        # Plan JSON should have been saved
        mock_slima.create_file.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_token_in_output(self, mock_slima, emitter):
        """If creates_book stage doesn't produce a token, book_token stays empty."""
        plan = TaskPlan(
            stages=[
                TaskStageDefinition(
                    number=1, name="brainstorm", prompt="think about ideas",
                    tool_set="none", creates_book=True,
                ),
                TaskStageDefinition(
                    number=2, name="write", prompt="write",
                    tool_set="write",
                ),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result(
                output="Here are some ideas for a fantasy novel...",
            ))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            book_token = await orch.run(plan)

        assert book_token == ""

    @pytest.mark.asyncio
    async def test_skipped_when_book_token_exists(self, mock_slima, emitter):
        """creates_book should be ignored when plan already has book_token."""
        plan = TaskPlan(
            book_token="bk_existing",
            stages=[
                TaskStageDefinition(
                    number=1, name="brainstorm", prompt="brainstorm",
                    tool_set="all", creates_book=True,
                ),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result(
                output="Created bk_shouldignore",
            ))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
            book_token = await orch.run(plan)

        # Should use the existing book, not the one from output
        assert book_token == "bk_existing"

    @pytest.mark.asyncio
    async def test_tracker_initialized_after_book_created(self, mock_slima, emitter):
        """PipelineTracker should be created after creates_book captures a token."""
        plan = TaskPlan(
            stages=[
                TaskStageDefinition(
                    number=1, name="brainstorm", prompt="create a book",
                    tool_set="all", creates_book=True,
                ),
                TaskStageDefinition(
                    number=2, name="write", prompt="write",
                    tool_set="write",
                ),
            ],
        )

        with patch("slima_agents.agents.task_orchestrator.TaskAgent") as MockAgent:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_result(
                output="Book created: bk_tracker01",
            ))
            instance.name = "TaskAgent"
            MockAgent.return_value = instance

            with patch("slima_agents.agents.task_orchestrator.PipelineTracker") as MockTracker:
                tracker_instance = AsyncMock()
                MockTracker.return_value = tracker_instance

                orch = TaskOrchestrator(mock_slima, model="test", emitter=emitter)
                await orch.run(plan)

            # Tracker should have been created (after book was captured)
            MockTracker.assert_called_once()
            tracker_instance.start.assert_awaited_once()
            tracker_instance.complete.assert_awaited_once()

    def test_extract_book_token_regex(self):
        """Unit test for _extract_book_token."""
        orch = TaskOrchestrator.__new__(TaskOrchestrator)
        assert orch._extract_book_token("Created bk_abc123 successfully") == "bk_abc123"
        assert orch._extract_book_token("bk_fantasy01 is ready") == "bk_fantasy01"
        assert orch._extract_book_token("No token here") == ""
        assert orch._extract_book_token("Token bk_ab too short") == ""  # < 6 chars after bk_
        assert orch._extract_book_token("Multiple bk_first1 and bk_second") == "bk_first1"
