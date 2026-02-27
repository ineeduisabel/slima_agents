"""Shared language detection and structure formatting utilities."""

from __future__ import annotations


def detect_language(text: str) -> str:
    """Detect prompt language. Returns 'ja', 'ko', 'zh', or 'en'.

    Priority: Japanese kana -> Korean Hangul -> CJK ideographs (Chinese) -> English.
    """
    for ch in text:
        # Japanese: Hiragana (3040-309F) or Katakana (30A0-30FF)
        if "\u3040" <= ch <= "\u309f" or "\u30a0" <= ch <= "\u30ff":
            return "ja"
        # Korean: Hangul Syllables (AC00-D7AF) or Hangul Jamo (1100-11FF)
        if "\uac00" <= ch <= "\ud7af" or "\u1100" <= ch <= "\u11ff":
            return "ko"
    # CJK Unified Ideographs (shared by zh/ja/ko, but if no kana/hangul -> zh)
    if any("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" for ch in text):
        return "zh"
    return "en"


def format_structure_tree(nodes: list[dict], prefix: str = "") -> str:
    """Format a list of FileSnapshot dicts into a tree diagram (like ``tree`` command)."""
    lines: list[str] = []
    # Sort: folders first, then files; within each group sort by position
    sorted_nodes = sorted(
        nodes,
        key=lambda n: (n.get("kind") != "folder", n.get("position", 0)),
    )
    for i, node in enumerate(sorted_nodes):
        is_last = i == len(sorted_nodes) - 1
        connector = "└── " if is_last else "├── "
        name = node.get("name", "?")
        kind = node.get("kind", "file")
        if kind == "folder":
            lines.append(f"{prefix}{connector}{name}/")
            children = node.get("children") or []
            if children:
                extension = "    " if is_last else "│   "
                lines.append(format_structure_tree(children, prefix + extension))
        else:
            lines.append(f"{prefix}{connector}{name}")
    return "\n".join(lines)


def flatten_paths(nodes: list[dict], prefix: str = "") -> list[str]:
    """Recursively extract all file paths from a book structure tree."""
    paths: list[str] = []
    for node in nodes:
        name = node.get("name", "")
        kind = node.get("kind", "file")
        children = node.get("children") or []
        path = f"{prefix}{name}" if prefix else name
        if kind == "folder" or children:
            paths.extend(flatten_paths(children, path + "/"))
        else:
            paths.append(path)
    return paths
