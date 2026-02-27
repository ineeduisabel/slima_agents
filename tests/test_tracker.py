"""Tests for PipelineTracker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from slima_agents.slima.client import SlimaClient
from slima_agents.tracker import PipelineTracker, StageRecord


@pytest.fixture
def mock_slima():
    slima = AsyncMock(spec=SlimaClient)
    slima.write_file = AsyncMock()
    slima.create_file = AsyncMock()
    slima.read_file = AsyncMock()
    return slima


@pytest.fixture
def tracker(mock_slima):
    t = PipelineTracker(
        pipeline_name="test",
        book_token="bk_test",
        prompt="Test prompt",
        slima=mock_slima,
    )
    t.define_stages([
        (1, "research"),
        (2, "writing"),
        (3, "validation"),
    ])
    return t


class TestDefineStages:
    def test_creates_stage_records(self, tracker):
        assert len(tracker.stages) == 3
        assert tracker.stages[0].number == 1
        assert tracker.stages[0].name == "research"
        assert tracker.stages[0].status == "pending"

    def test_all_pending(self, tracker):
        for s in tracker.stages:
            assert s.status == "pending"


class TestStageLifecycle:
    @pytest.mark.asyncio
    async def test_stage_start(self, tracker):
        await tracker.stage_start(1)
        rec = tracker._find(1)
        assert rec.status == "running"
        assert rec.started_at != ""

    @pytest.mark.asyncio
    async def test_stage_complete(self, tracker):
        await tracker.stage_start(1)
        await tracker.stage_complete(1, notes="Done well")
        rec = tracker._find(1)
        assert rec.status == "completed"
        assert rec.completed_at != ""
        assert rec.notes == "Done well"
        assert rec.duration_s >= 0

    @pytest.mark.asyncio
    async def test_stage_failed(self, tracker):
        await tracker.stage_start(1)
        await tracker.stage_failed(1, "Something broke")
        rec = tracker._find(1)
        assert rec.status == "failed"
        assert rec.notes == "Something broke"

    @pytest.mark.asyncio
    async def test_nonexistent_stage(self, tracker):
        # Should not raise
        await tracker.stage_start(99)
        await tracker.stage_complete(99)


class TestProgressTracking:
    def test_last_completed_stage_none(self, tracker):
        assert tracker.last_completed_stage() == 0

    @pytest.mark.asyncio
    async def test_last_completed_stage(self, tracker):
        await tracker.stage_start(1)
        await tracker.stage_complete(1)
        await tracker.stage_start(2)
        await tracker.stage_complete(2)
        assert tracker.last_completed_stage() == 2

    def test_next_stage_from_start(self, tracker):
        assert tracker.next_stage() == 1

    @pytest.mark.asyncio
    async def test_next_stage_after_some(self, tracker):
        await tracker.stage_start(1)
        await tracker.stage_complete(1)
        assert tracker.next_stage() == 2

    @pytest.mark.asyncio
    async def test_next_stage_all_done(self, tracker):
        for s in tracker.stages:
            s.status = "completed"
        assert tracker.next_stage() == -1


class TestMarkdownRendering:
    def test_render_contains_pipeline_info(self, tracker):
        md = tracker._render_markdown()
        assert "# Pipeline Progress" in md
        assert "**Pipeline**: test" in md
        assert "**Prompt**: Test prompt" in md

    def test_render_contains_stages(self, tracker):
        md = tracker._render_markdown()
        assert "research" in md
        assert "writing" in md
        assert "validation" in md

    def test_render_contains_resume_info(self, tracker):
        md = tracker._render_markdown()
        assert "Last completed stage: 0" in md
        assert "Next stage to run: 1" in md


class TestMarkdownRoundTrip:
    @pytest.mark.asyncio
    async def test_parse_recovers_state(self, mock_slima):
        # Create a tracker and advance it
        t = PipelineTracker(
            pipeline_name="mystery",
            book_token="bk_abc",
            prompt="A locked room mystery",
            slima=mock_slima,
        )
        t.define_stages([
            (1, "planning"), (2, "crime_design"), (3, "characters"),
        ])
        t.status = "running"
        t.started_at = "2026-02-27T10:00:00Z"
        t.stages[0].status = "completed"
        t.stages[0].duration_s = 120.5
        t.stages[1].status = "running"

        md = t._render_markdown()

        # Parse it back
        parsed = PipelineTracker._parse_markdown(md, mock_slima, "bk_abc")
        assert parsed.pipeline_name == "mystery"
        assert parsed.status == "running"
        assert len(parsed.stages) == 3
        assert parsed.stages[0].status == "completed"
        assert parsed.stages[0].duration_s == 120.5
        assert parsed.stages[1].status == "running"
        assert parsed.last_completed_stage() == 1
        assert parsed.next_stage() == 2


class TestPipelineLifecycle:
    @pytest.mark.asyncio
    async def test_start_writes_file(self, tracker, mock_slima):
        await tracker.start()
        assert tracker.status == "running"
        assert tracker.started_at != ""
        # Should attempt to write
        assert mock_slima.write_file.called or mock_slima.create_file.called

    @pytest.mark.asyncio
    async def test_complete(self, tracker):
        await tracker.start()
        await tracker.complete()
        assert tracker.status == "completed"

    @pytest.mark.asyncio
    async def test_fail(self, tracker):
        await tracker.start()
        await tracker.fail("Pipeline error")
        assert tracker.status == "failed"


class TestLoadFromBook:
    @pytest.mark.asyncio
    async def test_returns_none_on_missing_file(self, mock_slima):
        mock_slima.read_file.side_effect = Exception("Not found")
        result = await PipelineTracker.load_from_book(mock_slima, "bk_test")
        assert result is None

    @pytest.mark.asyncio
    async def test_loads_from_content(self, mock_slima):
        md = (
            "# Pipeline Progress\n\n"
            "- **Pipeline**: mystery\n"
            "- **Status**: running\n"
            "- **Started**: 2026-02-27T10:00:00Z\n"
            "- **Prompt**: A test\n\n"
            "## Stages\n\n"
            "| # | Stage | Status | Started | Completed | Duration | Notes |\n"
            "|---|-------|--------|---------|-----------|----------|-------|\n"
            "| 1 | planning | completed | 10:00:00 | 10:05:00 | 300s | OK |\n"
            "| 2 | writing | running | 10:05:01 | — | — | |\n"
        )
        resp = MagicMock()
        resp.content = md
        mock_slima.read_file.return_value = resp

        tracker = await PipelineTracker.load_from_book(mock_slima, "bk_test")
        assert tracker is not None
        assert tracker.pipeline_name == "mystery"
        assert tracker.status == "running"
        assert len(tracker.stages) == 2
        assert tracker.last_completed_stage() == 1
        assert tracker.next_stage() == 2
