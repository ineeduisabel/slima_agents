"""NDJSON progress event emitter for machine-readable pipeline output."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, TextIO

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProgressEmitter:
    """Emits NDJSON progress events to a stream (default: stdout).

    When ``enabled=False``, all emit methods are no-ops (zero overhead).
    """

    enabled: bool = False
    _stream: TextIO = field(default_factory=lambda: sys.stdout)

    def _emit(self, event: str, **data: Any) -> None:
        if not self.enabled:
            return
        payload = {"event": event, "timestamp": _iso_now(), **data}
        self._stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._stream.flush()

    # -- Pipeline lifecycle --------------------------------------------------

    def pipeline_start(self, prompt: str, total_stages: int) -> None:
        self._emit("pipeline_start", prompt=prompt, total_stages=total_stages)

    def pipeline_complete(
        self,
        book_token: str,
        total_duration_s: float,
        success: bool = True,
    ) -> None:
        self._emit(
            "pipeline_complete",
            book_token=book_token,
            total_duration_s=round(total_duration_s, 1),
            success=success,
        )

    # -- Stage lifecycle -----------------------------------------------------

    def stage_start(self, stage: int, name: str, agents: list[str] | None = None) -> None:
        self._emit("stage_start", stage=stage, name=name, agents=agents or [])

    def stage_complete(self, stage: int, name: str, duration_s: float) -> None:
        self._emit("stage_complete", stage=stage, name=name, duration_s=round(duration_s, 1))

    # -- Agent lifecycle -----------------------------------------------------

    def agent_start(self, stage: int, agent: str) -> None:
        self._emit("agent_start", stage=stage, agent=agent)

    def agent_complete(
        self,
        stage: int,
        agent: str,
        duration_s: float,
        timed_out: bool = False,
        summary: str = "",
        num_turns: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        self._emit(
            "agent_complete",
            stage=stage,
            agent=agent,
            duration_s=round(duration_s, 1),
            timed_out=timed_out,
            summary=summary[:200],
            num_turns=num_turns,
            cost_usd=round(cost_usd, 4),
        )

    # -- Data events ---------------------------------------------------------

    def book_created(self, book_token: str, title: str, description: str = "") -> None:
        self._emit("book_created", book_token=book_token, title=title, description=description)

    def file_created(self, path: str) -> None:
        self._emit("file_created", path=path)

    # -- Plan lifecycle -------------------------------------------------------

    def plan_ready(
        self, plan_json: str, session_id: str, version: int = 1
    ) -> None:
        self._emit(
            "plan_ready",
            plan_json=plan_json,
            session_id=session_id,
            version=version,
        )

    def plan_approved(self, version: int = 1) -> None:
        self._emit("plan_approved", version=version)

    # -- Streaming events ----------------------------------------------------

    def tool_use(self, agent: str, tool_name: str, stage: int | None = None) -> None:
        data: dict[str, Any] = {"agent": agent, "tool_name": tool_name}
        if stage is not None:
            data["stage"] = stage
        self._emit("tool_use", **data)

    def text_delta(self, agent: str, text: str, stage: int | None = None) -> None:
        data: dict[str, Any] = {"agent": agent, "text": text}
        if stage is not None:
            data["stage"] = stage
        self._emit("text_delta", **data)

    def ask_result(
        self,
        session_id: str,
        result: str,
        num_turns: int = 0,
        cost_usd: float = 0.0,
        duration_s: float = 0.0,
    ) -> None:
        self._emit(
            "ask_result",
            session_id=session_id,
            result=result,
            num_turns=num_turns,
            cost_usd=round(cost_usd, 4),
            duration_s=round(duration_s, 2),
        )

    def make_agent_callback(
        self, agent_name: str, stage: int | None = None
    ) -> Callable[[dict], None]:
        """Factory: create an on_event callback for ClaudeRunner.

        Parses Claude stream-json ``assistant`` events and emits
        ``tool_use`` / ``text_delta`` NDJSON events.
        """

        def _callback(event: dict) -> None:
            try:
                etype = event.get("type")
                if etype != "assistant":
                    return
                msg = event.get("message", {})
                for block in msg.get("content", []):
                    btype = block.get("type")
                    if btype == "tool_use":
                        self.tool_use(agent_name, block.get("name", ""), stage)
                    elif btype == "text":
                        text = block.get("text", "")
                        if text:
                            self.text_delta(agent_name, text, stage)
            except Exception:
                logger.debug("make_agent_callback error", exc_info=True)

        return _callback

    # -- Errors --------------------------------------------------------------

    def error(self, message: str, stage: int | None = None, agent: str | None = None) -> None:
        data: dict[str, Any] = {"message": message}
        if stage is not None:
            data["stage"] = stage
        if agent is not None:
            data["agent"] = agent
        self._emit("error", **data)
