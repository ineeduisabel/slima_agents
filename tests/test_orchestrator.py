"""Integration tests for the orchestrator with mocked agents."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from slima_agents.agents.base import AgentResult
from slima_agents.slima.client import SlimaClient
from slima_agents.slima.types import Book, Commit
from slima_agents.worldbuild.orchestrator import OrchestratorAgent, _detect_language


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
    return AgentResult(summary=summary, full_output=summary)


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

        orch = OrchestratorAgent(
            slima_client=mock_slima,
        )

        await orch.run("Test World")

        # get_book_structure should be called after phases 2, 3, 4, 5, and for README
        assert mock_slima.get_book_structure.call_count == 5
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


class TestDetectLanguage:
    """Tests for _detect_language()."""

    def test_chinese(self):
        assert _detect_language("建構一個台灣鬼怪世界") == "zh"

    def test_japanese_hiragana(self):
        assert _detect_language("ファンタジーの世界を作ってください") == "ja"

    def test_japanese_katakana(self):
        assert _detect_language("ファンタジー世界") == "ja"

    def test_korean(self):
        assert _detect_language("판타지 세계를 만들어주세요") == "ko"

    def test_english(self):
        assert _detect_language("Build a fantasy world") == "en"

    def test_mixed_cjk_no_kana_hangul(self):
        # CJK ideographs only (no kana/hangul) → zh
        assert _detect_language("三國演義") == "zh"

    def test_empty(self):
        assert _detect_language("") == "en"
