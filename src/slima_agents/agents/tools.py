"""MCP tool name constants for --allowedTools."""

from __future__ import annotations

# Slima MCP tools available via claude CLI
SLIMA_MCP_TOOLS: list[str] = [
    "mcp__slima__create_file",
    "mcp__slima__write_file",
    "mcp__slima__read_file",
    "mcp__slima__edit_file",
    "mcp__slima__get_book_structure",
    "mcp__slima__search_content",
]

# Read-only subset (for agents that should not create/write files)
SLIMA_MCP_READ_TOOLS: list[str] = [
    "mcp__slima__read_file",
    "mcp__slima__get_book_structure",
    "mcp__slima__search_content",
]
