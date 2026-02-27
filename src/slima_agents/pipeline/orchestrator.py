"""GenericOrchestrator: plan-driven pipeline execution."""

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
from .context import DynamicContext
from .models import PipelinePlan, StageDefinition, ValidationDefinition
from .planner import GenericPlannerAgent
from .writer_agent import WriterAgent

logger = logging.getLogger(__name__)


class GenericOrchestrator:
    """Execute a plan-driven writing pipeline.

    Public API:
        plan()         → (PipelinePlan, session_id)   — planning only
        revise_plan()  → (PipelinePlan, session_id)   — revise via session chaining
        execute()      → book_token                   — execute an approved plan
        run()          → book_token                   — plan + execute (backward compat)
    """

    def __init__(
        self,
        slima_client: SlimaClient,
        model: str | None = None,
        emitter: ProgressEmitter | None = None,
        console: Console | None = None,
    ):
        self.slima = slima_client
        self.model = model
        self.context: DynamicContext | None = None
        self.emitter = emitter or ProgressEmitter(enabled=False)
        self.console = console or Console()

    # --- Public API ---

    async def plan(
        self,
        prompt: str,
        source_book: str | None = None,
    ) -> tuple[PipelinePlan, str]:
        """Run planning only. Returns (plan, planner_session_id).

        Args:
            prompt: User's writing prompt.
            source_book: Optional existing book token for the planner to read.

        Raises:
            RuntimeError: If the planner fails to produce a valid plan.
        """
        plan, session_id, _ = await self._run_planning(prompt, source_book=source_book)
        if not plan:
            raise RuntimeError(
                "GenericPlannerAgent failed to produce a valid plan"
            )
        self.emitter.plan_ready(
            plan_json=plan.model_dump_json(indent=2),
            session_id=session_id,
        )
        return plan, session_id

    async def revise_plan(
        self,
        prompt: str,
        feedback: str,
        session_id: str,
        source_book: str | None = None,
    ) -> tuple[PipelinePlan, str]:
        """Revise a plan via session chaining. Returns (revised_plan, new_session_id).

        Args:
            prompt: Original user prompt.
            feedback: User's revision feedback.
            session_id: Session ID from previous plan() or revise_plan() call.
            source_book: Optional existing book token.

        Raises:
            RuntimeError: If revision fails to produce a valid plan.
        """
        planner_ctx = DynamicContext(allowed_sections=["concept"])
        planner = GenericPlannerAgent(
            context=planner_ctx,
            model=self.model,
            prompt=prompt,
            source_book=source_book or "",
        )

        self.console.print("[dim]Revising plan...[/dim]")
        result = await planner.revise(feedback, session_id)

        if not planner.plan:
            raise RuntimeError(
                "GenericPlannerAgent failed to produce a valid revised plan"
            )

        new_session_id = result.session_id
        self.emitter.plan_ready(
            plan_json=planner.plan.model_dump_json(indent=2),
            session_id=new_session_id,
        )
        return planner.plan, new_session_id

    async def execute(
        self,
        prompt: str,
        plan: PipelinePlan,
        resume_book: str | None = None,
    ) -> str:
        """Execute an approved plan. Returns book_token.

        Args:
            prompt: User's writing prompt.
            plan: The approved PipelinePlan to execute.
            resume_book: Optional book token to resume into (skip book creation).
        """
        start = time.time()
        book_token = resume_book or ""

        self.emitter.plan_approved(version=1)
        self.emitter.pipeline_start(prompt=prompt, total_stages=0)
        self.console.print(
            Panel(f"[bold]Executing Pipeline[/bold]\n{prompt}", border_style="blue")
        )

        try:
            # Compute total stages for emitter
            total = (
                len(plan.stages)
                + (1 if plan.validation else 0)
                + (1 if plan.polish_stage else 0)
                + 1  # book_setup
            )
            self.emitter.pipeline_start(prompt=prompt, total_stages=total)

            # --- Book setup ---
            book_token = await self._setup_book(plan, book_token)

            # --- Context init ---
            if self.context is None:
                self.context = DynamicContext.from_plan(plan)
                self.context.user_prompt = prompt
                await self.context.write("concept", plan.concept_summary)

            # --- Initialize tracker ---
            tracker = self._create_tracker(plan, book_token, prompt)
            await tracker.start()

            # --- Stage loop ---
            for stage_def in sorted(plan.stages, key=lambda s: s.number):
                await tracker.stage_start(stage_def.number)
                await self._run_writer_stage(stage_def, book_token)
                await self._inject_book_structure(book_token)
                if stage_def.summarize_chapters and stage_def.summary_section:
                    await self._summarize_chapters(
                        book_token, stage_def.summary_section, plan
                    )
                await tracker.stage_complete(stage_def.number)
                await self._save_context_snapshot(book_token)

            # --- Validation ---
            if plan.validation:
                await tracker.stage_start(plan.validation.number)
                await self._run_validation(plan.validation, book_token)
                await tracker.stage_complete(plan.validation.number)

            # --- Polish ---
            if plan.polish_stage:
                await tracker.stage_start(plan.polish_stage.number)
                await self._run_writer_stage(plan.polish_stage, book_token)
                await tracker.stage_complete(plan.polish_stage.number)

            await tracker.complete()

            elapsed = time.time() - start
            self.emitter.pipeline_complete(
                book_token=book_token, total_duration_s=elapsed, success=True
            )
            self.console.print()
            self.console.print(
                Panel(
                    f"[bold green]Pipeline complete![/bold green]\n\n"
                    f"Book Token: [cyan]{book_token}[/cyan]\n"
                    f"Elapsed: {elapsed:.0f}s\n\n"
                    f"View: {self.slima._base_url}/books/{book_token}",
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

    async def run(
        self,
        prompt: str,
        resume_book: str | None = None,
        external_plan: PipelinePlan | None = None,
        source_book: str | None = None,
    ) -> str:
        """Plan + execute in one call (backward compatible).

        Args:
            prompt: User's writing prompt.
            resume_book: Optional book token to resume.
            external_plan: Optional pre-made plan (skip planning).
            source_book: Optional source book for planner to read.
        """
        start = time.time()
        book_token = resume_book or ""
        resume_from = 1
        plan: PipelinePlan | None = external_plan

        self.emitter.pipeline_start(prompt=prompt, total_stages=0)
        self.console.print(
            Panel(f"[bold]Plan-Driven Pipeline[/bold]\n{prompt}", border_style="blue")
        )

        try:
            # --- Resume mode ---
            if resume_book:
                resume_from, plan = await self._handle_resume(resume_book)
                if resume_from == -1:
                    return resume_book

            # --- Stage 1: Planning ---
            if not plan and resume_from <= 1:
                plan_result, _, _ = await self._run_planning(
                    prompt, source_book=source_book
                )
                plan = plan_result
                if not plan:
                    raise RuntimeError(
                        "GenericPlannerAgent failed to produce a valid plan"
                    )

            if not plan:
                raise RuntimeError("No plan available (planning stage was skipped but no plan found)")

            # Compute total stages for emitter
            total = len(plan.stages) + (1 if plan.validation else 0) + (1 if plan.polish_stage else 0) + 2  # +2 for planning + book_setup
            self.emitter.pipeline_start(prompt=prompt, total_stages=total)

            # --- Stage 2: Book setup ---
            if resume_from <= 2:
                book_token = await self._setup_book(plan, book_token)

            # --- Context init ---
            if self.context is None:
                self.context = DynamicContext.from_plan(plan)
                self.context.user_prompt = prompt
                await self.context.write("concept", plan.concept_summary)

            # --- Initialize tracker ---
            tracker = self._create_tracker(plan, book_token, prompt)
            for sn in range(1, resume_from):
                rec = tracker._find(sn)
                if rec:
                    rec.status = "completed"
            await tracker.start()

            # --- Stage loop ---
            for stage_def in sorted(plan.stages, key=lambda s: s.number):
                if resume_from <= stage_def.number:
                    await tracker.stage_start(stage_def.number)
                    await self._run_writer_stage(stage_def, book_token)
                    await self._inject_book_structure(book_token)
                    if stage_def.summarize_chapters and stage_def.summary_section:
                        await self._summarize_chapters(
                            book_token, stage_def.summary_section, plan
                        )
                    await tracker.stage_complete(stage_def.number)
                    await self._save_context_snapshot(book_token)

            # --- Validation ---
            if plan.validation and resume_from <= plan.validation.number:
                await tracker.stage_start(plan.validation.number)
                await self._run_validation(plan.validation, book_token)
                await tracker.stage_complete(plan.validation.number)

            # --- Polish ---
            if plan.polish_stage and resume_from <= plan.polish_stage.number:
                await tracker.stage_start(plan.polish_stage.number)
                await self._run_writer_stage(plan.polish_stage, book_token)
                await tracker.stage_complete(plan.polish_stage.number)

            await tracker.complete()

            elapsed = time.time() - start
            self.emitter.pipeline_complete(
                book_token=book_token, total_duration_s=elapsed, success=True
            )
            self.console.print()
            self.console.print(
                Panel(
                    f"[bold green]Pipeline complete![/bold green]\n\n"
                    f"Book Token: [cyan]{book_token}[/cyan]\n"
                    f"Elapsed: {elapsed:.0f}s\n\n"
                    f"View: {self.slima._base_url}/books/{book_token}",
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

    # --- Internal methods ---

    async def _handle_resume(
        self, book_token: str
    ) -> tuple[int, PipelinePlan | None]:
        """Handle resume mode: load tracker + plan + context snapshot."""
        resume_from = 1
        plan: PipelinePlan | None = None

        tracker = await PipelineTracker.load_from_book(self.slima, book_token)
        if tracker:
            resume_from = tracker.next_stage()
            if resume_from == -1:
                self.console.print("  [green]All stages completed.[/green]")
                return -1, None
            self.console.print(
                f"  [yellow]Resume mode: continuing from stage {resume_from}[/yellow]"
            )
        else:
            self.console.print("  [yellow]No progress found, starting fresh[/yellow]")

        # Restore plan from book
        plan = await self._load_plan_from_book(book_token)

        # Restore context from snapshot
        if plan:
            self.context = DynamicContext.from_plan(plan)
            await self._restore_context_snapshot(book_token)

        return resume_from, plan

    async def _run_planning(
        self,
        prompt: str,
        source_book: str | None = None,
    ) -> tuple[PipelinePlan | None, str, AgentResult | None]:
        """Run the GenericPlannerAgent. Returns (plan, session_id, result)."""
        self.emitter.stage_start(1, "planning", ["GenericPlannerAgent"])
        stage_t0 = time.time()

        # Planner needs a minimal context (no plan yet)
        planner_ctx = DynamicContext(allowed_sections=["concept"])
        planner = GenericPlannerAgent(
            context=planner_ctx,
            model=self.model,
            prompt=prompt,
            source_book=source_book or "",
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task_id = progress.add_task("[Stage 1] Planning...", total=None)
            self.emitter.agent_start(1, "GenericPlannerAgent")
            result = await planner.run()

            if not planner.plan:
                progress.update(task_id, description="[Stage 1] Planning [yellow]retry[/yellow]...")
                result = await planner.run()

        if not planner.plan:
            return None, "", result

        self.emitter.agent_complete(
            stage=1, agent="GenericPlannerAgent",
            duration_s=result.duration_s, timed_out=result.timed_out,
            summary=result.summary, num_turns=result.num_turns,
            cost_usd=result.cost_usd,
        )
        self.emitter.stage_complete(1, "planning", time.time() - stage_t0)
        self.console.print(
            f"  [green]Plan ready:[/green] {planner.plan.title} ({planner.plan.genre})"
        )
        return planner.plan, result.session_id, result

    async def _setup_book(self, plan: PipelinePlan, book_token: str) -> str:
        """Create book and save plan JSON."""
        self.emitter.stage_start(2, "book_setup")
        stage_t0 = time.time()

        if not book_token:
            with _status("Creating Slima book...", self.console):
                book = await self.slima.create_book(
                    title=plan.title, description=plan.description
                )
            book_token = book.token
            self.emitter.book_created(book_token, plan.title, plan.description)
            self.console.print(
                f"  Book created: [cyan]{book_token}[/cyan]  "
                f"Title: [yellow]{plan.title}[/yellow]"
            )

        # Save plan JSON for resume
        with _status("Saving pipeline plan...", self.console):
            await self.slima.create_file(
                book_token,
                path="agent-log/pipeline-plan.json",
                content=plan.model_dump_json(indent=2),
                commit_message="Save pipeline plan",
            )

        # Write concept overview
        overview_path = plan.file_paths.get("overview_file", "planning/concept-overview.md")
        with _status(f"Writing {overview_path}...", self.console):
            await self.slima.create_file(
                book_token,
                path=overview_path,
                content=f"# Concept Overview\n\n{plan.concept_summary}",
                commit_message="Add concept overview",
            )
        self.emitter.file_created(overview_path)

        self.emitter.stage_complete(2, "book_setup", time.time() - stage_t0)
        return book_token

    async def _run_writer_stage(
        self, stage_def: StageDefinition, book_token: str
    ) -> AgentResult | None:
        """Execute a single WriterAgent stage."""
        stage_num = stage_def.number
        display = stage_def.display_name
        self.emitter.stage_start(stage_num, stage_def.name, [f"WriterAgent[{stage_def.name}]"])
        stage_t0 = time.time()

        # Snapshot paths BEFORE
        pre_paths = await self._get_all_file_paths(book_token)

        agent = WriterAgent(
            context=self.context,
            book_token=book_token,
            model=self.model,
            timeout=stage_def.timeout,
            stage_name=stage_def.name,
            stage_instructions=stage_def.instructions,
            stage_initial_message=stage_def.initial_message,
            tool_set=stage_def.tool_set,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task_id = progress.add_task(
                f"[Stage {stage_num}] {display}...", total=None
            )
            self.emitter.agent_start(stage_num, agent.name)
            try:
                result = await agent.run()
                self.emitter.agent_complete(
                    stage=stage_num, agent=agent.name,
                    duration_s=result.duration_s, timed_out=result.timed_out,
                    summary=result.summary, num_turns=result.num_turns,
                    cost_usd=result.cost_usd,
                )
                status_label = "[yellow]partial[/yellow]" if result.timed_out else "[green]done[/green]"
                progress.update(
                    task_id,
                    description=f"[Stage {stage_num}] {display} {status_label}",
                )
            except Exception as e:
                self.emitter.error(str(e), stage=stage_num, agent=agent.name)
                progress.update(
                    task_id,
                    description=f"[Stage {stage_num}] {display} [red]failed[/red]",
                )
                raise

        # Emit new files
        post_paths = await self._get_all_file_paths(book_token)
        for new_path in sorted(post_paths - pre_paths):
            self.emitter.file_created(new_path)

        self.emitter.stage_complete(stage_num, stage_def.name, time.time() - stage_t0)

        if result.timed_out:
            self.console.print(
                f"  [yellow]{display}:[/yellow] timed out but files saved (partial)"
            )
        else:
            self.console.print(f"  [green]{display}:[/green] {result.summary[:80]}")

        return result

    async def _run_validation(
        self, vdef: ValidationDefinition, book_token: str
    ) -> None:
        """Run validation R1 + R2 with session chaining."""
        display = "Validation"
        stage_num = vdef.number
        self.emitter.stage_start(stage_num, "validation", ["WriterAgent[validation_r1]", "WriterAgent[validation_r2]"])
        stage_t0 = time.time()

        # R1
        r1_agent = WriterAgent(
            context=self.context,
            book_token=book_token,
            model=self.model,
            timeout=vdef.timeout,
            stage_name="validation_r1",
            stage_instructions=vdef.r1_instructions,
            stage_initial_message=vdef.r1_initial_message,
            tool_set=vdef.tool_set,
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task_id = progress.add_task(f"[Stage {stage_num}] {display} R1...", total=None)
            self.emitter.agent_start(stage_num, r1_agent.name)
            r1_result = await r1_agent.run()
            self.emitter.agent_complete(
                stage=stage_num, agent=r1_agent.name,
                duration_s=r1_result.duration_s, timed_out=r1_result.timed_out,
                summary=r1_result.summary, num_turns=r1_result.num_turns,
                cost_usd=r1_result.cost_usd,
            )

        self.console.print(f"  [green]Validation R1:[/green] {r1_result.summary[:80]}")

        # R2 (chained session)
        r2_agent = WriterAgent(
            context=self.context,
            book_token=book_token,
            model=self.model,
            timeout=vdef.timeout,
            resume_session=r1_result.session_id,
            stage_name="validation_r2",
            stage_instructions=vdef.r2_instructions,
            stage_initial_message=vdef.r2_initial_message,
            tool_set=vdef.tool_set,
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task_id = progress.add_task(f"[Stage {stage_num}] {display} R2...", total=None)
            self.emitter.agent_start(stage_num, r2_agent.name)
            r2_result = await r2_agent.run()
            self.emitter.agent_complete(
                stage=stage_num, agent=r2_agent.name,
                duration_s=r2_result.duration_s, timed_out=r2_result.timed_out,
                summary=r2_result.summary, num_turns=r2_result.num_turns,
                cost_usd=r2_result.cost_usd,
            )

        self.console.print(f"  [green]Validation R2:[/green] {r2_result.summary[:80]}")
        self.emitter.stage_complete(stage_num, "validation", time.time() - stage_t0)

    # --- Shared helpers (same pattern as mystery orchestrator) ---

    def _create_tracker(
        self, plan: PipelinePlan, book_token: str, prompt: str
    ) -> PipelineTracker:
        """Create and configure a PipelineTracker from the plan."""
        tracker = PipelineTracker(
            pipeline_name=plan.genre,
            book_token=book_token,
            prompt=prompt,
            slima=self.slima,
        )
        stage_defs: list[tuple[int, str]] = [(1, "planning"), (2, "book_setup")]
        for s in sorted(plan.stages, key=lambda s: s.number):
            stage_defs.append((s.number, s.name))
        if plan.validation:
            stage_defs.append((plan.validation.number, "validation"))
        if plan.polish_stage:
            stage_defs.append((plan.polish_stage.number, "polish"))
        tracker.define_stages(stage_defs)
        return tracker

    async def _get_all_file_paths(self, book_token: str) -> set[str]:
        try:
            structure = await self.slima.get_book_structure(book_token)
            return set(flatten_paths(structure))
        except Exception:
            return set()

    async def _inject_book_structure(self, book_token: str) -> None:
        try:
            structure = await self.slima.get_book_structure(book_token)
            tree_str = format_structure_tree(structure)
            await self.context.write("book_structure", tree_str)
        except Exception as e:
            logger.warning(f"Failed to inject book structure: {e}")

    async def _summarize_chapters(
        self, book_token: str, section: str, plan: PipelinePlan
    ) -> None:
        try:
            structure = await self.slima.get_book_structure(book_token)
            all_paths = flatten_paths(structure)
            chapter_prefix = plan.file_paths.get("chapters_prefix", "chapters")
            chapter_paths = sorted(
                p for p in all_paths if p.startswith(chapter_prefix + "/")
            )
            summaries = []
            for path in chapter_paths:
                try:
                    resp = await self.slima.read_file(book_token, path)
                    content = resp.content if hasattr(resp, "content") else str(resp)
                    preview = content[:500].strip()
                    if preview:
                        summaries.append(f"### {path}\n{preview}...")
                except Exception:
                    pass
            if summaries:
                await self.context.write(section, "\n\n".join(summaries))
        except Exception as e:
            logger.warning(f"Failed to summarize chapters: {e}")

    async def _save_context_snapshot(self, book_token: str) -> None:
        try:
            snapshot = self.context.to_snapshot()
            await self.slima.write_file(
                book_token,
                path="agent-log/context-snapshot.json",
                content=json.dumps(snapshot, ensure_ascii=False, indent=2),
                commit_message="Update context snapshot",
            )
        except Exception as e:
            logger.warning(f"Failed to save context snapshot: {e}")

    async def _restore_context_snapshot(self, book_token: str) -> None:
        """Restore DynamicContext from JSON snapshot."""
        try:
            resp = await self.slima.read_file(
                book_token, "agent-log/context-snapshot.json"
            )
            content = resp.content if hasattr(resp, "content") else str(resp)
            snapshot = json.loads(content)
            self.context.from_snapshot(snapshot)
            logger.info("Restored context from snapshot")
        except Exception:
            logger.debug("No context snapshot found")

    async def _load_plan_from_book(self, book_token: str) -> PipelinePlan | None:
        """Load PipelinePlan JSON from book."""
        try:
            resp = await self.slima.read_file(
                book_token, "agent-log/pipeline-plan.json"
            )
            content = resp.content if hasattr(resp, "content") else str(resp)
            data = json.loads(content)
            return PipelinePlan.model_validate(data)
        except Exception:
            logger.warning("Failed to load pipeline plan from book")
            return None


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
