"""ClaudeRunner: executes agent prompts via the claude CLI."""

from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
DEFAULT_TIMEOUT = 600


class ClaudeRunnerError(Exception):
    """Raised when the claude CLI subprocess fails."""


class ClaudeRunner:
    """Executes prompts via `claude -p` subprocess.

    The claude CLI handles its own authentication and MCP tool execution,
    so no ANTHROPIC_API_KEY is needed.
    """

    @staticmethod
    async def run(
        prompt: str,
        system_prompt: str,
        allowed_tools: list[str] | None = None,
        model: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        retry_on_timeout: bool = True,
    ) -> str:
        """Run a prompt through the claude CLI and return the text output.

        Args:
            prompt: The user message to send.
            system_prompt: System prompt for the agent.
            allowed_tools: List of MCP tool names (e.g. "mcp__slima__create_file").
            model: Optional model override (e.g. "claude-sonnet-4-20250514").
            timeout: Max seconds to wait for the subprocess.
            retry_on_timeout: Whether to retry on timeout. Set False for agents
                that create files (retry could cause duplicates).

        Returns:
            The text output from claude CLI.

        Raises:
            ClaudeRunnerError: If the subprocess fails after retries.
        """
        # Build command — embed system prompt into user prompt instead of
        # using --system-prompt flag, which triggers extended thinking in
        # newer Claude CLI versions and exhausts output tokens on thinking.
        full_prompt = (
            f"<instructions>\n{system_prompt}\n</instructions>\n\n{prompt}"
        )
        cmd = [
            "claude",
            "-p", full_prompt,
            "--output-format", "json",
        ]

        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

        if model:
            cmd.extend(["--model", model])

        # Remove CLAUDECODE env var so claude CLI can run inside a Claude Code session
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            logger.debug(f"[ClaudeRunner] attempt {attempt}/{MAX_RETRIES}")
            logger.debug(
                f"[ClaudeRunner] cmd: claude -p <{len(full_prompt)} chars> "
                f"--output-format json (instructions: {len(system_prompt)} chars, "
                f"prompt: {len(prompt)} chars)"
            )

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )

                # Always log stderr for debugging
                stderr_text = stderr.decode().strip() if stderr else ""
                if stderr_text:
                    logger.debug(f"[ClaudeRunner] stderr: {stderr_text[:500]}")

                if proc.returncode != 0:
                    err_msg = stderr_text or f"exit code {proc.returncode}"
                    logger.warning(f"[ClaudeRunner] attempt {attempt} failed: {err_msg}")
                    last_error = ClaudeRunnerError(err_msg)
                    continue

                raw = stdout.decode("utf-8").strip()
                logger.debug(
                    f"[ClaudeRunner] stdout: {len(stdout)} raw bytes → "
                    f"{len(raw)} chars after decode+strip"
                )

                output = _extract_text(raw)

                if not output:
                    logger.warning(
                        f"[ClaudeRunner] attempt {attempt} returned empty output "
                        f"(raw bytes={len(stdout)}, returncode={proc.returncode}, "
                        f"stderr={stderr_text[:200]}, "
                        f"raw_preview={raw[:300]})"
                    )
                    last_error = ClaudeRunnerError(
                        f"Empty output (returncode={proc.returncode})"
                    )
                    continue

                logger.debug(f"[ClaudeRunner] extracted {len(output)} chars")
                return output

            except asyncio.TimeoutError:
                logger.warning(f"[ClaudeRunner] attempt {attempt} timed out ({timeout}s)")
                last_error = ClaudeRunnerError(f"Timed out after {timeout}s")
                try:
                    proc.kill()  # type: ignore[possibly-undefined]
                except ProcessLookupError:
                    pass
                # Don't retry on timeout if the agent creates files (would cause duplicates)
                if not retry_on_timeout:
                    break

            except (asyncio.CancelledError, KeyboardInterrupt):
                # Ensure subprocess is killed on cancellation
                logger.info("[ClaudeRunner] cancelled, killing subprocess")
                try:
                    proc.kill()  # type: ignore[possibly-undefined]
                except (ProcessLookupError, NameError):
                    pass
                raise

        raise last_error or ClaudeRunnerError("All retries exhausted")


def _extract_text(raw: str) -> str:
    """Extract text from claude CLI output.

    Tries JSON parsing first (--output-format json), falls back to plain text.
    JSON format: {"result": "text content", ...}
    """
    if not raw:
        return ""

    # Try JSON parse
    try:
        data = json.loads(raw)
        result = data.get("result", "")
        if result:
            return result.strip()
        # Log details for debugging when result is empty
        logger.warning(
            f"[ClaudeRunner] JSON 'result' is empty. "
            f"is_error: {data.get('is_error')}, "
            f"stop_reason: {data.get('stop_reason')}, "
            f"num_turns: {data.get('num_turns')}, "
            f"usage: {data.get('usage')}"
        )
        return ""
    except (json.JSONDecodeError, AttributeError):
        # Not JSON — treat as plain text (backward compat)
        return raw.strip()
