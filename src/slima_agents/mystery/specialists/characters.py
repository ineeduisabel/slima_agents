"""MysteryCharactersAgent: detective, suspects, victim, relationship web."""

from __future__ import annotations

from ...agents.base import BaseAgent
from ..templates import CHARACTERS_INSTRUCTIONS


class MysteryCharactersAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "MysteryCharactersAgent"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        return (
            f"{CHARACTERS_INSTRUCTIONS}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current Mystery Context\n{ctx}"
        )

    def initial_message(self) -> str:
        return (
            f"Use the Slima MCP tools to create character files in book '{self.book_token}'.\n\n"
            "Read the existing book structure and crime design files, then create "
            "detailed character profiles in the planning/characters/ folder as described "
            "in your instructions. Write ALL content and name ALL files/folders in the "
            "same language as the mystery context provided in your system prompt."
        )
