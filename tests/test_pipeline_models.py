"""Tests for pipeline data models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from slima_agents.pipeline.models import (
    PipelinePlan,
    StageDefinition,
    ValidationDefinition,
)


# --- StageDefinition ---


def test_stage_definition_minimal():
    """StageDefinition should work with only required fields."""
    stage = StageDefinition(
        number=1,
        name="crime_design",
        display_name="Crime Design",
        instructions="Design the crime...",
        initial_message="Create crime design files in book '{book_token}'.",
    )
    assert stage.number == 1
    assert stage.name == "crime_design"
    assert stage.tool_set == "write"
    assert stage.timeout == 3600
    assert stage.context_reads == []
    assert stage.context_writes == []
    assert stage.summarize_chapters is False
    assert stage.summary_section == ""


def test_stage_definition_full():
    """StageDefinition should accept all fields."""
    stage = StageDefinition(
        number=7,
        name="act1_writing",
        display_name="Act 1 Writing",
        instructions="Write act 1...",
        initial_message="Write chapters 1-4 in book '{book_token}'.",
        context_reads=["crime_design", "characters"],
        context_writes=["act1_summary"],
        summarize_chapters=True,
        summary_section="act1_summary",
        tool_set="write",
        timeout=7200,
    )
    assert stage.summarize_chapters is True
    assert stage.summary_section == "act1_summary"
    assert stage.timeout == 7200
    assert stage.context_reads == ["crime_design", "characters"]


def test_stage_definition_json_roundtrip():
    """StageDefinition should serialize to JSON and back."""
    stage = StageDefinition(
        number=1,
        name="test",
        display_name="Test",
        instructions="Do stuff",
        initial_message="Go",
    )
    data = json.loads(stage.model_dump_json())
    restored = StageDefinition.model_validate(data)
    assert restored == stage


def test_stage_definition_missing_required():
    """StageDefinition should reject missing required fields."""
    with pytest.raises(ValidationError):
        StageDefinition(number=1, name="x")  # type: ignore[call-arg]


# --- ValidationDefinition ---


def test_validation_definition():
    """ValidationDefinition should store R1 and R2 config."""
    v = ValidationDefinition(
        number=10,
        r1_instructions="Check consistency...",
        r1_initial_message="Validate book '{book_token}'.",
        r2_instructions="Verify fixes...",
        r2_initial_message="Verify fixes in book '{book_token}'.",
    )
    assert v.number == 10
    assert v.tool_set == "write"
    assert v.timeout == 3600


def test_validation_definition_json_roundtrip():
    """ValidationDefinition should survive JSON roundtrip."""
    v = ValidationDefinition(
        number=5,
        r1_instructions="R1",
        r1_initial_message="R1 msg",
        r2_instructions="R2",
        r2_initial_message="R2 msg",
        tool_set="read",
        timeout=1800,
    )
    data = json.loads(v.model_dump_json())
    restored = ValidationDefinition.model_validate(data)
    assert restored == v


# --- PipelinePlan ---


def _make_plan(**overrides) -> PipelinePlan:
    """Helper to create a valid PipelinePlan with sensible defaults."""
    defaults = dict(
        title="密室殺人事件",
        description="A locked-room mystery",
        genre="mystery",
        language="zh",
        concept_summary="The victim was found...",
        context_sections=["concept", "crime_design", "characters"],
        stages=[
            StageDefinition(
                number=1,
                name="crime_design",
                display_name="犯罪設計",
                instructions="Design the crime",
                initial_message="Create files in '{book_token}'",
            ),
        ],
        file_paths={"planning_prefix": "規劃"},
    )
    defaults.update(overrides)
    return PipelinePlan(**defaults)


def test_pipeline_plan_minimal():
    """PipelinePlan should work with required fields only."""
    plan = _make_plan()
    assert plan.title == "密室殺人事件"
    assert plan.genre == "mystery"
    assert plan.validation is None
    assert plan.polish_stage is None
    assert len(plan.stages) == 1


def test_pipeline_plan_with_validation():
    """PipelinePlan should accept optional validation."""
    v = ValidationDefinition(
        number=10,
        r1_instructions="R1",
        r1_initial_message="R1 msg",
        r2_instructions="R2",
        r2_initial_message="R2 msg",
    )
    plan = _make_plan(validation=v)
    assert plan.validation is not None
    assert plan.validation.number == 10


def test_pipeline_plan_with_polish():
    """PipelinePlan should accept optional polish stage."""
    polish = StageDefinition(
        number=11,
        name="polish",
        display_name="Polish",
        instructions="Polish everything",
        initial_message="Polish '{book_token}'",
    )
    plan = _make_plan(polish_stage=polish)
    assert plan.polish_stage is not None
    assert plan.polish_stage.name == "polish"


def test_pipeline_plan_json_roundtrip():
    """PipelinePlan should survive full JSON serialization roundtrip."""
    v = ValidationDefinition(
        number=10,
        r1_instructions="R1 check",
        r1_initial_message="R1 go",
        r2_instructions="R2 verify",
        r2_initial_message="R2 go",
    )
    polish = StageDefinition(
        number=11,
        name="polish",
        display_name="Polish",
        instructions="Polish",
        initial_message="Polish go",
    )
    plan = _make_plan(
        stages=[
            StageDefinition(
                number=1,
                name="s1",
                display_name="S1",
                instructions="I1",
                initial_message="M1",
                context_reads=["concept"],
                context_writes=["crime_design"],
                summarize_chapters=True,
                summary_section="act1_summary",
            ),
            StageDefinition(
                number=2,
                name="s2",
                display_name="S2",
                instructions="I2",
                initial_message="M2",
            ),
        ],
        validation=v,
        polish_stage=polish,
        file_paths={"planning_prefix": "規劃", "chapters_prefix": "章節"},
    )
    json_str = plan.model_dump_json()
    data = json.loads(json_str)
    restored = PipelinePlan.model_validate(data)
    assert restored == plan
    assert len(restored.stages) == 2
    assert restored.stages[0].summarize_chapters is True


def test_pipeline_plan_json_schema_has_required_fields():
    """PipelinePlan JSON schema should list required fields."""
    schema = PipelinePlan.model_json_schema()
    required = schema.get("required", [])
    assert "title" in required
    assert "genre" in required
    assert "language" in required
    assert "concept_summary" in required
    assert "context_sections" in required
    assert "stages" in required


def test_pipeline_plan_stages_ordering():
    """Stages should preserve their number ordering."""
    plan = _make_plan(
        stages=[
            StageDefinition(
                number=3, name="c", display_name="C",
                instructions="I", initial_message="M",
            ),
            StageDefinition(
                number=1, name="a", display_name="A",
                instructions="I", initial_message="M",
            ),
            StageDefinition(
                number=2, name="b", display_name="B",
                instructions="I", initial_message="M",
            ),
        ]
    )
    numbers = [s.number for s in plan.stages]
    assert numbers == [3, 1, 2]  # Preserves insertion order
    sorted_stages = sorted(plan.stages, key=lambda s: s.number)
    assert [s.name for s in sorted_stages] == ["a", "b", "c"]


# --- action_type / source_book ---


def test_pipeline_plan_action_type_default():
    """New action_type field should default to 'create'."""
    plan = _make_plan()
    assert plan.action_type == "create"


def test_pipeline_plan_source_book_default():
    """New source_book field should default to empty string."""
    plan = _make_plan()
    assert plan.source_book == ""


def test_pipeline_plan_action_type_custom():
    """action_type should accept any string value."""
    plan = _make_plan(action_type="rewrite", source_book="bk_abc123")
    assert plan.action_type == "rewrite"
    assert plan.source_book == "bk_abc123"


def test_pipeline_plan_backward_compat_old_json():
    """Old JSON without action_type/source_book should still parse."""
    old_json = {
        "title": "Test",
        "description": "D",
        "genre": "mystery",
        "language": "zh",
        "concept_summary": "C",
        "context_sections": ["concept"],
        "stages": [
            {
                "number": 1,
                "name": "s",
                "display_name": "S",
                "instructions": "I",
                "initial_message": "M",
            }
        ],
    }
    plan = PipelinePlan.model_validate(old_json)
    assert plan.action_type == "create"
    assert plan.source_book == ""


def test_pipeline_plan_new_fields_roundtrip():
    """action_type and source_book should survive JSON roundtrip."""
    plan = _make_plan(action_type="revise", source_book="bk_xyz789")
    data = json.loads(plan.model_dump_json())
    restored = PipelinePlan.model_validate(data)
    assert restored.action_type == "revise"
    assert restored.source_book == "bk_xyz789"
