"""ItemsAgent: artifacts, weapons, materials, notable objects."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import ITEMS_INSTRUCTIONS


class ItemsAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "ItemsAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{ITEMS_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current World Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create item files in book '{self.book_token}'.\n\n"
            "Read the existing book structure first to see what's already been created. "
            "Then create 10-18 individual item files organized in category sub-folders. "
            "Each item gets its own file with 800-1500+ words of rich detail. "
            "Write ALL content and name ALL files/folders in the "
            "same language as the world context provided in your system prompt."
        )
