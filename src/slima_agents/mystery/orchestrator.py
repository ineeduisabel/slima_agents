"""MysteryOrchestratorAgent: sequential pipeline for mystery novel writing."""

from __future__ import annotations

import json
import logging
import time

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from ..agents.base import AgentResult
from ..lang import detect_language, flatten_paths, format_structure_tree
from ..progress import ProgressEmitter
from ..slima.client import SlimaClient
from ..tracker import PipelineTracker
from .context import MysteryContext
from .planner import PlannerAgent
from .validator import MysteryValidationAgent
from .specialists.crime_design import CrimeDesignAgent
from .specialists.characters import MysteryCharactersAgent
from .specialists.plot_architecture import PlotArchitectureAgent
from .specialists.setting import SettingAgent
from .specialists.act1_writer import Act1WriterAgent
from .specialists.act2_writer import Act2WriterAgent
from .specialists.act3_writer import Act3WriterAgent
from .specialists.polish import PolishAgent

logger = logging.getLogger(__name__)


# --- Localized path mappings (mystery-specific) ---

_MYSTERY_PATHS_ZH = {
    "planning_prefix": "規劃",
    "chapters_prefix": "章節",
    "crime_design_folder": "規劃/犯罪設計",
    "characters_folder": "規劃/角色",
    "plot_folder": "規劃/情節",
    "setting_folder": "規劃/場景",
    "overview_file": "規劃/概念總覽.md",
}

_MYSTERY_PATHS_JA = {
    "planning_prefix": "企画",
    "chapters_prefix": "章",
    "crime_design_folder": "企画/犯罪設計",
    "characters_folder": "企画/登場人物",
    "plot_folder": "企画/プロット",
    "setting_folder": "企画/舞台設定",
    "overview_file": "企画/コンセプト概要.md",
}

_MYSTERY_PATHS_KO = {
    "planning_prefix": "기획",
    "chapters_prefix": "장",
    "crime_design_folder": "기획/범죄설계",
    "characters_folder": "기획/등장인물",
    "plot_folder": "기획/플롯",
    "setting_folder": "기획/배경",
    "overview_file": "기획/컨셉개요.md",
}

_MYSTERY_PATHS_EN = {
    "planning_prefix": "planning",
    "chapters_prefix": "chapters",
    "crime_design_folder": "planning/crime-design",
    "characters_folder": "planning/characters",
    "plot_folder": "planning/plot",
    "setting_folder": "planning/setting",
    "overview_file": "planning/concept-overview.md",
}

_MYSTERY_LANG_PATHS = {
    "zh": _MYSTERY_PATHS_ZH,
    "ja": _MYSTERY_PATHS_JA,
    "ko": _MYSTERY_PATHS_KO,
    "en": _MYSTERY_PATHS_EN,
}


class MysteryOrchestratorAgent:
    """Orchestrate the complete mystery novel writing pipeline."""

    def __init__(
        self,
        slima_client: SlimaClient,
        model: str | None = None,
        emitter: ProgressEmitter | None = None,
        console: Console | None = None,
    ):
        self.slima = slima_client
        self.model = model
        self.context = MysteryContext()
        self.emitter = emitter or ProgressEmitter(enabled=False)
        self.console = console or Console()

    async def run(self, prompt: str, resume_book: str | None = None) -> str:
        """Execute the full mystery pipeline. Returns the book token."""
        start = time.time()
        lang = detect_language(prompt)
        L = _MYSTERY_LANG_PATHS[lang]
        book_token = resume_book or ""
        resume_from = 1

        self.emitter.pipeline_start(prompt=prompt, total_stages=11)
        self.console.print(
            Panel(f"[bold]懸疑推理寫手 Agent[/bold]\n{prompt}", border_style="magenta")
        )

        self.context.user_prompt = prompt

        try:
            # --- Resume mode ---
            if resume_book:
                tracker = await PipelineTracker.load_from_book(self.slima, resume_book)
                if tracker:
                    resume_from = tracker.next_stage()
                    if resume_from == -1:
                        self.console.print("  [green]所有階段已完成，無需繼續。[/green]")
                        return resume_book
                    self.console.print(
                        f"  [yellow]恢復模式：從階段 {resume_from} 繼續[/yellow]"
                    )
                else:
                    self.console.print("  [yellow]找不到進度記錄，從頭開始[/yellow]")
                    resume_from = 1

                # Restore context from book
                await self._restore_context_from_book(resume_book, L)

            # --- Stage 1: Planning (no MCP) ---
            if resume_from <= 1:
                self.emitter.stage_start(1, "planning", ["PlannerAgent"])
                stage_t0 = time.time()
                planner = PlannerAgent(
                    context=self.context, model=self.model, prompt=prompt
                )
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    console=self.console,
                ) as progress:
                    task_id = progress.add_task(
                        "[階段 1] 企劃 Agent 正在分析提示詞...", total=None
                    )
                    self.emitter.agent_start(1, "PlannerAgent")
                    result = await planner.run()
                    if not result.full_output.strip():
                        progress.update(
                            task_id,
                            description="[階段 1] 企劃 Agent [yellow]重試中[/yellow]...",
                        )
                        result = await planner.run()

                if not result.full_output.strip():
                    raise RuntimeError("PlannerAgent returned empty output after retry")

                self.emitter.agent_complete(
                    stage=1, agent="PlannerAgent",
                    duration_s=result.duration_s, timed_out=result.timed_out,
                    summary=result.summary, num_turns=result.num_turns,
                    cost_usd=result.cost_usd,
                )
                self.emitter.stage_complete(1, "planning", time.time() - stage_t0)
                self.console.print(f"  [green]企劃完成：[/green] {result.summary[:80]}")
            else:
                planner = PlannerAgent(
                    context=self.context, model=self.model, prompt=prompt
                )

            # --- Stage 2: Book setup ---
            if resume_from <= 2:
                self.emitter.stage_start(2, "book_setup")
                stage_t0 = time.time()
                book_title = planner.suggested_title or prompt[:60]
                book_description = planner.suggested_description or prompt[:200]

                if not book_token:
                    with _status("正在建立 Slima 書籍...", self.console):
                        book = await self.slima.create_book(
                            title=book_title,
                            description=book_description,
                        )
                    book_token = book.token
                    self.emitter.book_created(book_token, book_title, book_description)
                    self.console.print(
                        f"  書籍已建立：[cyan]{book_token}[/cyan]  "
                        f"標題：[yellow]{book_title}[/yellow]"
                    )

                # Write concept overview
                overview_text = self.context.serialize_for_prompt()
                with _status(f"正在寫入 {L['overview_file']}...", self.console):
                    await self.slima.create_file(
                        book_token,
                        path=L["overview_file"],
                        content=f"# Concept Overview\n\n{overview_text}",
                        commit_message="Add concept overview",
                    )
                self.emitter.file_created(L["overview_file"])
                self.emitter.stage_complete(2, "book_setup", time.time() - stage_t0)

            # Initialize tracker (needs book_token)
            tracker = PipelineTracker(
                pipeline_name="mystery",
                book_token=book_token,
                prompt=prompt,
                slima=self.slima,
            )
            tracker.define_stages([
                (1, "planning"), (2, "book_setup"), (3, "crime_design"),
                (4, "characters"), (5, "plot_architecture"), (6, "setting"),
                (7, "act1_writing"), (8, "act2_writing"), (9, "act3_writing"),
                (10, "validation"), (11, "polish"),
            ])
            # Mark completed stages
            for sn in range(1, resume_from):
                rec = tracker._find(sn)
                if rec:
                    rec.status = "completed"
            await tracker.start()

            agent_kwargs = dict(
                context=self.context,
                book_token=book_token,
                model=self.model,
            )

            # --- Stage 3: Crime Design ---
            if resume_from <= 3:
                await tracker.stage_start(3)
                await self._run_stage(
                    3, "犯罪設計", CrimeDesignAgent(**agent_kwargs), book_token
                )
                await self._inject_book_structure(book_token)
                await tracker.stage_complete(3)
                await self._save_context_snapshot(book_token)

            # --- Stage 4: Characters ---
            if resume_from <= 4:
                await tracker.stage_start(4)
                await self._run_stage(
                    4, "角色設計", MysteryCharactersAgent(**agent_kwargs), book_token
                )
                await self._inject_book_structure(book_token)
                await tracker.stage_complete(4)
                await self._save_context_snapshot(book_token)

            # --- Stage 5: Plot Architecture ---
            if resume_from <= 5:
                await tracker.stage_start(5)
                await self._run_stage(
                    5, "情節架構", PlotArchitectureAgent(**agent_kwargs), book_token
                )
                await self._inject_book_structure(book_token)
                await tracker.stage_complete(5)
                await self._save_context_snapshot(book_token)

            # --- Stage 6: Setting ---
            if resume_from <= 6:
                await tracker.stage_start(6)
                await self._run_stage(
                    6, "場景設定", SettingAgent(**agent_kwargs), book_token
                )
                await self._inject_book_structure(book_token)
                await tracker.stage_complete(6)
                await self._save_context_snapshot(book_token)

            # --- Stage 7: Act 1 Writing ---
            if resume_from <= 7:
                await tracker.stage_start(7)
                await self._run_stage(
                    7, "第一幕寫作", Act1WriterAgent(**agent_kwargs), book_token
                )
                await self._inject_book_structure(book_token)
                await self._summarize_chapters(book_token, "act1_summary", L)
                await tracker.stage_complete(7)
                await self._save_context_snapshot(book_token)

            # --- Stage 8: Act 2 Writing ---
            if resume_from <= 8:
                await tracker.stage_start(8)
                await self._run_stage(
                    8, "第二幕寫作", Act2WriterAgent(**agent_kwargs), book_token
                )
                await self._inject_book_structure(book_token)
                await self._summarize_chapters(book_token, "act2_summary", L)
                await tracker.stage_complete(8)
                await self._save_context_snapshot(book_token)

            # --- Stage 9: Act 3 Writing ---
            if resume_from <= 9:
                await tracker.stage_start(9)
                await self._run_stage(
                    9, "第三幕寫作", Act3WriterAgent(**agent_kwargs), book_token
                )
                await self._inject_book_structure(book_token)
                await self._summarize_chapters(book_token, "act3_summary", L)
                await tracker.stage_complete(9)
                await self._save_context_snapshot(book_token)

            # --- Stage 10: Validation (R1 + R2) ---
            # Chain R2 onto R1's session so R2 doesn't need to re-read all files.
            if resume_from <= 10:
                await tracker.stage_start(10)
                r1_result = await self._run_stage(
                    10, "驗證-R1",
                    MysteryValidationAgent(**agent_kwargs, validation_round=1),
                    book_token,
                )
                r1_session_id = r1_result.session_id if r1_result else ""
                await self._run_stage(
                    10, "驗證-R2",
                    MysteryValidationAgent(
                        **agent_kwargs, validation_round=2,
                        resume_session=r1_session_id,
                    ),
                    book_token,
                )
                await tracker.stage_complete(10)

            # --- Stage 11: Polish + README ---
            if resume_from <= 11:
                await tracker.stage_start(11)
                await self._run_stage(
                    11, "潤色收尾", PolishAgent(**agent_kwargs), book_token
                )
                await tracker.stage_complete(11)

            await tracker.complete()

            elapsed = time.time() - start
            self.emitter.pipeline_complete(
                book_token=book_token, total_duration_s=elapsed, success=True
            )

            self.console.print()
            self.console.print(
                Panel(
                    f"[bold green]懸疑推理小說完成！[/bold green]\n\n"
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
            self.emitter.pipeline_complete(
                book_token=book_token, total_duration_s=elapsed, success=False
            )
            raise

    async def _run_stage(
        self, stage: int, name: str, agent: object, book_token: str
    ) -> AgentResult | None:
        """Run a single agent with progress display. Returns the AgentResult."""
        self.emitter.stage_start(stage, name, [agent.name])
        stage_t0 = time.time()

        # Snapshot book structure BEFORE
        pre_paths: set[str] = set()
        if book_token:
            pre_paths = await self._get_all_file_paths(book_token)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task_id = progress.add_task(f"[階段 {stage}] {name}...", total=None)
            self.emitter.agent_start(stage, agent.name)
            try:
                result = await agent.run()
                self.emitter.agent_complete(
                    stage=stage, agent=agent.name,
                    duration_s=result.duration_s, timed_out=result.timed_out,
                    summary=result.summary, num_turns=result.num_turns,
                    cost_usd=result.cost_usd,
                )
                if result.timed_out:
                    progress.update(
                        task_id,
                        description=f"[階段 {stage}] {name} [yellow]部分完成[/yellow]",
                    )
                else:
                    progress.update(
                        task_id,
                        description=f"[階段 {stage}] {name} [green]完成[/green]",
                    )
            except Exception as e:
                self.emitter.error(str(e), stage=stage, agent=agent.name)
                progress.update(
                    task_id,
                    description=f"[階段 {stage}] {name} [red]失敗[/red]",
                )
                logger.error(f"{name} 失敗：{e}")
                raise

        # Snapshot AFTER and emit new files
        if book_token:
            post_paths = await self._get_all_file_paths(book_token)
            for new_path in sorted(post_paths - pre_paths):
                self.emitter.file_created(new_path)

        self.emitter.stage_complete(stage, name, time.time() - stage_t0)

        if result.timed_out:
            self.console.print(
                f"  [yellow]{name}：[/yellow] 超時但檔案已建立（部分完成），繼續下一階段"
            )
        else:
            self.console.print(f"  [green]{name}：[/green] {result.summary[:80]}")

        return result

    async def _get_all_file_paths(self, book_token: str) -> set[str]:
        """Get all file paths in the book for diffing."""
        try:
            structure = await self.slima.get_book_structure(book_token)
            return set(flatten_paths(structure))
        except Exception:
            return set()

    async def _inject_book_structure(self, book_token: str) -> None:
        """Read current book structure and store in MysteryContext."""
        try:
            structure = await self.slima.get_book_structure(book_token)
            tree_str = format_structure_tree(structure)
            await self.context.write("book_structure", tree_str)
            logger.debug(f"Injected book structure ({len(tree_str)} chars)")
        except Exception as e:
            logger.warning(f"Failed to inject book structure: {e}")

    async def _summarize_chapters(
        self, book_token: str, section: str, L: dict
    ) -> None:
        """Read chapter files and create a brief summary for context continuity."""
        try:
            structure = await self.slima.get_book_structure(book_token)
            all_paths = flatten_paths(structure)
            chapter_prefix = L["chapters_prefix"]
            chapter_paths = sorted(
                p for p in all_paths if p.startswith(chapter_prefix + "/")
            )

            summaries = []
            for path in chapter_paths:
                try:
                    resp = await self.slima.read_file(book_token, path)
                    content = resp.content if hasattr(resp, "content") else str(resp)
                    # Take the first ~500 chars as a summary hint
                    preview = content[:500].strip()
                    if preview:
                        summaries.append(f"### {path}\n{preview}...")
                except Exception:
                    pass

            if summaries:
                await self.context.write(section, "\n\n".join(summaries))
                logger.debug(f"Summarized {len(summaries)} chapters into {section}")
        except Exception as e:
            logger.warning(f"Failed to summarize chapters: {e}")

    async def _save_context_snapshot(self, book_token: str) -> None:
        """Save current context as a JSON snapshot for O(1) resume loading."""
        try:
            snapshot = self.context.to_snapshot()
            await self.slima.write_file(
                book_token,
                path="agent-log/context-snapshot.json",
                content=json.dumps(snapshot, ensure_ascii=False, indent=2),
                commit_message="Update context snapshot",
            )
            logger.debug("Saved context snapshot")
        except Exception as e:
            logger.warning(f"Failed to save context snapshot: {e}")

    async def _restore_context_from_book(self, book_token: str, L: dict) -> None:
        """Restore MysteryContext from book. Prefers JSON snapshot over individual files."""
        # Try O(1) snapshot first
        try:
            resp = await self.slima.read_file(book_token, "agent-log/context-snapshot.json")
            content = resp.content if hasattr(resp, "content") else str(resp)
            snapshot = json.loads(content)
            self.context.from_snapshot(snapshot)
            logger.info("Restored context from snapshot")
            return
        except Exception:
            logger.debug("No context snapshot found, falling back to file-by-file restore")

        # Fallback: read individual files (legacy)
        await self._restore_context_from_files(book_token, L)

    async def _restore_context_from_files(self, book_token: str, L: dict) -> None:
        """Legacy restore: read individual book files to rebuild context."""
        async def _try_read(path: str) -> str:
            try:
                resp = await self.slima.read_file(book_token, path)
                return resp.content if hasattr(resp, "content") else str(resp)
            except Exception:
                return ""

        # Read concept overview
        overview = await _try_read(L["overview_file"])
        if overview:
            await self.context.write("concept", overview)

        # Read crime design overview
        crime = await _try_read(L["crime_design_folder"] + "/overview.md")
        if crime:
            await self.context.write("crime_design", crime)

        # Read character files
        try:
            structure = await self.slima.get_book_structure(book_token)
            all_paths = flatten_paths(structure)

            char_prefix = L["characters_folder"]
            char_paths = [p for p in all_paths if p.startswith(char_prefix + "/")]
            chars = []
            for path in sorted(char_paths):
                content = await _try_read(path)
                if content:
                    chars.append(f"### {path}\n{content[:300]}...")
            if chars:
                await self.context.write("characters", "\n\n".join(chars))

            # Read plot outline
            plot = await _try_read(L["plot_folder"] + "/chapter-outline.md")
            if plot:
                await self.context.write("plot_architecture", plot)

            # Read existing chapters for act summaries
            chapter_prefix = L["chapters_prefix"]
            chapter_paths = sorted(
                p for p in all_paths if p.startswith(chapter_prefix + "/")
            )
            for path in chapter_paths:
                content = await _try_read(path)
                if not content:
                    continue
                preview = content[:500]
                # Rough assignment based on file ordering
                name = path.split("/")[-1].lower()
                if any(x in name for x in ("01", "02", "03", "04", "1-", "2-", "3-", "4-")):
                    await self.context.append("act1_summary", f"### {path}\n{preview}...")
                elif any(x in name for x in ("05", "06", "07", "08", "5-", "6-", "7-", "8-")):
                    await self.context.append("act2_summary", f"### {path}\n{preview}...")
                elif any(x in name for x in ("09", "10", "11", "12", "9-")):
                    await self.context.append("act3_summary", f"### {path}\n{preview}...")

            # Inject book structure
            tree_str = format_structure_tree(structure)
            await self.context.write("book_structure", tree_str)

        except Exception as e:
            logger.warning(f"Failed to restore context from book: {e}")


class _status:
    """Simple context manager for status messages."""

    def __init__(self, msg: str, console: Console | None = None):
        self.msg = msg
        self.console = console or Console()

    def __enter__(self):
        self.console.print(f"  [dim]{self.msg}[/dim]")
        return self

    def __exit__(self, *exc):
        pass
