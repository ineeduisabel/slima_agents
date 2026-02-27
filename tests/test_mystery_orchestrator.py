"""Integration tests for the mystery orchestrator with mocked agents."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slima_agents.agents.base import AgentResult
from slima_agents.progress import ProgressEmitter
from slima_agents.slima.client import SlimaClient
from slima_agents.slima.types import Book
from slima_agents.mystery.orchestrator import MysteryOrchestratorAgent


@pytest.fixture
def mock_slima():
    slima = AsyncMock(spec=SlimaClient)
    slima._base_url = "https://test.slima.app"
    slima.create_book = AsyncMock(
        return_value=Book.model_validate({
            "token": "bk_mystery_test",
            "title": "Test Mystery",
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z",
        })
    )
    slima.create_file = AsyncMock()
    slima.write_file = AsyncMock()
    slima.read_file = AsyncMock(
        return_value=MagicMock(content="mock file content")
    )
    slima.get_book_structure = AsyncMock(return_value=[
        {"name": "planning", "kind": "folder", "position": 0, "children": [
            {"name": "concept-overview.md", "kind": "file", "position": 0},
        ]},
    ])
    return slima


def _make_agent_result(summary="Done"):
    return AgentResult(summary=summary, full_output=summary, duration_s=1.0)


_ALL_AGENT_PATCHES = [
    "slima_agents.mystery.orchestrator.PlannerAgent",
    "slima_agents.mystery.orchestrator.CrimeDesignAgent",
    "slima_agents.mystery.orchestrator.MysteryCharactersAgent",
    "slima_agents.mystery.orchestrator.PlotArchitectureAgent",
    "slima_agents.mystery.orchestrator.SettingAgent",
    "slima_agents.mystery.orchestrator.Act1WriterAgent",
    "slima_agents.mystery.orchestrator.Act2WriterAgent",
    "slima_agents.mystery.orchestrator.Act3WriterAgent",
    "slima_agents.mystery.orchestrator.MysteryValidationAgent",
    "slima_agents.mystery.orchestrator.PolishAgent",
]


def _patch_all_agents():
    """Context manager that patches all mystery agents."""
    import contextlib
    patchers = [patch(p) for p in _ALL_AGENT_PATCHES]
    return contextlib.ExitStack(), patchers


@pytest.mark.asyncio
async def test_mystery_orchestrator_creates_book(mock_slima):
    """Mystery orchestrator should create a book and run all stages."""
    with patch("slima_agents.mystery.orchestrator.PlannerAgent") as MockPlanner, \
         patch("slima_agents.mystery.orchestrator.CrimeDesignAgent") as MockCrime, \
         patch("slima_agents.mystery.orchestrator.MysteryCharactersAgent") as MockChars, \
         patch("slima_agents.mystery.orchestrator.PlotArchitectureAgent") as MockPlot, \
         patch("slima_agents.mystery.orchestrator.SettingAgent") as MockSetting, \
         patch("slima_agents.mystery.orchestrator.Act1WriterAgent") as MockAct1, \
         patch("slima_agents.mystery.orchestrator.Act2WriterAgent") as MockAct2, \
         patch("slima_agents.mystery.orchestrator.Act3WriterAgent") as MockAct3, \
         patch("slima_agents.mystery.orchestrator.MysteryValidationAgent") as MockValid, \
         patch("slima_agents.mystery.orchestrator.PolishAgent") as MockPolish:

        for MockCls in [MockPlanner, MockCrime, MockChars, MockPlot, MockSetting,
                        MockAct1, MockAct2, MockAct3, MockValid, MockPolish]:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_make_agent_result())
            instance.name = "MockAgent"
            MockCls.return_value = instance

        # Planner needs title/description
        MockPlanner.return_value.suggested_title = "Test Mystery"
        MockPlanner.return_value.suggested_description = "A test mystery"

        orch = MysteryOrchestratorAgent(slima_client=mock_slima)
        book_token = await orch.run("Test mystery prompt")

        assert book_token == "bk_mystery_test"
        mock_slima.create_book.assert_called_once()


@pytest.mark.asyncio
async def test_mystery_orchestrator_all_stages_run(mock_slima):
    """All agent types should be constructed."""
    with patch("slima_agents.mystery.orchestrator.PlannerAgent") as MockPlanner, \
         patch("slima_agents.mystery.orchestrator.CrimeDesignAgent") as MockCrime, \
         patch("slima_agents.mystery.orchestrator.MysteryCharactersAgent") as MockChars, \
         patch("slima_agents.mystery.orchestrator.PlotArchitectureAgent") as MockPlot, \
         patch("slima_agents.mystery.orchestrator.SettingAgent") as MockSetting, \
         patch("slima_agents.mystery.orchestrator.Act1WriterAgent") as MockAct1, \
         patch("slima_agents.mystery.orchestrator.Act2WriterAgent") as MockAct2, \
         patch("slima_agents.mystery.orchestrator.Act3WriterAgent") as MockAct3, \
         patch("slima_agents.mystery.orchestrator.MysteryValidationAgent") as MockValid, \
         patch("slima_agents.mystery.orchestrator.PolishAgent") as MockPolish:

        for MockCls in [MockPlanner, MockCrime, MockChars, MockPlot, MockSetting,
                        MockAct1, MockAct2, MockAct3, MockValid, MockPolish]:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_make_agent_result())
            instance.name = "MockAgent"
            MockCls.return_value = instance

        MockPlanner.return_value.suggested_title = "Test"
        MockPlanner.return_value.suggested_description = "Test"

        orch = MysteryOrchestratorAgent(slima_client=mock_slima)
        await orch.run("Test mystery")

        # All agents should be constructed
        MockPlanner.assert_called_once()
        MockCrime.assert_called_once()
        MockChars.assert_called_once()
        MockPlot.assert_called_once()
        MockSetting.assert_called_once()
        MockAct1.assert_called_once()
        MockAct2.assert_called_once()
        MockAct3.assert_called_once()
        # Validation is called twice (R1 + R2)
        assert MockValid.call_count == 2
        MockPolish.assert_called_once()


@pytest.mark.asyncio
async def test_mystery_orchestrator_validation_rounds(mock_slima):
    """Validation should run two rounds (R1 and R2)."""
    with patch("slima_agents.mystery.orchestrator.PlannerAgent") as MockPlanner, \
         patch("slima_agents.mystery.orchestrator.CrimeDesignAgent") as MockCrime, \
         patch("slima_agents.mystery.orchestrator.MysteryCharactersAgent") as MockChars, \
         patch("slima_agents.mystery.orchestrator.PlotArchitectureAgent") as MockPlot, \
         patch("slima_agents.mystery.orchestrator.SettingAgent") as MockSetting, \
         patch("slima_agents.mystery.orchestrator.Act1WriterAgent") as MockAct1, \
         patch("slima_agents.mystery.orchestrator.Act2WriterAgent") as MockAct2, \
         patch("slima_agents.mystery.orchestrator.Act3WriterAgent") as MockAct3, \
         patch("slima_agents.mystery.orchestrator.MysteryValidationAgent") as MockValid, \
         patch("slima_agents.mystery.orchestrator.PolishAgent") as MockPolish:

        for MockCls in [MockPlanner, MockCrime, MockChars, MockPlot, MockSetting,
                        MockAct1, MockAct2, MockAct3, MockPolish]:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_make_agent_result())
            instance.name = "MockAgent"
            MockCls.return_value = instance

        MockPlanner.return_value.suggested_title = "Test"
        MockPlanner.return_value.suggested_description = "Test"

        # Track validation instances
        valid_instances = []

        def make_valid_instance(**kwargs):
            inst = AsyncMock()
            inst.run = AsyncMock(return_value=_make_agent_result())
            inst.name = f"MysteryValidationAgent-R{kwargs.get('validation_round', 1)}"
            inst.validation_round = kwargs.get("validation_round", 1)
            valid_instances.append(inst)
            return inst

        MockValid.side_effect = make_valid_instance

        orch = MysteryOrchestratorAgent(slima_client=mock_slima)
        await orch.run("Test")

        assert MockValid.call_count == 2
        calls = MockValid.call_args_list
        assert calls[0].kwargs.get("validation_round") == 1
        assert calls[1].kwargs.get("validation_round") == 2


@pytest.mark.asyncio
async def test_mystery_orchestrator_emits_json_progress(mock_slima):
    """Mystery orchestrator should emit NDJSON events when emitter is enabled."""
    buf = StringIO()
    emitter = ProgressEmitter(enabled=True, _stream=buf)

    with patch("slima_agents.mystery.orchestrator.PlannerAgent") as MockPlanner, \
         patch("slima_agents.mystery.orchestrator.CrimeDesignAgent") as MockCrime, \
         patch("slima_agents.mystery.orchestrator.MysteryCharactersAgent") as MockChars, \
         patch("slima_agents.mystery.orchestrator.PlotArchitectureAgent") as MockPlot, \
         patch("slima_agents.mystery.orchestrator.SettingAgent") as MockSetting, \
         patch("slima_agents.mystery.orchestrator.Act1WriterAgent") as MockAct1, \
         patch("slima_agents.mystery.orchestrator.Act2WriterAgent") as MockAct2, \
         patch("slima_agents.mystery.orchestrator.Act3WriterAgent") as MockAct3, \
         patch("slima_agents.mystery.orchestrator.MysteryValidationAgent") as MockValid, \
         patch("slima_agents.mystery.orchestrator.PolishAgent") as MockPolish:

        for MockCls in [MockPlanner, MockCrime, MockChars, MockPlot, MockSetting,
                        MockAct1, MockAct2, MockAct3, MockValid, MockPolish]:
            instance = AsyncMock()
            instance.run = AsyncMock(return_value=_make_agent_result())
            instance.name = "MockAgent"
            MockCls.return_value = instance

        MockPlanner.return_value.suggested_title = "Test"
        MockPlanner.return_value.suggested_description = "Test"

        orch = MysteryOrchestratorAgent(
            slima_client=mock_slima, emitter=emitter,
        )
        await orch.run("Test Mystery")

    buf.seek(0)
    events = [json.loads(line) for line in buf if line.strip()]
    event_types = [e["event"] for e in events]

    assert event_types[0] == "pipeline_start"
    assert events[0]["prompt"] == "Test Mystery"
    assert event_types[-1] == "pipeline_complete"
    assert events[-1]["success"] is True
    assert events[-1]["book_token"] == "bk_mystery_test"

    assert "stage_start" in event_types
    assert "stage_complete" in event_types
    assert "agent_start" in event_types
    assert "agent_complete" in event_types
    assert "book_created" in event_types


@pytest.mark.asyncio
async def test_mystery_orchestrator_resume_all_done(mock_slima):
    """Resume mode should skip when all stages are completed."""
    # Mock the tracker load to return all-completed
    md = (
        "# Pipeline Progress\n\n"
        "- **Pipeline**: mystery\n"
        "- **Status**: completed\n"
        "- **Started**: 2026-01-01T00:00:00Z\n"
        "- **Prompt**: old prompt\n\n"
        "## Stages\n\n"
        "| # | Stage | Status | Started | Completed | Duration | Notes |\n"
        "|---|-------|--------|---------|-----------|----------|-------|\n"
        "| 1 | planning | completed | 10:00:00 | 10:05:00 | 300s | |\n"
        "| 2 | book_setup | completed | 10:05:00 | 10:05:02 | 2s | |\n"
        "| 3 | crime_design | completed | 10:05:03 | 10:10:00 | 297s | |\n"
        "| 4 | characters | completed | 10:10:01 | 10:15:00 | 299s | |\n"
        "| 5 | plot_architecture | completed | 10:15:01 | 10:20:00 | 299s | |\n"
        "| 6 | setting | completed | 10:20:01 | 10:25:00 | 299s | |\n"
        "| 7 | act1_writing | completed | 10:25:01 | 10:30:00 | 299s | |\n"
        "| 8 | act2_writing | completed | 10:30:01 | 10:35:00 | 299s | |\n"
        "| 9 | act3_writing | completed | 10:35:01 | 10:40:00 | 299s | |\n"
        "| 10 | validation | completed | 10:40:01 | 10:45:00 | 299s | |\n"
        "| 11 | polish | completed | 10:45:01 | 10:50:00 | 299s | |\n"
    )
    resp = MagicMock()
    resp.content = md
    mock_slima.read_file.return_value = resp

    orch = MysteryOrchestratorAgent(slima_client=mock_slima)
    book_token = await orch.run("Continue", resume_book="bk_existing")

    assert book_token == "bk_existing"
    # Should NOT create a new book
    mock_slima.create_book.assert_not_called()
