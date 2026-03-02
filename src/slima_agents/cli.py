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
    "--readonly", is_flag=True, default=False,
    help="限制為唯讀模式（預設可讀寫）。",
)
@click.option("--resume", "-r", default=None, help="Resume 之前的 session ID（多輪對話）。")
@click.option("--system-prompt", default=None, help="自訂 system prompt。")
@click.option("--json", "json_output", is_flag=True, default=False, help="輸出 JSON（含 session_id）。")
@click.option("--json-progress", "json_progress", is_flag=True, default=False, help="輸出 NDJSON 串流事件到 stdout。")
def ask(
    prompt: str,
    model: str | None,
    book: str | None,
    readonly: bool,
    resume: str | None,
    system_prompt: str | None,
    json_output: bool,
    json_progress: bool,
):
    """快速提問或操作 Slima 書籍（輕量版，不跑完整管線）。

    \b
    使用範例：
      slima-agents ask "列出我所有的書"
      slima-agents ask --book bk_abc123 "這本書有哪些章節？"
      slima-agents ask --book bk_abc123 "幫我建一個 notes.md"
      slima-agents ask --resume sess_abc123 "繼續上次的話題"
      slima-agents ask --system-prompt "你是一個海盜" "說你好"
      slima-agents ask --json "你好"
      slima-agents ask --json-progress "search AI news"
    """
    use_ndjson = json_progress or json_output
    if use_ndjson:
        console = Console(file=sys.stderr, no_color=True)
    else:
        console = Console()
    resolved_model = model or os.getenv("SLIMA_AGENTS_MODEL", DEFAULT_MODEL)
    emitter = ProgressEmitter(enabled=json_progress)

    async def _run():
        from .agents.ask import AskAgent
        from .agents.context import WorldContext

        on_event = emitter.make_agent_callback("AskAgent") if json_progress else None
        agent = AskAgent(
            context=WorldContext(),
            book_token=book or "",
            model=resolved_model,
            prompt=prompt,
            writable=not readonly,
            resume_session=resume or "",
            custom_system_prompt=system_prompt,
            on_event=on_event,
        )
        return await agent.run()

    try:
        result = asyncio.run(_run())

        if json_progress:
            # NDJSON mode: emit ask_result event
            emitter.ask_result(
                session_id=result.session_id,
                result=result.full_output,
                num_turns=result.num_turns,
                cost_usd=result.cost_usd,
                duration_s=result.duration_s,
            )
        elif json_output:
            # Legacy JSON mode: single JSON blob for backward compat
            import json as json_mod
            payload = json_mod.dumps({
                "session_id": result.session_id,
                "result": result.full_output,
                "num_turns": result.num_turns,
                "cost_usd": result.cost_usd,
                "duration_s": round(result.duration_s, 2),
            }, ensure_ascii=False)
            sys.stdout.buffer.write(payload.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.buffer.flush()
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
@click.option("--book", "-b", default=None, help="Target book token（如 bk_abc123）。")
@click.option(
    "--tool-set", "-t", default="read",
    type=click.Choice(["write", "read", "all", "none"], case_sensitive=False),
    help="工具集（default: read）。",
)
@click.option("--system-prompt", default=None, help="自訂 system prompt。")
@click.option("--plan-first", is_flag=True, default=False, help="啟用規劃模式。")
@click.option("--resume", "-r", default=None, help="Resume 之前的 session ID。")
@click.option("--json", "json_output", is_flag=True, default=False, help="輸出 JSON（含 session_id）。")
@click.option("--json-progress", "json_progress", is_flag=True, default=False, help="輸出 NDJSON 串流事件到 stdout。")
@click.option("--timeout", default=3600, type=int, help="超時秒數（default: 3600）。")
def task(
    prompt: str,
    model: str | None,
    book: str | None,
    tool_set: str,
    system_prompt: str | None,
    plan_first: bool,
    resume: str | None,
    json_output: bool,
    json_progress: bool,
    timeout: int,
):
    """通用可配置 Agent — 透過參數決定行為。

    \b
    使用範例：
      slima-agents task "列出我所有的書"
      slima-agents task --book bk_abc123 --tool-set write "建立角色檔案"
      slima-agents task --plan-first "寫一個短篇故事"
      slima-agents task --system-prompt "你是一個海盜" "說你好"
      slima-agents task --json "你好"
      slima-agents task --resume sess_abc123 "繼續上次的話題"
    """
    use_ndjson = json_progress or json_output
    if use_ndjson:
        console = Console(file=sys.stderr, no_color=True)
    else:
        console = Console()
    resolved_model = model or os.getenv("SLIMA_AGENTS_MODEL", DEFAULT_MODEL)
    emitter = ProgressEmitter(enabled=json_progress)

    async def _run():
        from .agents.context import WorldContext
        from .agents.task import TaskAgent

        on_event = emitter.make_agent_callback("TaskAgent") if json_progress else None
        agent = TaskAgent(
            context=WorldContext(),
            book_token=book or "",
            model=resolved_model,
            timeout=timeout,
            prompt=prompt,
            system_prompt_text=system_prompt or "",
            tool_set=tool_set,
            plan_first=plan_first,
            resume_session=resume or "",
            on_event=on_event,
        )
        return await agent.run()

    try:
        result = asyncio.run(_run())

        if json_progress:
            emitter.ask_result(
                session_id=result.session_id,
                result=result.full_output,
                num_turns=result.num_turns,
                cost_usd=result.cost_usd,
                duration_s=result.duration_s,
            )
        elif json_output:
            import json as json_mod
            payload = json_mod.dumps({
                "session_id": result.session_id,
                "result": result.full_output,
                "num_turns": result.num_turns,
                "cost_usd": result.cost_usd,
                "duration_s": round(result.duration_s, 2),
            }, ensure_ascii=False)
            sys.stdout.buffer.write(payload.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.buffer.flush()
        else:
            sys.stdout.buffer.write(result.full_output.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.buffer.flush()

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise SystemExit(130)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@main.command("task-pipeline")
@click.option("--model", "-m", default=None, help="指定 Claude 模型（如 claude-opus-4-6）。")
@click.option("--json-progress", is_flag=True, default=False, help="輸出 NDJSON 進度事件到 stdout。")
def task_pipeline(model: str | None, json_progress: bool):
    """Front-end configurable multi-stage TaskAgent pipeline.

    \b
    Reads a TaskPlan JSON from stdin.
    Stages with the same number run concurrently (asyncio.gather).
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

    # Load TaskPlan from stdin
    import json as json_mod
    from .agents.task_models import TaskPlan

    try:
        raw = sys.stdin.read()
        if not raw.strip():
            cli_console.print("[red]Error:[/red] No JSON provided via stdin.")
            raise SystemExit(1)
        data = json_mod.loads(raw)
        task_plan = TaskPlan.model_validate(data)
    except SystemExit:
        raise
    except Exception as e:
        cli_console.print(f"[red]Plan error:[/red] {e}")
        raise SystemExit(1)

    async def _run():
        from .agents.task_orchestrator import TaskOrchestrator
        async with SlimaClient(config.slima_base_url, config.slima_api_token) as slima:
            orch = TaskOrchestrator(
                slima_client=slima,
                model=config.model,
                emitter=emitter,
                console=cli_console,
            )
            return await orch.run(task_plan)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        cli_console.print("\n[yellow]Cancelled.[/yellow] (Ctrl+C)")
        raise SystemExit(130)
    except SystemExit:
        raise
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
