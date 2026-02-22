"""ValidationAgent: reads all files and checks for consistency."""

from __future__ import annotations

from ..agents.base import BaseAgent
from .templates import VALIDATION_INSTRUCTIONS, VERIFICATION_INSTRUCTIONS


class ValidationAgent(BaseAgent):
    """Reads all book files and produces a consistency report.

    Round 1: consistency + content completeness check, fix issues, write preliminary report.
    Round 2: verify fixes, fix residual issues, overwrite report with final status.
    """

    def __init__(self, *, validation_round: int = 1, **kwargs):
        super().__init__(**kwargs)
        self.validation_round = validation_round

    @property
    def name(self) -> str:
        return f"ValidationAgent-R{self.validation_round}"

    def system_prompt(self) -> str:
        ctx = self.context.serialize_for_prompt()
        instructions = (
            VALIDATION_INSTRUCTIONS
            if self.validation_round == 1
            else VERIFICATION_INSTRUCTIONS
        )
        return (
            f"{instructions}\n\n"
            f"# Target Book\n"
            f"book_token: {self.book_token}\n\n"
            f"# Current World Context\n{ctx}"
        )

    def initial_message(self) -> str:
        if self.validation_round == 1:
            return (
                f"Use the Slima MCP tools to work with book '{self.book_token}'.\n\n"
                "1. Get the book structure to see all files.\n"
                "2. Read each file and check for consistency issues.\n"
                "3. Check content completeness: are the world's core topics adequately covered? "
                "Are there missing entries for important categories?\n"
                "4. Fix any issues by editing the affected files. "
                "Create new files for missing entries if needed.\n"
                "5. Create a preliminary consistency report in the meta folder with your findings.\n\n"
                "Write the report in the same language as the existing book content."
            )
        return (
            f"Use the Slima MCP tools to work with book '{self.book_token}'.\n\n"
            "1. Read the preliminary consistency report from the meta folder.\n"
            "2. For each issue marked as fixed, read the actual file to verify the fix.\n"
            "3. Check for any residual or newly introduced issues.\n"
            "4. Fix any remaining problems.\n"
            "5. Overwrite the consistency report with a FINAL status report "
            "showing per-folder completeness and an all-clear verdict.\n\n"
            "Write the report in the same language as the existing book content."
        )
