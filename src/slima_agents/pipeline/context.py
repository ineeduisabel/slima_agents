"""DynamicContext: plan-driven shared state with dynamic section names."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import PipelinePlan


class DynamicContext:
    """In-memory shared state whose sections are defined by a PipelinePlan.

    Drop-in replacement for WorldContext / MysteryContext — same interface
    (read, write, append, serialize_for_prompt, to_snapshot, from_snapshot)
    but sections are dynamic instead of hardcoded.

    ``book_structure`` is always implicitly available.
    """

    def __init__(self, allowed_sections: list[str]) -> None:
        # Ensure book_structure is always present
        self._allowed_sections: tuple[str, ...] = tuple(
            dict.fromkeys([*allowed_sections, "book_structure"])
        )
        self._data: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self.user_prompt: str = ""

    @classmethod
    def from_plan(cls, plan: "PipelinePlan") -> "DynamicContext":
        """Create a DynamicContext from a PipelinePlan."""
        return cls(allowed_sections=list(plan.context_sections))

    # --- Compatibility alias ---

    @property
    def SECTIONS(self) -> tuple[str, ...]:
        return self._allowed_sections

    # --- Core operations (same interface as WorldContext / MysteryContext) ---

    async def read(self, section: str) -> str:
        if section not in self._allowed_sections:
            return f"Unknown section: {section}. Valid: {', '.join(self._allowed_sections)}"
        async with self._lock:
            return self._data.get(section, "")

    async def write(self, section: str, content: str) -> str:
        if section not in self._allowed_sections:
            return f"Unknown section: {section}. Valid: {', '.join(self._allowed_sections)}"
        async with self._lock:
            self._data[section] = content
        return f"Updated context section '{section}'"

    async def append(self, section: str, content: str) -> str:
        if section not in self._allowed_sections:
            return f"Unknown section: {section}. Valid: {', '.join(self._allowed_sections)}"
        async with self._lock:
            current = self._data.get(section, "")
            self._data[section] = current + "\n" + content if current else content
        return f"Appended to context section '{section}'"

    # --- Serialization ---

    def serialize_for_prompt(self) -> str:
        """Render all non-empty sections as a string for agent system prompts."""
        parts: list[str] = []
        if self.user_prompt:
            parts.append(f"## User Request\n{self.user_prompt}")
        for section in self._allowed_sections:
            value = self._data.get(section, "")
            if value:
                header = section.replace("_", " ").title()
                parts.append(f"## {header}\n{value}")
        if not parts:
            return "(No context populated yet.)"
        return "\n\n".join(parts)

    def to_snapshot(self) -> dict:
        """Serialize to a JSON-safe dict for persistence."""
        data: dict = {"_allowed_sections": list(self._allowed_sections)}
        if self.user_prompt:
            data["user_prompt"] = self.user_prompt
        for section in self._allowed_sections:
            value = self._data.get(section, "")
            if value:
                data[section] = value
        return data

    def from_snapshot(self, data: dict) -> None:
        """Restore context from a snapshot dict."""
        if "_allowed_sections" in data:
            self._allowed_sections = tuple(data["_allowed_sections"])
        self.user_prompt = data.get("user_prompt", "")
        for section in self._allowed_sections:
            if section in data:
                self._data[section] = data[section]
