"""PlotArchitectureAgent: chapter outline, clue distribution, tension arc."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import PLOT_ARCHITECTURE_INSTRUCTIONS


class PlotArchitectureAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "PlotArchitectureAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{PLOT_ARCHITECTURE_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current Mystery Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create plot architecture files in book '{self.book_token}'.\n\n"
            "Read the existing book structure, crime design, and character files, then create "
            "detailed plot architecture files in the planning/plot/ folder as described "
            "in your instructions. Write ALL content and name ALL files/folders in the "
            "same language as the mystery context provided in your system prompt."
        )
