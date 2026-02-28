"""AskAgent: lightweight prompt-through agent for ad-hoc queries."""

from __future__ import annotations

from .base import BaseAgent
from .tools import SLIMA_MCP_ALL_READ_TOOLS, SLIMA_MCP_TOOLS


class AskAgent(BaseAgent):
    """Passes a user prompt directly to claude with Slima MCP tools.

    Unlike worldbuild specialists, this agent does not use WorldContext
    content or pipeline stages. It is a simple one-shot query agent.
    """

    def __init__(
        self,
        *,
        prompt: str = "",
        writable: bool = False,
        custom_system_prompt: str | None = None,
        **kwargs,
    ):
        kwargs.setdefault("timeout", 300)
        super().__init__(**kwargs)
        self._prompt = prompt
        self._writable = writable
        self._custom_system_prompt = custom_system_prompt

    @property
    def name(self) -> str:
        return "AskAgent"

    def system_prompt(self) -> str:
        lines = [
            "You are a helpful assistant with access to Slima book management tools.",
            "Help the user query, inspect, or manage their books.",
            "Always respond in the same language as the user's prompt.",
        ]
        if self._custom_system_prompt:
            lines.append(f"\n{self._custom_system_prompt}")
        if self.book_token:
            lines.append(f"\nTarget book token: {self.book_token}")
        return "\n".join(lines)

    def initial_message(self) -> str:
        return self._prompt

    def allowed_tools(self) -> list[str]:
        if self._writable:
            return SLIMA_MCP_TOOLS
        return SLIMA_MCP_ALL_READ_TOOLS
