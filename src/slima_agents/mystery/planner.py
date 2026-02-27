"""PlannerAgent: analyzes prompt and designs the core mystery concept."""

from __future__ import annotations

from ..agents.base import BaseAgent, AgentResult
from .templates import PLANNER_INSTRUCTIONS


class PlannerAgent(BaseAgent):
    """Analyzes the user's prompt and produces a structured mystery concept.

    Like worldbuild's ResearchAgent, this agent uses no MCP tools — it only
    generates text output which the orchestrator parses into MysteryContext.
    """

    def __init__(self, *args, prompt: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.prompt = prompt
        self.suggested_title: str = ""
        self.suggested_description: str = ""

    @property
    def name(self) -> str:
        return "PlannerAgent"

    def system_prompt(self) -> str:
        return PLANNER_INSTRUCTIONS

    def allowed_tools(self) -> list[str]:
        return []  # Pure text output, no MCP tools

    def initial_message(self) -> str:
        return (
            f"Analyze this mystery novel prompt and design the complete crime concept.\n\n"
            f'User prompt: "{self.prompt}"\n\n'
            f"IMPORTANT: Write ALL content in the same language as the prompt above.\n\n"
            f"Output your complete mystery design organized with these exact section headers "
            f"(keep these English headers for parsing, but write content in the prompt's language):\n\n"
            f"## Title\n"
            f"(Create a compelling mystery novel title. Use the same language as the prompt.)\n\n"
            f"## Description\n"
            f"(1-2 sentence description of the novel's premise.)\n\n"
            f"## Concept\n## The Crime\n## The False Story\n## Evidence Chain\n"
            f"## Red Herrings\n## Character Sketches\n## Act Structure\n\n"
            f"Be thorough and specific. Vague planning leads to plot holes."
        )

    async def run(self) -> AgentResult:
        """Run planning and parse output into MysteryContext sections."""
        result = await super().run()
        await self._parse_into_context(result.full_output)
        return result

    async def _parse_into_context(self, output: str) -> None:
        """Parse structured output into MysteryContext.concept."""
        section_map = {
            "## concept": "concept",
            "## the crime": "crime_design",
            "## the false story": "crime_design",
            "## evidence chain": "crime_design",
            "## red herrings": "crime_design",
            "## character sketches": "characters",
            "## act structure": "plot_architecture",
        }

        lines = output.split("\n")
        current_section: str | None = None
        current_content: list[str] = []
        in_title = False
        in_description = False
        # Track which context sections we've already appended to
        appended: set[str] = set()

        for line in lines:
            lower = line.strip().lower()

            if lower == "## title" or lower.startswith("## title:") or lower.startswith("## title "):
                if in_description:
                    self._extract_description(current_content)
                    in_description = False
                if current_section:
                    await self._write_section(current_section, current_content, appended)
                current_section = None
                current_content = []
                in_title = True
                continue

            if lower == "## description" or lower.startswith("## description:") or lower.startswith("## description "):
                if in_title:
                    self._extract_title(current_content)
                    in_title = False
                if current_section:
                    await self._write_section(current_section, current_content, appended)
                current_section = None
                current_content = []
                in_description = True
                continue

            matched = False
            for header, section_name in section_map.items():
                if lower == header or lower.startswith(header + ":") or lower.startswith(header + " "):
                    if in_title:
                        self._extract_title(current_content)
                        in_title = False
                    if in_description:
                        self._extract_description(current_content)
                        in_description = False
                    if current_section:
                        await self._write_section(current_section, current_content, appended)
                    current_section = section_name
                    current_content = [line]  # Include the header itself
                    matched = True
                    break

            if not matched:
                if in_title or in_description or current_section is not None:
                    current_content.append(line)

        # Save trailing content
        if in_title:
            self._extract_title(current_content)
        if in_description:
            self._extract_description(current_content)
        if current_section:
            await self._write_section(current_section, current_content, appended)

    async def _write_section(
        self, section: str, content: list[str], appended: set[str]
    ) -> None:
        """Write or append content to a context section."""
        text = "\n".join(content).strip()
        if not text:
            return
        if section in appended:
            await self.context.append(section, text)
        else:
            await self.context.write(section, text)
            appended.add(section)

    def _extract_title(self, content_lines: list[str]) -> None:
        """Extract the first non-empty line as suggested_title."""
        self.suggested_title = "\n".join(content_lines).strip()
        for t_line in content_lines:
            cleaned = t_line.strip().strip("#").strip("*").strip()
            if cleaned:
                self.suggested_title = cleaned
                break

    def _extract_description(self, content_lines: list[str]) -> None:
        """Extract the joined non-empty lines as suggested_description."""
        desc = "\n".join(content_lines).strip()
        if desc:
            self.suggested_description = desc
