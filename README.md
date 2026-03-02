# Slima Agents

AI 驅動的寫作系統。透過可配置的 TaskAgent 管線，將自然語言需求轉換為結構化的書籍內容。所有產出寫入 [Slima](https://slima.app) 書籍。

## 指令總覽

| 指令 | 說明 |
|------|------|
| `task` | 通用可配置 Agent — 透過參數決定行為 |
| `plan-build` | 用自然語言產生驗證過的 TaskPlan JSON |
| `task-pipeline` | 前端可配置多階段 TaskAgent 管線（stdin JSON） |
| `status` | 檢查 Slima 認證狀態與 Claude CLI 可用性 |

## 快速開始

```bash
# 安裝依賴
uv sync

# 檢查連線狀態
uv run slima-agents status

# 通用 Agent（讀取模式）
uv run slima-agents task "列出我所有的書"

# 指定書籍 + 寫入工具
uv run slima-agents task --book bk_abc123 --tool-set write "建立角色檔案"

# 先規劃再執行
uv run slima-agents task --plan-first "寫短篇故事"

# 用自然語言產生 pipeline plan
uv run slima-agents plan-build "建構一個奇幻世界觀"

# 修改既有 plan
echo '{"stages":[...]}' | slima-agents plan-build "加一個角色設計階段"

# 執行多階段管線
uv run slima-agents task-pipeline < stages.json
```

## CLI 指令

### `task` — 通用可配置 Agent

```bash
uv run slima-agents task "列出我所有的書"
uv run slima-agents task --book bk_abc123 --tool-set write "建立角色檔案"
uv run slima-agents task --plan-first "寫一個短篇故事"
uv run slima-agents task --system-prompt "你是一個海盜" "說你好"
uv run slima-agents task --json "你好"                     # JSON 輸出（含 session_id）
uv run slima-agents task --resume sess_abc123 "繼續上次的話題"
uv run slima-agents task --model claude-opus-4-6 "需求"
uv run slima-agents -v task "需求描述"                      # 除錯日誌
```

**選項：**
- `--book, -b` — 目標書籍 token
- `--tool-set, -t` — 工具集：`write`（讀寫）、`read`（唯讀）、`all`（全部）、`none`（無 MCP）
- `--system-prompt` — 自訂 system prompt
- `--plan-first` — 啟用規劃模式
- `--resume, -r` — Resume 之前的 session ID
- `--json` — 輸出 JSON（含 session_id）
- `--json-progress` — 輸出 NDJSON 串流事件
- `--timeout` — 超時秒數（預設 3600）
- `--model, -m` — 指定 Claude 模型

### `plan-build` — 產生 TaskPlan JSON

用自然語言描述需求，產出驗證過的 TaskPlan JSON。可搭配 `task-pipeline` 使用。

```bash
# 從零產生 plan
uv run slima-agents plan-build "建構一個奇幻世界觀"

# 修改既有 plan（透過 stdin 傳入）
echo '{"stages":[...]}' | slima-agents plan-build "加一個角色設計階段"

# 串流模式（前端用）
uv run slima-agents plan-build --json-progress "寫一個推理小說"
```

**選項：**
- `--model, -m` — 指定 Claude 模型
- `--json-progress` — 輸出 NDJSON 串流事件（含 `plan_build_result` 事件）
- `--timeout` — 超時秒數（預設 300）

**輸出：** 永遠只輸出驗證過的 TaskPlan JSON（stdout），錯誤訊息輸出到 stderr。

### `task-pipeline` — 多階段管線

```bash
# 從 stdin 讀取 TaskPlan JSON
uv run slima-agents task-pipeline < stages.json

# 串流模式
uv run slima-agents task-pipeline --json-progress < stages.json
```

**TaskPlan JSON 格式：**

```json
{
  "title": "奇幻世界觀",
  "stages": [
    {
      "number": 1,
      "name": "research",
      "display_name": "研究設定",
      "prompt": "研究並分析奇幻世界觀的核心元素...",
      "tool_set": "read",
      "context_section": "research_result"
    },
    {
      "number": 2,
      "name": "worldbuild",
      "display_name": "建構世界觀",
      "prompt": "根據研究結果，建立世界觀檔案...",
      "tool_set": "write",
      "plan_first": true,
      "timeout": 3600
    }
  ]
}
```

**Stage 欄位：**
- `number` — 執行順序（相同 number 的 stage 平行執行）
- `name` — 機器識別名（snake_case）
- `display_name` — 人類可讀名稱（選填）
- `prompt` — 給 TaskAgent 的指令
- `system_prompt` — 自訂 system prompt（選填）
- `tool_set` — `write` / `read` / `all` / `none`（預設 `read`）
- `plan_first` — 先規劃再執行（選填）
- `context_section` — 將結果存入此 context section，供後續 stage 使用（選填）
- `chain_to_previous` — 使用前一 stage 的 session ID（選填）
- `timeout` — 超時秒數（預設 3600）

### `status` — 檢查連線

```bash
uv run slima-agents status
```

## 架構

### 核心設計

| 概念 | 說明 |
|------|------|
| **Agent 執行** | 每個 Agent 透過 `claude -p` CLI subprocess 執行，Claude CLI 自動處理 tool-use loop |
| **MCP 工具** | Agent 的 Slima 操作由 Claude CLI 的 MCP 整合執行（`mcp__slima__*`） |
| **認證** | 不需要 ANTHROPIC_API_KEY — Claude CLI 自帶認證 |
| **共享狀態** | Agent 之間透過 Context（WorldContext / DynamicContext）共享知識 |
| **語言匹配** | 自動偵測需求語言（中/英/日/韓），所有產出使用相同語言 |
| **NDJSON 進度** | `--json-progress` 輸出即時事件到 stdout，供前端監聽 |

### Agent 一覽

| 元件 | 檔案 | 說明 |
|------|------|------|
| `TaskAgent` | `agents/task.py` | 通用可配置 Agent，行為由參數決定（tool_set, system_prompt, plan_first 等） |
| `TaskOrchestrator` | `agents/task_orchestrator.py` | 前端 JSON 定義 stages → 依序/平行 TaskAgent |

### Agent 執行流程

```
BaseAgent.run()
  → self.system_prompt()       # 語言規則 + 專用指令 + Context
  → self.initial_message()     # 使用者 prompt（含 book_token）
  → self.allowed_tools()       # MCP 工具白名單
  → ClaudeRunner.run()         # claude -p subprocess + stream-json
  → AgentResult(summary, full_output, session_id)
```

### MCP 工具集

| 工具集 | 包含工具 | 使用時機 |
|--------|---------|---------|
| `SLIMA_MCP_TOOLS` | create_file, write_file, read_file, edit_file, get_book_structure, search_content | `tool_set="write"` |
| `SLIMA_MCP_READ_TOOLS` | read_file, get_book_structure, search_content | `tool_set="read"` |
| `SLIMA_MCP_ALL_READ_TOOLS` | list_books, get_book, get_book_structure, get_writing_stats, get_chapter, read_file, search_content | `tool_set="read"`（extended） |
| `SLIMA_MCP_ALL_TOOLS` | 全部 Slima MCP 操作 | `tool_set="all"` |
| `WEB_TOOLS` | WebSearch, WebFetch | 所有 tool_set |

## NDJSON 進度事件

使用 `--json-progress` 時，stdout 輸出 NDJSON 格式的即時事件：

| 事件 | 說明 | 欄位 |
|------|------|------|
| `pipeline_start` | 管線開始 | `prompt`, `total_stages` |
| `stage_start` | 階段開始 | `stage`, `name`, `agents[]` |
| `agent_start` | Agent 開始 | `stage`, `agent` |
| `agent_complete` | Agent 完成 | `stage`, `agent`, `duration_s`, `summary`, `num_turns`, `cost_usd` |
| `stage_complete` | 階段完成 | `stage`, `name`, `duration_s` |
| `book_created` | 書籍建立 | `book_token`, `title`, `description` |
| `file_created` | 檔案建立 | `path` |
| `tool_use` | Agent 呼叫工具 | `agent`, `tool_name`, `stage?` |
| `text_delta` | Agent 產出文字 | `agent`, `text`, `stage?` |
| `task_result` | task 完成 | `session_id`, `result`, `num_turns`, `cost_usd`, `duration_s` |
| `plan_build_result` | plan-build 完成 | `plan_json`, `session_id`, `num_turns`, `cost_usd`, `duration_s` |
| `error` | 錯誤 | `message`, `stage?`, `agent?` |
| `pipeline_complete` | 管線完成 | `book_token`, `total_duration_s`, `success` |

## 前端整合（Electron）

前端透過 spawn 二進位 subprocess + 讀取 NDJSON 事件流來串接。

### plan-build → task-pipeline 工作流

```
1. 使用者輸入自然語言需求
   ↓
2. Electron spawn plan-build
   spawn("slima-agents", ["plan-build", "--json-progress", prompt])
   → NDJSON events (streaming)
   → plan_build_result event → 取得 validated TaskPlan JSON
   ↓
3. （可選）使用者在 UI 上編輯/確認 plan
   ↓
4. Electron spawn task-pipeline
   spawn("slima-agents", ["task-pipeline", "--json-progress"], { stdin: plan_json })
   → NDJSON events (streaming) → pipeline_start → stage_start → ... → pipeline_complete
```

### plan-build 串接

```typescript
// 方式 A：串流模式（推薦）
const proc = spawn("slima-agents", ["plan-build", "--json-progress", prompt]);
// 如果要修改既有 plan，透過 stdin 傳入
proc.stdin.write(existingPlanJson);
proc.stdin.end();
// stdout 讀取 NDJSON
proc.stdout.on("data", (chunk) => {
  // 解析 NDJSON → 找 plan_build_result 事件
  // event.plan_json 就是驗證過的 TaskPlan JSON
});
```

```typescript
// 方式 B：簡單模式（stdout 直接輸出 JSON）
const proc = spawn("slima-agents", ["plan-build", prompt]);
let output = "";
proc.stdout.on("data", (chunk) => { output += chunk; });
proc.on("close", (code) => {
  if (code === 0) {
    const plan = JSON.parse(output);  // validated TaskPlan
  }
});
```

### task-pipeline 串接

```typescript
const proc = spawn("slima-agents", ["task-pipeline", "--json-progress"], {
  stdio: ["pipe", "pipe", "pipe"],
});
proc.stdin.write(planJson);
proc.stdin.end();

proc.stdout.on("data", (chunk) => {
  // readline → parse NDJSON events → IPC → Vue Renderer
});
```

### 前端專案

前端專案：`slima_vue`（Electron + Vue 3 + Pinia）

關鍵檔案：
- `electron/services/agentService.ts` — binary 管理 + subprocess spawn + NDJSON 解析
- `electron/preload.ts` — IPC bridge（`window.electronAPI.agent.*`）
- `src/stores/agentStore.ts` — Pinia store（session 管理 + 事件處理）
- `src/types/agent.ts` — 型別定義

## 專案結構

```
src/slima_agents/
├── cli.py                    # Click CLI 入口（task / plan-build / task-pipeline / status）
├── config.py                 # Config.load()：env vars → ~/.slima/credentials.json
├── templates.py              # LANGUAGE_RULE 共用常數
├── lang.py                   # 共用語言工具：detect_language, format_structure_tree, flatten_paths
├── progress.py               # ProgressEmitter：NDJSON 進度事件串流
├── tracker.py                # PipelineTracker：管線進度持久化到 agent-log/progress.md
├── slima/
│   ├── client.py             # SlimaClient：httpx async REST client
│   └── types.py              # Book, Commit, FileSnapshot 等 Pydantic models
└── agents/
    ├── claude_runner.py      # ClaudeRunner：claude -p + stream-json 即時解析
    ├── base.py               # BaseAgent(ABC)：prompt → ClaudeRunner → AgentResult
    ├── context.py            # WorldContext + DynamicContext：共享狀態
    ├── tools.py              # MCP 工具名稱常數
    ├── task.py               # TaskAgent：通用可配置 Agent
    ├── task_models.py        # TaskPlan, TaskStageDefinition（前端 JSON 對應）
    ├── task_orchestrator.py  # TaskOrchestrator：前端可配置多階段 TaskAgent 管線
    └── plan_builder.py       # extract_json_object + PLAN_BUILD_SYSTEM_PROMPT

tests/                        # 全 mock，不需 API
docs/
├── worldbuild-pipeline.md   # Worldbuild 完整工作流 + prompt 模板（已歸檔）
├── mystery-pipeline.md      # Mystery 完整工作流 + prompt 模板（已歸檔）
└── task-pipeline-guide.md   # task-pipeline 使用指南
entry.py                      # Nuitka 編譯入口點
```

## 安裝

```bash
# 用 uv 安裝依賴
uv sync
```

### 環境設定

1. **Claude CLI**：確認已安裝並登入
   ```bash
   claude --version
   ```

2. **Slima 認證**（二擇一）：
   - **方法 A（推薦）**：`slima-mcp auth`，系統讀取 `~/.slima/credentials.json`
   - **方法 B**：`export SLIMA_API_TOKEN=你的token`

3. **確認連線**：
   ```bash
   uv run slima-agents status
   ```

## 測試

```bash
uv run pytest -v                                       # 全部測試
uv run pytest tests/test_base_agent.py -v              # Agent 單元測試
uv run pytest tests/test_lang.py -v                    # 語言偵測 + 結構工具測試
uv run pytest tests/test_tracker.py -v                 # PipelineTracker 測試
uv run pytest tests/test_slima_client.py -v            # API client 測試
uv run pytest tests/test_config.py -v                  # Config 載入 + 優先序測試
uv run pytest tests/test_cli.py -v                     # CLI 指令測試（Click）
uv run pytest tests/test_progress.py -v                # ProgressEmitter 測試
uv run pytest tests/test_task_agent.py -v              # TaskAgent 可配置 Agent 測試
uv run pytest tests/test_task_models.py -v             # TaskPlan / TaskStageDefinition 測試
uv run pytest tests/test_task_orchestrator.py -v       # TaskOrchestrator 整合測試
uv run pytest tests/test_plan_builder.py -v            # JSON 提取 + plan-build prompt 測試
```

所有 Agent 測試透過 mock `ClaudeRunner` 執行，不需要 API key。

## CI/CD

### 自動測試 (`test.yml`)

- **觸發**：push 到 `main` 或 `features/**` 分支，或 PR 到 `main`
- **環境**：Ubuntu + Python 3.11 + uv
- **執行**：`uv run pytest -v`

### 二進位編譯 (`build-binary.yml`)

- **觸發**：push `v*` tag（如 `v0.2.0`）
- **平台**：Linux x64 / Windows x64 / macOS ARM64
- **工具**：[Nuitka](https://nuitka.net/) standalone onefile 編譯
- **產出**：單一可執行檔，自動上傳到 GitHub Release

```bash
# 發布新版本
git tag v0.2.0
git push origin v0.2.0
# → GitHub Actions 自動編譯三個平台 → 上傳到 Release
```

## 技術規格

- **Python 3.11+**
- **依賴**：httpx, pydantic, click, rich, python-dotenv
- **不需要** `anthropic` SDK — 透過 Claude CLI 執行
- **預設模型**：`claude-opus-4-6`（可用 `--model` 或 `SLIMA_AGENTS_MODEL` env var 覆蓋）
- **Slima API**：`https://api.slima.ai`
- **MCP 工具**：`mcp__slima__create_file`, `write_file`, `read_file`, `edit_file`, `get_book_structure`, `search_content` 等
