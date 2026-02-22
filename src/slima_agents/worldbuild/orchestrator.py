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


def _detect_language(text: str) -> str:
    """Detect prompt language. Returns 'ja', 'ko', 'zh', or 'en'.

    Priority: Japanese kana → Korean Hangul → CJK ideographs (Chinese) → English.
    """
    for ch in text:
        # Japanese: Hiragana (3040-309F) or Katakana (30A0-30FF)
        if "\u3040" <= ch <= "\u309f" or "\u30a0" <= ch <= "\u30ff":
            return "ja"
        # Korean: Hangul Syllables (AC00-D7AF) or Hangul Jamo (1100-11FF)
        if "\uac00" <= ch <= "\ud7af" or "\u1100" <= ch <= "\u11ff":
            return "ko"
    # CJK Unified Ideographs (shared by zh/ja/ko, but if no kana/hangul → zh)
    if any("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" for ch in text):
        return "zh"
    return "en"


# Localized path/label mappings
_PATHS_ZH = {
    "worldview_prefix": "世界觀",
    "overview_folder": "世界觀/總覽",
    "overview_file": "世界觀/總覽/世界觀總覽.md",
    "overview_title": "# 世界觀總覽",
    "overview_commit": "新增世界觀總覽",
    "glossary_folder": "世界觀/參考資料",
    "glossary_file": "世界觀/參考資料/詞彙表.md",
    "glossary_title": "# 詞彙表",
    "glossary_intro": "本詞彙表包含世界觀聖經中的重要術語、名稱與概念。",
    "glossary_commit": "新增詞彙表",
}

_PATHS_JA = {
    "worldview_prefix": "世界観",
    "overview_folder": "世界観/概要",
    "overview_file": "世界観/概要/世界観概要.md",
    "overview_title": "# 世界観概要",
    "overview_commit": "世界観概要を追加",
    "glossary_folder": "世界観/参考資料",
    "glossary_file": "世界観/参考資料/用語集.md",
    "glossary_title": "# 用語集",
    "glossary_intro": "この用語集には、世界観バイブルの重要な用語、名前、概念が含まれています。",
    "glossary_commit": "用語集を追加",
}

_PATHS_KO = {
    "worldview_prefix": "세계관",
    "overview_folder": "세계관/개요",
    "overview_file": "세계관/개요/세계관개요.md",
    "overview_title": "# 세계관 개요",
    "overview_commit": "세계관 개요 추가",
    "glossary_folder": "세계관/참고자료",
    "glossary_file": "세계관/참고자료/용어집.md",
    "glossary_title": "# 용어집",
    "glossary_intro": "이 용어집은 세계관 바이블의 주요 용어, 이름, 개념을 포함합니다.",
    "glossary_commit": "용어집 추가",
}

_PATHS_EN = {
    "worldview_prefix": "worldview",
    "overview_folder": "worldview/meta",
    "overview_file": "worldview/meta/overview.md",
    "overview_title": "# World Bible Overview",
    "overview_commit": "Add world overview",
    "glossary_folder": "worldview/reference",
    "glossary_file": "worldview/reference/glossary.md",
    "glossary_title": "# Glossary",
    "glossary_intro": "This glossary contains key terms, names, and concepts from the world bible.",
    "glossary_commit": "Add glossary",
}

_LANG_PATHS = {
    "zh": _PATHS_ZH,
    "ja": _PATHS_JA,
    "ko": _PATHS_KO,
    "en": _PATHS_EN,
}


def _format_structure_tree(nodes: list[dict], prefix: str = "") -> str:
    """Format a list of FileSnapshot dicts into a tree diagram (like `tree` command)."""
    lines: list[str] = []
    # Sort: folders first, then files; within each group sort by position
    sorted_nodes = sorted(
        nodes,
        key=lambda n: (n.get("kind") != "folder", n.get("position", 0)),
    )
    for i, node in enumerate(sorted_nodes):
        is_last = i == len(sorted_nodes) - 1
        connector = "└── " if is_last else "├── "
        name = node.get("name", "?")
        kind = node.get("kind", "file")
        if kind == "folder":
            lines.append(f"{prefix}{connector}{name}/")
            children = node.get("children") or []
            if children:
                extension = "    " if is_last else "│   "
                lines.append(_format_structure_tree(children, prefix + extension))
        else:
            lines.append(f"{prefix}{connector}{name}")
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
        lang = _detect_language(prompt)
        L = _LANG_PATHS[lang]

        console.print(Panel(f"[bold]世界觀建構 Agent[/bold]\n{prompt}", border_style="blue"))

        # 將使用者原始需求存入 WorldContext，確保所有 Agent 都知道要建構什麼
        self.context.user_prompt = prompt

        # 步驟 1：研究（不需要書籍，先產出世界觀內容和標題）
        research = ResearchAgent(context=self.context, model=self.model, prompt=prompt)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("[階段 1] 研究 Agent 正在分析提示詞...", total=None)
            result = await research.run()
            if not result.full_output.strip():
                progress.update(task_id, description="[階段 1] 研究 Agent [yellow]重試中[/yellow]...")
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

        # 步驟 2：用研究 Agent 產出的標題和描述建立 Slima 書籍
        book_title = research.suggested_title or prompt[:60]
        book_description = research.suggested_description or prompt[:200]
        with _status("正在建立 Slima 書籍..."):
            book = await self.slima.create_book(
                title=book_title,
                description=book_description,
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
                ("角色", CharactersAgent(**agent_kwargs)),
                ("物品", ItemsAgent(**agent_kwargs)),
                ("怪獸圖鑑", BestiaryAgent(**agent_kwargs)),
            ],
        )
        await self._inject_book_structure(book_token)

        # 步驟 8：階段 6 — 敘事
        await self._run_phase(
            "階段 6：敘事",
            [("敘事", NarrativeAgent(**agent_kwargs))],
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

        # 步驟 10：驗證（第一輪 — 一致性 + 內容完整度檢查 + 修復）
        await self._run_phase(
            "階段 7a：驗證",
            [("驗證-R1", ValidationAgent(**agent_kwargs, validation_round=1))],
        )

        # 步驟 11：驗證（第二輪 — 確認修復 + 最終報告）
        await self._run_phase(
            "階段 7b：確認",
            [("驗證-R2", ValidationAgent(**agent_kwargs, validation_round=2))],
        )

        # 步驟 12：建立 README.md
        with _status("正在建立 README.md..."):
            try:
                structure = await self.slima.get_book_structure(book_token)
                tree_str = _format_structure_tree(structure)
            except Exception:
                tree_str = "(unable to retrieve)"
            readme_content = self._build_readme(
                title=book_title,
                description=book_description,
                tree=tree_str,
                L=L,
            )
            await self.slima.create_file(
                book_token,
                path="README.md",
                content=readme_content,
                commit_message="Add README",
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

    def _build_readme(self, title: str, description: str, tree: str, L: dict) -> str:
        """Build a README.md for the root of the book."""
        prefix = L["worldview_prefix"]
        if L is _PATHS_ZH:
            return (
                f"# {title}\n\n"
                f"{description}\n\n"
                f"## 結構\n\n"
                f"```\n{tree}\n```\n\n"
                f"## 使用方式\n\n"
                f"本書是一本**世界觀聖經**（World Bible），包含完整的世界設定資料。\n\n"
                f"- `{prefix}/` — 所有世界觀設定檔案\n"
                f"- `{L['overview_file']}` — 世界觀總覽\n"
                f"- `{L['glossary_file']}` — 詞彙表\n\n"
                f"## 致謝\n\n"
                f"本世界觀聖經由 [Slima](https://slima.ai) + Claude AI 協作生成。\n"
            )
        if L is _PATHS_JA:
            return (
                f"# {title}\n\n"
                f"{description}\n\n"
                f"## 構成\n\n"
                f"```\n{tree}\n```\n\n"
                f"## 使い方\n\n"
                f"本書は**世界観バイブル**（World Bible）であり、包括的な世界設定資料を含んでいます。\n\n"
                f"- `{prefix}/` — すべての世界観設定ファイル\n"
                f"- `{L['overview_file']}` — 世界観概要\n"
                f"- `{L['glossary_file']}` — 用語集\n\n"
                f"## クレジット\n\n"
                f"この世界観バイブルは [Slima](https://slima.ai) + Claude AI の協力により生成されました。\n"
            )
        if L is _PATHS_KO:
            return (
                f"# {title}\n\n"
                f"{description}\n\n"
                f"## 구조\n\n"
                f"```\n{tree}\n```\n\n"
                f"## 사용 방법\n\n"
                f"이 책은 포괄적인 세계 설정 자료를 포함한 **세계관 바이블**(World Bible)입니다.\n\n"
                f"- `{prefix}/` — 모든 세계관 설정 파일\n"
                f"- `{L['overview_file']}` — 세계관 개요\n"
                f"- `{L['glossary_file']}` — 용어집\n\n"
                f"## 크레딧\n\n"
                f"이 세계관 바이블은 [Slima](https://slima.ai) + Claude AI의 협력으로 생성되었습니다.\n"
            )
        return (
            f"# {title}\n\n"
            f"{description}\n\n"
            f"## Structure\n\n"
            f"```\n{tree}\n```\n\n"
            f"## Usage\n\n"
            f"This book is a **World Bible** containing comprehensive world-building reference material.\n\n"
            f"- `{prefix}/` — All world-building files\n"
            f"- `{L['overview_file']}` — World overview\n"
            f"- `{L['glossary_file']}` — Glossary of terms\n\n"
            f"## Credits\n\n"
            f"This world bible was collaboratively generated by [Slima](https://slima.ai) + Claude AI.\n"
        )

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
