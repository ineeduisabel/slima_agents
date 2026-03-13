"""Plan builder: JSON extraction utility and system prompt for plan-build command."""

from __future__ import annotations

import json
import re

from .task_models import TaskPlan

# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def extract_json_object(text: str) -> dict:
    """Extract a JSON object from *text* with a three-layer fallback.

    1. Direct ``json.loads`` (pure JSON string).
    2. Regex: last ```json ... ``` fenced block.
    3. Brace-matching: last balanced ``{...}`` from the tail.

    Raises ``ValueError`` when no valid JSON object can be found.
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty input — no JSON found")

    # --- Layer 1: direct parse ---
    try:
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError(f"Expected JSON object, got {type(obj).__name__}")
        return obj
    except json.JSONDecodeError:
        pass

    # --- Layer 2: fenced code block (last match) ---
    fence_pattern = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)
    matches = fence_pattern.findall(text)
    if matches:
        candidate = matches[-1].strip()
        try:
            obj = json.loads(candidate)
            if not isinstance(obj, dict):
                raise ValueError(f"Expected JSON object, got {type(obj).__name__}")
            return obj
        except json.JSONDecodeError:
            pass

    # --- Layer 3: brace-matching from tail ---
    depth = 0
    end = -1
    for i in range(len(text) - 1, -1, -1):
        ch = text[i]
        if ch == "}":
            if depth == 0:
                end = i
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                candidate = text[i : end + 1]
                try:
                    obj = json.loads(candidate)
                    if not isinstance(obj, dict):
                        raise ValueError(
                            f"Expected JSON object, got {type(obj).__name__}"
                        )
                    return obj
                except json.JSONDecodeError:
                    pass

    raise ValueError("No valid JSON object found in text")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SCHEMA_JSON = json.dumps(TaskPlan.model_json_schema(), indent=2, ensure_ascii=False)

PLAN_BUILD_SYSTEM_PROMPT = f"""\
You are a pipeline plan architect. Your ONLY job is to produce a single valid \
JSON object that conforms to the TaskPlan schema below.

# Output Format

- Output EXACTLY ONE JSON object inside a ```json code fence.
- Do NOT output anything else — no explanation, no commentary.

# TaskPlan JSON Schema

```json
{_SCHEMA_JSON}
```

# Field Semantics

## Top-level fields
- **title** (string): If non-empty, a new book will be created with this title. \
Leave empty ("") when working with an existing book.
- **book_token** (string): If non-empty, the pipeline uses this existing book. \
Leave empty ("") when creating a new book.
- **stages** (array): At least one stage. Stages with the same `number` run in parallel.

## Stage fields
- **number** (int): Execution order. Stages sharing the same number run concurrently. \
Start from 1 and increment.
- **name** (string): Machine identifier (snake_case, e.g. "research_setting").
- **display_name** (string): Human-readable label (e.g. "Research Setting"). Optional.
- **prompt** (string): The instruction for the TaskAgent. Be specific and detailed.
- **system_prompt** (string): Custom system prompt override. Usually leave empty.
- **tool_set** (string): One of "write", "read", "all", "none". \
"read" for research/analysis, "write" for creating/editing files, "none" for pure text generation.
- **plan_first** (bool): If true, the agent plans before executing. Good for complex write stages.
- **context_section** (string): If set, the agent's output is stored in this named context section \
and made available to subsequent stages. Use this to pass information between stages.
- **chain_to_previous** (bool): If true, resumes the previous stage's Claude session. \
Rarely needed — prefer context_section for data flow.
- **creates_book** (bool): If true, this stage is responsible for creating the book via MCP \
``create_book`` tool. The orchestrator will extract the book_token from the agent's output \
and use it for all subsequent stages. Use this when the book title is not known upfront \
(e.g. a brainstorming stage that decides the title). Requires tool_set="all". \
Only one stage should set this to true.
- **timeout** (int): Timeout in seconds. Default 3600. Use shorter for simple tasks.

# Design Principles

1. **Research before writing**: Early stages should use tool_set="read" to gather information, \
storing results in context_section. Later stages use that context to write.
2. **Use context_section for data flow**: When stage B needs output from stage A, \
set context_section on stage A and reference it in stage B's prompt.
3. **Parallel when independent**: Stages that don't depend on each other should share the same number.
4. **Specific prompts**: Each stage prompt should be detailed enough for an AI to execute without ambiguity.
5. **Appropriate tool_set**: "read" for research, "write" for file creation/editing, "none" for pure reasoning.
6. **Deferred book creation**: When the book title is not known upfront (e.g. brainstorming), \
set creates_book=true on the stage that decides the title. That stage MUST use tool_set="all" \
so it has access to create_book. Leave top-level title and book_token empty. \
Do NOT set creates_book when the user already provides a title or book_token.

# CRITICAL Requirements

- The top-level object MUST contain a "stages" array (NOT "steps", NOT "pipeline", NOT "tasks").
- Each element in "stages" MUST have at minimum: number, name, prompt, tool_set.
- The key name is exactly "stages" — any other name will cause a validation error.

# Modifying an Existing Plan

When the user provides an existing plan (in the prompt), modify it according to their request. \
Keep unchanged stages intact and only alter what the user asks for.
"""