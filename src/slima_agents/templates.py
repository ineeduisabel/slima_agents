"""Shared prompt templates used across all agents."""

from __future__ import annotations

# --- Language rule (prepended to all agent instructions) ---

LANGUAGE_RULE = """\
**CRITICAL — Language Rule (MUST FOLLOW):**
You MUST write ALL output in the SAME language as the world context below.
This is NON-NEGOTIABLE and applies to EVERYTHING you produce:
- **Top-level worldview folder**: The root folder "worldview/" must also be translated \
to match the content language (e.g., "世界觀/" for Chinese, "世界観/" for Japanese, \
"세계관/" for Korean). Check the existing book structure to see which prefix is already in use.
- **Folder names**: e.g., use "歷史" NOT "history", "地理" NOT "geography" (for Chinese)
- **File names**: e.g., use "年表.md" NOT "timeline.md" (for Chinese)
- **All markdown content**: headings, descriptions, body text
- **No English folder or file names** when the context language is not English
- For proper nouns from other languages, keep the original and add a translation \
in parentheses (e.g., "杜月笙 (Du Yuesheng)" or "The Bund（外灘）").
- When in doubt, look at the existing files in the book for language consistency.

"""
