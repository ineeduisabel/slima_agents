"""Tests for DynamicContext."""

from __future__ import annotations

import json

import pytest

from slima_agents.pipeline.context import DynamicContext
from slima_agents.pipeline.models import PipelinePlan, StageDefinition


# --- Helpers ---


def _make_context(sections=None) -> DynamicContext:
    return DynamicContext(allowed_sections=sections or ["concept", "characters"])


def _make_plan(**overrides) -> PipelinePlan:
    defaults = dict(
        title="Test",
        description="Test plan",
        genre="mystery",
        language="zh",
        concept_summary="Summary",
        context_sections=["concept", "crime_design", "characters"],
        stages=[
            StageDefinition(
                number=1, name="s1", display_name="S1",
                instructions="I", initial_message="M",
            ),
        ],
    )
    defaults.update(overrides)
    return PipelinePlan(**defaults)


# --- from_plan ---


def test_from_plan_creates_sections():
    """DynamicContext.from_plan should create context with plan's sections."""
    plan = _make_plan(context_sections=["concept", "crime_design", "characters"])
    ctx = DynamicContext.from_plan(plan)
    assert "concept" in ctx.SECTIONS
    assert "crime_design" in ctx.SECTIONS
    assert "characters" in ctx.SECTIONS
    assert "book_structure" in ctx.SECTIONS  # always implicit


def test_from_plan_deduplicates_book_structure():
    """book_structure should not be duplicated if already in plan."""
    plan = _make_plan(context_sections=["concept", "book_structure"])
    ctx = DynamicContext.from_plan(plan)
    assert ctx.SECTIONS.count("book_structure") == 1


# --- read / write / append ---


@pytest.mark.asyncio
async def test_write_and_read():
    """Should write and read back a section value."""
    ctx = _make_context()
    await ctx.write("concept", "The victim was found dead")
    result = await ctx.read("concept")
    assert result == "The victim was found dead"


@pytest.mark.asyncio
async def test_read_empty_section():
    """Should return empty string for unwritten sections."""
    ctx = _make_context()
    result = await ctx.read("concept")
    assert result == ""


@pytest.mark.asyncio
async def test_read_unknown_section():
    """Should return error message for unknown section."""
    ctx = _make_context(["concept"])
    result = await ctx.read("nonexistent")
    assert "Unknown section" in result


@pytest.mark.asyncio
async def test_write_unknown_section():
    """Should return error message for unknown section."""
    ctx = _make_context(["concept"])
    result = await ctx.write("nonexistent", "data")
    assert "Unknown section" in result


@pytest.mark.asyncio
async def test_append():
    """Should append to existing content with newline separator."""
    ctx = _make_context()
    await ctx.write("concept", "Line 1")
    await ctx.append("concept", "Line 2")
    result = await ctx.read("concept")
    assert result == "Line 1\nLine 2"


@pytest.mark.asyncio
async def test_append_to_empty():
    """Append to empty section should not add leading newline."""
    ctx = _make_context()
    await ctx.append("concept", "First line")
    result = await ctx.read("concept")
    assert result == "First line"


@pytest.mark.asyncio
async def test_append_unknown_section():
    """Should return error for unknown section."""
    ctx = _make_context(["concept"])
    result = await ctx.append("nonexistent", "data")
    assert "Unknown section" in result


# --- serialize_for_prompt ---


@pytest.mark.asyncio
async def test_serialize_empty():
    """Empty context should return placeholder."""
    ctx = _make_context()
    assert ctx.serialize_for_prompt() == "(No context populated yet.)"


@pytest.mark.asyncio
async def test_serialize_with_data():
    """Should render non-empty sections with headers."""
    ctx = _make_context()
    await ctx.write("concept", "A murder")
    await ctx.write("characters", "Detective Smith")
    output = ctx.serialize_for_prompt()
    assert "## Concept\nA murder" in output
    assert "## Characters\nDetective Smith" in output


@pytest.mark.asyncio
async def test_serialize_includes_user_prompt():
    """Should include user_prompt at the top."""
    ctx = _make_context()
    ctx.user_prompt = "Write a mystery"
    await ctx.write("concept", "A murder")
    output = ctx.serialize_for_prompt()
    assert output.startswith("## User Request\nWrite a mystery")


@pytest.mark.asyncio
async def test_serialize_skips_empty_sections():
    """Should skip sections with no content."""
    ctx = _make_context(["concept", "characters", "setting"])
    await ctx.write("concept", "content")
    output = ctx.serialize_for_prompt()
    assert "Concept" in output
    assert "Characters" not in output
    assert "Setting" not in output


# --- snapshot roundtrip ---


@pytest.mark.asyncio
async def test_snapshot_roundtrip():
    """to_snapshot → from_snapshot should preserve all data."""
    ctx = _make_context(["concept", "crime_design", "characters"])
    ctx.user_prompt = "Write a mystery"
    await ctx.write("concept", "The crime")
    await ctx.write("characters", "Detective")

    snapshot = ctx.to_snapshot()
    assert snapshot["user_prompt"] == "Write a mystery"
    assert snapshot["concept"] == "The crime"
    assert snapshot["characters"] == "Detective"
    assert "_allowed_sections" in snapshot

    # Restore into a fresh context
    ctx2 = DynamicContext(allowed_sections=[])
    ctx2.from_snapshot(snapshot)
    assert ctx2.user_prompt == "Write a mystery"
    assert await ctx2.read("concept") == "The crime"
    assert await ctx2.read("characters") == "Detective"
    assert "crime_design" in ctx2.SECTIONS


@pytest.mark.asyncio
async def test_snapshot_preserves_allowed_sections():
    """Snapshot should include _allowed_sections for resume."""
    ctx = _make_context(["a", "b", "c"])
    snapshot = ctx.to_snapshot()
    assert "a" in snapshot["_allowed_sections"]
    assert "b" in snapshot["_allowed_sections"]
    assert "c" in snapshot["_allowed_sections"]
    assert "book_structure" in snapshot["_allowed_sections"]


@pytest.mark.asyncio
async def test_snapshot_json_safe():
    """Snapshot should be JSON-serializable."""
    ctx = _make_context(["concept"])
    ctx.user_prompt = "中文提示"
    await ctx.write("concept", "內容")
    snapshot = ctx.to_snapshot()
    json_str = json.dumps(snapshot, ensure_ascii=False)
    restored = json.loads(json_str)
    assert restored["concept"] == "內容"


# --- book_structure always available ---


@pytest.mark.asyncio
async def test_book_structure_always_available():
    """book_structure should always be writable even if not in explicit list."""
    ctx = _make_context(["concept"])
    assert "book_structure" in ctx.SECTIONS
    await ctx.write("book_structure", "├── file.md")
    result = await ctx.read("book_structure")
    assert result == "├── file.md"
