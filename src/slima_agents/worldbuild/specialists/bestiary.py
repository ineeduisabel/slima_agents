"""BestiaryAgent: creatures, monsters, supernatural beings, flora."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import BESTIARY_INSTRUCTIONS


class BestiaryAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "BestiaryAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{BESTIARY_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current World Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create bestiary files in book '{self.book_token}'.\n\n"
            "Read the existing book structure first to see what's already been created. "
            "Then create 17-30 individual creature and flora files organized in category sub-folders. "
            "Each creature/plant gets its own file with 800-1500+ words of rich detail. "
            "Write ALL content and name ALL files/folders in the "
            "same language as the world context provided in your system prompt."
        )
