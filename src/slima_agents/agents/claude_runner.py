"""ClaudeRunner: executes agent prompts via the claude CLI."""

from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
DEFAULT_TIMEOUT = 3600  # 1 hour safety net; normally finishes via stream-json result event
DEFAULT_MAX_TURNS = 50


class ClaudeRunnerError(Exception):
    """Raised when the claude CLI subprocess fails."""


class ClaudeRunner:
    """Executes prompts via `claude -p` subprocess.

    Uses --output-format stream-json to read events in real-time.
    When the final {"type":"result"} event arrives, the agent is done
    and we return immediately — no need to wait for a timeout.
    """

    @staticmethod
    async def run(
        prompt: str,
        system_prompt: str,
        allowed_tools: list[str] | None = None,
        model: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_turns: int = DEFAULT_MAX_TURNS,
        retry_on_timeout: bool = True,
    ) -> str:
        """Run a prompt through the claude CLI and return the text output.

        Args:
            prompt: The user message to send.
            system_prompt: System prompt for the agent.
            allowed_tools: List of MCP tool names (e.g. "mcp__slima__create_file").
            model: Optional model override (e.g. "claude-opus-4-6").
            timeout: Max seconds to wait (safety net, normally finishes earlier).
            max_turns: Max agentic turns (each turn = one model response).
            retry_on_timeout: Whether to retry on timeout. Set False for agents
                that create files (retry could cause duplicates).

        Returns:
            The text output from claude CLI.

        Raises:
            ClaudeRunnerError: If the subprocess fails after retries.
        """
        cmd = [
            "claude",
            "-p", prompt,
            "--verbose",
            "--output-format", "stream-json",
            "--system-prompt", system_prompt,
            "--max-turns", str(max_turns),
        ]

        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

        if model:
            cmd.extend(["--model", model])

        # Remove CLAUDECODE env var so claude CLI can run inside a Claude Code
        # session. Disable thinking to prevent it from consuming all output
        # tokens (which causes empty results with --system-prompt).
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        env["MAX_THINKING_TOKENS"] = "0"

        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            logger.debug(f"[ClaudeRunner] attempt {attempt}/{MAX_RETRIES}")
            logger.debug(
                f"[ClaudeRunner] prompt: {len(prompt)} chars, "
                f"system: {len(system_prompt)} chars, "
                f"max_turns: {max_turns}"
            )

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    limit=10 * 1024 * 1024,  # 10 MB — stream-json lines can be very large
                )

                result_text, num_turns, timed_out = await _read_stream(
                    proc, timeout
                )

                if timed_out:
                    logger.warning(
                        f"[ClaudeRunner] attempt {attempt} timed out ({timeout}s)"
                    )
                    last_error = ClaudeRunnerError(f"Timed out after {timeout}s")
                    if not retry_on_timeout:
                        break
                    continue

                # Log stderr for debugging
                stderr = await proc.stderr.read() if proc.stderr else b""
                stderr_text = stderr.decode().strip() if stderr else ""
                if stderr_text:
                    logger.debug(f"[ClaudeRunner] stderr: {stderr_text[:500]}")

                logger.debug(
                    f"[ClaudeRunner] done: {len(result_text)} chars, "
                    f"{num_turns} turns"
                )

                if not result_text:
                    logger.warning(
                        f"[ClaudeRunner] attempt {attempt} returned empty result "
                        f"({num_turns} turns)"
                    )
                    last_error = ClaudeRunnerError("Empty result")
                    continue

                return result_text

            except (asyncio.CancelledError, KeyboardInterrupt):
                logger.info("[ClaudeRunner] cancelled, killing subprocess")
                try:
                    proc.kill()  # type: ignore[possibly-undefined]
                except (ProcessLookupError, NameError):
                    pass
                raise

        raise last_error or ClaudeRunnerError("All retries exhausted")


async def _read_stream(
    proc: asyncio.subprocess.Process,
    timeout: int,
) -> tuple[str, int, bool]:
    """Read stream-json events from the subprocess stdout.

    Returns (result_text, num_turns, timed_out).
    """
    result_text = ""
    num_turns = 0
    last_assistant_text = ""

    try:
        async with asyncio.timeout(timeout):
            async for raw_line in proc.stdout:  # type: ignore[union-attr]
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")

                if etype == "assistant":
                    # Track assistant text for fallback
                    msg = event.get("message", {})
                    for block in msg.get("content", []):
                        if block.get("type") == "text":
                            last_assistant_text = block.get("text", "")
                        if block.get("type") == "tool_use":
                            logger.debug(
                                f"[stream] tool_use: {block.get('name', '?')}"
                            )

                elif etype == "result":
                    result_text = event.get("result", "")
                    num_turns = event.get("num_turns", 0)
                    cost = event.get("total_cost_usd", 0)
                    logger.debug(
                        f"[stream] result event: {len(result_text)} chars, "
                        f"{num_turns} turns, ${cost:.4f}"
                    )
                    break

    except TimeoutError:
        # Safety-net timeout — kill the process and drain pipes
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            if proc.stdout:
                await proc.stdout.read()
            if proc.stderr:
                await proc.stderr.read()
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (asyncio.TimeoutError, ProcessLookupError, OSError):
            pass
        return last_assistant_text or result_text, num_turns, True

    # Drain remaining pipe data and ensure the process exits cleanly.
    # Without draining, the subprocess transport __del__ may raise
    # "Event loop is closed" during garbage collection.
    try:
        if proc.stdout:
            await proc.stdout.read()
        if proc.stderr:
            await proc.stderr.read()
        await asyncio.wait_for(proc.wait(), timeout=10)
    except (asyncio.TimeoutError, ProcessLookupError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass

    # Fallback: if result is empty but we saw assistant text, use that
    if not result_text and last_assistant_text:
        result_text = last_assistant_text

    return result_text, num_turns, False
