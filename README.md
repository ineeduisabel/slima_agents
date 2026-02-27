# Slima Agents

AI 驅動的寫作系統。支援三種管線：**世界觀建構**、**懸疑推理小說**、**通用 Plan-Driven 寫作**（任何類型）。所有產出寫入 [Slima](https://slima.app) 書籍。

## 管線總覽

| 管線 | 指令 | 說明 | Agent 數量 |
|------|------|------|-----------|
| **Worldbuild** | `worldbuild` | 世界觀百科全書（80-150+ 檔案） | 12 個固定 Agent |
| **Mystery** | `mystery` | 懸疑推理小說（12 章 + 設定文件） | 11 個固定 Agent |
| **Write** (通用) | `write` | AI 先規劃再寫作，任何類型 | 1 Planner + N WriterAgent |
| **Plan** | `plan` | 只產出 pipeline plan JSON（不執行） | 1 Planner |
| **Plan-Loop** | `plan-loop` | 互動式 plan 修訂迴圈 | 1 Planner（多輪） |

## 快速開始

```bash
# 安裝依賴
uv sync

# 檢查連線狀態
uv run slima-agents status

# 世界觀建構
uv run slima-agents worldbuild "台灣鬼怪故事 台灣版的百鬼夜行"

# 懸疑推理小說
uv run slima-agents mystery "維多利亞莊園的密室殺人事件"

# 通用寫作（AI 自動規劃 pipeline）
uv run slima-agents write "寫一部校園推理小說"

# 只產出規劃（不執行）
uv run slima-agents plan "寫羅曼史" > plan.json

# 互動式規劃修訂
uv run slima-agents plan-loop "寫密室推理"
```

## CLI 指令

### `worldbuild` — 世界觀建構

```bash
uv run slima-agents worldbuild "需求描述"
uv run slima-agents worldbuild "英雄聯盟世界觀" --model claude-opus-4-6
uv run slima-agents worldbuild --json-progress "海賊王世界觀"  # NDJSON 進度輸出
uv run slima-agents -v worldbuild "DnD 被遺忘的國度"            # 除錯日誌
```

### `mystery` — 懸疑推理小說

```bash
uv run slima-agents mystery "維多利亞莊園的密室殺人事件"
uv run slima-agents mystery --book bk_abc123 "繼續寫作"          # 恢復模式
uv run slima-agents mystery "連環殺手在台北" --model claude-opus-4-6
```

### `write` — 通用 Plan-Driven 寫作

```bash
uv run slima-agents write "寫密室推理"                           # AI 自動規劃 + 執行
uv run slima-agents write --book bk_abc123 "繼續寫作"            # 恢復模式
uv run slima-agents write --source-book bk_abc123 "依照這本書重寫" # 讀既有書來規劃
uv run slima-agents write --plan plan.json "執行自訂計畫"         # 用自訂 plan
```

### `plan` — 只產出 Plan JSON

```bash
uv run slima-agents plan "寫密室推理"                            # 從零規劃
uv run slima-agents plan --book bk_abc123 "依照這本書重寫"        # 讀既有書規劃
```

### `plan-loop` — 互動式 Plan 修訂

```bash
uv run slima-agents plan-loop "寫密室推理"
# → 顯示 Plan v1 摘要
# → 輸入回饋修改（或 approve 核准）
# → 顯示 Plan v2 ...
# → approve → 輸出最終 plan JSON 到 stdout
```

### `ask` — 快速提問

```bash
uv run slima-agents ask "列出我所有的書"
uv run slima-agents ask --book bk_abc123 "這本書有哪些章節？"
uv run slima-agents ask --book bk_abc123 --writable "幫我建一個 notes.md"
```

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
| **共享狀態** | Agent 之間透過 Context（WorldContext / MysteryContext / DynamicContext）共享知識 |
| **語言匹配** | 自動偵測需求語言（中/英/日/韓），所有產出使用相同語言 |
| **Session Chaining** | Validation R1→R2 透過 `claude --resume` 延續對話，保持完整脈絡 |
| **NDJSON 進度** | `--json-progress` 輸出即時事件到 stdout，供前端監聽 |

### Agent 執行流程

```
BaseAgent.run()
  → self.system_prompt()       # 語言規則 + 專用指令 + Context
  → self.initial_message()     # 使用者 prompt（含 book_token）
  → self.allowed_tools()       # MCP 工具白名單
  → ClaudeRunner.run()         # claude -p subprocess + stream-json
  → AgentResult(summary, full_output, session_id)
```

### Worldbuild 管線

```
使用者 prompt
  │
  ▼
OrchestratorAgent
  │
  ├─ 階段 1  ResearchAgent（純文字，分析需求 + 生成書名）
  ├─ 建立 Slima 書籍
  ├─ 階段 2  CosmologyAgent + GeographyAgent + HistoryAgent  [平行]
  ├─ 階段 3  PeoplesAgent + CulturesAgent  [平行]
  ├─ 階段 4  PowerStructuresAgent
  ├─ 階段 5  CharactersAgent + ItemsAgent + BestiaryAgent  [平行]
  ├─ 階段 6  NarrativeAgent
  ├─ 階段 7  ValidationAgent R1 + R2（session chaining）
  └─ 完成！輸出書籍 URL
```

12 個固定 Agent，平行與依序混合。產出 80-150+ 個 Markdown 檔案的完整世界觀百科全書。

### Mystery 管線

```
使用者 prompt
  │
  ▼
MysteryOrchestratorAgent（全部依序，有因果依賴）
  │
  ├─ 1. PlannerAgent（分析 prompt → 犯罪概念，無 MCP）
  ├─ 2. Book Setup（建立/載入書籍 + 概念總覽）
  ├─ 3. CrimeDesignAgent
  ├─ 4. MysteryCharactersAgent
  ├─ 5. PlotArchitectureAgent
  ├─ 6. SettingAgent
  ├─ 7. Act1WriterAgent（第一幕 ch 1-4）
  ├─ 8. Act2WriterAgent（第二幕 ch 5-8）
  ├─ 9. Act3WriterAgent（第三幕 ch 9-12）
  ├─ 10. ValidationAgent R1 + R2
  └─ 11. PolishAgent + README
```

11 個固定 Agent，全部依序執行。支援 `--book` 恢復模式（從中斷處繼續）。

### 通用 Plan-Driven 管線（`write`）

```
使用者 prompt
  │
  ▼
GenericOrchestrator
  │
  ├─ 1. Planning
  │     GenericPlannerAgent → PipelinePlan JSON
  │     （若有 --source-book，Planner 用 MCP 讀取既有書）
  │
  ├─ 2. Book Setup
  │     create_book() + 存 plan 到 agent-log/pipeline-plan.json
  │
  ├─ 3. Context Init
  │     DynamicContext.from_plan(plan) + 注入 concept_summary
  │
  ├─ 4. Stage Loop
  │     for stage in plan.stages:
  │         WriterAgent(instructions, initial_message, tool_set)
  │         → 寫入書籍 → 更新 context → 注入結構
  │
  ├─ 5. Validation（optional）
  │     WriterAgent[R1] → session chaining → WriterAgent[R2]
  │
  └─ 6. Polish（optional）
        WriterAgent[polish] + README
```

**核心概念**：Claude 先規劃 pipeline（PipelinePlan JSON），再用同一個通用 `WriterAgent` 依序執行各階段。**新增寫作類型 = 零程式碼**。

#### PipelinePlan 資料模型

```json
{
  "title": "書名",
  "description": "描述",
  "genre": "mystery",
  "language": "zh",
  "action_type": "create",
  "source_book": "",
  "concept_summary": "概念摘要...",
  "context_sections": ["concept", "characters", "plot"],
  "stages": [
    {
      "number": 3,
      "name": "characters",
      "display_name": "角色設計",
      "instructions": "設計所有角色...",
      "initial_message": "在 '{book_token}' 建立角色檔案",
      "tool_set": "write",
      "timeout": 3600
    }
  ],
  "validation": {
    "number": 10,
    "r1_instructions": "驗證一致性...",
    "r2_instructions": "確認修復..."
  },
  "polish_stage": { ... },
  "file_paths": { "planning_prefix": "planning" }
}
```

#### Orchestrator 公開 API

```python
# 分步驟 API（供 UI 使用）
plan, session_id = await orch.plan(prompt, source_book="bk_xxx")
plan, session_id = await orch.revise_plan(prompt, feedback, session_id)
book_token = await orch.execute(prompt, plan)

# 一口氣 API（向後相容）
book_token = await orch.run(prompt, resume_book=None, external_plan=None, source_book=None)
```

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
| `plan_ready` | Plan 產出 | `plan_json`, `session_id`, `version` |
| `plan_approved` | Plan 核准 | `version` |
| `error` | 錯誤 | `message`, `stage?`, `agent?` |
| `pipeline_complete` | 管線完成 | `book_token`, `total_duration_s`, `success` |

## 專案結構

```
src/slima_agents/
├── cli.py                        # Click CLI 入口（worldbuild/mystery/write/plan/plan-loop/ask/status）
├── config.py                     # Config.load()：env vars → ~/.slima/credentials.json
├── lang.py                       # 語言偵測（zh/en/ja/ko）+ 結構樹工具
├── tracker.py                    # PipelineTracker：進度持久化到 agent-log/progress.md
├── progress.py                   # ProgressEmitter：NDJSON 事件輸出
├── slima/
│   ├── client.py                 # SlimaClient：httpx async REST client
│   └── types.py                  # Book, Commit, FileSnapshot 等 Pydantic models
├── agents/
│   ├── claude_runner.py          # ClaudeRunner：claude -p + stream-json 即時解析
│   ├── base.py                   # BaseAgent(ABC)：prompt → ClaudeRunner → AgentResult
│   ├── context.py                # WorldContext：12 section 共享狀態
│   ├── ask.py                    # AskAgent：快速提問（輕量版）
│   └── tools.py                  # MCP 工具名稱常數
├── worldbuild/                   # 世界觀建構管線
│   ├── orchestrator.py           # 12 階段管線 + 平行排程
│   ├── research.py               # ResearchAgent（純文字）
│   ├── validator.py              # ValidationAgent（R1+R2）
│   ├── templates.py              # LANGUAGE_RULE + QUALITY_STANDARD + 指令模板
│   └── specialists/              # 10 個專家 Agent
├── mystery/                      # 懸疑推理小說管線
│   ├── orchestrator.py           # 11 階段依序管線 + 恢復模式
│   ├── planner.py                # PlannerAgent（分析犯罪概念）
│   ├── validator.py              # MysteryValidationAgent（R1+R2）
│   ├── context.py                # MysteryContext：10 section 共享狀態
│   ├── templates.py              # MYSTERY_QUALITY_STANDARD + 指令模板
│   └── specialists/              # 8 個專家 Agent
└── pipeline/                     # 通用 Plan-Driven 管線
    ├── models.py                 # PipelinePlan, StageDefinition, ValidationDefinition
    ├── context.py                # DynamicContext：動態 section（由 plan 定義）
    ├── writer_agent.py           # WriterAgent：通用寫作 Agent（取代所有 specialist）
    ├── planner.py                # GenericPlannerAgent：prompt → PipelinePlan JSON
    └── orchestrator.py           # GenericOrchestrator：plan → book → stages → validation

tests/                            # 227 個測試（全 mock，不需 API）
entry.py                          # Nuitka 編譯入口點
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
uv run pytest -v              # 全部 227 tests
uv run pytest tests/test_base_agent.py -v
uv run pytest tests/test_orchestrator.py -v
uv run pytest tests/test_mystery_orchestrator.py -v
uv run pytest tests/test_generic_orchestrator.py -v
uv run pytest tests/test_orchestrator_split.py -v
uv run pytest tests/test_planner_upgrade.py -v
uv run pytest tests/test_progress.py -v
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

### 編譯入口

`entry.py` 使用 absolute import（`from slima_agents.cli import main`），避免 Nuitka onefile 解壓後 relative import 失敗。

## 前端整合（Electron）

前端透過 spawn 二進位 subprocess + 讀取 NDJSON 事件流來串接：

```
Electron Main Process
  │
  ├─ spawn("slima-agents", ["write", "--json-progress", prompt])
  │
  ├─ stdout readline → 解析 NDJSON 事件
  │   ├─ pipeline_start  → 初始化進度 UI
  │   ├─ stage_start     → 更新階段進度
  │   ├─ agent_complete   → 顯示完成摘要
  │   ├─ plan_ready       → 顯示 plan 給使用者審閱
  │   ├─ book_created     → 記錄 book_token
  │   ├─ error            → 顯示錯誤
  │   └─ pipeline_complete → 完成
  │
  └─ IPC → Vue Renderer（Pinia store）
```

## 技術規格

- **Python 3.11+**
- **依賴**：httpx, pydantic, click, rich, python-dotenv
- **不需要** `anthropic` SDK — 透過 Claude CLI 執行
- **預設模型**：`claude-opus-4-6`（可用 `--model` 或 `SLIMA_AGENTS_MODEL` env var 覆蓋）
- **Slima API**：`https://api.slima.ai`
- **MCP 工具**：`mcp__slima__create_file`, `write_file`, `read_file`, `edit_file`, `get_book_structure`, `search_content` 等
