"""Data models for the plan-driven pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StageDefinition(BaseModel):
    """A single stage in the pipeline plan."""

    number: int = Field(description="Execution order (1-based)")
    name: str = Field(description="Machine identifier (e.g. 'crime_design')")
    display_name: str = Field(description="Human-readable stage name")
    instructions: str = Field(description="Full instructions for the writing agent")
    initial_message: str = Field(
        description="User message for the agent. Use {book_token} as placeholder."
    )
    context_reads: list[str] = Field(
        default_factory=list,
        description="Context sections this stage needs. Empty = all.",
    )
    context_writes: list[str] = Field(
        default_factory=list,
        description="Context sections this stage produces.",
    )
    summarize_chapters: bool = Field(
        default=False,
        description="Whether to summarize chapter files after this stage.",
    )
    summary_section: str = Field(
        default="",
        description="Context section to write chapter summaries into.",
    )
    tool_set: str = Field(
        default="write",
        description="Tool access level: 'write' | 'read' | 'none'.",
    )
    timeout: int = Field(default=3600, description="Stage timeout in seconds.")


class ValidationDefinition(BaseModel):
    """Validation stage configuration (R1 + R2 with session chaining)."""

    number: int = Field(description="Stage number for tracking")
    r1_instructions: str = Field(description="Round 1 validation instructions")
    r1_initial_message: str = Field(
        description="Round 1 user message. Use {book_token} as placeholder."
    )
    r2_instructions: str = Field(description="Round 2 verification instructions")
    r2_initial_message: str = Field(
        description="Round 2 user message. Use {book_token} as placeholder."
    )
    tool_set: str = Field(default="write", description="Tool access for validation.")
    timeout: int = Field(default=3600, description="Per-round timeout in seconds.")


class PipelinePlan(BaseModel):
    """Complete pipeline plan produced by the GenericPlannerAgent."""

    title: str = Field(description="Book title (in prompt language)")
    description: str = Field(description="Short book description")
    genre: str = Field(description="Genre identifier (e.g. 'mystery', 'romance')")
    language: str = Field(description="Detected language code: 'zh'|'en'|'ja'|'ko'")
    concept_summary: str = Field(
        description="Full concept injected as initial context"
    )
    context_sections: list[str] = Field(
        description="Dynamic context section names for this pipeline"
    )
    stages: list[StageDefinition] = Field(description="Ordered writing stages")
    validation: ValidationDefinition | None = Field(
        default=None, description="Optional validation stage"
    )
    polish_stage: StageDefinition | None = Field(
        default=None, description="Optional polish/readme stage"
    )
    file_paths: dict[str, str] = Field(
        default_factory=dict,
        description="Language-specific path mappings (e.g. {'planning_prefix': '規劃'})",
    )
    action_type: str = Field(
        default="create",
        description="Action type: 'create' | 'rewrite' | 'continue' | 'revise' | 'review' | ...",
    )
    source_book: str = Field(
        default="",
        description="Source book token for non-create actions (e.g. 'bk_abc123').",
    )
