"""Act1WriterAgent: writes chapters 1-4 (Setup)."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import ACT1_INSTRUCTIONS


class Act1WriterAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Act1WriterAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{ACT1_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current Mystery Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to write Act 1 chapters in book '{self.book_token}'.\n\n"
            "1. Read ALL planning files (crime design, characters, plot, setting).\n"
            "2. Write chapters 1-4 in the chapters/ folder.\n"
            "3. Each chapter should be 2000-4000 words of polished narrative prose.\n"
            "4. Plant clues subtly as described in the clue distribution plan.\n"
            "5. End each chapter with a hook that compels the reader to continue.\n\n"
            "Write ALL content and name ALL files in the same language as the "
            "mystery context provided in your system prompt."
        )
