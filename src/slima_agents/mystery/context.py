"""Shared mystery context passed between agents."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class MysteryContext:
    """In-memory shared state for the mystery pipeline.

    Thread-safe via asyncio.Lock. Each section is a plain string
    that agents can append to or replace.
    """

    user_prompt: str = ""
    concept: str = ""               # PlannerAgent: core concept, sub-genre, style
    crime_design: str = ""          # Crime design: who, how, why, evidence chain
    characters: str = ""            # Detective, suspects, victim, relationship web
    plot_architecture: str = ""     # Chapter outline, clue distribution, red herrings
    setting: str = ""               # Scenes, locations, atmosphere
    act1_summary: str = ""          # Act 1 writing summary (for continuity)
    act2_summary: str = ""          # Act 2
    act3_summary: str = ""          # Act 3
    validation_report: str = ""     # Consistency check results
    book_structure: str = ""        # Current file tree

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    SECTIONS: tuple[str, ...] = (
        "concept",
        "crime_design",
        "characters",
        "plot_architecture",
        "setting",
        "act1_summary",
        "act2_summary",
        "act3_summary",
        "validation_report",
        "book_structure",
    )

    async def read(self, section: str) -> str:
        if section not in self.SECTIONS:
            return f"Unknown section: {section}. Valid: {', '.join(self.SECTIONS)}"
        async with self._lock:
            return getattr(self, section)

    async def write(self, section: str, content: str) -> str:
        if section not in self.SECTIONS:
            return f"Unknown section: {section}. Valid: {', '.join(self.SECTIONS)}"
        async with self._lock:
            setattr(self, section, content)
        return f"Updated context section '{section}'"

    async def append(self, section: str, content: str) -> str:
        if section not in self.SECTIONS:
            return f"Unknown section: {section}. Valid: {', '.join(self.SECTIONS)}"
        async with self._lock:
            current = getattr(self, section)
            setattr(self, section, current + "\n" + content if current else content)
        return f"Appended to context section '{section}'"

    def to_snapshot(self) -> dict[str, str]:
        """Serialize non-empty sections to a JSON-safe dict for persistence."""
        data: dict[str, str] = {}
        if self.user_prompt:
            data["user_prompt"] = self.user_prompt
        for section in self.SECTIONS:
            value = getattr(self, section)
            if value:
                data[section] = value
        return data

    def from_snapshot(self, data: dict[str, str]) -> None:
        """Restore context from a snapshot dict."""
        self.user_prompt = data.get("user_prompt", "")
        for section in self.SECTIONS:
            if section in data:
                setattr(self, section, data[section])

    def serialize_for_prompt(self) -> str:
        """Render all non-empty sections as a string for agent system prompts."""
        parts = []

        if self.user_prompt:
            parts.append(f"## User Request\n{self.user_prompt}")

        for section in self.SECTIONS:
            value = getattr(self, section)
            if value:
                header = section.replace("_", " ").title()
                parts.append(f"## {header}\n{value}")
        if not parts:
            return "(No mystery context populated yet.)"
        return "\n\n".join(parts)
