"""Shared world context passed between agents."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class WorldContext:
    """In-memory shared state that agents read from and write to.

    Thread-safe via asyncio.Lock. Each section is a plain string
    that agents can append to or replace.
    """

    user_prompt: str = ""
    overview: str = ""
    cosmology: str = ""
    geography: str = ""
    history: str = ""
    peoples: str = ""
    cultures: str = ""
    power_structures: str = ""
    characters: str = ""
    items_bestiary: str = ""
    narrative: str = ""
    naming_conventions: str = ""
    book_structure: str = ""

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    SECTIONS: tuple[str, ...] = (
        "overview",
        "cosmology",
        "geography",
        "history",
        "peoples",
        "cultures",
        "power_structures",
        "characters",
        "items_bestiary",
        "narrative",
        "naming_conventions",
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

    def serialize_for_prompt(self) -> str:
        """Render all non-empty sections as a string for agent system prompts."""
        parts = []

        # Always include user prompt at the top so agents know what was requested
        if self.user_prompt:
            parts.append(f"## User Request\n{self.user_prompt}")

        for section in self.SECTIONS:
            value = getattr(self, section)
            if value:
                header = section.replace("_", " ").title()
                parts.append(f"## {header}\n{value}")
        if not parts:
            return "(No world context populated yet.)"
        return "\n\n".join(parts)
