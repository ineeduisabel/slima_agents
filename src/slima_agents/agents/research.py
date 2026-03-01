"""MarketResearchAgent: single-stage agent for market research reports.

Designed as a lightweight end-to-end test of the full stack:
Config → SlimaClient → Book creation → ClaudeRunner → MCP write → Done.
"""

from __future__ import annotations

from .base import BaseAgent
from .tools import SLIMA_MCP_TOOLS


class MarketResearchAgent(BaseAgent):
    """Creates a market research report in a Slima book.

    Single-stage agent — simpler than worldbuild (12 stages) or mystery (11),
    but exercises the same full stack: config, SlimaClient, MCP tools, progress.
    """

    def __init__(self, *, prompt: str = "", **kwargs):
        kwargs.setdefault("timeout", 600)
        super().__init__(**kwargs)
        self._prompt = prompt

    @property
    def name(self) -> str:
        return "MarketResearchAgent"

    def system_prompt(self) -> str:
        lines = [
            "You are a market research analyst. Create a concise market research report.",
            "",
            "Write your analysis as markdown files in the book using MCP tools.",
            f"Book token: {self.book_token}",
            "",
            "Structure your report:",
            "1. Create `report/executive-summary.md` — key findings and overview",
            "2. Create `report/market-analysis.md` — detailed market analysis",
            "3. Create `report/recommendations.md` — actionable recommendations",
            "",
            "Keep each file focused and well-structured with headers.",
            "Respond in the same language as the user's prompt.",
        ]
        return "\n".join(lines)

    def initial_message(self) -> str:
        parts = [f"Research topic: {self._prompt}"]
        if self.book_token:
            parts.append(f"Book: {self.book_token}")
        return "\n".join(parts)

    def allowed_tools(self) -> list[str]:
        return SLIMA_MCP_TOOLS
