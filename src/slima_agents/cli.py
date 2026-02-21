"""CLI 入口點：使用 Click + Rich。"""

from __future__ import annotations

import asyncio
import logging
import sys

import click
from rich.console import Console

from .config import Config, ConfigError
from .slima.client import SlimaClient
from .worldbuild.orchestrator import OrchestratorAgent

console = Console()


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
def worldbuild(prompt: str, model: str | None):
    """從提示詞建構完整的世界觀聖經（World Bible）。

    \b
    使用範例：
      slima-agents worldbuild "英雄聯盟世界觀"
      slima-agents worldbuild "1980年代的美國" --model claude-opus-4-6
      slima-agents worldbuild "DnD 被遺忘的國度" -v
    """
    try:
        config = Config.load(model_override=model)
    except ConfigError as e:
        console.print(f"[red]設定錯誤：[/red] {e}")
        raise SystemExit(1)

    async def _run():
        async with SlimaClient(config.slima_base_url, config.slima_api_token) as slima:
            orch = OrchestratorAgent(
                slima_client=slima,
                model=config.model,
            )
            return await orch.run(prompt)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消。[/yellow] (Ctrl+C)")
        raise SystemExit(130)


@main.command()
def status():
    """檢查 Slima 認證狀態與 Claude CLI 可用性。"""
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
