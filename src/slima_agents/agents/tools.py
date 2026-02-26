"""MCP tool name constants for --allowedTools.

Supports both local MCP ("slima") and remote cloud MCP ("claude.ai Slima")
naming conventions. The --allowedTools flag ignores names that don't match
any configured server, so including both is safe.
"""

from __future__ import annotations

# Two possible prefixes depending on MCP server configuration:
#   Local:  mcp__slima__         (configured via `claude mcp add`)
#   Remote: mcp__claude_ai_Slima__  (configured via claude.ai cloud MCP)
_PREFIXES = ["mcp__slima__", "mcp__claude_ai_Slima__"]


def _both(tool: str) -> list[str]:
    """Generate tool names for both MCP prefixes."""
    return [f"{prefix}{tool}" for prefix in _PREFIXES]


# Full write tools (for agents that create/write files)
SLIMA_MCP_TOOLS: list[str] = [
    *_both("create_file"),
    *_both("write_file"),
    *_both("read_file"),
    *_both("edit_file"),
    *_both("get_book_structure"),
    *_both("search_content"),
]

# Read-only subset (for agents that should not create/write files)
SLIMA_MCP_READ_TOOLS: list[str] = [
    *_both("read_file"),
    *_both("get_book_structure"),
    *_both("search_content"),
]

# All read-only tools including library-level (list/get books) and book-level operations.
# Superset of SLIMA_MCP_READ_TOOLS — used by AskAgent for general-purpose queries.
SLIMA_MCP_ALL_READ_TOOLS: list[str] = [
    *_both("list_books"),
    *_both("get_book"),
    *_both("get_book_structure"),
    *_both("get_writing_stats"),
    *_both("get_chapter"),
    *_both("read_file"),
    *_both("search_content"),
]
