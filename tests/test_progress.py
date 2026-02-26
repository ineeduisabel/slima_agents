"""Tests for ProgressEmitter NDJSON output."""

from __future__ import annotations

import json
from io import StringIO

from slima_agents.progress import ProgressEmitter


def _make_emitter() -> tuple[ProgressEmitter, StringIO]:
    """Create an enabled emitter writing to a StringIO buffer."""
    buf = StringIO()
    return ProgressEmitter(enabled=True, _stream=buf), buf


def _parse_events(buf: StringIO) -> list[dict]:
    """Parse all NDJSON lines from buffer."""
    buf.seek(0)
    return [json.loads(line) for line in buf if line.strip()]


class TestEmitterDisabled:
    def test_no_output_when_disabled(self):
        buf = StringIO()
        emitter = ProgressEmitter(enabled=False, _stream=buf)
        emitter.pipeline_start("test", 12)
        emitter.stage_start(1, "research", ["ResearchAgent"])
        emitter.agent_start(1, "ResearchAgent")
        emitter.agent_complete(1, "ResearchAgent", duration_s=10.0)
        emitter.book_created("bk_test", "Title")
        emitter.file_created("path.md")
        emitter.error("something broke")
        emitter.pipeline_complete("bk_test", 100.0)
        assert buf.getvalue() == ""


class TestEmitterOutput:
    def test_writes_valid_ndjson(self):
        emitter, buf = _make_emitter()
        emitter.pipeline_start("test prompt", 12)
        emitter.stage_start(1, "research", ["ResearchAgent"])
        emitter.agent_start(1, "ResearchAgent")
        emitter.agent_complete(1, "ResearchAgent", duration_s=10.5, summary="Done")
        emitter.pipeline_complete("bk_test", 100.0)

        events = _parse_events(buf)
        assert len(events) == 5
        # Each line should be valid JSON with event and timestamp
        for ev in events:
            assert "event" in ev
            assert "timestamp" in ev

    def test_pipeline_start_schema(self):
        emitter, buf = _make_emitter()
        emitter.pipeline_start("海賊王世界觀", 12)
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "pipeline_start"
        assert ev["prompt"] == "海賊王世界觀"
        assert ev["total_stages"] == 12

    def test_stage_start_schema(self):
        emitter, buf = _make_emitter()
        emitter.stage_start(4, "foundation", ["CosmologyAgent", "GeographyAgent"])
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "stage_start"
        assert ev["stage"] == 4
        assert ev["name"] == "foundation"
        assert ev["agents"] == ["CosmologyAgent", "GeographyAgent"]

    def test_agent_complete_schema(self):
        emitter, buf = _make_emitter()
        emitter.agent_complete(
            stage=1, agent="ResearchAgent",
            duration_s=133.26, timed_out=False,
            summary="World overview generated", num_turns=5, cost_usd=0.1234,
        )
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "agent_complete"
        assert ev["stage"] == 1
        assert ev["agent"] == "ResearchAgent"
        assert ev["duration_s"] == 133.3  # rounded to 1 decimal
        assert ev["timed_out"] is False
        assert ev["summary"] == "World overview generated"
        assert ev["num_turns"] == 5
        assert ev["cost_usd"] == 0.1234

    def test_summary_truncated_at_200(self):
        emitter, buf = _make_emitter()
        long_summary = "x" * 500
        emitter.agent_complete(1, "Test", duration_s=1.0, summary=long_summary)
        events = _parse_events(buf)
        assert len(events[0]["summary"]) == 200

    def test_book_created_schema(self):
        emitter, buf = _make_emitter()
        emitter.book_created("bk_abc123", "海賊王世界觀", "一個關於海賊的世界")
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "book_created"
        assert ev["book_token"] == "bk_abc123"
        assert ev["title"] == "海賊王世界觀"
        assert ev["description"] == "一個關於海賊的世界"

    def test_file_created_schema(self):
        emitter, buf = _make_emitter()
        emitter.file_created("世界觀/宇宙觀/創世神話.md")
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "file_created"
        assert ev["path"] == "世界觀/宇宙觀/創世神話.md"

    def test_error_schema(self):
        emitter, buf = _make_emitter()
        emitter.error("Connection failed", stage=2, agent="GeographyAgent")
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "error"
        assert ev["message"] == "Connection failed"
        assert ev["stage"] == 2
        assert ev["agent"] == "GeographyAgent"

    def test_error_without_stage(self):
        emitter, buf = _make_emitter()
        emitter.error("Fatal error")
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "error"
        assert "stage" not in ev
        assert "agent" not in ev

    def test_pipeline_complete_schema(self):
        emitter, buf = _make_emitter()
        emitter.pipeline_complete("bk_abc123", total_duration_s=1800.456, success=True)
        events = _parse_events(buf)
        ev = events[0]
        assert ev["event"] == "pipeline_complete"
        assert ev["book_token"] == "bk_abc123"
        assert ev["total_duration_s"] == 1800.5  # rounded
        assert ev["success"] is True

    def test_cjk_preserved_in_json(self):
        """ensure_ascii=False should preserve CJK characters."""
        emitter, buf = _make_emitter()
        emitter.file_created("世界觀/宇宙觀/創世神話.md")
        raw = buf.getvalue()
        assert "世界觀" in raw  # not escaped as \\uXXXX

    def test_each_line_flushed(self):
        """Each event should end with newline."""
        emitter, buf = _make_emitter()
        emitter.pipeline_start("test", 12)
        emitter.stage_start(1, "research")
        raw = buf.getvalue()
        lines = raw.strip().split("\n")
        assert len(lines) == 2
