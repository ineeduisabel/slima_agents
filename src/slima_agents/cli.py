"""CLI 入口點：使用 Click + Rich。"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import click
from rich.console import Console

from .config import DEFAULT_MODEL, Config, ConfigError
from .mystery.orchestrator import MysteryOrchestratorAgent
from .progress import ProgressEmitter
from .slima.client import SlimaClient
from .worldbuild.orchestrator import OrchestratorAgent


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="開啟除錯日誌。")
def main(verbose: bool):
    """Slima Agents — AI 驅動的世界觀建構系統。"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="指定 Claude 模型（如 claude-opus-4-6）。")
@click.option("--json-progress", is_flag=True, default=False, help="輸出 NDJSON 進度事件到 stdout。")
def worldbuild(prompt: str, model: str | None, json_progress: bool):
    """從提示詞建構完整的世界觀聖經（World Bible）。

    \b
    使用範例：
      slima-agents worldbuild "英雄聯盟世界觀"
      slima-agents worldbuild "1980年代的美國" --model claude-opus-4-6
      slima-agents -v worldbuild "DnD 被遺忘的國度"
      slima-agents worldbuild --json-progress "海賊王世界觀"
    """
    # When --json-progress is on, Rich goes to stderr so stdout is pure NDJSON
    if json_progress:
        cli_console = Console(file=sys.stderr, no_color=True)
    else:
        cli_console = Console()

    emitter = ProgressEmitter(enabled=json_progress)

    try:
        config = Config.load(model_override=model)
    except ConfigError as e:
        cli_console.print(f"[red]Config error:[/red] {e}")
        raise SystemExit(1)

    async def _run():
        async with SlimaClient(config.slima_base_url, config.slima_api_token) as slima:
            orch = OrchestratorAgent(
                slima_client=slima,
                model=config.model,
                emitter=emitter,
                console=cli_console,
            )
            return await orch.run(prompt)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        cli_console.print("\n[yellow]Cancelled.[/yellow] (Ctrl+C)")
        raise SystemExit(130)


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="指定 Claude 模型（如 claude-opus-4-6）。")
@click.option("--book", "-b", default=None, help="繼續寫作指定書籍（恢復模式）。")
@click.option("--json-progress", is_flag=True, default=False, help="輸出 NDJSON 進度事件到 stdout。")
def mystery(prompt: str, model: str | None, book: str | None, json_progress: bool):
    """從概念建構完整的懸疑推理小說。

    \b
    使用範例：
      slima-agents mystery "一座維多利亞莊園的密室殺人事件"
      slima-agents mystery --book bk_abc123 "繼續寫作"
      slima-agents mystery "連環殺手在台北" --model claude-opus-4-6
    """
    if json_progress:
        cli_console = Console(file=sys.stderr, no_color=True)
    else:
        cli_console = Console()

    emitter = ProgressEmitter(enabled=json_progress)

    try:
        config = Config.load(model_override=model)
    except ConfigError as e:
        cli_console.print(f"[red]Config error:[/red] {e}")
        raise SystemExit(1)

    async def _run():
        async with SlimaClient(config.slima_base_url, config.slima_api_token) as slima:
            orch = MysteryOrchestratorAgent(
                slima_client=slima,
                model=config.model,
                emitter=emitter,
                console=cli_console,
            )
            return await orch.run(prompt, resume_book=book)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        cli_console.print("\n[yellow]Cancelled.[/yellow] (Ctrl+C)")
        raise SystemExit(130)


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="指定 Claude 模型。")
@click.option("--book", "-b", default=None, help="指定書籍 token（如 bk_abc123）。")
@click.option(
    "--writable", "-w", is_flag=True, default=False,
    help="允許建立/編輯檔案（預設唯讀）。",
)
@click.option("--resume", "-r", default=None, help="Resume 之前的 session ID（多輪對話）。")
@click.option("--system-prompt", default=None, help="自訂 system prompt。")
@click.option("--json", "json_output", is_flag=True, default=False, help="輸出 JSON（含 session_id）。")
def ask(
    prompt: str,
    model: str | None,
    book: str | None,
    writable: bool,
    resume: str | None,
    system_prompt: str | None,
    json_output: bool,
):
    """快速提問或操作 Slima 書籍（輕量版，不跑完整管線）。

    \b
    使用範例：
      slima-agents ask "列出我所有的書"
      slima-agents ask --book bk_abc123 "這本書有哪些章節？"
      slima-agents ask --book bk_abc123 --writable "幫我建一個 notes.md"
      slima-agents ask --resume sess_abc123 "繼續上次的話題"
      slima-agents ask --system-prompt "你是一個海盜" "說你好"
      slima-agents ask --json "你好"
    """
    console = Console()
    resolved_model = model or os.getenv("SLIMA_AGENTS_MODEL", DEFAULT_MODEL)

    async def _run():
        from .agents.ask import AskAgent
        from .agents.context import WorldContext

        agent = AskAgent(
            context=WorldContext(),
            book_token=book or "",
            model=resolved_model,
            prompt=prompt,
            writable=writable,
            resume_session=resume or "",
            custom_system_prompt=system_prompt,
        )
        return await agent.run()

    try:
        import json as json_mod

        result = asyncio.run(_run())

        if json_output:
            # JSON mode: structured output with session_id for frontend
            payload = json_mod.dumps({
                "session_id": result.session_id,
                "result": result.full_output,
                "num_turns": result.num_turns,
                "cost_usd": result.cost_usd,
                "duration_s": round(result.duration_s, 2),
            }, ensure_ascii=False)
            sys.stdout.buffer.write(payload.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")
        else:
            # Plain text mode (backward compatible)
            # Write UTF-8 directly to stdout buffer to avoid:
            # 1. Rich _unicode_data crash in Nuitka onefile builds
            # 2. Windows cp950 encoding errors with Chinese text
            sys.stdout.buffer.write(result.full_output.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")

        sys.stdout.buffer.flush()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(130)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="指定 Claude 模型（如 claude-opus-4-6）。")
@click.option("--book", "-b", default=None, help="繼續寫作指定書籍（恢復模式）。")
@click.option("--source-book", "-s", default=None, help="來源書籍 token（讀取既有書來規劃）。")
@click.option("--plan", "plan_file", default=None, type=click.Path(exists=True), help="使用自訂 plan JSON 檔案。")
@click.option("--json-progress", is_flag=True, default=False, help="輸出 NDJSON 進度事件到 stdout。")
def write(prompt: str, model: str | None, book: str | None, source_book: str | None, plan_file: str | None, json_progress: bool):
    """Plan-driven pipeline: AI 先規劃再依序寫作（任何類型）。

    \b
    使用範例：
      slima-agents write "寫密室推理"
      slima-agents write --book bk_abc123 "繼續寫作"
      slima-agents write --source-book bk_abc123 "依照這本書重寫"
      slima-agents write --plan my-plan.json "執行自訂計畫"
      slima-agents write "A sci-fi adventure" --model claude-opus-4-6
    """
    if json_progress:
        cli_console = Console(file=sys.stderr, no_color=True)
    else:
        cli_console = Console()

    emitter = ProgressEmitter(enabled=json_progress)

    try:
        config = Config.load(model_override=model)
    except ConfigError as e:
        cli_console.print(f"[red]Config error:[/red] {e}")
        raise SystemExit(1)

    # Load external plan if provided
    external_plan = None
    if plan_file:
        import json as json_mod
        from .pipeline.models import PipelinePlan
        try:
            with open(plan_file, encoding="utf-8") as f:
                data = json_mod.load(f)
            external_plan = PipelinePlan.model_validate(data)
            cli_console.print(f"  [green]Loaded plan from:[/green] {plan_file}")
        except Exception as e:
            cli_console.print(f"[red]Plan file error:[/red] {e}")
            raise SystemExit(1)

    async def _run():
        from .pipeline.orchestrator import GenericOrchestrator
        async with SlimaClient(config.slima_base_url, config.slima_api_token) as slima:
            orch = GenericOrchestrator(
                slima_client=slima,
                model=config.model,
                emitter=emitter,
                console=cli_console,
            )
            return await orch.run(
                prompt,
                resume_book=book,
                external_plan=external_plan,
                source_book=source_book,
            )

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        cli_console.print("\n[yellow]Cancelled.[/yellow] (Ctrl+C)")
        raise SystemExit(130)


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="指定 Claude 模型。")
@click.option("--book", "-b", default=None, help="來源書籍 token（讀取既有書來規劃）。")
def plan(prompt: str, model: str | None, book: str | None):
    """只產生 pipeline plan JSON（不執行）。

    \b
    使用範例：
      slima-agents plan "寫密室推理"
      slima-agents plan --book bk_abc123 "依照這本書重寫"
      slima-agents plan "A romance novel" --model claude-opus-4-6
    """
    cli_console = Console(file=sys.stderr)

    try:
        config = Config.load(model_override=model)
    except ConfigError as e:
        cli_console.print(f"[red]Config error:[/red] {e}")
        raise SystemExit(1)

    async def _run():
        from .pipeline.context import DynamicContext
        from .pipeline.planner import GenericPlannerAgent

        ctx = DynamicContext(allowed_sections=["concept"])
        planner = GenericPlannerAgent(
            context=ctx, model=config.model, prompt=prompt,
            source_book=book or "",
        )

        if book:
            cli_console.print(f"[dim]Running planner (source book: {book})...[/dim]")
        else:
            cli_console.print("[dim]Running planner...[/dim]")
        await planner.run()

        if not planner.plan:
            cli_console.print("[red]Planner failed to produce a valid plan.[/red]")
            raise SystemExit(1)

        return planner.plan

    try:
        result_plan = asyncio.run(_run())
        # Output plan JSON to stdout
        sys.stdout.buffer.write(result_plan.model_dump_json(indent=2).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()
    except KeyboardInterrupt:
        cli_console.print("\n[yellow]Cancelled.[/yellow] (Ctrl+C)")
        raise SystemExit(130)
    except SystemExit:
        raise
    except Exception as e:
        cli_console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@main.command("plan-loop")
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="指定 Claude 模型。")
@click.option("--book", "-b", default=None, help="來源書籍 token（讀取既有書來規劃）。")
def plan_loop(prompt: str, model: str | None, book: str | None):
    """互動式 plan 修訂迴圈：產生 → 審閱 → 修改 → 核准。

    \b
    使用範例：
      slima-agents plan-loop "寫密室推理"
      slima-agents plan-loop --book bk_abc123 "依照這本書重寫"
    """
    import json as json_mod

    cli_console = Console(file=sys.stderr)

    try:
        config = Config.load(model_override=model)
    except ConfigError as e:
        cli_console.print(f"[red]Config error:[/red] {e}")
        raise SystemExit(1)

    async def _run():
        from .pipeline.orchestrator import GenericOrchestrator

        async with SlimaClient(config.slima_base_url, config.slima_api_token) as slima:
            orch = GenericOrchestrator(
                slima_client=slima,
                model=config.model,
                console=cli_console,
            )

            # Initial plan
            cli_console.print("[dim]Generating initial plan...[/dim]")
            current_plan, session_id = await orch.plan(prompt, source_book=book)
            version = 1

            while True:
                # Display plan summary
                cli_console.print()
                cli_console.print(f"[bold cyan]===== Plan v{version} =====[/bold cyan]")
                cli_console.print(f"  Title: [yellow]{current_plan.title}[/yellow]")
                cli_console.print(f"  Genre: {current_plan.genre}")
                cli_console.print(f"  Action: {current_plan.action_type}")
                cli_console.print(f"  Stages: {len(current_plan.stages)}")
                for s in sorted(current_plan.stages, key=lambda x: x.number):
                    cli_console.print(f"    {s.number}. {s.display_name} ({s.name})")
                if current_plan.validation:
                    cli_console.print(f"    {current_plan.validation.number}. Validation (R1+R2)")
                if current_plan.polish_stage:
                    cli_console.print(f"    {current_plan.polish_stage.number}. {current_plan.polish_stage.display_name}")
                cli_console.print()

                # Get user input
                cli_console.print("[bold]Enter feedback to revise, or 'approve' to accept:[/bold]")
                try:
                    feedback = input("> ").strip()
                except EOFError:
                    cli_console.print("[yellow]EOF — aborting.[/yellow]")
                    raise SystemExit(130)

                if not feedback:
                    continue

                if feedback.lower() in ("approve", "ok", "yes", "y", "確認", "核准"):
                    cli_console.print("[green]Plan approved![/green]")
                    break

                # Revise
                cli_console.print(f"[dim]Revising plan (v{version + 1})...[/dim]")
                current_plan, session_id = await orch.revise_plan(
                    prompt=prompt,
                    feedback=feedback,
                    session_id=session_id,
                    source_book=book,
                )
                version += 1

            return current_plan

    try:
        final_plan = asyncio.run(_run())
        # Output final approved plan JSON to stdout
        sys.stdout.buffer.write(
            final_plan.model_dump_json(indent=2).encode("utf-8")
        )
        sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()
    except KeyboardInterrupt:
        cli_console.print("\n[yellow]Cancelled.[/yellow] (Ctrl+C)")
        raise SystemExit(130)
    except SystemExit:
        raise
    except Exception as e:
        cli_console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="Specify Claude model.")
@click.option("--book", "-b", default=None, help="Write to existing book (skip creation).")
@click.option("--json-progress", is_flag=True, default=False, help="Output NDJSON progress events to stdout.")
def research(prompt: str, model: str | None, book: str | None, json_progress: bool):
    """Quick market research — single-stage, full stack.

    \b
    Creates a Slima book and writes a market research report.
    Simplest pipeline command — good for testing the full flow.

    \b
    Examples:
      slima-agents research "AI code assistants market 2026"
      slima-agents research --book bk_abc123 "competitor analysis"
      slima-agents research --json-progress "SaaS pricing trends"
    """
    if json_progress:
        cli_console = Console(file=sys.stderr, no_color=True)
    else:
        cli_console = Console()

    emitter = ProgressEmitter(enabled=json_progress)

    try:
        config = Config.load(model_override=model)
    except ConfigError as e:
        cli_console.print(f"[red]Config error:[/red] {e}")
        raise SystemExit(1)

    async def _run():
        from .agents.context import WorldContext
        from .agents.research import MarketResearchAgent

        async with SlimaClient(config.slima_base_url, config.slima_api_token) as slima:
            book_token = book or ""

            if not book_token:
                created = await slima.create_book(
                    title=f"Market Research: {prompt[:50]}",
                    description=prompt[:200],
                )
                book_token = created.token
                emitter.book_created(book_token, created.title, prompt[:200])
                cli_console.print(f"  Book created: [cyan]{book_token}[/cyan]")

            emitter.pipeline_start(prompt=prompt, total_stages=1)
            emitter.stage_start(1, "research", ["MarketResearchAgent"])
            cli_console.print("  [dim]Running MarketResearchAgent...[/dim]")

            agent = MarketResearchAgent(
                context=WorldContext(),
                book_token=book_token,
                model=config.model,
                prompt=prompt,
            )
            result = await agent.run()

            emitter.agent_complete(
                stage=1, agent="MarketResearchAgent",
                duration_s=result.duration_s, timed_out=result.timed_out,
                summary=result.summary, num_turns=result.num_turns,
                cost_usd=result.cost_usd,
            )
            emitter.stage_complete(1, "research", result.duration_s)
            emitter.pipeline_complete(book_token, result.duration_s)

            cli_console.print(f"  [green]Done![/green] Book: [cyan]{book_token}[/cyan]")
            return book_token

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        cli_console.print("\n[yellow]Cancelled.[/yellow] (Ctrl+C)")
        raise SystemExit(130)
    except Exception as e:
        cli_console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@main.command()
def status():
    """檢查 Slima 認證狀態與 Claude CLI 可用性。"""
    console = Console()
    try:
        config = Config.load()
        console.print(f"[green]Slima Token:[/green] ...{config.slima_api_token[-8:]}")
        console.print(f"[green]Slima URL:[/green] {config.slima_base_url}")
        console.print(f"[green]Model:[/green] {config.model}")

        async def _check():
            async with SlimaClient(config.slima_base_url, config.slima_api_token) as slima:
                books = await slima.list_books()
                console.print(f"[green]Slima API:[/green] OK ({len(books)} books)")

        asyncio.run(_check())

    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Connection error:[/red] {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
