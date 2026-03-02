# Slima Agents — Claude Code 開發指南

## 快速指令

```bash
uv run pytest                                          # 執行測試（369 tests）
uv run slima-agents status                             # 檢查 API 連線
uv run slima-agents worldbuild "需求描述"               # 建構世界觀
uv run slima-agents mystery "密室殺人事件"              # 建構懸疑推理小說
uv run slima-agents mystery --book bk_xxx "繼續寫作"    # 恢復模式
uv run slima-agents task "列出我所有的書"               # 通用可配置 Agent
uv run slima-agents task -b bk_xxx -t write "建立角色"  # 指定書籍 + 寫入工具
uv run slima-agents task --plan-first "寫短篇故事"      # 先規劃再執行
uv run slima-agents task-pipeline --plan stages.json   # 前端可配置多階段管線
uv run slima-agents task-pipeline --plan stages.json --json-progress  # NDJSON 串流
uv run slima-agents worldbuild "需求描述" --model claude-opus-4-6  # 指定模型
uv run slima-agents -v worldbuild "需求描述"              # 除錯日誌
```

## 專案結構

```
src/slima_agents/
├── cli.py                    # Click CLI，入口點 = slima_agents.cli:main
├── config.py                 # Config.load()：env vars → ~/.slima/credentials.json
├── lang.py                   # 共用語言工具：detect_language, format_structure_tree, flatten_paths
├── tracker.py                # PipelineTracker：管線進度持久化到 agent-log/progress.md
├── slima/
│   ├── client.py             # SlimaClient：httpx async，base_url = https://api.slima.ai
│   └── types.py              # Book, Commit, FileSnapshot, McpFile* Pydantic models
├── agents/
│   ├── claude_runner.py      # ClaudeRunner.run()：claude -p --output-format stream-json，即時完成偵測，MAX_THINKING_TOKENS=0
│   ├── base.py               # BaseAgent(ABC)：system_prompt + initial_message → ClaudeRunner → AgentResult
│   ├── context.py            # WorldContext + DynamicContext：共享狀態，asyncio.Lock
│   ├── tools.py              # SLIMA_MCP_TOOLS / SLIMA_MCP_READ_TOOLS 字串列表
│   ├── task_models.py        # TaskPlan, TaskStageDefinition（前端 JSON 對應）
│   ├── task_orchestrator.py  # TaskOrchestrator：前端可配置多階段 TaskAgent 管線
│   └── ask.py               # AskAgent：輕量快速提問（timeout=3600, 支援 web search）
├── worldbuild/
│   ├── orchestrator.py       # OrchestratorAgent.run()：12 階段管線 + 階段間結構注入 + PipelineTracker
│   ├── research.py           # ResearchAgent：純文字輸出（無 MCP），解析 ## 區段 + ## Title + ## Description
│   ├── validator.py          # ValidationAgent：讀取全部檔案，產出一致性報告
│   ├── templates.py          # LANGUAGE_RULE + QUALITY_STANDARD + 12 個 *_INSTRUCTIONS
│   └── specialists/          # 10 個專家 Agent（每個都是 BaseAgent 子類別）
│       ├── cosmology.py, geography.py, history.py
│       ├── peoples.py, cultures.py, power_structures.py
│       └── characters.py, items.py, bestiary.py, narrative.py
└── mystery/
    ├── orchestrator.py       # MysteryOrchestratorAgent.run()：11 階段依序管線 + 恢復模式
    ├── planner.py            # PlannerAgent：純文字分析（無 MCP），解析犯罪概念 + 標題
    ├── validator.py          # MysteryValidationAgent：線索鏈 + 角色一致性檢查（R1 + R2）
    ├── context.py            # MysteryContext：10 個 section，asyncio.Lock
    ├── templates.py          # MYSTERY_QUALITY_STANDARD + 11 個 *_INSTRUCTIONS（import LANGUAGE_RULE）
    └── specialists/          # 8 個專家 Agent
        ├── crime_design.py, characters.py, plot_architecture.py, setting.py
        └── act1_writer.py, act2_writer.py, act3_writer.py, polish.py
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

### Agent 完整清單（24 個 Agent + 3 個 Orchestrator）

#### Worldbuild Agent（12 個）

| Agent | 檔案 | MCP | 階段 | 說明 |
|-------|------|-----|------|------|
| `ResearchAgent` | `worldbuild/research.py` | 無 | 1 | 純文字分析需求 + 生成書名 |
| `CosmologyAgent` | `worldbuild/specialists/cosmology.py` | write | 2 (平行) | 宇宙觀 |
| `GeographyAgent` | `worldbuild/specialists/geography.py` | write | 2 (平行) | 地理 |
| `HistoryAgent` | `worldbuild/specialists/history.py` | write | 2 (平行) | 歷史 |
| `PeoplesAgent` | `worldbuild/specialists/peoples.py` | write | 3 (平行) | 種族/民族 |
| `CulturesAgent` | `worldbuild/specialists/cultures.py` | write | 3 (平行) | 文化 |
| `PowerStructuresAgent` | `worldbuild/specialists/power_structures.py` | write | 4 | 權力結構 |
| `CharactersAgent` | `worldbuild/specialists/characters.py` | write | 5 (平行) | 角色（15-25） |
| `ItemsAgent` | `worldbuild/specialists/items.py` | write | 5 (平行) | 物品/神器 |
| `BestiaryAgent` | `worldbuild/specialists/bestiary.py` | write | 5 (平行) | 怪獸圖鑑 |
| `NarrativeAgent` | `worldbuild/specialists/narrative.py` | write | 6 | 敘事/故事線 |
| `ValidationAgent` | `worldbuild/validator.py` | write | 7 | R1+R2 驗證（session chaining） |

#### Mystery Agent（10 個）

| Agent | 檔案 | MCP | 階段 | 說明 |
|-------|------|-----|------|------|
| `PlannerAgent` | `mystery/planner.py` | 無 | 1 | 純文字分析犯罪概念 |
| `CrimeDesignAgent` | `mystery/specialists/crime_design.py` | write | 3 | 犯罪設計 |
| `MysteryCharactersAgent` | `mystery/specialists/characters.py` | write | 4 | 偵探+嫌疑犯+被害者 |
| `PlotArchitectureAgent` | `mystery/specialists/plot_architecture.py` | write | 5 | 章節大綱+線索配置 |
| `SettingAgent` | `mystery/specialists/setting.py` | write | 6 | 場景設定 |
| `Act1WriterAgent` | `mystery/specialists/act1_writer.py` | write | 7 | 第一幕 (ch 1-4) |
| `Act2WriterAgent` | `mystery/specialists/act2_writer.py` | write | 8 | 第二幕 (ch 5-8) |
| `Act3WriterAgent` | `mystery/specialists/act3_writer.py` | write | 9 | 第三幕 (ch 9-12) |
| `MysteryValidationAgent` | `mystery/validator.py` | write | 10 | R1+R2 驗證（session chaining） |
| `PolishAgent` | `mystery/specialists/polish.py` | write | 11 | 索引+README |

#### 通用 Agent（2 個）

| Agent | 檔案 | MCP | 說明 |
|-------|------|-----|------|
| `AskAgent` | `agents/ask.py` | 無限制（可選 write） | 輕量快速提問（timeout=3600, 支援 web search） |
| `TaskAgent` | `agents/task.py` | 可配置（write/read/all/none + web） | 通用可配置 Agent，行為由參數決定 |

#### Orchestrator（3 個，非 BaseAgent 子類別）

| Class | 檔案 | 管線 | 說明 |
|-------|------|------|------|
| `OrchestratorAgent` | `worldbuild/orchestrator.py` | Worldbuild | 12 階段平行+依序排程 |
| `MysteryOrchestratorAgent` | `mystery/orchestrator.py` | Mystery | 11 階段依序 + 恢復模式 |
| `TaskOrchestrator` | `agents/task_orchestrator.py` | Task Pipeline | 前端 JSON 定義 stages → 依序/平行 TaskAgent |

#### MCP 工具集（`agents/tools.py`）

| 工具集 | 包含工具 | 使用者 |
|--------|---------|--------|
| `SLIMA_MCP_TOOLS` | create_file, write_file, read_file, edit_file, get_book_structure, search_content | 所有 specialist |
| `SLIMA_MCP_READ_TOOLS` | read_file, get_book_structure, search_content | TaskAgent(read) |
| `SLIMA_MCP_ALL_READ_TOOLS` | list_books, get_book, get_book_structure, get_writing_stats, get_chapter, read_file, search_content | AskAgent |

### 共用基礎設施

#### lang.py — 語言偵測與結構工具

- `detect_language(text)` → `'ja'` | `'ko'` | `'zh'` | `'en'`
- `format_structure_tree(nodes)` → 樹狀圖字串
- `flatten_paths(nodes)` → 所有檔案路徑列表
- worldbuild 和 mystery 管線共用

#### tracker.py — PipelineTracker

- 在書籍內 `agent-log/progress.md` 持久化管線進度
- `define_stages()` → 定義階段列表
- `stage_start/complete/failed()` → 更新階段狀態
- `load_from_book()` → 從書籍讀取恢復（解析 Markdown 表格）
- `last_completed_stage()` / `next_stage()` → 恢復模式邏輯
- 使用 SlimaClient REST API（不是 MCP），由 orchestrator Python 呼叫

### WorldContext（worldbuild 共享狀態）

12 個區段：`overview`, `cosmology`, `geography`, `history`, `peoples`, `cultures`, `power_structures`, `characters`, `items_bestiary`, `narrative`, `naming_conventions`, `book_structure`

### MysteryContext（mystery 共享狀態）

10 個區段：`concept`, `crime_design`, `characters`, `plot_architecture`, `setting`, `act1_summary`, `act2_summary`, `act3_summary`, `validation_report`, `book_structure`

### Worldbuild 管線階段

| 階段 | Agent | 平行 | Timeout |
|------|-------|------|---------|
| 1 | ResearchAgent | 否 | 3600s |
| 2 | Cosmology + Geography + History | 是 | 3600s |
| 3 | Peoples + Cultures | 是 | 3600s |
| 4 | PowerStructures | 否 | 3600s |
| 5 | Characters + Items + Bestiary | 是 | 3600s |
| 6 | Narrative | 否 | 3600s |
| 7a | ValidationAgent-R1（一致性 + 內容完整度 + 修復） | 否 | 3600s |
| 7b | ValidationAgent-R2（確認修復 + 最終報告） | 否 | 3600s |
| 8 | 建立 README.md | 否 | — |

### Mystery 管線階段（全部依序）

| # | 階段 | Agent | 說明 |
|---|------|-------|------|
| 1 | planning | PlannerAgent | 分析 prompt，產出犯罪概念（無 MCP） |
| 2 | book_setup | — | 建立/載入 Slima 書籍 + 寫入概念總覽 |
| 3 | crime_design | CrimeDesignAgent | 詳細犯罪設計 |
| 4 | characters | MysteryCharactersAgent | 偵探+嫌疑犯+被害者 |
| 5 | plot_architecture | PlotArchitectureAgent | 章節大綱+線索配置 |
| 6 | setting | SettingAgent | 場景設定 |
| 7 | act1_writing | Act1WriterAgent | 第一幕 (ch 1-4) |
| 8 | act2_writing | Act2WriterAgent | 第二幕 (ch 5-8) |
| 9 | act3_writing | Act3WriterAgent | 第三幕 (ch 9-12) |
| 10 | validation | MysteryValidationAgent R1 + R2 | 一致性驗證（兩輪） |
| 11 | polish | PolishAgent + README | 索引+README |

**為何全部依序**：犯罪→角色→情節→場景→Act 1→Act 2→Act 3 有嚴格因果依賴。

**恢復模式**（`--book bk_xxx`）：
- 讀取 `agent-log/progress.md` → `PipelineTracker.load_from_book()`
- 從書籍讀取已有內容重建 `MysteryContext`
- 跳過已完成階段，從中斷處繼續

### DynamicContext（`agents/context.py`）

- 動態 section 名稱版本的 Context（用於 TaskOrchestrator）
- `book_structure` 永遠隱含可用
- 相同介面：`read()`, `write()`, `append()`, `serialize_for_prompt()`, `to_snapshot()`, `from_snapshot()`

### 語言偵測

- `lang.detect_language(prompt)` → 回傳 `'ja'`、`'ko'`、`'zh'` 或 `'en'`
  - 日文：偵測到平假名（U+3040-309F）或片假名（U+30A0-30FF）→ `'ja'`
  - 韓文：偵測到 Hangul（U+AC00-D7AF / U+1100-11FF）→ `'ko'`
  - 中文：有 CJK 漢字但無假名/韓文 → `'zh'`
  - 其他 → `'en'`
- worldbuild 用 `_LANG_PATHS[lang]` → worldview-specific 路徑
- mystery 用 `_MYSTERY_LANG_PATHS[lang]` → mystery-specific 路徑
- `templates.LANGUAGE_RULE` → 嵌入所有 agent 的 system prompt

### Prompt 模板結構

**worldbuild/templates.py**:
```
LANGUAGE_RULE          # 語言規則（嵌入所有 agent，worldbuild + mystery 共用）
QUALITY_STANDARD       # 品質標準 + 參考資料要求
*_INSTRUCTIONS         # 每個 worldbuild specialist 的專用指令
```

**mystery/templates.py**:
```
from ..worldbuild.templates import LANGUAGE_RULE  # 共用語言規則
MYSTERY_QUALITY_STANDARD     # 推理寫作品質標準
PLANNER_INSTRUCTIONS         # 企劃 Agent（純文字，無 MCP）
CRIME_DESIGN_INSTRUCTIONS    # 犯罪設計
CHARACTERS_INSTRUCTIONS      # 角色設計
PLOT_ARCHITECTURE_INSTRUCTIONS # 情節架構
SETTING_INSTRUCTIONS         # 場景設定
ACT1/2/3_INSTRUCTIONS        # 三幕寫作
MYSTERY_VALIDATION/VERIFICATION_INSTRUCTIONS  # 驗證
POLISH_INSTRUCTIONS          # 潤色收尾
```

## 新增 Agent 的步驟（worldbuild）

1. 在 `worldbuild/templates.py` 新增 `NEW_INSTRUCTIONS = LANGUAGE_RULE + """...""" + QUALITY_STANDARD`
2. 在 `worldbuild/specialists/` 新增 `new_agent.py`，繼承 `BaseAgent`
3. 實作 `name`, `system_prompt()`, `initial_message()`
4. 在 `specialists/__init__.py` 新增 export
5. 在 `orchestrator.py` 加入對應階段（注意平行/依序、timeout）
6. 更新 `tests/test_orchestrator.py` mock 列表

## 新增 Agent 的步驟（mystery）

1. 在 `mystery/templates.py` 新增 `NEW_INSTRUCTIONS = LANGUAGE_RULE + """...""" + MYSTERY_QUALITY_STANDARD`
2. 在 `mystery/specialists/` 新增 `new_agent.py`，繼承 `BaseAgent`（context 是 `MysteryContext`）
3. 在 `specialists/__init__.py` 新增 export
4. 在 `mystery/orchestrator.py` 加入對應階段
5. 更新 `tests/test_mystery_orchestrator.py` mock 列表

### ProgressEmitter 事件

Pipeline 生命週期事件：
- `pipeline_start`、`pipeline_complete`、`stage_start`、`stage_complete`
- `agent_start`、`agent_complete`
- `book_created`、`file_created`

串流事件（Phase 1-4 新增）：
- `tool_use`：agent 呼叫 tool（含 agent, tool_name, stage?）
- `text_delta`：agent 產出文字（含 agent, text, stage?）
- `ask_result`：ask agent 完成（含 session_id, result, num_turns, cost_usd, duration_s）
- `make_agent_callback(agent_name, stage?)` 工廠方法：建立 on_event callback

## 修改 Prompt 模板的注意事項

- `LANGUAGE_RULE`（worldbuild/templates.py）嵌入 worldbuild + mystery 所有 agent — 改這裡影響兩邊
- `QUALITY_STANDARD` 附加到所有 worldbuild specialist
- `MYSTERY_QUALITY_STANDARD` 附加到所有 mystery specialist
- 語言偵測邏輯在 `lang.py`，兩個管線共用

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

## 測試

```bash
uv run pytest -v                                       # 全部 369 tests
uv run pytest tests/test_base_agent.py -v              # Agent 單元測試
uv run pytest tests/test_orchestrator.py -v            # Worldbuild orchestrator 整合測試
uv run pytest tests/test_lang.py -v                    # 語言偵測 + 結構工具測試
uv run pytest tests/test_tracker.py -v                 # PipelineTracker 測試
uv run pytest tests/test_mystery_planner.py -v         # Mystery planner 測試
uv run pytest tests/test_mystery_orchestrator.py -v    # Mystery orchestrator 整合測試
uv run pytest tests/test_slima_client.py -v            # API client 測試
uv run pytest tests/test_session_resume.py -v          # Session resume 測試（Phase 1-3a）
uv run pytest tests/test_context_snapshot.py -v        # Context snapshot 測試（Phase 4）
uv run pytest tests/test_config.py -v                  # Config 載入 + 優先序測試
uv run pytest tests/test_cli.py -v                     # CLI 指令測試（Click）
uv run pytest tests/test_specialists.py -v             # 全部 21 Specialist Agent 測試
uv run pytest tests/test_task_agent.py -v             # TaskAgent 可配置 Agent 測試
uv run pytest tests/test_task_models.py -v            # TaskPlan / TaskStageDefinition 測試
uv run pytest tests/test_task_orchestrator.py -v      # TaskOrchestrator 整合測試
uv run pytest tests/test_streaming.py -v              # NDJSON 串流架構測試
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
Electron Main → spawn("slima-agents", ["task-pipeline", "--plan", plan_json, "--json-progress"])
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
