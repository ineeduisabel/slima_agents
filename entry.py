"""Nuitka 編譯入口點 — 使用 absolute import 避免 onefile 解壓後 relative import 失敗。"""

from slima_agents.cli import main

if __name__ == "__main__":
    main()
