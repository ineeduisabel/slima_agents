"""PolishAgent: chapter summaries, character index, clue index."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import POLISH_INSTRUCTIONS


class PolishAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "PolishAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{POLISH_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current Mystery Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create supplementary files in book '{self.book_token}'.\n\n"
            "1. Read ALL files in the book (planning + chapters).\n"
            "2. Create chapter-summaries.md with concise per-chapter summaries.\n"
            "3. Create character-index.md with an alphabetical character list.\n"
            "4. Create clue-index.md (spoiler document) with every clue mapped.\n"
            "5. Create or update README.md with book overview and file structure.\n\n"
            "Write ALL content and name ALL files in the same language as the "
            "mystery context provided in your system prompt."
        )
