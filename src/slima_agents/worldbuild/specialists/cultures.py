"""CulturesAgent: languages, religions, traditions, art."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import CULTURES_INSTRUCTIONS


class CulturesAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "CulturesAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{CULTURES_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current World Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create culture files in book '{self.book_token}'.\n\n"
            "Read the existing book structure, then create culture files. "
            "Write ALL content and name ALL files/folders in the "
            "same language as the world context provided in your system prompt."
        )
