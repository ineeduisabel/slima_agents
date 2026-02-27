"""Integration tests for the orchestrator with mocked agents."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.base import AgentResult
from slima_agents.progress import ProgressEmitter
from slima_agents.slima.client import SlimaClient
from slima_agents.slima.types import Book, Commit
from slima_agents.lang import detect_language, flatten_paths
from slima_agents.worldbuild.orchestrator import OrchestratorAgent


@pytest.fixture
def mock_slima():
    slima = AsyncMock(spec=SlimaClient)
    slima._base_url = "https://test.slima.app"
    slima.create_book = AsyncMock(
        return_value=Book.model_validate({
            "token": "bk_test",
            "title": "Test World",
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z",
        })
    )
    slima.create_file = AsyncMock()
    # Mock get_book_structure for inter-phase injection
    slima.get_book_structure = AsyncMock(return_value=[
        {"name": "meta", "kind": "folder", "position": 0, "children": [
            {"name": "overview.md", "kind": "file", "position": 0},
        ]},
    ])
    return slima


def _make_agent_result(summary="Done"):
    return AgentResult(summary=summary, full_output=summary, duration_s=1.0)


@pytest.mark.asyncio
async def test_orchestrator_creates_book(mock_slima):
    """Orchestrator should create a book and run all phases."""
    with patch("slima_agents.worldbuild.orchestrator.ResearchAgent") as MockResearch, \
         patch("slima_agents.worldbuild.orchestrator.CosmologyAgent") as MockCosmo, \
         patch("slima_agents.worldbuild.orchestrator.GeographyAgent") as MockGeo, \
         patch("slima_agents.worldbuild.orchestrator.HistoryAgent") as MockHist, \
         patch("slima_agents.worldbuild.orchestrator.PeoplesAgent") as MockPeoples, \
         patch("slima_agents.worldbuild.orchestrator.CulturesAgent") as MockCultures, \
         patch("slima_agents.worldbuild.orchestrator.PowerStructuresAgent") as MockPower, \
         patch("slima_agents.worldbuild.orchestrator.CharactersAgent") as MockChars, \
         patch("slima_agents.worldbuild.orchestrator.ItemsAgent") as MockItems, \
         patch("slima_agents.worldbuild.orchestrator.BestiaryAgent") as MockBestiary, \
         patch("slima_agents.worldbuild.orchestrator.NarrativeAgent") as MockNarr, \
         patch("slima_agents.worldbuild.orchestrator.ValidationAgent") as MockValid:

        # Make all agent constructors return mocks with async run()
        for MockCls in [MockResearch, MockCosmo, MockGeo, MockHist, MockPeoples,
                        MockCultures, MockPower, MockChars, MockItems, MockBestiary,
                        MockNarr, MockValid]:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_make_agent_result())
            MockCls.return_value = instance

        orch = OrchestratorAgent(
            slima_client=mock_slima,
        )

        book_token = await orch.run("Test World")
        assert book_token == "bk_test"
        mock_slima.create_book.assert_called_once()
        # At least overview + glossary files created
        assert mock_slima.create_file.call_count >= 2


@pytest.mark.asyncio
async def test_orchestrator_injects_book_structure(mock_slima):
    """Orchestrator should inject book structure between phases."""
    with patch("slima_agents.worldbuild.orchestrator.ResearchAgent") as MockResearch, \
         patch("slima_agents.worldbuild.orchestrator.CosmologyAgent") as MockCosmo, \
         patch("slima_agents.worldbuild.orchestrator.GeographyAgent") as MockGeo, \
         patch("slima_agents.worldbuild.orchestrator.HistoryAgent") as MockHist, \
         patch("slima_agents.worldbuild.orchestrator.PeoplesAgent") as MockPeoples, \
         patch("slima_agents.worldbuild.orchestrator.CulturesAgent") as MockCultures, \
         patch("slima_agents.worldbuild.orchestrator.PowerStructuresAgent") as MockPower, \
         patch("slima_agents.worldbuild.orchestrator.CharactersAgent") as MockChars, \
         patch("slima_agents.worldbuild.orchestrator.ItemsAgent") as MockItems, \
         patch("slima_agents.worldbuild.orchestrator.BestiaryAgent") as MockBestiary, \
         patch("slima_agents.worldbuild.orchestrator.NarrativeAgent") as MockNarr, \
         patch("slima_agents.worldbuild.orchestrator.ValidationAgent") as MockValid:

        for MockCls in [MockResearch, MockCosmo, MockGeo, MockHist, MockPeoples,
                        MockCultures, MockPower, MockChars, MockItems, MockBestiary,
                        MockNarr, MockValid]:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_make_agent_result())
            MockCls.return_value = instance

        # ResearchAgent needs string attributes for title/description
        MockResearch.return_value.suggested_title = "Test World"
        MockResearch.return_value.suggested_description = "A test world"

        orch = OrchestratorAgent(
            slima_client=mock_slima,
        )

        await orch.run("Test World")

        # get_book_structure is called:
        #   - 2x per _run_phase (pre/post file diff) x 7 phases = 14
        #   - 4x _inject_book_structure (after phases 2-5)
        #   - 1x for README
        assert mock_slima.get_book_structure.call_count == 19
        # Context should have book_structure populated
        structure = await orch.context.read("book_structure")
        assert "meta/" in structure
        assert "overview.md" in structure


@pytest.mark.asyncio
async def test_orchestrator_splits_items_and_bestiary(mock_slima):
    """Orchestrator Phase 5 should run Characters, Items, and Bestiary in parallel."""
    with patch("slima_agents.worldbuild.orchestrator.ResearchAgent") as MockResearch, \
         patch("slima_agents.worldbuild.orchestrator.CosmologyAgent") as MockCosmo, \
         patch("slima_agents.worldbuild.orchestrator.GeographyAgent") as MockGeo, \
         patch("slima_agents.worldbuild.orchestrator.HistoryAgent") as MockHist, \
         patch("slima_agents.worldbuild.orchestrator.PeoplesAgent") as MockPeoples, \
         patch("slima_agents.worldbuild.orchestrator.CulturesAgent") as MockCultures, \
         patch("slima_agents.worldbuild.orchestrator.PowerStructuresAgent") as MockPower, \
         patch("slima_agents.worldbuild.orchestrator.CharactersAgent") as MockChars, \
         patch("slima_agents.worldbuild.orchestrator.ItemsAgent") as MockItems, \
         patch("slima_agents.worldbuild.orchestrator.BestiaryAgent") as MockBestiary, \
         patch("slima_agents.worldbuild.orchestrator.NarrativeAgent") as MockNarr, \
         patch("slima_agents.worldbuild.orchestrator.ValidationAgent") as MockValid:

        for MockCls in [MockResearch, MockCosmo, MockGeo, MockHist, MockPeoples,
                        MockCultures, MockPower, MockChars, MockItems, MockBestiary,
                        MockNarr, MockValid]:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_make_agent_result())
            MockCls.return_value = instance

        orch = OrchestratorAgent(slima_client=mock_slima)
        await orch.run("Test World")

        # Items and Bestiary are now separate agents, both should be constructed
        MockItems.assert_called_once()
        MockBestiary.assert_called_once()
        MockChars.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_runs_two_validation_rounds(mock_slima):
    """Orchestrator should run ValidationAgent twice: round 1 and round 2."""
    with patch("slima_agents.worldbuild.orchestrator.ResearchAgent") as MockResearch, \
         patch("slima_agents.worldbuild.orchestrator.CosmologyAgent") as MockCosmo, \
         patch("slima_agents.worldbuild.orchestrator.GeographyAgent") as MockGeo, \
         patch("slima_agents.worldbuild.orchestrator.HistoryAgent") as MockHist, \
         patch("slima_agents.worldbuild.orchestrator.PeoplesAgent") as MockPeoples, \
         patch("slima_agents.worldbuild.orchestrator.CulturesAgent") as MockCultures, \
         patch("slima_agents.worldbuild.orchestrator.PowerStructuresAgent") as MockPower, \
         patch("slima_agents.worldbuild.orchestrator.CharactersAgent") as MockChars, \
         patch("slima_agents.worldbuild.orchestrator.ItemsAgent") as MockItems, \
         patch("slima_agents.worldbuild.orchestrator.BestiaryAgent") as MockBestiary, \
         patch("slima_agents.worldbuild.orchestrator.NarrativeAgent") as MockNarr, \
         patch("slima_agents.worldbuild.orchestrator.ValidationAgent") as MockValid:

        for MockCls in [MockResearch, MockCosmo, MockGeo, MockHist, MockPeoples,
                        MockCultures, MockPower, MockChars, MockItems, MockBestiary,
                        MockNarr]:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_make_agent_result())
            MockCls.return_value = instance

        # ValidationAgent is called twice — return a new mock each time
        valid_instances = []

        def make_valid_instance(**kwargs):
            inst = AsyncMock()
            inst.run = AsyncMock(return_value=_make_agent_result())
            inst.validation_round = kwargs.get("validation_round", 1)
            valid_instances.append(inst)
            return inst

        MockValid.side_effect = make_valid_instance

        orch = OrchestratorAgent(slima_client=mock_slima)
        await orch.run("Test World")

        # ValidationAgent should be constructed exactly twice
        assert MockValid.call_count == 2

        # First call: round 1, second call: round 2
        calls = MockValid.call_args_list
        assert calls[0].kwargs.get("validation_round") == 1
        assert calls[1].kwargs.get("validation_round") == 2

        # Both instances should have run()
        assert len(valid_instances) == 2
        for inst in valid_instances:
            inst.run.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_emits_json_progress(mock_slima):
    """Orchestrator should emit NDJSON events when emitter is enabled."""
    buf = StringIO()
    emitter = ProgressEmitter(enabled=True, _stream=buf)

    with patch("slima_agents.worldbuild.orchestrator.ResearchAgent") as MockResearch, \
         patch("slima_agents.worldbuild.orchestrator.CosmologyAgent") as MockCosmo, \
         patch("slima_agents.worldbuild.orchestrator.GeographyAgent") as MockGeo, \
         patch("slima_agents.worldbuild.orchestrator.HistoryAgent") as MockHist, \
         patch("slima_agents.worldbuild.orchestrator.PeoplesAgent") as MockPeoples, \
         patch("slima_agents.worldbuild.orchestrator.CulturesAgent") as MockCultures, \
         patch("slima_agents.worldbuild.orchestrator.PowerStructuresAgent") as MockPower, \
         patch("slima_agents.worldbuild.orchestrator.CharactersAgent") as MockChars, \
         patch("slima_agents.worldbuild.orchestrator.ItemsAgent") as MockItems, \
         patch("slima_agents.worldbuild.orchestrator.BestiaryAgent") as MockBestiary, \
         patch("slima_agents.worldbuild.orchestrator.NarrativeAgent") as MockNarr, \
         patch("slima_agents.worldbuild.orchestrator.ValidationAgent") as MockValid:

        for MockCls in [MockResearch, MockCosmo, MockGeo, MockHist, MockPeoples,
                        MockCultures, MockPower, MockChars, MockItems, MockBestiary,
                        MockNarr, MockValid]:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_make_agent_result())
            MockCls.return_value = instance

        # ResearchAgent needs string attributes for title/description
        MockResearch.return_value.suggested_title = "Test World"
        MockResearch.return_value.suggested_description = "A test world"

        orch = OrchestratorAgent(
            slima_client=mock_slima,
            emitter=emitter,
        )
        await orch.run("Test World")

    # Parse all events
    buf.seek(0)
    events = [json.loads(line) for line in buf if line.strip()]
    event_types = [e["event"] for e in events]

    # Should start with pipeline_start and end with pipeline_complete
    assert event_types[0] == "pipeline_start"
    assert events[0]["prompt"] == "Test World"
    assert events[0]["total_stages"] == 12
    assert event_types[-1] == "pipeline_complete"
    assert events[-1]["success"] is True
    assert events[-1]["book_token"] == "bk_test"

    # Should contain expected event types
    assert "stage_start" in event_types
    assert "stage_complete" in event_types
    assert "agent_start" in event_types
    assert "agent_complete" in event_types
    assert "book_created" in event_types
    assert "file_created" in event_types


class TestFlattenPaths:
    """Tests for flatten_paths()."""

    def test_simple_structure(self):
        nodes = [
            {"name": "meta", "kind": "folder", "children": [
                {"name": "overview.md", "kind": "file"},
            ]},
            {"name": "README.md", "kind": "file"},
        ]
        paths = flatten_paths(nodes)
        assert set(paths) == {"meta/overview.md", "README.md"}

    def test_nested_folders(self):
        nodes = [
            {"name": "worldview", "kind": "folder", "children": [
                {"name": "cosmology", "kind": "folder", "children": [
                    {"name": "creation.md", "kind": "file"},
                    {"name": "magic.md", "kind": "file"},
                ]},
                {"name": "overview.md", "kind": "file"},
            ]},
        ]
        paths = flatten_paths(nodes)
        assert set(paths) == {
            "worldview/cosmology/creation.md",
            "worldview/cosmology/magic.md",
            "worldview/overview.md",
        }

    def test_empty(self):
        assert flatten_paths([]) == []


class TestDetectLanguage:
    """Tests for detect_language()."""

    def test_chinese(self):
        assert detect_language("建構一個台灣鬼怪世界") == "zh"

    def test_japanese_hiragana(self):
        assert detect_language("ファンタジーの世界を作ってください") == "ja"

    def test_japanese_katakana(self):
        assert detect_language("ファンタジー世界") == "ja"

    def test_korean(self):
        assert detect_language("판타지 세계를 만들어주세요") == "ko"

    def test_english(self):
        assert detect_language("Build a fantasy world") == "en"

    def test_mixed_cjk_no_kana_hangul(self):
        # CJK ideographs only (no kana/hangul) → zh
        assert detect_language("三國演義") == "zh"

    def test_empty(self):
        assert detect_language("") == "en"
