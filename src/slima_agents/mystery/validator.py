"""MysteryValidationAgent: reads all files and checks for consistency."""

from __future__ import annotations

from ..agents.base import BaseAgent
from .templates import MYSTERY_VALIDATION_INSTRUCTIONS, MYSTERY_VERIFICATION_INSTRUCTIONS


class MysteryValidationAgent(BaseAgent):
    """Reads all book files and produces a consistency report.

    Round 1: consistency + clue chain + character check, fix issues, write report.
    Round 2: verify fixes, fix residual issues, overwrite report with final status.
    """

    def __init__(self, *, validation_round: int = 1, **kwargs):
        super().__init__(**kwargs)
        self.validation_round = validation_round

    @property
    def name(self) -> str:
        return f"MysteryValidationAgent-R{self.validation_round}"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        instructions = (
            MYSTERY_VALIDATION_INSTRUCTIONS
            if self.validation_round == 1
            else MYSTERY_VERIFICATION_INSTRUCTIONS
        )
        return (
            f"{instructions}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current Mystery Context\n{ctx}"
        )

    def initial_message(self) -> str:
        if self.validation_round == 1:
            return (
                f"Use the Slima MCP tools to work with book '{self.book_token}'.\n\n"
                "1. Get the book structure to see all files.\n"
                "2. Read ALL planning files and ALL chapter files.\n"
                "3. Check: plot consistency (does the reveal match the crime design?), "
                "clue chain (every planted clue is discoverable), character consistency, "
                "timeline logic, fair play compliance.\n"
                "4. Fix any issues by editing the affected files.\n"
                "5. Create a preliminary validation report in the planning/ folder.\n\n"
                "Write the report in the same language as the existing book content."
            )
        return (
            f"Use the Slima MCP tools to work with book '{self.book_token}'.\n\n"
            "1. Read the preliminary validation report from the planning/ folder.\n"
            "2. For each issue marked as fixed, verify the fix in the actual file.\n"
            "3. Check for residual or newly introduced issues.\n"
            "4. Fix any remaining problems.\n"
            "5. Overwrite the validation report with a FINAL status report "
            "showing clue chain verification, character consistency, and verdict.\n\n"
            "Write the report in the same language as the existing book content."
        )
