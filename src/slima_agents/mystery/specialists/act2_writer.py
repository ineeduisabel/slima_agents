"""Act2WriterAgent: writes chapters 5-8 (Investigation)."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import ACT2_INSTRUCTIONS


class Act2WriterAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Act2WriterAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{ACT2_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current Mystery Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to write Act 2 chapters in book '{self.book_token}'.\n\n"
            "1. Read ALL existing chapters (Act 1) for continuity.\n"
            "2. Read ALL planning files (crime design, characters, plot, setting).\n"
            "3. Write chapters 5-8 in the chapters/ folder.\n"
            "4. Each chapter should be 2000-4000 words of polished narrative prose.\n"
            "5. Include the midpoint twist as planned.\n"
            "6. Deploy red herrings and deepen the investigation.\n\n"
            "Write ALL content and name ALL files in the same language as the "
            "mystery context provided in your system prompt."
        )
