"""Act3WriterAgent: writes chapters 9-12 (Resolution)."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import ACT3_INSTRUCTIONS


class Act3WriterAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Act3WriterAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{ACT3_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current Mystery Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to write Act 3 chapters in book '{self.book_token}'.\n\n"
            "1. Read ALL existing chapters (Act 1 + Act 2) for continuity.\n"
            "2. Read ALL planning files, especially the crime design and evidence chain.\n"
            "3. Write chapters 9-12 in the chapters/ folder.\n"
            "4. The reveal must match the planned crime exactly.\n"
            "5. Reference specific clues from earlier chapters.\n"
            "6. Each chapter should be 2000-4000 words of polished narrative prose.\n\n"
            "Write ALL content and name ALL files in the same language as the "
            "mystery context provided in your system prompt."
        )
