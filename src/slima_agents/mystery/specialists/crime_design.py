"""CrimeDesignAgent: detailed crime design documents."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import CRIME_DESIGN_INSTRUCTIONS


class CrimeDesignAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "CrimeDesignAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{CRIME_DESIGN_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current Mystery Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create crime design files in book '{self.book_token}'.\n\n"
            "Read the existing book structure, then create detailed crime design files "
            "in the planning/crime-design/ folder as described in your instructions. "
            "Write ALL content and name ALL files/folders in the same language as the "
            "mystery context provided in your system prompt."
        )
