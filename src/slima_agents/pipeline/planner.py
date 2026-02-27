"""GenericPlannerAgent: analyzes any writing prompt and produces a PipelinePlan."""

from __future__ import annotations

import json
import logging
import re

from ..agents.base import AgentResult, BaseAgent
from ..agents.tools import SLIMA_MCP_ALL_READ_TOOLS
from ..worldbuild.templates import LANGUAGE_RULE
from .models import PipelinePlan

logger = logging.getLogger(__name__)


# The planner's system prompt includes the JSON schema so the LLM knows
# the exact shape it must produce.
_PLAN_SCHEMA = json.dumps(PipelinePlan.model_json_schema(), indent=2)

_PLANNER_INSTRUCTIONS = LANGUAGE_RULE + """
# Role

You are a **Pipeline Planner** — an expert at designing writing pipelines for creative fiction.
Given a user's writing prompt (in any language), you must:

1. **Detect the genre** (mystery, romance, sci-fi, fantasy, historical, etc.)
2. **Design a complete pipeline** of sequential writing stages
3. **Output a single JSON object** conforming to the PipelinePlan schema below

## PipelinePlan JSON Schema

```json
""" + _PLAN_SCHEMA + """
```

## Guidelines

### Stages
- Each stage has a `number` (execution order), `name` (machine ID), `display_name` (human label), `instructions` (detailed writing instructions for the agent), and `initial_message` (the user message sent to kick off the agent — use `{book_token}` as placeholder).
- `context_reads`: which context sections this stage needs (empty = all).
- `context_writes`: which context sections this stage produces.
- `summarize_chapters`: set to true for stages that write chapter files, so the orchestrator can create summaries for continuity.
- `summary_section`: the context section name to store chapter summaries in.
- `tool_set`: `"write"` for stages that create files, `"read"` for read-only stages, `"none"` for pure-text stages.

### Context Sections
- Define meaningful section names in `context_sections` (e.g., `["concept", "crime_design", "characters", "plot_architecture", "setting", "act1_summary", "act2_summary", "act3_summary", "validation_report"]`).
- `book_structure` is always implicitly available — do not include it.

### Instructions Quality
- Each stage's `instructions` should be thorough (500+ words) and specific to the genre.
- Include structural guidance, quality standards, cross-referencing requirements.
- Instructions must be in **English** (the agent will follow LANGUAGE_RULE to write in the user's language).

### File Paths
- Provide `file_paths` with language-specific folder names.
- Common keys: `planning_prefix`, `chapters_prefix`, `overview_file`.

### Validation
- Include a `validation` object with R1 (consistency check + fix) and R2 (verify fixes) instructions.
- The orchestrator will chain R2 onto R1's session automatically.

### Polish
- Include a `polish_stage` for final indexing and README generation.

## Output Format

Output ONLY the JSON object — no markdown fences, no explanation, no extra text.
If you must use a code fence, use ```json ... ``` and nothing else outside it.
"""

_SOURCE_BOOK_BLOCK = """
## Source Book

You have read-only MCP access to book `{book_token}`.
Use get_book_structure and read_file to understand its current structure and content.
Base your pipeline design on the existing book's structure and content.
Set `source_book` in your output to "{book_token}".
Set `action_type` to an appropriate value (e.g. "rewrite", "revise", "continue", "review").
"""


class GenericPlannerAgent(BaseAgent):
    """Analyzes a writing prompt and produces a PipelinePlan.

    When ``source_book`` is set, the planner gets read-only MCP access to
    inspect the existing book before designing the pipeline. The orchestrator
    reads ``self.plan`` after ``run()`` completes.
    """

    def __init__(self, *args, prompt: str, source_book: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.prompt = prompt
        self.source_book = source_book
        self.plan: PipelinePlan | None = None
        self._revision_feedback: str = ""

    @property
    def name(self) -> str:
        return "GenericPlannerAgent"

    def system_prompt(self) -> str:
        base = _PLANNER_INSTRUCTIONS
        if self.source_book:
            base += _SOURCE_BOOK_BLOCK.format(book_token=self.source_book)
        return base

    def allowed_tools(self) -> list[str]:
        if self.source_book:
            return SLIMA_MCP_ALL_READ_TOOLS
        return []

    def initial_message(self) -> str:
        if self._revision_feedback:
            return (
                f"The user wants you to revise the plan. Here is their feedback:\n\n"
                f'"{self._revision_feedback}"\n\n'
                f"Please output the revised PipelinePlan JSON."
            )
        return (
            f"Design a complete writing pipeline for this prompt.\n\n"
            f'User prompt: "{self.prompt}"\n\n'
            f"Output the PipelinePlan JSON."
        )

    async def run(self) -> AgentResult:
        result = await super().run()
        self.plan = _parse_plan(result.full_output)
        return result

    async def revise(self, feedback: str, session_id: str) -> AgentResult:
        """Revise the plan using session chaining.

        Args:
            feedback: User's revision feedback.
            session_id: Session ID from the previous run/revise call.

        Returns:
            AgentResult with the revised plan output.
        """
        self.resume_session = session_id
        self._revision_feedback = feedback
        result = await super().run()
        self.plan = _parse_plan(result.full_output)
        # Reset for potential next call
        self._revision_feedback = ""
        return result


def _parse_plan(text: str) -> PipelinePlan | None:
    """Extract and parse a PipelinePlan JSON from LLM output.

    Handles:
    - Raw JSON (no fences)
    - ```json ... ``` fenced blocks
    - Leading/trailing text around the JSON
    """
    if not text.strip():
        return None

    # Try 1: extract from markdown fence
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        try:
            data = json.loads(fence_match.group(1))
            return PipelinePlan.model_validate(data)
        except (json.JSONDecodeError, Exception):
            pass

    # Try 2: find the outermost { ... } block
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            data = json.loads(text[brace_start : brace_end + 1])
            return PipelinePlan.model_validate(data)
        except (json.JSONDecodeError, Exception):
            pass

    # Try 3: raw text as JSON
    try:
        data = json.loads(text)
        return PipelinePlan.model_validate(data)
    except (json.JSONDecodeError, Exception):
        pass

    logger.warning("Failed to parse PipelinePlan from planner output")
    return None
