# JSON Progress 結構化輸出 — 對話摘要與實作計畫

> 日期：2026-02-26

## 背景討論

### 問題：如何將 slima-agents 分享給不懂程式的使用者？

**現有專案：**
- `slima_agents`（Python）— 本地端世界觀建構 agent，用 `claude -p` subprocess 執行
- `slima-mcp`（npm/TypeScript）— Slima MCP server，已發布到 npm
- `slima_vue`（Vue + Electron）— Writing Studio 桌面 App，已有完整的打包/自動更新機制

**討論過的方案：**

| 方案 | 說明 | 結論 |
|------|------|------|
| npm 合併 | 把 Python agent 塞進 slima-mcp npm 包 | ❌ 語言不同，依賴 Python + claude CLI |
| 改用 Anthropic SDK (TS) | 全部用 TypeScript 重寫，直接呼叫 API | ❌ API 成本太高（Opus 一次 worldbuild 估 $5-15 vs 訂閱 $20/月吃到飽） |
| Electron UI + 本地 claude CLI | 在 slima_vue 加 Agent 面板，spawn Python subprocess | ✅ 採用此方案 |

### 成本比較（Claude Opus）

| | Claude Pro 訂閱 | Claude API |
|---|---|---|
| 月費 | $20/月 | 用多少付多少 |
| 跑一次 worldbuild | $0（吃訂閱額度） | 估 $5-15+ |
| 跑 10 次 | 還是 $20/月 | $50-150 |

**結論：保持用 `claude -p`（吃訂閱額度），在 Electron App 裡整合。**

### 整合架構

```
slima_vue (Electron App)
├── 現有 Writing Studio（不動）
├── electron/services/agentService.ts    ← 未來新增
│   ├── checkDependencies()              # 檢查 python/uv/claude
│   ├── runAgent(type, prompt, options)   # spawn subprocess
│   └── parseProgress(line)              # 解析 NDJSON 事件
└── src/（Vue 前端）
    ├── components/shared/AgentPanel/    ← 未來新增
    └── stores/agentStore.ts             ← 未來新增
```

### 實作步驟（總共 4 步）

| 步驟 | 說明 | 狀態 |
|------|------|------|
| **1. slima-agents 發布到 PyPI** | `uv publish`，讓使用者可以安裝 | 待做 |
| **2. slima-agents 加結構化輸出** | `--json-progress` flag，輸出 NDJSON | **← 目前在做** |
| **3. Electron 加 agentService** | spawn subprocess + 解析進度 + IPC | 待做 |
| **4. Vue 加 Agent UI** | 角色卡片 + 執行面板 + 環境引導 | 待做 |

---

## 步驟 2 實作計畫：`--json-progress` 結構化輸出

### Event Schema

```jsonl
{"event":"pipeline_start","timestamp":"...","prompt":"...","total_stages":12}
{"event":"stage_start","timestamp":"...","stage":1,"name":"research","agents":["ResearchAgent"]}
{"event":"agent_start","timestamp":"...","stage":1,"agent":"ResearchAgent"}
{"event":"agent_complete","timestamp":"...","stage":1,"agent":"ResearchAgent","duration_s":133.2,"timed_out":false,"summary":"...","num_turns":5,"cost_usd":0.12}
{"event":"stage_complete","timestamp":"...","stage":1,"name":"research","duration_s":133.5}
{"event":"book_created","timestamp":"...","book_token":"bk_abc123","title":"..."}
{"event":"file_created","timestamp":"...","path":"世界觀/總覽/世界觀總覽.md"}
{"event":"error","timestamp":"...","stage":2,"agent":"GeographyAgent","message":"..."}
{"event":"pipeline_complete","timestamp":"...","book_token":"bk_abc123","total_duration_s":1800.0,"success":true}
```

### 實作步驟

#### Step 1: 新增 `src/slima_agents/progress.py`

新建 `ProgressEmitter` class：
- `enabled: bool` — `False` 時所有方法都是 no-op
- `_stream: TextIO` — 預設 `sys.stdout`
- `_emit(event, **data)` — 寫一行 JSON + flush
- 方法：`pipeline_start`, `stage_start`, `stage_complete`, `agent_start`, `agent_complete`, `book_created`, `file_created`, `error`, `pipeline_complete`

#### Step 2: 修改 `ClaudeRunner` 回傳類型

**檔案**：`src/slima_agents/agents/claude_runner.py`

- 新增 `RunOutput` dataclass：`text`, `num_turns`, `cost_usd`, `timed_out`
- `_read_stream` 回傳改為 4-tuple：`(result_text, num_turns, cost_usd, timed_out)`
- `ClaudeRunner.run()` 回傳改為 `RunOutput`（原本回傳 `str`）

#### Step 3: 擴充 `AgentResult` 並修改 `BaseAgent.run()`

**檔案**：`src/slima_agents/agents/base.py`

- `AgentResult.__init__` 新增：`num_turns`, `cost_usd`, `duration_s`
- `BaseAgent.run()` 加入計時 + 解包 `RunOutput`

#### Step 4: 修改 `OrchestratorAgent`

**檔案**：`src/slima_agents/worldbuild/orchestrator.py`

- Constructor 新增 `emitter` 和 `console` 參數
- 全域 `console` → `self.console`
- `_status` class 接受 `console` 參數
- `run()` 各步驟插入 emitter 呼叫（12 個 stage）
- `_run_phase` 加 `stage` 和 `book_token` 參數
- 新增 `_get_all_file_paths` helper（diff book structure 找新增檔案）
- 整體 try/except 包住 `run()`

#### Step 5: CLI 加 `--json-progress` flag

**檔案**：`src/slima_agents/cli.py`

- `--json-progress` 啟用時 Rich Console 轉到 stderr
- 建立 `ProgressEmitter(enabled=json_progress)` 傳入 orchestrator

#### Step 6: 更新測試

- 新增 `tests/test_progress.py`
- 修改 `tests/test_base_agent.py` — mock 回傳 `RunOutput`
- 修改 `tests/test_orchestrator.py` — 新增 emitter 整合測試

### 檔案變更清單

| 檔案 | 操作 |
|------|------|
| `src/slima_agents/progress.py` | **新增** |
| `src/slima_agents/agents/claude_runner.py` | 修改 |
| `src/slima_agents/agents/base.py` | 修改 |
| `src/slima_agents/worldbuild/orchestrator.py` | 修改 |
| `src/slima_agents/cli.py` | 修改 |
| `tests/test_progress.py` | **新增** |
| `tests/test_base_agent.py` | 修改 |
| `tests/test_orchestrator.py` | 修改 |

### Stage 編號對照表

| Stage | 名稱 | 動作 |
|-------|------|------|
| 1 | research | ResearchAgent |
| 2 | book_creation | create_book |
| 3 | overview | create overview file |
| 4 | foundation | Cosmology + Geography + History (parallel) |
| 5 | culture | Peoples + Cultures (parallel) |
| 6 | power | PowerStructures |
| 7 | detail | Characters + Items + Bestiary (parallel) |
| 8 | narrative | Narrative |
| 9 | glossary | create glossary file |
| 10 | validation_r1 | ValidationAgent R1 |
| 11 | validation_r2 | ValidationAgent R2 |
| 12 | readme | create README |

### 驗證方式

```bash
# 所有現有測試通過（向後相容）
uv run pytest -v

# 正常模式不變
uv run slima-agents worldbuild "test"

# JSON 模式輸出 NDJSON
uv run slima-agents worldbuild --json-progress "test" 2>/dev/null | head -5

# Rich 輸出轉到 stderr
uv run slima-agents worldbuild --json-progress "test" 1>/dev/null
```
