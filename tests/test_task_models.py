"""Tests for TaskPlan and TaskStageDefinition models."""

from __future__ import annotations

import json

import pytest

from slima_agents.agents.task_models import TaskPlan, TaskStageDefinition


# ---------- TaskStageDefinition ----------


class TestTaskStageDefinition:
    def test_defaults(self):
        s = TaskStageDefinition(number=1, name="research", prompt="analyze")
        assert s.number == 1
        assert s.name == "research"
        assert s.prompt == "analyze"
        assert s.display_name == ""
        assert s.system_prompt == ""
        assert s.tool_set == "read"
        assert s.plan_first is False
        assert s.include_language_rule is False
        assert s.context_section == ""
        assert s.chain_to_previous is False
        assert s.timeout == 3600

    def test_display_name_default_to_name(self):
        s = TaskStageDefinition(number=1, name="research", prompt="x")
        assert s.resolved_display_name == "research"

    def test_display_name_explicit(self):
        s = TaskStageDefinition(number=1, name="research", prompt="x", display_name="需求分析")
        assert s.resolved_display_name == "需求分析"

    def test_all_fields(self):
        s = TaskStageDefinition(
            number=2,
            name="writing",
            display_name="Write Chapter",
            prompt="write the chapter",
            system_prompt="You are a novelist",
            tool_set="write",
            plan_first=True,
            include_language_rule=True,
            context_section="chapters",
            timeout=7200,
        )
        assert s.tool_set == "write"
        assert s.plan_first is True
        assert s.include_language_rule is True
        assert s.context_section == "chapters"
        assert s.timeout == 7200

    def test_json_roundtrip(self):
        s = TaskStageDefinition(number=1, name="a", prompt="b")
        data = json.loads(s.model_dump_json())
        s2 = TaskStageDefinition.model_validate(data)
        assert s == s2


# ---------- TaskPlan ----------


class TestTaskPlan:
    def test_minimal(self):
        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="s1", prompt="do"),
        ])
        assert plan.title == ""
        assert plan.book_token == ""
        assert len(plan.stages) == 1

    def test_empty_stages_rejected(self):
        with pytest.raises(Exception):
            TaskPlan(stages=[])

    def test_context_sections_derived(self):
        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="a", prompt="x", context_section="overview"),
            TaskStageDefinition(number=2, name="b", prompt="y", context_section="cosmology"),
            TaskStageDefinition(number=2, name="c", prompt="z", context_section="geography"),
        ])
        sections = plan.context_sections
        assert "_pipeline_info" in sections
        assert "overview" in sections
        assert "cosmology" in sections
        assert "geography" in sections
        assert "book_structure" in sections

    def test_context_sections_no_duplicates(self):
        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="a", prompt="x", context_section="overview"),
            TaskStageDefinition(number=2, name="b", prompt="y", context_section="overview"),
        ])
        sections = plan.context_sections
        assert sections.count("overview") == 1

    def test_context_sections_always_has_book_structure(self):
        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="a", prompt="x"),
        ])
        assert "book_structure" in plan.context_sections

    def test_with_book_token(self):
        plan = TaskPlan(
            book_token="bk_abc123",
            stages=[TaskStageDefinition(number=1, name="s", prompt="p")],
        )
        assert plan.book_token == "bk_abc123"
        assert plan.title == ""

    def test_with_title(self):
        plan = TaskPlan(
            title="My Fantasy World",
            stages=[TaskStageDefinition(number=1, name="s", prompt="p")],
        )
        assert plan.title == "My Fantasy World"
        assert plan.book_token == ""

    def test_no_title_no_book(self):
        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="s", prompt="p"),
        ])
        assert plan.title == ""
        assert plan.book_token == ""

    def test_full_worldbuild_like_plan(self):
        """Parse a full worldbuild-like plan from JSON."""
        raw = {
            "title": "奇幻世界觀",
            "stages": [
                {"number": 1, "name": "research", "display_name": "需求分析",
                 "prompt": "分析需求", "tool_set": "none", "context_section": "overview"},
                {"number": 2, "name": "cosmology", "display_name": "宇宙觀",
                 "prompt": "設計宇宙觀", "tool_set": "write", "context_section": "cosmology"},
                {"number": 2, "name": "geography", "display_name": "地理",
                 "prompt": "設計地理", "tool_set": "write", "context_section": "geography"},
                {"number": 3, "name": "narrative", "display_name": "敘事",
                 "prompt": "設計故事線", "tool_set": "write", "context_section": "narrative"},
            ],
        }
        plan = TaskPlan.model_validate(raw)
        assert plan.title == "奇幻世界觀"
        assert len(plan.stages) == 4
        # Stage 2 has 2 parallel stages
        stage2 = [s for s in plan.stages if s.number == 2]
        assert len(stage2) == 2
        assert {s.name for s in stage2} == {"cosmology", "geography"}

    def test_json_roundtrip(self):
        plan = TaskPlan(
            title="Test",
            stages=[
                TaskStageDefinition(number=1, name="a", prompt="do a", context_section="sec_a"),
                TaskStageDefinition(number=2, name="b", prompt="do b"),
            ],
        )
        data = json.loads(plan.model_dump_json())
        plan2 = TaskPlan.model_validate(data)
        assert plan == plan2

    def test_context_sections_empty_sections_ignored(self):
        """Stages without context_section should not contribute."""
        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="a", prompt="x"),
            TaskStageDefinition(number=2, name="b", prompt="y", context_section="data"),
        ])
        sections = plan.context_sections
        # _pipeline_info + "data" + "book_structure"
        assert sections == ["_pipeline_info", "data", "book_structure"]

    def test_context_sections_preserves_order(self):
        """Sections should appear in stage definition order."""
        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="a", prompt="x", context_section="z_section"),
            TaskStageDefinition(number=2, name="b", prompt="y", context_section="a_section"),
        ])
        sections = plan.context_sections
        assert sections.index("z_section") < sections.index("a_section")

    def test_context_sections_pipeline_info_first(self):
        """_pipeline_info should always be the first section."""
        plan = TaskPlan(stages=[
            TaskStageDefinition(number=1, name="a", prompt="x", context_section="overview"),
        ])
        assert plan.context_sections[0] == "_pipeline_info"

    def test_chain_to_previous_field(self):
        s = TaskStageDefinition(number=2, name="s", prompt="p", chain_to_previous=True)
        assert s.chain_to_previous is True

    def test_chain_to_previous_in_json(self):
        raw = {"number": 2, "name": "s", "prompt": "p", "chain_to_previous": True}
        s = TaskStageDefinition.model_validate(raw)
        assert s.chain_to_previous is True
