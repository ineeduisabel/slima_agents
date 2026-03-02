"""TaskOrchestrator: front-end configurable multi-stage TaskAgent pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from ..agents.base import AgentResult
from ..lang import flatten_paths, format_structure_tree
from .context import DynamicContext
from ..progress import ProgressEmitter
from ..slima.client import SlimaClient
from ..tracker import PipelineTracker
from .task import TaskAgent
from .task_models import TaskPlan, TaskStageDefinition

logger = logging.getLogger(__name__)


class TaskOrchestrator:
    """Execute a front-end-defined TaskAgent pipeline.

    Stages with the same ``number`` run in parallel (asyncio.gather).
    Different numbers run sequentially, lowest first.
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

    async def run(self, plan: TaskPlan) -> str:
        """Execute a TaskPlan. Returns book_token (or "" if no book)."""
        start = time.time()
        book_token = plan.book_token

        total_stages = len(plan.stages)
        self.emitter.pipeline_start(prompt=plan.title or "(task-pipeline)", total_stages=total_stages)
        self.console.print(f"  [bold]Task Pipeline[/bold]: {plan.title or '(no title)'}")

        try:
            # --- Book setup ---
            book_token = await self._setup_book(plan, book_token)

            # --- Context init ---
            self.context = DynamicContext(allowed_sections=plan.context_sections)
            await self._inject_pipeline_info(plan, book_token)

            # --- Tracker init ---
            tracker: PipelineTracker | None = None
            if book_token:
                tracker = self._create_tracker(plan, book_token)
                await tracker.start()

            # --- Group stages by number ---
            groups = self._group_stages(plan.stages)
            last_session_id = ""  # for chain_to_previous

            for number in sorted(groups.keys()):
                group = groups[number]

                if tracker:
                    await tracker.stage_start(number)

                if len(group) == 1:
                    result = await self._run_single_stage(group[0], book_token, last_session_id)
                    last_session_id = result.session_id or last_session_id
                else:
                    results = await self._run_parallel_stages(group, book_token)
                    # After parallel group, pick last non-empty session_id
                    for r in results:
                        if r.session_id:
                            last_session_id = r.session_id

                # Post-group: inject book structure + save snapshot
                if book_token:
                    await self._inject_book_structure(book_token)
                    await self._save_context_snapshot(book_token)

                if tracker:
                    await tracker.stage_complete(number)

            if tracker:
                await tracker.complete()

            elapsed = time.time() - start
            self.emitter.pipeline_complete(
                book_token=book_token, total_duration_s=elapsed, success=True,
            )
            self.console.print(f"  [green]Pipeline complete![/green] Book: [cyan]{book_token or '(none)'}[/cyan]  ({elapsed:.0f}s)")
            return book_token

        except Exception as e:
            elapsed = time.time() - start
            self.emitter.error(str(e))
            self.emitter.pipeline_complete(
                book_token=book_token, total_duration_s=elapsed, success=False,
            )
            raise

    # --- Internal ---

    async def _setup_book(self, plan: TaskPlan, book_token: str) -> str:
        """Create a book if title is set and no existing token."""
        if book_token:
            self.console.print(f"  Using existing book: [cyan]{book_token}[/cyan]")
            return book_token

        if plan.title:
            book = await self.slima.create_book(title=plan.title)
            book_token = book.token
            self.emitter.book_created(book_token, plan.title, "")
            self.console.print(f"  Book created: [cyan]{book_token}[/cyan]  Title: [yellow]{plan.title}[/yellow]")

            # Save plan JSON for resume
            await self.slima.create_file(
                book_token,
                path="agent-log/task-plan.json",
                content=plan.model_dump_json(indent=2),
                commit_message="Save task plan",
            )

        return book_token

    def _create_tracker(self, plan: TaskPlan, book_token: str) -> PipelineTracker:
        """Create a PipelineTracker from the plan."""
        tracker = PipelineTracker(
            pipeline_name="task-pipeline",
            book_token=book_token,
            prompt=plan.title,
            slima=self.slima,
        )
        groups = self._group_stages(plan.stages)
        stage_defs: list[tuple[int, str]] = []
        for number in sorted(groups.keys()):
            names = [s.name for s in groups[number]]
            stage_defs.append((number, "+".join(names)))
        tracker.define_stages(stage_defs)
        return tracker

    @staticmethod
    def _group_stages(
        stages: list[TaskStageDefinition],
    ) -> dict[int, list[TaskStageDefinition]]:
        """Group stages by number. Same number = parallel."""
        groups: dict[int, list[TaskStageDefinition]] = {}
        for s in stages:
            groups.setdefault(s.number, []).append(s)
        return groups

    async def _run_single_stage(
        self, stage_def: TaskStageDefinition, book_token: str,
        last_session_id: str = "",
    ) -> AgentResult:
        """Run one TaskAgent stage."""
        display = stage_def.resolved_display_name
        stage_num = stage_def.number
        agent_name = f"TaskAgent[{stage_def.name}]"

        self.emitter.stage_start(stage_num, stage_def.name, [agent_name])
        stage_t0 = time.time()

        # Snapshot paths BEFORE
        pre_paths = await self._get_all_file_paths(book_token) if book_token else set()

        # Session chaining: if stage requests it, resume from previous session
        resume_session = last_session_id if stage_def.chain_to_previous and last_session_id else ""

        agent = self._create_agent(stage_def, book_token, resume_session=resume_session)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task_id = progress.add_task(f"[Stage {stage_num}] {display}...", total=None)
            agent.on_event = self.emitter.make_agent_callback(agent_name, stage=stage_num)
            self.emitter.agent_start(stage_num, agent_name)

            try:
                result = await agent.run()
                self.emitter.agent_complete(
                    stage=stage_num, agent=agent_name,
                    duration_s=result.duration_s, timed_out=result.timed_out,
                    summary=result.summary, num_turns=result.num_turns,
                    cost_usd=result.cost_usd,
                )
                status_label = "[yellow]partial[/yellow]" if result.timed_out else "[green]done[/green]"
                progress.update(task_id, description=f"[Stage {stage_num}] {display} {status_label}")
            except Exception as e:
                self.emitter.error(str(e), stage=stage_num, agent=agent_name)
                progress.update(task_id, description=f"[Stage {stage_num}] {display} [red]failed[/red]")
                raise

        # Emit new files
        new_files: set[str] = set()
        if book_token:
            post_paths = await self._get_all_file_paths(book_token)
            new_files = post_paths - pre_paths
            for new_path in sorted(new_files):
                self.emitter.file_created(new_path)

        self.emitter.stage_complete(stage_num, stage_def.name, time.time() - stage_t0)

        # Structured handoff: write result + metadata into context section
        if stage_def.context_section and result.full_output:
            handoff = self._build_handoff(stage_def, result, new_files)
            await self.context.write(stage_def.context_section, handoff)

        self.console.print(f"  [green]{display}:[/green] {result.summary[:80]}")
        return result

    async def _run_parallel_stages(
        self, stages: list[TaskStageDefinition], book_token: str,
    ) -> list[AgentResult]:
        """Run multiple stages in parallel (same number)."""
        stage_num = stages[0].number
        agent_names = [f"TaskAgent[{s.name}]" for s in stages]
        phase_name = f"Stage {stage_num}"

        self.emitter.stage_start(stage_num, phase_name, agent_names)
        stage_t0 = time.time()

        # Snapshot paths BEFORE
        pre_paths = await self._get_all_file_paths(book_token) if book_token else set()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            tasks = {}
            for s in stages:
                tasks[s.name] = progress.add_task(f"[{phase_name}] {s.resolved_display_name}...", total=None)

            async def _run_one(stage_def: TaskStageDefinition) -> tuple[str, AgentResult]:
                agent_name = f"TaskAgent[{stage_def.name}]"
                agent = self._create_agent(stage_def, book_token)
                agent.on_event = self.emitter.make_agent_callback(agent_name, stage=stage_num)
                self.emitter.agent_start(stage_num, agent_name)
                try:
                    result = await agent.run()
                    self.emitter.agent_complete(
                        stage=stage_num, agent=agent_name,
                        duration_s=result.duration_s, timed_out=result.timed_out,
                        summary=result.summary, num_turns=result.num_turns,
                        cost_usd=result.cost_usd,
                    )
                    status_label = "[yellow]partial[/yellow]" if result.timed_out else "[green]done[/green]"
                    progress.update(tasks[stage_def.name], description=f"[{phase_name}] {stage_def.resolved_display_name} {status_label}")

                    # Structured handoff: write result + metadata into context
                    if stage_def.context_section and result.full_output:
                        # Note: new_files not available per-agent in parallel mode
                        handoff = self._build_handoff(stage_def, result, set())
                        await self.context.write(stage_def.context_section, handoff)

                    return stage_def.name, result
                except Exception as e:
                    self.emitter.error(str(e), stage=stage_num, agent=agent_name)
                    progress.update(tasks[stage_def.name], description=f"[{phase_name}] {stage_def.resolved_display_name} [red]failed[/red]")
                    logger.error(f"{agent_name} failed: {e}")
                    raise

            results = await asyncio.gather(
                *[_run_one(s) for s in stages],
                return_exceptions=True,
            )

        # Snapshot paths AFTER
        if book_token:
            post_paths = await self._get_all_file_paths(book_token)
            for new_path in sorted(post_paths - pre_paths):
                self.emitter.file_created(new_path)

        self.emitter.stage_complete(stage_num, phase_name, time.time() - stage_t0)

        agent_results: list[AgentResult] = []
        for r in results:
            if isinstance(r, Exception):
                self.console.print(f"  [red]Error:[/red] {r}")
            else:
                name, result = r
                agent_results.append(result)
                if result.timed_out:
                    self.console.print(f"  [yellow]{name}:[/yellow] timed out but files saved (partial)")
                else:
                    self.console.print(f"  [green]{name}:[/green] {result.summary[:80]}")

        return agent_results

    def _create_agent(
        self, stage_def: TaskStageDefinition, book_token: str,
        resume_session: str = "",
    ) -> TaskAgent:
        """Build a TaskAgent from a stage definition."""
        return TaskAgent(
            context=self.context,
            book_token=book_token,
            model=self.model,
            timeout=stage_def.timeout,
            prompt=stage_def.prompt,
            system_prompt_text=stage_def.system_prompt,
            tool_set=stage_def.tool_set,
            plan_first=stage_def.plan_first,
            include_language_rule=stage_def.include_language_rule,
            resume_session=resume_session,
        )

    # --- Context enrichment ---

    async def _inject_pipeline_info(self, plan: TaskPlan, book_token: str) -> None:
        """Inject pipeline metadata into context so all agents see the overall plan."""
        stage_lines = []
        for s in sorted(plan.stages, key=lambda x: x.number):
            stage_lines.append(f"  {s.number}. {s.resolved_display_name} ({s.name})")
        info = (
            f"Title: {plan.title or '(untitled)'}\n"
            f"Book: {book_token or '(no book)'}\n"
            f"Total stages: {len(plan.stages)}\n"
            f"Stage plan:\n" + "\n".join(stage_lines)
        )
        await self.context.write("_pipeline_info", info)

    @staticmethod
    def _build_handoff(
        stage_def: TaskStageDefinition,
        result: AgentResult,
        new_files: set[str],
    ) -> str:
        """Build a structured handoff string for context propagation."""
        header_parts = [
            f"[Stage {stage_def.number} '{stage_def.resolved_display_name}' completed]",
        ]
        if new_files:
            header_parts.append(f"Files created: {', '.join(sorted(new_files))}")
        if result.timed_out:
            header_parts.append("(timed out — partial output)")
        header = "\n".join(header_parts)
        return f"{header}\n---\n{result.full_output}"

    # --- Shared helpers (same pattern as GenericOrchestrator) ---

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
