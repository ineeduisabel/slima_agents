"""CharactersAgent: key figures with backstories."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import CHARACTERS_INSTRUCTIONS


class CharactersAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "CharactersAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{CHARACTERS_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current World Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create character files in book '{self.book_token}'.\n\n"
            "Read the existing book structure first to see what's already been created. "
            "Then create 15-25 individual character files organized in category sub-folders. "
            "Each character gets their own file with 1000-2000+ words of rich detail. "
            "Write ALL content and name ALL files/folders "
            "in the same language as the world context provided in your system prompt."
        )
