# Slima Agents — Claude Code 開發指南

## 快速指令

```bash
uv run pytest                                          # 執行測試（174 tests）
uv run slima-agents status                             # 檢查 API 連線
uv run slima-agents task "列出我所有的書"               # 通用可配置 Agent
uv run slima-agents task -b bk_xxx -t write "建立角色"  # 指定書籍 + 寫入工具
uv run slima-agents task --plan-first "寫短篇故事"      # 先規劃再執行
uv run slima-agents task-pipeline < stages.json        # 前端可配置多階段管線（stdin JSON）
uv run slima-agents task --model claude-opus-4-6 "需求" # 指定模型
uv run slima-agents -v task "需求描述"                  # 除錯日誌
```

## 專案結構

```
src/slima_agents/
├── cli.py                    # Click CLI，入口點 = slima_agents.cli:main
├── config.py                 # Config.load()：env vars → ~/.slima/credentials.json
├── templates.py              # LANGUAGE_RULE 共用常數
├── lang.py                   # 共用語言工具：detect_language, format_structure_tree, flatten_paths
├── progress.py               # ProgressEmitter：NDJSON 進度事件串流
├── tracker.py                # PipelineTracker：管線進度持久化到 agent-log/progress.md
├── slima/
│   ├── client.py             # SlimaClient：httpx async，base_url = https://api.slima.ai
│   └── types.py              # Book, Commit, FileSnapshot, McpFile* Pydantic models
└── agents/
    ├── claude_runner.py      # ClaudeRunner.run()：claude -p --output-format stream-json，即時完成偵測，MAX_THINKING_TOKENS=0
    ├── base.py               # BaseAgent(ABC)：system_prompt + initial_message → ClaudeRunner → AgentResult
    ├── context.py            # WorldContext + DynamicContext：共享狀態，asyncio.Lock
    ├── tools.py              # SLIMA_MCP_TOOLS / SLIMA_MCP_READ_TOOLS 字串列表
    ├── task.py               # TaskAgent：通用可配置 Agent，行為由參數決定
    ├── task_models.py        # TaskPlan, TaskStageDefinition（前端 JSON 對應）
    └── task_orchestrator.py  # TaskOrchestrator：前端可配置多階段 TaskAgent 管線

docs/
├── worldbuild-pipeline.md   # Worldbuild 完整工作流 + prompt 模板文件
└── mystery-pipeline.md      # Mystery 完整工作流 + prompt 模板文件
```

## 架構關鍵概念

### Agent 執行流程

```
BaseAgent.run()
  → self.initial_message()     # 使用者 prompt（包含 book_token）
  → self.system_prompt()       # LANGUAGE_RULE + *_INSTRUCTIONS + Context
  → self.allowed_tools()       # SLIMA_MCP_TOOLS（字串列表），[] = 不限制
  → ClaudeRunner.run(on_event=self.on_event)  # claude -p subprocess + 串流 callback
  → AgentResult(summary, full_output)
```

每個 Agent 是一次 `claude -p` 呼叫。Claude CLI 自己處理 tool-use loop（最多 50 回合，受 `--max-turns` 限制）。
ClaudeRunner 使用 `--output-format stream-json --verbose` 即時讀取事件流，收到 `{"type":"result"}` 立即返回，無需等待 timeout。

### Agent 清單

#### 通用 Agent（1 個）

| Agent | 檔案 | MCP | 說明 |
|-------|------|-----|------|
| `TaskAgent` | `agents/task.py` | 可配置（write/read/all/none + web） | 通用可配置 Agent，行為由參數決定 |

#### Orchestrator（1 個，非 BaseAgent 子類別）

| Class | 檔案 | 管線 | 說明 |
|-------|------|------|------|
| `TaskOrchestrator` | `agents/task_orchestrator.py` | Task Pipeline | 前端 JSON 定義 stages → 依序/平行 TaskAgent |

#### MCP 工具集（`agents/tools.py`）

| 工具集 | 包含工具 | 使用者 |
|--------|---------|--------|
| `SLIMA_MCP_TOOLS` | create_file, write_file, read_file, edit_file, get_book_structure, search_content | TaskAgent(write) |
| `SLIMA_MCP_READ_TOOLS` | read_file, get_book_structure, search_content | TaskAgent(read) |
| `SLIMA_MCP_ALL_READ_TOOLS` | list_books, get_book, get_book_structure, get_writing_stats, get_chapter, read_file, search_content | TaskAgent(read, extended) |
| `SLIMA_MCP_ALL_TOOLS` | 全部 Slima MCP 操作 | TaskAgent(all) |
| `WEB_TOOLS` | WebSearch, WebFetch | 所有 tool_set |

### 共用基礎設施

#### templates.py — 共用 Prompt 常數

- `LANGUAGE_RULE` → 嵌入所有 agent 的 system prompt，強制語言一致性

#### lang.py — 語言偵測與結構工具

- `detect_language(text)` → `'ja'` | `'ko'` | `'zh'` | `'en'`
- `format_structure_tree(nodes)` → 樹狀圖字串
- `flatten_paths(nodes)` → 所有檔案路徑列表

#### tracker.py — PipelineTracker

- 在書籍內 `agent-log/progress.md` 持久化管線進度
- `define_stages()` → 定義階段列表
- `stage_start/complete/failed()` → 更新階段狀態
- `load_from_book()` → 從書籍讀取恢復（解析 Markdown 表格）
- `last_completed_stage()` / `next_stage()` → 恢復模式邏輯
- 使用 SlimaClient REST API（不是 MCP），由 orchestrator Python 呼叫

### DynamicContext（`agents/context.py`）

- 動態 section 名稱版本的 Context（用於 TaskOrchestrator）
- `book_structure` 永遠隱含可用
- 相同介面：`read()`, `write()`, `append()`, `serialize_for_prompt()`, `to_snapshot()`, `from_snapshot()`

### WorldContext（`agents/context.py`）

12 個固定區段：`overview`, `cosmology`, `geography`, `history`, `peoples`, `cultures`, `power_structures`, `characters`, `items_bestiary`, `narrative`, `naming_conventions`, `book_structure`

### 語言偵測

- `lang.detect_language(prompt)` → 回傳 `'ja'`、`'ko'`、`'zh'` 或 `'en'`
  - 日文：偵測到平假名（U+3040-309F）或片假名（U+30A0-30FF）→ `'ja'`
  - 韓文：偵測到 Hangul（U+AC00-D7AF / U+1100-11FF）→ `'ko'`
  - 中文：有 CJK 漢字但無假名/韓文 → `'zh'`
  - 其他 → `'en'`

### ProgressEmitter 事件

Pipeline 生命週期事件：
- `pipeline_start`、`pipeline_complete`、`stage_start`、`stage_complete`
- `agent_start`、`agent_complete`
- `book_created`、`file_created`

串流事件：
- `tool_use`：agent 呼叫 tool（含 agent, tool_name, stage?）
- `text_delta`：agent 產出文字（含 agent, text, stage?）
- `task_result`：task agent 完成（含 session_id, result, num_turns, cost_usd, duration_s）
- `make_agent_callback(agent_name, stage?)` 工廠方法：建立 on_event callback

### ClaudeRunner 實作細節

```
claude -p <prompt> --verbose --output-format stream-json \
  --system-prompt <system> --max-turns 50 \
  [--allowedTools tool1,tool2] [--model claude-opus-4-6]
```

- **stream-json**：即時讀取 NDJSON 事件流（`assistant`、`result` 等），收到 `{"type":"result"}` 立即返回
- **on_event callback**：`_read_stream()` 每解析一個 JSON 事件就呼叫 `on_event(event)`（try/except 保護）。透過 `BaseAgent.on_event` → `ClaudeRunner.run(on_event=...)` 傳遞。Orchestrator 用 `emitter.make_agent_callback()` 建立 callback。
- **MAX_THINKING_TOKENS=0**：環境變數，停用 extended thinking（避免輸出 token 被 thinking 耗盡導致空結果）
- **CLAUDECODE env var 移除**：允許在 Claude Code session 內啟動子 `claude` process
- **--max-turns 50**：限制 agentic 回合數（安全網）
- **重試**：最多 2 次，write agent（有 MCP create/write 工具的）不重試 timeout（避免檔案重複）
- **Timeout fallback**：write agent timeout 時視為部分成功（檔案已透過 MCP 儲存），回傳 `AgentResult(timed_out=True)`

## 關鍵限制

- **claude -p 不能在 Claude Code session 裡執行**：subprocess 會 hang。測試必須在獨立終端機
- **單次 session 限制**：每個 Agent 是一次 `claude -p` 呼叫。如果 timeout 到，不會斷點續傳
- **Context 膨脹**：所有區段序列化後嵌入每個 agent 的 system prompt。隨著前置 agent 產出越多內容，system prompt 越大
- **MCP 工具限制**：Agent 只能用 `--allowedTools` 列表中的 Slima MCP 工具。如需新增，改 `tools.py`

## 已歸檔的管線

Worldbuild 和 Mystery 管線的完整工作流和 prompt 模板已歸檔為文件：
- `docs/worldbuild-pipeline.md` — 12 階段世界觀建構管線
- `docs/mystery-pipeline.md` — 11 階段懸疑推理小說管線

這些文件包含完整的 prompt 模板、品質標準、task-pipeline JSON 範例，可用 `task-pipeline` 重建。

## 測試

```bash
uv run pytest -v                                       # 全部 174 tests
uv run pytest tests/test_base_agent.py -v              # Agent 單元測試
uv run pytest tests/test_lang.py -v                    # 語言偵測 + 結構工具測試
uv run pytest tests/test_tracker.py -v                 # PipelineTracker 測試
uv run pytest tests/test_slima_client.py -v            # API client 測試
uv run pytest tests/test_config.py -v                  # Config 載入 + 優先序測試
uv run pytest tests/test_cli.py -v                     # CLI 指令測試（Click）
uv run pytest tests/test_progress.py -v               # ProgressEmitter 測試
uv run pytest tests/test_task_agent.py -v             # TaskAgent 可配置 Agent 測試
uv run pytest tests/test_task_models.py -v            # TaskPlan / TaskStageDefinition 測試
uv run pytest tests/test_task_orchestrator.py -v      # TaskOrchestrator 整合測試
```

所有 Agent 測試透過 mock `ClaudeRunner` 執行。Orchestrator 測試 mock 所有 Agent + SlimaClient。

## CI/CD

### 自動測試 (`.github/workflows/test.yml`)

- **觸發**：push 到 `main` 或 `features/**`，PR 到 `main`
- **環境**：ubuntu-latest + Python 3.11 + uv
- **執行**：`uv run pytest -v`

### 二進位編譯 (`.github/workflows/build-binary.yml`)

- **觸發**：push `v*` tag（如 `v0.2.0`）
- **平台矩陣**：

| OS | Artifact 名稱 |
|----|--------------|
| ubuntu-22.04 | `slima-agents-linux-x64` |
| windows-latest | `slima-agents-windows-x64.exe` |
| macos-14 | `slima-agents-macos-arm64` |

- **工具**：Nuitka standalone onefile（`--standalone --onefile`）
- **入口**：`entry.py`（使用 absolute import 避免 onefile 解壓後 relative import 失敗）
- **包含**：`--include-package=slima_agents --include-package=rich`
- **排除**：`--nofollow-import-to=pytest --nofollow-import-to=tests`
- **產出**：自動上傳到 GitHub Release（`softprops/action-gh-release@v2`）

### 發布流程

```bash
# 1. 確認測試通過
uv run pytest -v

# 2. 更新版本號（pyproject.toml）
# version = "0.2.0"

# 3. commit + tag + push
git add -A && git commit -m "release: v0.2.0"
git tag v0.2.0
git push origin main --tags
# → GitHub Actions 自動編譯 3 平台 → Release
```

### 前端整合

Electron 前端透過 spawn 二進位 + NDJSON 事件流串接：

```
Electron Main → spawn("slima-agents", ["task-pipeline", "--json-progress"], { stdin: plan_json })
             → stdout readline → 解析 NDJSON 事件 → IPC → Vue Renderer
```

前端專案：`slima_vue`（Electron + Vue 3 + Pinia）

關鍵檔案：
- `electron/services/agentService.ts` — binary 管理 + subprocess spawn + NDJSON 解析
- `electron/preload.ts` — IPC bridge（`window.electronAPI.agent.*`）
- `src/stores/agentStore.ts` — Pinia store（session 管理 + 事件處理）
- `src/types/agent.ts` — 型別定義

## 環境

- Python 3.11+
- 依賴：httpx, pydantic, click, rich, python-dotenv（不需要 anthropic SDK）
- 預設模型：`claude-opus-4-6`（可用 `--model` 或 `SLIMA_AGENTS_MODEL` env var 覆蓋）
- Slima API base URL：`https://api.slima.ai`
- Claude CLI 必須已安裝且登入（需支援 `--output-format stream-json`）
- Slima 認證：`~/.slima/credentials.json`（slima-mcp auth）或 `SLIMA_API_TOKEN` env var
