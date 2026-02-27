"""OrchestratorAgent：分階段管線協調器。"""

from __future__ import annotations

import asyncio
import logging
import time

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from ..agents.context import WorldContext
from ..lang import detect_language, flatten_paths, format_structure_tree
from ..progress import ProgressEmitter
from ..slima.client import SlimaClient
from ..tracker import PipelineTracker
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


class OrchestratorAgent:
    """協調完整的世界觀建構管線。"""

    def __init__(
        self,
        slima_client: SlimaClient,
        model: str | None = None,
        emitter: ProgressEmitter | None = None,
        console: Console | None = None,
    ):
        self.slima = slima_client
        self.model = model
        self.context = WorldContext()
        self.emitter = emitter or ProgressEmitter(enabled=False)
        self.console = console or Console()

    async def run(self, prompt: str) -> str:
        """執行完整管線，回傳 book token。"""
        start = time.time()
        lang = detect_language(prompt)
        L = _LANG_PATHS[lang]
        book_token = ""

        self.emitter.pipeline_start(prompt=prompt, total_stages=12)
        self.console.print(Panel(f"[bold]世界觀建構 Agent[/bold]\n{prompt}", border_style="blue"))

        # 將使用者原始需求存入 WorldContext，確保所有 Agent 都知道要建構什麼
        self.context.user_prompt = prompt

        try:
            # 步驟 1：研究（不需要書籍，先產出世界觀內容和標題）
            self.emitter.stage_start(1, "research", ["ResearchAgent"])
            stage_t0 = time.time()
            research = ResearchAgent(context=self.context, model=self.model, prompt=prompt)
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=self.console,
            ) as progress:
                task_id = progress.add_task("[階段 1] 研究 Agent 正在分析提示詞...", total=None)
                self.emitter.agent_start(1, "ResearchAgent")
                result = await research.run()
                if not result.full_output.strip():
                    progress.update(task_id, description="[階段 1] 研究 Agent [yellow]重試中[/yellow]...")
                    result = await research.run()

            if not result.full_output.strip():
                self.console.print(
                    "  [red]研究 Agent 連續兩次回傳空白。請檢查 Claude CLI 是否正常運作：[/red]\n"
                    "  [dim]  claude -p \"hello\" --output-format text[/dim]"
                )
                raise RuntimeError("ResearchAgent returned empty output after retry")

            self.emitter.agent_complete(
                stage=1, agent="ResearchAgent",
                duration_s=result.duration_s, timed_out=result.timed_out,
                summary=result.summary, num_turns=result.num_turns, cost_usd=result.cost_usd,
            )
            self.emitter.stage_complete(1, "research", time.time() - stage_t0)

            overview_text = self.context.serialize_for_prompt()
            if overview_text == "(No world context populated yet.)":
                self.console.print("  [yellow]警告：研究 Agent 有輸出但解析失敗，WorldContext 為空[/yellow]")
                logger.warning(f"Research output (first 500 chars): {result.full_output[:500]}")

            self.console.print(f"  [green]研究完成：[/green] {result.summary[:80]}")

            # 步驟 2：用研究 Agent 產出的標題和描述建立 Slima 書籍
            self.emitter.stage_start(2, "book_creation")
            stage_t0 = time.time()
            book_title = research.suggested_title or prompt[:60]
            book_description = research.suggested_description or prompt[:200]
            with _status("正在建立 Slima 書籍...", self.console):
                book = await self.slima.create_book(
                    title=book_title,
                    description=book_description,
                )
            book_token = book.token
            self.emitter.book_created(book_token, book_title, book_description)
            self.emitter.stage_complete(2, "book_creation", time.time() - stage_t0)
            self.console.print(f"  書籍已建立：[cyan]{book_token}[/cyan]  標題：[yellow]{book_title}[/yellow]")

            # Initialize pipeline tracker (in-book progress.md)
            tracker = PipelineTracker(
                pipeline_name="worldbuild",
                book_token=book_token,
                prompt=prompt,
                slima=self.slima,
            )
            tracker.define_stages([
                (1, "research"), (2, "book_creation"), (3, "overview"),
                (4, "foundation"), (5, "cultures"), (6, "power_structures"),
                (7, "details"), (8, "narrative"), (9, "glossary"),
                (10, "validation_r1"), (11, "validation_r2"), (12, "readme"),
            ])
            # Mark stages 1-2 as already completed (they ran before tracker init)
            for sn in (1, 2):
                rec = tracker._find(sn)
                if rec:
                    rec.status = "completed"
            await tracker.start()

            agent_kwargs = dict(
                context=self.context,
                book_token=book_token,
                model=self.model,
            )

            # 步驟 3：建立總覽檔案
            await tracker.stage_start(3)
            self.emitter.stage_start(3, "overview")
            stage_t0 = time.time()
            with _status(f"正在寫入 {L['overview_file']}...", self.console):
                overview = self.context.serialize_for_prompt()
                await self.slima.create_file(
                    book_token,
                    path=L["overview_file"],
                    content=f"{L['overview_title']}\n\n{overview}",
                    commit_message=L["overview_commit"],
                )
            self.emitter.file_created(L["overview_file"])
            self.emitter.stage_complete(3, "overview", time.time() - stage_t0)
            await tracker.stage_complete(3)

            # 步驟 4：階段 2 — 宇宙觀 + 地理 + 歷史（平行）
            await tracker.stage_start(4)
            await self._run_phase(
                "階段 2：基礎",
                [
                    ("宇宙觀", CosmologyAgent(**agent_kwargs)),
                    ("地理", GeographyAgent(**agent_kwargs)),
                    ("歷史", HistoryAgent(**agent_kwargs)),
                ],
                stage=4, book_token=book_token,
            )
            await self._inject_book_structure(book_token)
            await tracker.stage_complete(4)

            # 步驟 5：階段 3 — 種族 + 文化（平行）
            await tracker.stage_start(5)
            await self._run_phase(
                "階段 3：文化",
                [
                    ("種族", PeoplesAgent(**agent_kwargs)),
                    ("文化", CulturesAgent(**agent_kwargs)),
                ],
                stage=5, book_token=book_token,
            )
            await self._inject_book_structure(book_token)
            await tracker.stage_complete(5)

            # 步驟 6：階段 4 — 權力結構
            await tracker.stage_start(6)
            await self._run_phase(
                "階段 4：權力結構",
                [("權力結構", PowerStructuresAgent(**agent_kwargs))],
                stage=6, book_token=book_token,
            )
            await self._inject_book_structure(book_token)
            await tracker.stage_complete(6)

            # 步驟 7：階段 5 — 角色 + 物品 + 怪獸圖鑑（平行）
            await tracker.stage_start(7)
            await self._run_phase(
                "階段 5：細節",
                [
                    ("角色", CharactersAgent(**agent_kwargs)),
                    ("物品", ItemsAgent(**agent_kwargs)),
                    ("怪獸圖鑑", BestiaryAgent(**agent_kwargs)),
                ],
                stage=7, book_token=book_token,
            )
            await self._inject_book_structure(book_token)
            await tracker.stage_complete(7)

            # 步驟 8：階段 6 — 敘事
            await tracker.stage_start(8)
            await self._run_phase(
                "階段 6：敘事",
                [("敘事", NarrativeAgent(**agent_kwargs))],
                stage=8, book_token=book_token,
            )
            await tracker.stage_complete(8)

            # 步驟 9：建立詞彙表
            await tracker.stage_start(9)
            self.emitter.stage_start(9, "glossary")
            stage_t0 = time.time()
            with _status(f"正在寫入 {L['glossary_file']}...", self.console):
                glossary_content = self._build_glossary(L)
                await self.slima.create_file(
                    book_token,
                    path=L["glossary_file"],
                    content=glossary_content,
                    commit_message=L["glossary_commit"],
                )
            self.emitter.file_created(L["glossary_file"])
            self.emitter.stage_complete(9, "glossary", time.time() - stage_t0)
            await tracker.stage_complete(9)

            # 步驟 10：驗證（第一輪 — 一致性 + 內容完整度檢查 + 修復）
            await tracker.stage_start(10)
            await self._run_phase(
                "階段 7a：驗證",
                [("驗證-R1", ValidationAgent(**agent_kwargs, validation_round=1))],
                stage=10, book_token=book_token,
            )
            await tracker.stage_complete(10)

            # 步驟 11：驗證（第二輪 — 確認修復 + 最終報告）
            await tracker.stage_start(11)
            await self._run_phase(
                "階段 7b：確認",
                [("驗證-R2", ValidationAgent(**agent_kwargs, validation_round=2))],
                stage=11, book_token=book_token,
            )
            await tracker.stage_complete(11)

            # 步驟 12：建立 README.md
            await tracker.stage_start(12)
            self.emitter.stage_start(12, "readme")
            stage_t0 = time.time()
            with _status("正在建立 README.md...", self.console):
                try:
                    structure = await self.slima.get_book_structure(book_token)
                    tree_str = format_structure_tree(structure)
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
            self.emitter.file_created("README.md")
            self.emitter.stage_complete(12, "readme", time.time() - stage_t0)
            await tracker.stage_complete(12)
            await tracker.complete()

            elapsed = time.time() - start
            self.emitter.pipeline_complete(book_token=book_token, total_duration_s=elapsed, success=True)

            self.console.print()
            self.console.print(
                Panel(
                    f"[bold green]世界觀聖經建構完成！[/bold green]\n\n"
                    f"書籍 Token：[cyan]{book_token}[/cyan]\n"
                    f"耗時：{elapsed:.0f} 秒\n\n"
                    f"在此查看：{self.slima._base_url}/books/{book_token}",
                    border_style="green",
                )
            )

            return book_token

        except Exception as e:
            elapsed = time.time() - start
            self.emitter.error(str(e))
            self.emitter.pipeline_complete(book_token=book_token, total_duration_s=elapsed, success=False)
            raise

    async def _run_phase(
        self, phase_name: str, agents: list[tuple[str, object]],
        *, stage: int = 0, book_token: str = "",
    ) -> None:
        """以平行方式執行一組 Agent，並顯示進度。"""
        agent_names = [name for name, _ in agents]
        self.emitter.stage_start(stage, phase_name, agent_names)
        stage_t0 = time.time()

        # Snapshot book structure BEFORE (for file diffing)
        pre_paths: set[str] = set()
        if book_token:
            pre_paths = await self._get_all_file_paths(book_token)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            tasks = {}
            for name, agent in agents:
                tasks[name] = progress.add_task(f"[{phase_name}] {name}...", total=None)

            async def _run_one(name: str, agent):
                self.emitter.agent_start(stage, name)
                try:
                    result = await agent.run()
                    self.emitter.agent_complete(
                        stage=stage, agent=name,
                        duration_s=result.duration_s, timed_out=result.timed_out,
                        summary=result.summary, num_turns=result.num_turns,
                        cost_usd=result.cost_usd,
                    )
                    if result.timed_out:
                        progress.update(tasks[name], description=f"[{phase_name}] {name} [yellow]部分完成[/yellow]")
                    else:
                        progress.update(tasks[name], description=f"[{phase_name}] {name} [green]完成[/green]")
                    return name, result
                except Exception as e:
                    self.emitter.error(str(e), stage=stage, agent=name)
                    progress.update(tasks[name], description=f"[{phase_name}] {name} [red]失敗[/red]")
                    logger.error(f"{name} 失敗：{e}")
                    raise

            results = await asyncio.gather(
                *[_run_one(name, agent) for name, agent in agents],
                return_exceptions=True,
            )

        # Snapshot book structure AFTER and emit file_created for new paths
        if book_token:
            post_paths = await self._get_all_file_paths(book_token)
            for new_path in sorted(post_paths - pre_paths):
                self.emitter.file_created(new_path)

        self.emitter.stage_complete(stage, phase_name, time.time() - stage_t0)

        for r in results:
            if isinstance(r, Exception):
                self.console.print(f"  [red]錯誤：[/red] {r}")
            else:
                name, result = r
                if result.timed_out:
                    self.console.print(f"  [yellow]{name}：[/yellow] 超時但檔案已建立（部分完成），繼續下一階段")
                else:
                    self.console.print(f"  [green]{name}：[/green] {result.summary[:80]}")

    async def _get_all_file_paths(self, book_token: str) -> set[str]:
        """Get all file paths in the book for diffing."""
        try:
            structure = await self.slima.get_book_structure(book_token)
            return set(flatten_paths(structure))
        except Exception:
            return set()

    async def _inject_book_structure(self, book_token: str) -> None:
        """Read the current book structure and store it in WorldContext.

        This lets later-phase agents see what files already exist,
        enabling better cross-referencing and avoiding duplicate work.
        """
        try:
            structure = await self.slima.get_book_structure(book_token)
            tree_str = format_structure_tree(structure)
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

    def __init__(self, msg: str, console: Console | None = None):
        self.msg = msg
        self.console = console or Console()

    def __enter__(self):
        self.console.print(f"  [dim]{self.msg}[/dim]")
        return self

    def __exit__(self, *exc):
        pass
