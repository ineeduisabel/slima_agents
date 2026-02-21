"""PowerStructuresAgent: governments, factions, economics, military."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import POWER_STRUCTURES_INSTRUCTIONS


class PowerStructuresAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "PowerStructuresAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{POWER_STRUCTURES_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current World Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create power structure files in book '{self.book_token}'.\n\n"
            "Read the existing book structure, then create power structure files. "
            "Write ALL content and name ALL files/folders in the "
            "same language as the world context provided in your system prompt."
        )
