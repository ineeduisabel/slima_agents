"""OrchestratorAgent：分階段管線協調器。"""

from __future__ import annotations

import asyncio
import logging
import time

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from ..agents.context import WorldContext
from ..slima.client import SlimaClient
from .research import ResearchAgent
from .validator import ValidationAgent
from .specialists.cosmology import CosmologyAgent
from .specialists.geography import GeographyAgent
from .specialists.history import HistoryAgent
from .specialists.peoples import PeoplesAgent
from .specialists.cultures import CulturesAgent
from .specialists.power_structures import PowerStructuresAgent
from .specialists.characters import CharactersAgent
from .specialists.items import ItemsAgent
from .specialists.bestiary import BestiaryAgent
from .specialists.narrative import NarrativeAgent

logger = logging.getLogger(__name__)
console = Console()


def _detect_cjk(text: str) -> bool:
    """Return True if text contains CJK characters (Chinese/Japanese/Korean)."""
    return any("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" for ch in text)


# Localized path/label mappings
_PATHS_ZH = {
    "overview_folder": "總覽",
    "overview_file": "總覽/世界觀總覽.md",
    "overview_title": "# 世界觀總覽",
    "overview_commit": "新增世界觀總覽",
    "glossary_folder": "參考資料",
    "glossary_file": "參考資料/詞彙表.md",
    "glossary_title": "# 詞彙表",
    "glossary_intro": "本詞彙表包含世界觀聖經中的重要術語、名稱與概念。",
    "glossary_commit": "新增詞彙表",
}

_PATHS_EN = {
    "overview_folder": "meta",
    "overview_file": "meta/overview.md",
    "overview_title": "# World Bible Overview",
    "overview_commit": "Add world overview",
    "glossary_folder": "reference",
    "glossary_file": "reference/glossary.md",
    "glossary_title": "# Glossary",
    "glossary_intro": "This glossary contains key terms, names, and concepts from the world bible.",
    "glossary_commit": "Add glossary",
}


def _format_structure_tree(nodes: list[dict], indent: int = 0) -> str:
    """Format a list of FileSnapshot dicts into a readable tree string."""
    lines: list[str] = []
    for node in sorted(nodes, key=lambda n: n.get("position", 0)):
        prefix = "  " * indent
        name = node.get("name", "?")
        kind = node.get("kind", "file")
        if kind == "folder":
            lines.append(f"{prefix}{name}/")
            children = node.get("children") or []
            if children:
                lines.append(_format_structure_tree(children, indent + 1))
        else:
            lines.append(f"{prefix}{name}")
    return "\n".join(lines)


class OrchestratorAgent:
    """協調完整的世界觀建構管線。"""

    def __init__(
        self,
        slima_client: SlimaClient,
        model: str | None = None,
    ):
        self.slima = slima_client
        self.model = model
        self.context = WorldContext()

    async def run(self, prompt: str) -> str:
        """執行完整管線，回傳 book token。"""
        start = time.time()
        L = _PATHS_ZH if _detect_cjk(prompt) else _PATHS_EN

        console.print(Panel(f"[bold]世界觀建構 Agent[/bold]\n{prompt}", border_style="blue"))

        # 將使用者原始需求存入 WorldContext，確保所有 Agent 都知道要建構什麼
        self.context.user_prompt = prompt

        # 步驟 1：研究（不需要書籍，先產出世界觀內容和標題）
        with _status("[階段 1] 研究 Agent 正在分析提示詞..."):
            research = ResearchAgent(context=self.context, model=self.model, prompt=prompt)
            result = await research.run()

        if not result.full_output.strip():
            console.print("  [red]研究 Agent 回傳空白內容！正在重試...[/red]")
            result = await research.run()

        if not result.full_output.strip():
            console.print(
                "  [red]研究 Agent 連續兩次回傳空白。請檢查 Claude CLI 是否正常運作：[/red]\n"
                "  [dim]  claude -p \"hello\" --output-format text[/dim]"
            )
            raise RuntimeError("ResearchAgent returned empty output after retry")

        overview_text = self.context.serialize_for_prompt()
        if overview_text == "(No world context populated yet.)":
            console.print("  [yellow]警告：研究 Agent 有輸出但解析失敗，WorldContext 為空[/yellow]")
            logger.warning(f"Research output (first 500 chars): {result.full_output[:500]}")

        console.print(f"  [green]研究完成：[/green] {result.summary[:80]}")

        # 步驟 2：用研究 Agent 產出的標題建立 Slima 書籍
        book_title = research.suggested_title or prompt[:60]
        with _status("正在建立 Slima 書籍..."):
            book = await self.slima.create_book(
                title=book_title,
                description=prompt,
            )
        book_token = book.token
        console.print(f"  書籍已建立：[cyan]{book_token}[/cyan]  標題：[yellow]{book_title}[/yellow]")

        agent_kwargs = dict(
            context=self.context,
            book_token=book_token,
            model=self.model,
        )

        # 步驟 3：建立總覽檔案
        with _status(f"正在寫入 {L['overview_file']}..."):
            overview = self.context.serialize_for_prompt()
            await self.slima.create_file(
                book_token,
                path=L["overview_file"],
                content=f"{L['overview_title']}\n\n{overview}",
                commit_message=L["overview_commit"],
            )

        # 步驟 4：階段 2 — 宇宙觀 + 地理 + 歷史（平行）
        await self._run_phase(
            "階段 2：基礎",
            [
                ("宇宙觀", CosmologyAgent(**agent_kwargs)),
                ("地理", GeographyAgent(**agent_kwargs)),
                ("歷史", HistoryAgent(**agent_kwargs)),
            ],
        )
        await self._inject_book_structure(book_token)

        # 步驟 5：階段 3 — 種族 + 文化（平行）
        await self._run_phase(
            "階段 3：文化",
            [
                ("種族", PeoplesAgent(**agent_kwargs)),
                ("文化", CulturesAgent(**agent_kwargs)),
            ],
        )
        await self._inject_book_structure(book_token)

        # 步驟 6：階段 4 — 權力結構
        await self._run_phase(
            "階段 4：權力結構",
            [("權力結構", PowerStructuresAgent(**agent_kwargs))],
        )
        await self._inject_book_structure(book_token)

        # 步驟 7：階段 5 — 角色 + 物品 + 怪獸圖鑑（平行，加長 timeout）
        await self._run_phase(
            "階段 5：細節",
            [
                ("角色", CharactersAgent(**agent_kwargs, timeout=1200)),
                ("物品", ItemsAgent(**agent_kwargs, timeout=1200)),
                ("怪獸圖鑑", BestiaryAgent(**agent_kwargs, timeout=1200)),
            ],
        )
        await self._inject_book_structure(book_token)

        # 步驟 8：階段 6 — 敘事（加長 timeout）
        await self._run_phase(
            "階段 6：敘事",
            [("敘事", NarrativeAgent(**agent_kwargs, timeout=1200))],
        )

        # 步驟 9：建立詞彙表
        with _status(f"正在寫入 {L['glossary_file']}..."):
            glossary_content = self._build_glossary(L)
            await self.slima.create_file(
                book_token,
                path=L["glossary_file"],
                content=glossary_content,
                commit_message=L["glossary_commit"],
            )

        # 步驟 10：驗證
        await self._run_phase(
            "階段 7：驗證",
            [("驗證", ValidationAgent(**agent_kwargs))],
        )

        elapsed = time.time() - start
        console.print()
        console.print(
            Panel(
                f"[bold green]世界觀聖經建構完成！[/bold green]\n\n"
                f"書籍 Token：[cyan]{book_token}[/cyan]\n"
                f"耗時：{elapsed:.0f} 秒\n\n"
                f"在此查看：{self.slima._base_url}/books/{book_token}",
                border_style="green",
            )
        )

        return book_token

    async def _run_phase(self, phase_name: str, agents: list[tuple[str, object]]) -> None:
        """以平行方式執行一組 Agent，並顯示進度。"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            tasks = {}
            for name, agent in agents:
                tasks[name] = progress.add_task(f"[{phase_name}] {name}...", total=None)

            async def _run_one(name: str, agent):
                try:
                    result = await agent.run()
                    if result.timed_out:
                        progress.update(tasks[name], description=f"[{phase_name}] {name} [yellow]部分完成[/yellow]")
                    else:
                        progress.update(tasks[name], description=f"[{phase_name}] {name} [green]完成[/green]")
                    return name, result
                except Exception as e:
                    progress.update(tasks[name], description=f"[{phase_name}] {name} [red]失敗[/red]")
                    logger.error(f"{name} 失敗：{e}")
                    raise

            results = await asyncio.gather(
                *[_run_one(name, agent) for name, agent in agents],
                return_exceptions=True,
            )

        for r in results:
            if isinstance(r, Exception):
                console.print(f"  [red]錯誤：[/red] {r}")
            else:
                name, result = r
                if result.timed_out:
                    console.print(f"  [yellow]{name}：[/yellow] 超時但檔案已建立（部分完成），繼續下一階段")
                else:
                    console.print(f"  [green]{name}：[/green] {result.summary[:80]}")

    async def _inject_book_structure(self, book_token: str) -> None:
        """Read the current book structure and store it in WorldContext.

        This lets later-phase agents see what files already exist,
        enabling better cross-referencing and avoiding duplicate work.
        """
        try:
            structure = await self.slima.get_book_structure(book_token)
            tree_str = _format_structure_tree(structure)
            await self.context.write("book_structure", tree_str)
            logger.debug(f"Injected book structure ({len(tree_str)} chars)")
        except Exception as e:
            logger.warning(f"Failed to inject book structure: {e}")

    def _build_glossary(self, L: dict) -> str:
        """從 context 建構詞彙表。"""
        return (
            f"{L['glossary_title']}\n\n"
            f"{L['glossary_intro']}\n\n"
            f"---\n\n{self.context.serialize_for_prompt()}"
        )


class _status:
    """簡易 context manager，印出狀態訊息。"""

    def __init__(self, msg: str):
        self.msg = msg

    def __enter__(self):
        console.print(f"  [dim]{self.msg}[/dim]")
        return self

    def __exit__(self, *exc):
        pass
