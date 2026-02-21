"""ResearchAgent: analyzes prompt and returns world context as text."""

from __future__ import annotations

from ..agents.base import BaseAgent, AgentResult
from ..agents.claude_runner import ClaudeRunner
from .templates import RESEARCH_INSTRUCTIONS


class ResearchAgent(BaseAgent):
    """Uses Claude's knowledge to produce foundational world context from the user's prompt.

    Unlike other agents, the ResearchAgent does not use Slima MCP tools.
    It only generates text output which the orchestrator parses into WorldContext.
    It also generates a creative book title based on the user's prompt.
    """

    def __init__(self, *args, prompt: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.prompt = prompt
        self.suggested_title: str = ""

    @property
    def name(self) -> str:
        return "ResearchAgent"

    def system_prompt(self) -> str:
        return RESEARCH_INSTRUCTIONS

    def allowed_tools(self) -> list[str]:
        # Research agent doesn't need any MCP tools — it just generates text
        return []

    def initial_message(self) -> str:
        return (
            f"Research and analyze this world-building prompt, then output a comprehensive "
            f"world context document organized by sections.\n\n"
            f'User prompt: "{self.prompt}"\n\n'
            f"IMPORTANT: Write ALL content in the same language as the prompt above.\n\n"
            f"Output your findings organized with these exact section headers "
            f"(keep these English headers for parsing, but write content in the prompt's language):\n\n"
            f"## Title\n"
            f"(Create a short, evocative, creative title for this world — NOT a description. "
            f"Think of it as the name of a world encyclopedia or atlas. "
            f"Examples: '艾澤拉斯編年史', '瓦羅蘭大陸誌', 'The Silmarillion', '台灣百鬼錄'. "
            f"Just output the title text, nothing else. Use the same language as the prompt.)\n\n"
            f"## Overview\n## Cosmology\n## Geography\n## History\n## Peoples\n"
            f"## Cultures\n## Power Structures\n## Characters\n## Items Bestiary\n"
            f"## Narrative\n## Naming Conventions\n\n"
            f"Write detailed, factual content under each section in the prompt's language."
        )

    async def run(self) -> AgentResult:
        """Run research and parse output into WorldContext sections."""
        result = await super().run()

        # Parse the output into WorldContext sections (and extract title)
        await self._parse_into_context(result.full_output)

        return result

    async def _parse_into_context(self, output: str) -> None:
        """Parse structured output into WorldContext sections."""
        section_map = {
            "## overview": "overview",
            "## cosmology": "cosmology",
            "## geography": "geography",
            "## history": "history",
            "## peoples": "peoples",
            "## cultures": "cultures",
            "## power structures": "power_structures",
            "## characters": "characters",
            "## items bestiary": "items_bestiary",
            "## narrative": "narrative",
            "## naming conventions": "naming_conventions",
        }

        lines = output.split("\n")
        current_section = None
        current_content: list[str] = []
        in_title = False

        for line in lines:
            lower = line.strip().lower()

            # Check for ## Title header
            if lower == "## title" or lower.startswith("## title:") or lower.startswith("## title "):
                # Save previous section
                if current_section:
                    await self.context.write(current_section, "\n".join(current_content).strip())
                current_section = None
                current_content = []
                in_title = True
                continue

            # Check for other section headers
            matched = False
            for header, section_name in section_map.items():
                if lower == header or lower.startswith(header + ":") or lower.startswith(header + " "):
                    # Save title if we were collecting it
                    if in_title:
                        self.suggested_title = "\n".join(current_content).strip()
                        # Clean up: take just the first non-empty line as title
                        for t_line in current_content:
                            cleaned = t_line.strip().strip("#").strip("*").strip()
                            if cleaned:
                                self.suggested_title = cleaned
                                break
                        in_title = False

                    # Save previous section
                    if current_section:
                        await self.context.write(current_section, "\n".join(current_content).strip())
                    current_section = section_name
                    current_content = []
                    matched = True
                    break

            if not matched:
                if in_title or current_section is not None:
                    current_content.append(line)

        # Save last section
        if current_section:
            await self.context.write(current_section, "\n".join(current_content).strip())
