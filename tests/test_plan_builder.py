"""Tests for plan_builder: JSON extraction and system prompt."""

from __future__ import annotations

import json

import pytest

from slima_agents.agents.plan_builder import PLAN_BUILD_SYSTEM_PROMPT, extract_json_object


# ===== TestExtractJsonObject =====


class TestExtractJsonObject:
    """Tests for extract_json_object with its three-layer fallback."""

    # --- Layer 1: direct JSON parse ---

    def test_pure_json(self):
        raw = '{"title": "My Book", "stages": []}'
        result = extract_json_object(raw)
        assert result == {"title": "My Book", "stages": []}

    def test_pure_json_with_whitespace(self):
        raw = '  \n  {"key": "value"}  \n  '
        result = extract_json_object(raw)
        assert result == {"key": "value"}

    # --- Layer 2: fenced code block ---

    def test_fenced_json(self):
        raw = 'Here is the plan:\n```json\n{"title": "Test"}\n```\nDone.'
        result = extract_json_object(raw)
        assert result == {"title": "Test"}

    def test_fenced_json_multiline(self):
        raw = (
            "Some text\n"
            "```json\n"
            '{\n  "title": "Book",\n  "stages": []\n}\n'
            "```\n"
            "End."
        )
        result = extract_json_object(raw)
        assert result == {"title": "Book", "stages": []}

    def test_multiple_fences_takes_last(self):
        raw = (
            '```json\n{"version": 1}\n```\n'
            "Some text in between\n"
            '```json\n{"version": 2}\n```\n'
        )
        result = extract_json_object(raw)
        assert result == {"version": 2}

    # --- Layer 3: brace matching ---

    def test_mixed_text_brace_matching(self):
        raw = 'The plan is: {"title": "Found"} and that is all.'
        result = extract_json_object(raw)
        assert result == {"title": "Found"}

    def test_nested_json_brace_matching(self):
        raw = 'Output: {"outer": {"inner": "value"}}'
        result = extract_json_object(raw)
        assert result == {"outer": {"inner": "value"}}

    def test_brace_matching_takes_last_object(self):
        raw = '{"first": 1} some text {"second": 2}'
        result = extract_json_object(raw)
        assert result == {"second": 2}

    # --- Unicode content ---

    def test_unicode_content(self):
        raw = '{"title": "\u4e16\u754c\u89c0\u5efa\u69cb", "stages": []}'
        result = extract_json_object(raw)
        assert result["title"] == "\u4e16\u754c\u89c0\u5efa\u69cb"

    def test_unicode_in_fence(self):
        raw = '```json\n{"name": "\u7814\u7a76\u968e\u6bb5"}\n```'
        result = extract_json_object(raw)
        assert result["name"] == "\u7814\u7a76\u968e\u6bb5"

    # --- Error cases ---

    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="Empty input"):
            extract_json_object("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="Empty input"):
            extract_json_object("   \n  ")

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="No valid JSON object"):
            extract_json_object("This is just plain text with no JSON at all.")

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="No valid JSON object"):
            extract_json_object("{invalid json content!!}")

    def test_list_not_dict_raises(self):
        with pytest.raises(ValueError, match="Expected JSON object"):
            extract_json_object('[1, 2, 3]')

    def test_list_in_fence_raises(self):
        raw = '```json\n[1, 2, 3]\n```'
        with pytest.raises(ValueError, match="Expected JSON object"):
            extract_json_object(raw)

    # --- Additional edge cases ---

    def test_json_string_containing_braces(self):
        raw = '{"code": "function() { return {}; }"}'
        result = extract_json_object(raw)
        assert result["code"] == "function() { return {}; }"

    def test_deeply_nested_objects(self):
        raw = '{"a": {"b": {"c": {"d": "deep"}}}}'
        result = extract_json_object(raw)
        assert result["a"]["b"]["c"]["d"] == "deep"

    def test_fence_with_trailing_whitespace(self):
        raw = '```json  \n{"key": "value"}\n```  \n'
        result = extract_json_object(raw)
        assert result == {"key": "value"}

    def test_number_top_level_raises(self):
        with pytest.raises(ValueError, match="Expected JSON object"):
            extract_json_object("42")

    def test_string_top_level_raises(self):
        with pytest.raises(ValueError, match="Expected JSON object"):
            extract_json_object('"just a string"')

    def test_bool_top_level_raises(self):
        with pytest.raises(ValueError, match="Expected JSON object"):
            extract_json_object("true")

    def test_real_world_claude_output(self):
        """Simulate typical Claude output with explanation before/after JSON."""
        raw = (
            "Here is the pipeline plan I've created based on your request:\n\n"
            "```json\n"
            '{\n'
            '  "title": "Fantasy World",\n'
            '  "stages": [\n'
            '    {"number": 1, "name": "research", "prompt": "Research fantasy tropes"}\n'
            '  ]\n'
            '}\n'
            "```\n\n"
            "This plan includes one research stage that will analyze common fantasy elements."
        )
        result = extract_json_object(raw)
        assert result["title"] == "Fantasy World"
        assert len(result["stages"]) == 1


# ===== TestPlanBuildSystemPrompt =====


class TestPlanBuildSystemPrompt:
    """Tests for PLAN_BUILD_SYSTEM_PROMPT content."""

    def test_contains_json_schema(self):
        assert "TaskPlan JSON Schema" in PLAN_BUILD_SYSTEM_PROMPT

    def test_contains_field_semantics(self):
        assert "Field Semantics" in PLAN_BUILD_SYSTEM_PROMPT
        assert "tool_set" in PLAN_BUILD_SYSTEM_PROMPT
        assert "context_section" in PLAN_BUILD_SYSTEM_PROMPT
        assert "number" in PLAN_BUILD_SYSTEM_PROMPT

    def test_contains_design_principles(self):
        assert "Design Principles" in PLAN_BUILD_SYSTEM_PROMPT
        assert "Research before writing" in PLAN_BUILD_SYSTEM_PROMPT

    def test_contains_output_format(self):
        assert "```json" in PLAN_BUILD_SYSTEM_PROMPT
        assert "Output Format" in PLAN_BUILD_SYSTEM_PROMPT

    def test_contains_modification_instructions(self):
        assert "Modifying an Existing Plan" in PLAN_BUILD_SYSTEM_PROMPT
