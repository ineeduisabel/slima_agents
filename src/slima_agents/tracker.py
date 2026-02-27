"""PipelineTracker: persist pipeline progress to agent-log/progress.md in a book."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .slima.client import SlimaClient

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short_time(iso: str) -> str:
    """Extract HH:MM:SS from an ISO timestamp."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except (ValueError, AttributeError):
        return iso


@dataclass
class StageRecord:
    number: int
    name: str
    status: str = "pending"  # pending | running | completed | failed | skipped
    started_at: str = ""
    completed_at: str = ""
    duration_s: float = 0.0
    notes: str = ""


@dataclass
class PipelineTracker:
    """Track pipeline progress and persist it as Markdown in the book."""

    pipeline_name: str  # "worldbuild" | "mystery" etc.
    book_token: str
    prompt: str
    slima: "SlimaClient"
    stages: list[StageRecord] = field(default_factory=list)
    status: str = "pending"  # pending | running | completed | failed
    started_at: str = ""

    PROGRESS_PATH: str = "agent-log/progress.md"

    def define_stages(self, stage_defs: list[tuple[int, str]]) -> None:
        """Initialize stage records from (number, name) tuples."""
        self.stages = [StageRecord(number=n, name=name) for n, name in stage_defs]

    async def start(self) -> None:
        """Mark pipeline as running and write initial progress file."""
        self.status = "running"
        self.started_at = _iso_now()
        await self._write()

    async def stage_start(self, stage_number: int) -> None:
        """Mark a stage as running."""
        rec = self._find(stage_number)
        if rec:
            rec.status = "running"
            rec.started_at = _iso_now()
            await self._write()

    async def stage_complete(self, stage_number: int, notes: str = "") -> None:
        """Mark a stage as completed."""
        rec = self._find(stage_number)
        if rec:
            rec.status = "completed"
            rec.completed_at = _iso_now()
            if rec.started_at:
                try:
                    t0 = datetime.fromisoformat(rec.started_at.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(rec.completed_at.replace("Z", "+00:00"))
                    rec.duration_s = round((t1 - t0).total_seconds(), 1)
                except (ValueError, AttributeError):
                    pass
            if notes:
                rec.notes = notes
            await self._write()

    async def stage_failed(self, stage_number: int, error: str) -> None:
        """Mark a stage as failed."""
        rec = self._find(stage_number)
        if rec:
            rec.status = "failed"
            rec.completed_at = _iso_now()
            rec.notes = error[:200]
            await self._write()

    async def complete(self) -> None:
        """Mark the entire pipeline as completed."""
        self.status = "completed"
        await self._write()

    async def fail(self, error: str) -> None:
        """Mark the entire pipeline as failed."""
        self.status = "failed"
        await self._write()

    def last_completed_stage(self) -> int:
        """Return the number of the last completed stage, or 0 if none."""
        completed = [s.number for s in self.stages if s.status == "completed"]
        return max(completed) if completed else 0

    def next_stage(self) -> int:
        """Return the number of the next pending stage, or -1 if all done."""
        for s in sorted(self.stages, key=lambda s: s.number):
            if s.status in ("pending", "running", "failed"):
                return s.number
        return -1

    def _find(self, stage_number: int) -> StageRecord | None:
        for s in self.stages:
            if s.number == stage_number:
                return s
        return None

    def _render_markdown(self) -> str:
        """Render current state as Markdown."""
        lines = [
            "# Pipeline Progress",
            "",
            f"- **Pipeline**: {self.pipeline_name}",
            f"- **Status**: {self.status}",
            f"- **Started**: {self.started_at}",
            f"- **Prompt**: {self.prompt[:200]}",
            "",
            "## Stages",
            "",
            "| # | Stage | Status | Started | Completed | Duration | Notes |",
            "|---|-------|--------|---------|-----------|----------|-------|",
        ]
        for s in sorted(self.stages, key=lambda s: s.number):
            dur = f"{s.duration_s}s" if s.duration_s else "—"
            lines.append(
                f"| {s.number} | {s.name} | {s.status} "
                f"| {_short_time(s.started_at)} | {_short_time(s.completed_at)} "
                f"| {dur} | {s.notes} |"
            )
        lines.extend([
            "",
            "## Resume Info",
            "",
            f"Last completed stage: {self.last_completed_stage()}",
            f"Next stage to run: {self.next_stage()}",
        ])
        return "\n".join(lines)

    async def _write(self) -> None:
        """Write progress Markdown to the book."""
        content = self._render_markdown()
        try:
            await self.slima.write_file(
                self.book_token,
                path=self.PROGRESS_PATH,
                content=content,
                commit_message=f"Update pipeline progress ({self.status})",
            )
        except Exception:
            # First write — file doesn't exist yet, create it
            try:
                await self.slima.create_file(
                    self.book_token,
                    path=self.PROGRESS_PATH,
                    content=content,
                    commit_message=f"Create pipeline progress ({self.status})",
                )
            except Exception as e:
                logger.warning(f"Failed to write pipeline progress: {e}")

    @classmethod
    async def load_from_book(
        cls, slima: "SlimaClient", book_token: str
    ) -> PipelineTracker | None:
        """Load tracker state from an existing progress file in the book."""
        try:
            resp = await slima.read_file(book_token, cls.PROGRESS_PATH)
            content = resp.content if hasattr(resp, "content") else str(resp)
            return cls._parse_markdown(content, slima, book_token)
        except Exception:
            return None

    @classmethod
    def _parse_markdown(
        cls, content: str, slima: "SlimaClient", book_token: str
    ) -> PipelineTracker:
        """Parse a progress Markdown file back into a PipelineTracker."""
        tracker = cls(
            pipeline_name="",
            book_token=book_token,
            prompt="",
            slima=slima,
        )

        for line in content.split("\n"):
            if line.startswith("- **Pipeline**:"):
                tracker.pipeline_name = line.split(":", 1)[1].strip()
            elif line.startswith("- **Status**:"):
                tracker.status = line.split(":", 1)[1].strip()
            elif line.startswith("- **Started**:"):
                tracker.started_at = line.split(":", 1)[1].strip()
            elif line.startswith("- **Prompt**:"):
                tracker.prompt = line.split(":", 1)[1].strip()

        # Parse stage table rows
        stages: list[StageRecord] = []
        in_table = False
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("| # |"):
                in_table = True
                continue
            if stripped.startswith("|---|"):
                continue
            if in_table and stripped.startswith("|"):
                parts = [p.strip() for p in stripped.split("|")]
                # parts[0] is empty (before first |), parts[-1] is empty (after last |)
                parts = [p for p in parts if p != ""]
                if len(parts) >= 6:
                    try:
                        number = int(parts[0])
                    except (ValueError, IndexError):
                        continue
                    rec = StageRecord(
                        number=number,
                        name=parts[1],
                        status=parts[2],
                        notes=parts[6] if len(parts) > 6 else "",
                    )
                    # Parse duration
                    dur_str = parts[5]
                    if dur_str != "—":
                        m = re.match(r"([\d.]+)s", dur_str)
                        if m:
                            rec.duration_s = float(m.group(1))
                    stages.append(rec)
            elif in_table and not stripped.startswith("|"):
                in_table = False

        tracker.stages = stages
        return tracker
