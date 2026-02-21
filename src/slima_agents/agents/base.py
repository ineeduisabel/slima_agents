"""BaseAgent: executes agent prompts via the claude CLI."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from rich.console import Console

from .claude_runner import ClaudeRunner, ClaudeRunnerError
from .context import WorldContext
from .tools import SLIMA_MCP_TOOLS

logger = logging.getLogger(__name__)
console = Console()


class AgentResult:
    """Result returned when an agent finishes."""

    def __init__(
        self,
        summary: str,
        full_output: str = "",
        files_created: list[str] | None = None,
        timed_out: bool = False,
    ):
        self.summary = summary
        self.full_output = full_output
        self.files_created = files_created or []
        self.timed_out = timed_out

    def __repr__(self) -> str:
        return f"AgentResult(summary={self.summary!r}, files={self.files_created}, timed_out={self.timed_out})"


class BaseAgent(ABC):
    """Abstract base for all agents. Subclasses define prompts and tool sets.

    Each agent runs via the claude CLI which handles tool execution through MCP.
    """

    def __init__(
        self,
        context: WorldContext,
        book_token: str = "",
        model: str | None = None,
        timeout: int = 900,
    ):
        self.context = context
        self.book_token = book_token
        self.model = model
        self.timeout = timeout

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable agent name for logging."""

    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt including world context and domain instructions."""

    @abstractmethod
    def initial_message(self) -> str:
        """User message prompt to kick off the agent."""

    def allowed_tools(self) -> list[str]:
        """MCP tools available to this agent. Override to customize."""
        return SLIMA_MCP_TOOLS

    def _has_write_tools(self) -> bool:
        """Check if this agent has MCP tools that create/write files."""
        return any("create" in t or "write" in t for t in self.allowed_tools())

    async def run(self) -> AgentResult:
        """Execute the agent via claude CLI."""
        prompt = self.initial_message()
        system = self.system_prompt()
        tools = self.allowed_tools()
        has_write = self._has_write_tools()

        logger.info(f"[{self.name}] starting (tools: {len(tools)})")

        try:
            output = await ClaudeRunner.run(
                prompt=prompt,
                system_prompt=system,
                allowed_tools=tools,
                model=self.model,
                timeout=self.timeout,
                retry_on_timeout=not has_write,
            )

            logger.info(f"[{self.name}] finished ({len(output)} chars)")

            return AgentResult(
                summary=output[:200],
                full_output=output,
            )

        except ClaudeRunnerError as e:
            if "Timed out" in str(e) and has_write:
                # For MCP agents, timeout is partial success — files are already
                # saved in Slima via MCP tool calls. Don't treat as failure.
                logger.warning(
                    f"[{self.name}] timed out after {self.timeout}s, "
                    f"but files were likely created via MCP tools. Treating as partial success."
                )
                return AgentResult(
                    summary=f"(timeout after {self.timeout}s — partial completion, files already saved)",
                    full_output="",
                    timed_out=True,
                )
            # For non-timeout errors or agents without write tools, re-raise
            raise
