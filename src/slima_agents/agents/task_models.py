"""Pydantic models for the TaskAgent pipeline (front-end configurable)."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class TaskStageDefinition(BaseModel):
    """A single stage in a TaskAgent pipeline.

    Front-end sends these as JSON; each maps directly to TaskAgent constructor params.
    Stages with the same ``number`` run in parallel (asyncio.gather).
    """

    number: int  # execution order (same number = parallel)
    name: str  # machine identifier
    display_name: str = ""  # human-readable (defaults to name)
    prompt: str  # → TaskAgent._prompt
    system_prompt: str = ""  # → TaskAgent._system_prompt_text
    tool_set: str = "read"  # → TaskAgent._tool_set
    plan_first: bool = False  # → TaskAgent._plan_first
    include_language_rule: bool = False  # → TaskAgent._include_language_rule
    context_section: str = ""  # write result into this context section
    chain_to_previous: bool = False  # use previous stage's session_id (--resume)
    timeout: int = 3600

    @property
    def resolved_display_name(self) -> str:
        return self.display_name or self.name


class TaskPlan(BaseModel):
    """A front-end-defined multi-stage pipeline for TaskAgent.

    Either ``title`` (create a new book) or ``book_token`` (use existing) may be set.
    If neither is set, the pipeline runs in book-less mode.
    """

    title: str = ""  # non-empty → create book
    book_token: str = ""  # non-empty → use existing book
    stages: list[TaskStageDefinition]  # at least 1

    @field_validator("stages")
    @classmethod
    def _at_least_one_stage(cls, v: list[TaskStageDefinition]) -> list[TaskStageDefinition]:
        if not v:
            raise ValueError("stages must contain at least 1 stage")
        return v

    @property
    def context_sections(self) -> list[str]:
        """Derive context section names from stages (+ _pipeline_info + book_structure)."""
        sections: list[str] = ["_pipeline_info"]
        seen: set[str] = {"_pipeline_info"}
        for s in self.stages:
            if s.context_section and s.context_section not in seen:
                sections.append(s.context_section)
                seen.add(s.context_section)
        if "book_structure" not in seen:
            sections.append("book_structure")
        return sections
