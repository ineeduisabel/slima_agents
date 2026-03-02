"""TaskAgent: configurable general-purpose agent driven by parameters."""

from __future__ import annotations

from ..templates import LANGUAGE_RULE
from .base import BaseAgent
from .tools import (
    SLIMA_MCP_ALL_READ_TOOLS,
    SLIMA_MCP_ALL_TOOLS,
    SLIMA_MCP_TOOLS,
    WEB_TOOLS,
)

_DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to Slima book management tools "
    "and web search.\n"
    "Help the user with their request.\n"
    "Always respond in the same language as the user's prompt."
)

_PLAN_FIRST_GUIDANCE = (
    "# Planning Mode\n"
    "Before executing, first create a detailed plan:\n"
    "1. Analyze the request and identify what needs to be done\n"
    "2. List the steps you will take\n"
    "3. Execute the steps one by one\n"
    "4. Summarize what was accomplished"
)

_TOOL_SETS: dict[str, list[str]] = {
    "write": [*SLIMA_MCP_TOOLS, *WEB_TOOLS],
    "read": [*SLIMA_MCP_ALL_READ_TOOLS, *WEB_TOOLS],
    "all": [*SLIMA_MCP_ALL_TOOLS, *WEB_TOOLS],
    "none": [*WEB_TOOLS],
}


class TaskAgent(BaseAgent):
    """A fully configurable agent whose behaviour is defined by constructor parameters.

    Unlike specialist agents that have fixed prompts and tool sets, TaskAgent
    can be configured at runtime to replicate any agent's behaviour.
    """

    def __init__(
        self,
        *,
        prompt: str = "",
        system_prompt_text: str = "",
        tool_set: str = "read",
        plan_first: bool = False,
        **kwargs,
    ):
        kwargs.setdefault("timeout", 3600)
        super().__init__(**kwargs)
        self._prompt = prompt
        self._system_prompt_text = system_prompt_text
        self._tool_set = tool_set
        self._plan_first = plan_first

    @property
    def name(self) -> str:
        return "TaskAgent"

    def system_prompt(self) -> str:
        parts: list[str] = []

        # 1. Language rule (always on)
        parts.append(LANGUAGE_RULE)

        # 2. Custom or default instructions
        parts.append(self._system_prompt_text or _DEFAULT_SYSTEM_PROMPT)

        # 3. Plan-first guidance (optional)
        if self._plan_first:
            parts.append(_PLAN_FIRST_GUIDANCE)

        # 4. Target book (optional)
        if self.book_token:
            parts.append(f"# Target Book\nbook_token: {self.book_token}")

        # 5. Context serialization (if context has content)
        ctx_str = self.context.serialize_for_prompt()
        if not ctx_str.startswith("(No "):
            parts.append(f"# Current Context\n{ctx_str}")

        return "\n\n".join(parts)

    def initial_message(self) -> str:
        return self._prompt

    def allowed_tools(self) -> list[str]:
        return _TOOL_SETS.get(self._tool_set, _TOOL_SETS["read"])
