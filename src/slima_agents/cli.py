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
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
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
        cli_console.print(f"[red]設定錯誤：[/red] {e}")
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
        cli_console.print("\n[yellow]已取消。[/yellow] (Ctrl+C)")
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
        cli_console.print(f"[red]設定錯誤：[/red] {e}")
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
        cli_console.print("\n[yellow]已取消。[/yellow] (Ctrl+C)")
        raise SystemExit(130)


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="指定 Claude 模型。")
@click.option("--book", "-b", default=None, help="指定書籍 token（如 bk_abc123）。")
@click.option(
    "--writable", "-w", is_flag=True, default=False,
    help="允許建立/編輯檔案（預設唯讀）。",
)
def ask(prompt: str, model: str | None, book: str | None, writable: bool):
    """快速提問或操作 Slima 書籍（輕量版，不跑完整管線）。

    \b
    使用範例：
      slima-agents ask "列出我所有的書"
      slima-agents ask --book bk_abc123 "這本書有哪些章節？"
      slima-agents ask --book bk_abc123 --writable "幫我建一個 notes.md"
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
        )
        return await agent.run()

    try:
        result = asyncio.run(_run())
        # Write UTF-8 directly to stdout buffer to avoid:
        # 1. Rich _unicode_data crash in Nuitka onefile builds
        # 2. Windows cp950 encoding errors with Chinese text
        sys.stdout.buffer.write(result.full_output.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消。[/yellow]")
        raise SystemExit(130)
    except Exception as e:
        console.print(f"[red]錯誤：[/red] {e}")
        raise SystemExit(1)


@main.command()
def status():
    """檢查 Slima 認證狀態與 Claude CLI 可用性。"""
    console = Console()
    try:
        config = Config.load()
        console.print(f"[green]Slima Token：[/green] ...{config.slima_api_token[-8:]}")
        console.print(f"[green]Slima URL：[/green] {config.slima_base_url}")
        console.print(f"[green]模型：[/green] {config.model}")

        async def _check():
            async with SlimaClient(config.slima_base_url, config.slima_api_token) as slima:
                books = await slima.list_books()
                console.print(f"[green]Slima API：[/green] 連線正常（{len(books)} 本書）")

        asyncio.run(_check())

    except ConfigError as e:
        console.print(f"[red]設定錯誤：[/red] {e}")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]連線錯誤：[/red] {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
