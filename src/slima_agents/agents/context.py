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


class DynamicContext:
    """In-memory shared state whose sections are defined dynamically.

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
