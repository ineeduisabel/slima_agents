"""ValidationAgent: reads all files and checks for consistency."""

from __future__ import annotations

from ..agents.base import BaseAgent
from .templates import VALIDATION_INSTRUCTIONS


class ValidationAgent(BaseAgent):
    """Reads all book files and produces a consistency report."""

    @property
    def name(self) -> str:
        return "ValidationAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{VALIDATION_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current World Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to work with book '{self.book_token}'.\n\n"
            "1. Get the book structure to see all files.\n"
            "2. Read each file and check for consistency issues.\n"
            "3. Create a consistency report in the meta folder with your findings.\n"
            "4. Fix any critical issues by editing the affected files.\n\n"
            "Write the report in the same language as the existing book content."
        )
