"""SettingAgent: scenes, locations, atmosphere."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import SETTING_INSTRUCTIONS


class SettingAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "SettingAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{SETTING_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current Mystery Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create setting files in book '{self.book_token}'.\n\n"
            "Read the existing book structure, crime design, characters, and plot files, "
            "then create detailed setting files in the planning/setting/ folder as described "
            "in your instructions. Write ALL content and name ALL files/folders in the "
            "same language as the mystery context provided in your system prompt."
        )
