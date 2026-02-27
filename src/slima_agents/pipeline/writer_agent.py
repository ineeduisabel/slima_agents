"""WriterAgent: generic agent that executes a single pipeline stage."""

from __future__ import annotations

from ..agents.base import BaseAgent
from ..agents.tools import SLIMA_MCP_READ_TOOLS, SLIMA_MCP_TOOLS
from ..worldbuild.templates import LANGUAGE_RULE


_TOOL_SETS: dict[str, list[str]] = {
    "write": SLIMA_MCP_TOOLS,
    "read": SLIMA_MCP_READ_TOOLS,
    "none": [],
}


class WriterAgent(BaseAgent):
    """A generic writing agent whose behaviour is fully defined by parameters.

    Replaces all specialist agents — the plan provides the instructions,
    initial message, and tool set.
    """

    def __init__(
        self,
        *,
        stage_name: str,
        stage_instructions: str,
        stage_initial_message: str,
        tool_set: str = "write",
        quality_standard: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._stage_name = stage_name
        self._stage_instructions = stage_instructions
        self._stage_initial_message = stage_initial_message
        self._tool_set = tool_set
        self._quality_standard = quality_standard

    @property
    def name(self) -> str:
        return f"WriterAgent[{self._stage_name}]"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        parts = [LANGUAGE_RULE, self._stage_instructions]
        if self._quality_standard:
            parts.append(self._quality_standard)
        parts.append(f"# Target Book\nbook_token: {self.book_token}")
        parts.append(f"# Current Context\n{ctx}")
        return "\n\n".join(parts)

    def initial_message(self) -> str:
        return self._stage_initial_message.replace("{book_token}", self.book_token)

    def allowed_tools(self) -> list[str]:
        return _TOOL_SETS.get(self._tool_set, SLIMA_MCP_TOOLS)
