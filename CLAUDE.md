# Slima Agents — Claude Code 開發指南

## 快速指令

```bash
uv run pytest                                          # 執行測試（16 tests）
uv run slima-agents status                             # 檢查 API 連線
uv run slima-agents worldbuild "需求描述"               # 建構世界觀
uv run slima-agents worldbuild "需求描述" --model claude-opus-4-6  # 指定模型
uv run slima-agents worldbuild "需求描述" -v            # 除錯日誌
```

## 專案結構

```
src/slima_agents/
├── cli.py                    # Click CLI，入口點 = slima_agents.cli:main
├── config.py                 # Config.load()：env vars → ~/.slima/credentials.json
├── slima/
│   ├── client.py             # SlimaClient：httpx async，base_url = https://api.slima.ai
│   └── types.py              # Book, Commit, FileSnapshot, McpFile* Pydantic models
├── agents/
│   ├── claude_runner.py      # ClaudeRunner.run()：claude -p subprocess，2 retries，CancelledError 處理
│   ├── base.py               # BaseAgent(ABC)：system_prompt + initial_message → ClaudeRunner → AgentResult
│   ├── context.py            # WorldContext：12 個 section（含 book_structure），asyncio.Lock
│   └── tools.py              # SLIMA_MCP_TOOLS / SLIMA_MCP_READ_TOOLS 字串列表
└── worldbuild/
    ├── orchestrator.py       # OrchestratorAgent.run()：7 階段管線 + 階段間結構注入
    ├── research.py           # ResearchAgent：純文字輸出（無 MCP），解析 ## 區段 + ## Title
    ├── validator.py          # ValidationAgent：讀取全部檔案，產出一致性報告
    ├── templates.py          # LANGUAGE_RULE + QUALITY_STANDARD + 12 個 *_INSTRUCTIONS
    └── specialists/          # 10 個專家 Agent（每個都是 BaseAgent 子類別）
        ├── cosmology.py, geography.py, history.py
        ├── peoples.py, cultures.py, power_structures.py
        ├── characters.py, items.py, bestiary.py, narrative.py
```

## 架構關鍵概念

### Agent 執行流程

```
BaseAgent.run()
  → self.initial_message()     # 使用者 prompt（包含 book_token）
  → self.system_prompt()       # LANGUAGE_RULE + *_INSTRUCTIONS + WorldContext
  → self.allowed_tools()       # SLIMA_MCP_TOOLS（字串列表）
  → ClaudeRunner.run()         # claude -p subprocess
  → AgentResult(summary, full_output)
```

每個 Agent 是一次 `claude -p` 呼叫。Claude CLI 自己處理 tool-use loop（不限回合數，受 timeout 限制）。

### WorldContext（共享狀態）

12 個區段：`overview`, `cosmology`, `geography`, `history`, `peoples`, `cultures`, `power_structures`, `characters`, `items_bestiary`, `narrative`, `naming_conventions`, `book_structure`

- ResearchAgent 寫入前 11 個區段
- OrchestratorAgent 在每個階段後注入 `book_structure`（從 Slima API 讀取書籍檔案樹）
- 所有 specialist agent 的 `system_prompt()` 包含完整的 `context.serialize_for_prompt()`

### 管線階段與 Timeout

| 階段 | Agent | 平行 | Timeout |
|------|-------|------|---------|
| 1 | ResearchAgent | 否 | 600s |
| 2 | Cosmology + Geography + History | 是 | 600s |
| 3 | Peoples + Cultures | 是 | 600s |
| 4 | PowerStructures | 否 | 600s |
| 5 | Characters + Items + Bestiary | 是 | **900s** |
| 6 | Narrative | 否 | **900s** |
| 7 | Validation | 否 | 600s |

階段 2-5 完成後會呼叫 `_inject_book_structure()` 注入檔案樹。

### 語言偵測

- `orchestrator._detect_cjk(prompt)` → 決定用 `_PATHS_ZH` 或 `_PATHS_EN`（總覽/詞彙表路徑）
- `templates.LANGUAGE_RULE` → 嵌入每個 specialist 的 system prompt，強制所有產出用提示詞語言
- ResearchAgent 的 `initial_message()` 明確要求用提示詞語言撰寫

### 標題生成

- ResearchAgent 輸出 `## Title` 區段 → 解析到 `research.suggested_title`
- OrchestratorAgent 用此標題建立 Slima 書籍
- Fallback：若解析失敗，使用 `prompt[:60]`

### Prompt 模板結構（templates.py）

```
LANGUAGE_RULE          # 語言規則（嵌入所有 agent）
QUALITY_STANDARD       # 品質標準 + 參考資料要求（附加到所有 specialist）
*_INSTRUCTIONS         # 每個 specialist 的專用指令 = LANGUAGE_RULE + 具體指令 + QUALITY_STANDARD
RESEARCH_INSTRUCTIONS  # 研究 Agent 指令（含 ## Title 要求）
VALIDATION_INSTRUCTIONS # 驗證 Agent 指令
```

## 新增 Agent 的步驟

1. 在 `templates.py` 新增 `NEW_INSTRUCTIONS = LANGUAGE_RULE + """...""" + QUALITY_STANDARD`
2. 在 `specialists/` 新增 `new_agent.py`，繼承 `BaseAgent`
3. 實作 `name`, `system_prompt()`, `initial_message()`
4. 在 `specialists/__init__.py` 新增 export
5. 在 `orchestrator.py` 加入對應階段（注意平行/依序、timeout）
6. 更新 `tests/test_orchestrator.py` mock 列表

## 修改 Prompt 模板的注意事項

- `QUALITY_STANDARD` 會附加到所有 specialist — 改這裡影響全部
- `LANGUAGE_RULE` 嵌入所有 agent — 改語言偵測邏輯要同時改 `orchestrator._detect_cjk()`
- 每個 specialist 的 `initial_message()` 是實際發送給 `claude -p` 的 user prompt
- `system_prompt()` = instructions + book_token + WorldContext 序列化
- 參考資料要求在 `QUALITY_STANDARD` 裡 — 要求每個檔案底部有 `## 參考資料`

## 關鍵限制

- **claude -p 不能在 Claude Code session 裡執行**：subprocess 會 hang。測試必須在獨立終端機
- **單次 session 限制**：每個 Agent 是一次 `claude -p` 呼叫。如果 timeout 到，不會斷點續傳
- **WorldContext 膨脹**：所有 11 個區段序列化後嵌入每個 agent 的 system prompt。隨著 ResearchAgent 產出越多內容，system prompt 越大
- **MCP 工具限制**：Agent 只能用 `--allowedTools` 列表中的 Slima MCP 工具。如需新增，改 `tools.py`

## 測試

```bash
uv run pytest -v    # 全部 16 tests
uv run pytest tests/test_base_agent.py -v        # Agent 單元測試（含 ResearchAgent 標題解析）
uv run pytest tests/test_orchestrator.py -v      # Orchestrator 整合測試
uv run pytest tests/test_slima_client.py -v      # API client 測試
```

所有 Agent 測試透過 mock `ClaudeRunner` 執行。Orchestrator 測試 mock 所有 Agent + SlimaClient。

## 環境

- Python 3.11+
- 依賴：httpx, pydantic, click, rich, python-dotenv（不需要 anthropic SDK）
- Slima API base URL：`https://api.slima.ai`
- Claude CLI 必須已安裝且登入
- Slima 認證：`~/.slima/credentials.json`（slima-mcp auth）或 `SLIMA_API_TOKEN` env var
