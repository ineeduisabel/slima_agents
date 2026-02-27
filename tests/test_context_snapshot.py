"""BDD tests for Phase 4: Context snapshot persistence.

Contexts should be able to serialize to/from JSON snapshots.
Orchestrators should save snapshots after each stage and load them on resume.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slima_agents.agents.context import WorldContext
from slima_agents.mystery.context import MysteryContext


# ===========================================================================
# Context snapshot serialization
# ===========================================================================

class TestWorldContextSnapshot:
    """WorldContext should support to_snapshot() and from_snapshot()."""

    @pytest.mark.asyncio
    async def test_to_snapshot_captures_all_sections(self):
        """to_snapshot() should return a dict with user_prompt and all non-empty sections."""
        ctx = WorldContext()
        ctx.user_prompt = "Build a fantasy world"
        await ctx.write("overview", "A vast world of magic.")
        await ctx.write("cosmology", "Three moons orbit the planet.")
        # Leave others empty

        snapshot = ctx.to_snapshot()
        assert snapshot["user_prompt"] == "Build a fantasy world"
        assert snapshot["overview"] == "A vast world of magic."
        assert snapshot["cosmology"] == "Three moons orbit the planet."
        # Empty sections should not be in snapshot
        assert "geography" not in snapshot
        assert "history" not in snapshot

    @pytest.mark.asyncio
    async def test_from_snapshot_restores_context(self):
        """from_snapshot() should populate context from a snapshot dict."""
        ctx = WorldContext()
        snapshot = {
            "user_prompt": "Build a sci-fi world",
            "overview": "Space opera setting.",
            "characters": "Captain Zara, Engineer Kael.",
        }
        ctx.from_snapshot(snapshot)

        assert ctx.user_prompt == "Build a sci-fi world"
        assert await ctx.read("overview") == "Space opera setting."
        assert await ctx.read("characters") == "Captain Zara, Engineer Kael."
        # Non-included sections remain empty
        assert await ctx.read("cosmology") == ""

    @pytest.mark.asyncio
    async def test_snapshot_roundtrip(self):
        """to_snapshot → JSON → from_snapshot should preserve all data."""
        ctx1 = WorldContext()
        ctx1.user_prompt = "Fantasy world"
        await ctx1.write("overview", "Dragons and wizards.")
        await ctx1.write("geography", "Mountain kingdoms.")
        await ctx1.write("naming_conventions", "Nordic-style names.")

        json_str = json.dumps(ctx1.to_snapshot(), ensure_ascii=False)
        data = json.loads(json_str)

        ctx2 = WorldContext()
        ctx2.from_snapshot(data)

        assert ctx2.user_prompt == ctx1.user_prompt
        assert await ctx2.read("overview") == await ctx1.read("overview")
        assert await ctx2.read("geography") == await ctx1.read("geography")
        assert await ctx2.read("naming_conventions") == await ctx1.read("naming_conventions")
        assert await ctx2.read("cosmology") == ""

    def test_to_snapshot_empty_context(self):
        """to_snapshot() on empty context returns empty dict."""
        ctx = WorldContext()
        snapshot = ctx.to_snapshot()
        assert snapshot == {}

    def test_from_snapshot_ignores_unknown_keys(self):
        """from_snapshot() should ignore keys that are not SECTIONS or user_prompt."""
        ctx = WorldContext()
        ctx.from_snapshot({"user_prompt": "test", "bogus_key": "ignore me"})
        assert ctx.user_prompt == "test"
        assert not hasattr(ctx, "bogus_key") or getattr(ctx, "bogus_key", None) is None


class TestMysteryContextSnapshot:
    """MysteryContext should support to_snapshot() and from_snapshot()."""

    @pytest.mark.asyncio
    async def test_to_snapshot_captures_all_sections(self):
        ctx = MysteryContext()
        ctx.user_prompt = "Write a locked-room mystery"
        await ctx.write("concept", "Classic whodunit in a mansion.")
        await ctx.write("crime_design", "Poisoning disguised as heart attack.")

        snapshot = ctx.to_snapshot()
        assert snapshot["user_prompt"] == "Write a locked-room mystery"
        assert snapshot["concept"] == "Classic whodunit in a mansion."
        assert snapshot["crime_design"] == "Poisoning disguised as heart attack."
        assert "characters" not in snapshot

    @pytest.mark.asyncio
    async def test_from_snapshot_restores_context(self):
        ctx = MysteryContext()
        ctx.from_snapshot({
            "user_prompt": "Noir detective story",
            "concept": "Hard-boiled detective.",
            "act1_summary": "### ch1\nThe body was found...",
        })
        assert ctx.user_prompt == "Noir detective story"
        assert await ctx.read("concept") == "Hard-boiled detective."
        assert await ctx.read("act1_summary") == "### ch1\nThe body was found..."

    @pytest.mark.asyncio
    async def test_snapshot_roundtrip(self):
        ctx1 = MysteryContext()
        ctx1.user_prompt = "Mystery"
        await ctx1.write("concept", "Locked room")
        await ctx1.write("crime_design", "Poison")
        await ctx1.write("characters", "Detective Holmes")

        json_str = json.dumps(ctx1.to_snapshot(), ensure_ascii=False)
        ctx2 = MysteryContext()
        ctx2.from_snapshot(json.loads(json_str))

        assert ctx2.user_prompt == ctx1.user_prompt
        for section in ("concept", "crime_design", "characters"):
            assert await ctx2.read(section) == await ctx1.read(section)


# ===========================================================================
# Orchestrator saves snapshot after stages
# ===========================================================================

class TestWorldbuildSnapshotSave:
    """Worldbuild orchestrator should save context snapshot after each stage."""

    @pytest.mark.asyncio
    async def test_orchestrator_saves_context_snapshot(self):
        """Orchestrator should write context-snapshot.json to the book."""
        from slima_agents.agents.base import AgentResult
        from slima_agents.slima.types import Book
        from slima_agents.worldbuild.orchestrator import OrchestratorAgent

        mock_slima = AsyncMock()
        mock_slima._base_url = "https://test.slima.app"
        mock_slima.create_book = AsyncMock(
            return_value=Book.model_validate({
                "token": "bk_snap", "title": "T",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
            })
        )
        mock_slima.create_file = AsyncMock()
        mock_slima.write_file = AsyncMock()
        mock_slima.get_book_structure = AsyncMock(return_value=[])

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
                inst = AsyncMock()
                inst.run = AsyncMock(return_value=AgentResult(
                    summary="Done", full_output="Done", duration_s=1.0,
                ))
                MockCls.return_value = inst

            MockResearch.return_value.suggested_title = "Test"
            MockResearch.return_value.suggested_description = "Test"

            orch = OrchestratorAgent(slima_client=mock_slima)
            await orch.run("Test World")

        # Check that write_file was called with context-snapshot.json
        snapshot_calls = [
            c for c in mock_slima.write_file.call_args_list
            if c.kwargs.get("path", "") == "agent-log/context-snapshot.json"
            or (len(c.args) >= 2 and c.args[1] == "agent-log/context-snapshot.json")
        ]
        assert len(snapshot_calls) > 0, "Should have saved context-snapshot.json at least once"

        # The last snapshot should be valid JSON
        last_call = snapshot_calls[-1]
        content = last_call.kwargs.get("content") or last_call.args[2]
        data = json.loads(content)
        assert "user_prompt" in data


class TestMysterySnapshotSave:
    """Mystery orchestrator should save context snapshot after stages."""

    @pytest.mark.asyncio
    async def test_orchestrator_saves_context_snapshot(self):
        from slima_agents.agents.base import AgentResult
        from slima_agents.slima.types import Book
        from slima_agents.mystery.orchestrator import MysteryOrchestratorAgent

        mock_slima = AsyncMock()
        mock_slima._base_url = "https://test.slima.app"
        mock_slima.create_book = AsyncMock(
            return_value=Book.model_validate({
                "token": "bk_msnap", "title": "M",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
            })
        )
        mock_slima.create_file = AsyncMock()
        mock_slima.write_file = AsyncMock()
        mock_slima.read_file = AsyncMock(return_value=MagicMock(content="mock"))
        mock_slima.get_book_structure = AsyncMock(return_value=[])

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
                inst = AsyncMock()
                inst.run = AsyncMock(return_value=AgentResult(
                    summary="Done", full_output="Done", duration_s=1.0,
                ))
                inst.name = "MockAgent"
                MockCls.return_value = inst

            MockPlanner.return_value.suggested_title = "Test"
            MockPlanner.return_value.suggested_description = "Test"

            orch = MysteryOrchestratorAgent(slima_client=mock_slima)
            await orch.run("Test mystery")

        snapshot_calls = [
            c for c in mock_slima.write_file.call_args_list
            if c.kwargs.get("path", "") == "agent-log/context-snapshot.json"
            or (len(c.args) >= 2 and c.args[1] == "agent-log/context-snapshot.json")
        ]
        assert len(snapshot_calls) > 0


# ===========================================================================
# Mystery restore from snapshot (replaces _restore_context_from_book)
# ===========================================================================

class TestMysterySnapshotRestore:
    """Mystery orchestrator resume should prefer context-snapshot.json."""

    @pytest.mark.asyncio
    async def test_restore_from_snapshot_instead_of_files(self):
        """When context-snapshot.json exists, use it instead of reading individual files."""
        from slima_agents.agents.base import AgentResult
        from slima_agents.mystery.orchestrator import MysteryOrchestratorAgent

        snapshot_data = {
            "user_prompt": "old prompt",
            "concept": "A locked-room mystery.",
            "crime_design": "Poison in the wine.",
            "characters": "Detective, Butler, Wife.",
        }

        # progress.md: stages 1-5 completed, resume from 6
        progress_md = (
            "# Pipeline Progress\n\n"
            "- **Pipeline**: mystery\n"
            "- **Status**: running\n"
            "- **Started**: 2026-01-01T00:00:00Z\n"
            "- **Prompt**: old prompt\n\n"
            "## Stages\n\n"
            "| # | Stage | Status | Started | Completed | Duration | Notes |\n"
            "|---|-------|--------|---------|-----------|----------|-------|\n"
            "| 1 | planning | completed | 10:00 | 10:05 | 300s | |\n"
            "| 2 | book_setup | completed | 10:05 | 10:05 | 2s | |\n"
            "| 3 | crime_design | completed | 10:05 | 10:10 | 300s | |\n"
            "| 4 | characters | completed | 10:10 | 10:15 | 300s | |\n"
            "| 5 | plot_architecture | completed | 10:15 | 10:20 | 300s | |\n"
            "| 6 | setting | pending | — | — | — | |\n"
            "| 7 | act1_writing | pending | — | — | — | |\n"
            "| 8 | act2_writing | pending | — | — | — | |\n"
            "| 9 | act3_writing | pending | — | — | — | |\n"
            "| 10 | validation | pending | — | — | — | |\n"
            "| 11 | polish | pending | — | — | — | |\n"
        )

        mock_slima = AsyncMock()
        mock_slima._base_url = "https://test.slima.app"
        mock_slima.create_file = AsyncMock()
        mock_slima.write_file = AsyncMock()
        mock_slima.get_book_structure = AsyncMock(return_value=[])

        # read_file returns different content based on path
        async def mock_read_file(book_token, path):
            resp = MagicMock()
            if path == "agent-log/progress.md":
                resp.content = progress_md
            elif path == "agent-log/context-snapshot.json":
                resp.content = json.dumps(snapshot_data)
            else:
                resp.content = "fallback content"
            return resp

        mock_slima.read_file = AsyncMock(side_effect=mock_read_file)

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
                inst = AsyncMock()
                inst.run = AsyncMock(return_value=AgentResult(
                    summary="Done", full_output="Done", duration_s=1.0,
                ))
                inst.name = "MockAgent"
                MockCls.return_value = inst

            MockPlanner.return_value.suggested_title = "Test"
            MockPlanner.return_value.suggested_description = "Test"

            orch = MysteryOrchestratorAgent(slima_client=mock_slima)
            await orch.run("Continue writing", resume_book="bk_existing")

            # Context should be populated from snapshot
            assert await orch.context.read("concept") == "A locked-room mystery."
            assert await orch.context.read("crime_design") == "Poison in the wine."
            assert await orch.context.read("characters") == "Detective, Butler, Wife."
