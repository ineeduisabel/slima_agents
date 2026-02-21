# Slima Agents

AI 驅動的世界觀建構系統。輸入一句需求描述，自動產出完整的世界觀百科全書，寫入 [Slima](https://slima.app) 書籍。

## 運作方式

使用者輸入一句需求（不是書名），系統會：
1. 由 **Research Agent** 分析需求、產出世界觀基礎知識，並自動生成一個創意書名
2. 在 Slima 上建立書籍
3. 由 **12 個專業 Agent** 分階段平行工作，產出 80-150+ 個檔案的完整世界觀
4. 最後由 **Validation Agent** 檢查一致性並自動修正

```bash
# 輸入的是「需求」，不是書名 — Agent 會自動起一個創意標題
uv run slima-agents worldbuild "台灣鬼怪故事 台灣版的百鬼夜行"
# → 書名可能是「台灣百鬼錄」、「寶島幽冥誌」之類的

uv run slima-agents worldbuild "英雄聯盟的完整世界觀"
# → 書名可能是「符文之地編年史」
```

## 架構總覽

```
使用者: "台灣鬼怪故事 台灣版的百鬼夜行"
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  OrchestratorAgent（管線協調器）                               │
│                                                             │
│  階段 1  ResearchAgent                                       │
│          ├─ 分析需求，產出世界觀基礎知識                         │
│          ├─ 生成創意書名（如「台灣百鬼錄」）                      │
│          └─ 填充 WorldContext（共享記憶體）                     │
│                     │                                       │
│          建立 Slima 書籍 + 寫入總覽檔案                         │
│                     │                                       │
│  階段 2  ┌──────────┼──────────┐                              │
│  (平行)  CosmologyAgent  GeographyAgent  HistoryAgent        │
│          宇宙觀          地理             歷史                 │
│                     │                                       │
│          ← 注入書籍結構到 WorldContext →                       │
│                     │                                       │
│  階段 3  ┌──────────┤                                        │
│  (平行)  PeoplesAgent   CulturesAgent                        │
│          種族/民族       文化                                  │
│                     │                                       │
│          ← 注入書籍結構到 WorldContext →                       │
│                     │                                       │
│  階段 4  PowerStructuresAgent                                │
│          權力結構（政治/經濟/軍事/地下勢力）                      │
│                     │                                       │
│          ← 注入書籍結構到 WorldContext →                       │
│                     │                                       │
│  階段 5  ┌──────────┼──────────┐          timeout: 900s      │
│  (平行)  CharactersAgent  ItemsAgent  BestiaryAgent          │
│          角色 (15-25)    物品 (10-18)  怪獸圖鑑 (17-30)       │
│                     │                                       │
│          ← 注入書籍結構到 WorldContext →                       │
│                     │                                       │
│  階段 6  NarrativeAgent                  timeout: 900s       │
│          敘事（衝突/預言/故事線/謎團）                           │
│                     │                                       │
│  階段 7  ValidationAgent                                     │
│          一致性驗證 + 自動修正                                  │
│                     │                                       │
│          寫入詞彙表                                           │
│                     │                                       │
│  完成！ 輸出書籍 URL                                          │
└─────────────────────────────────────────────────────────────┘
```

### 核心設計

| 概念 | 說明 |
|------|------|
| **Agent 執行方式** | 每個 Agent 透過 `claude -p` CLI subprocess 執行，Claude CLI 自動處理 tool-use loop |
| **MCP 工具** | Agent 的 Slima 操作由 Claude CLI 的 MCP 整合直接執行（`mcp__slima__*` 工具） |
| **認證** | 不需要 ANTHROPIC_API_KEY — Claude CLI 自帶認證 |
| **共享狀態** | Agent 之間透過 `WorldContext` 共享知識（記憶體內，`asyncio.Lock` 保護） |
| **階段間感知** | 每個階段完成後，Orchestrator 讀取書籍結構注入 WorldContext，讓後續 Agent 知道已建立的檔案 |
| **平行執行** | 同階段內的獨立 Agent 以 `asyncio.gather` 平行執行 |
| **語言匹配** | 自動偵測需求語言，所有產出（檔名、資料夾名、內容）使用相同語言 |
| **參考資料** | 每個檔案底部自動附上相關的參考資料來源 |

### Agent 一覽

| Agent | 類型 | 階段 | 產出檔案數 | Timeout |
|-------|------|------|-----------|---------|
| ResearchAgent | 純文字（無 MCP） | 1 | 0（填充 WorldContext） | 600s |
| CosmologyAgent | Specialist | 2 | 6-12 | 600s |
| GeographyAgent | Specialist | 2 | 8-15 | 600s |
| HistoryAgent | Specialist | 2 | 10-18 | 600s |
| PeoplesAgent | Specialist | 3 | 8-15 | 600s |
| CulturesAgent | Specialist | 3 | 10-18 | 600s |
| PowerStructuresAgent | Specialist | 4 | 10-18 | 600s |
| CharactersAgent | Specialist | 5 | 15-25 | 900s |
| ItemsAgent | Specialist | 5 | 10-18 | 900s |
| BestiaryAgent | Specialist | 5 | 17-30 | 900s |
| NarrativeAgent | Specialist | 6 | 12-18 | 900s |
| ValidationAgent | 驗證 | 7 | 1（報告）+ 修正 | 600s |

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
   - **方法 A（推薦）**：先執行 `slima-mcp auth`，系統自動讀取 `~/.slima/credentials.json`
   - **方法 B**：設定環境變數 `export SLIMA_API_TOKEN=你的token`

3. **確認連線**：
   ```bash
   uv run slima-agents status
   ```

## 使用方式

```bash
# 基本用法 — 輸入你想要的世界觀需求
uv run slima-agents worldbuild "台灣鬼怪故事 台灣版的百鬼夜行"

# 已知 IP
uv run slima-agents worldbuild "英雄聯盟的完整世界觀"

# 歷史設定
uv run slima-agents worldbuild "1920-1930年代上海租界時代"

# 原創世界觀
uv run slima-agents worldbuild "蒸氣龐克海洋世界"

# 指定模型（更高品質，較慢）
uv run slima-agents worldbuild "三國演義世界觀" --model claude-opus-4-6

# 開啟除錯日誌
uv run slima-agents worldbuild "星際大戰世界觀" -v

# 隨時按 Ctrl+C 取消執行
```

## 產出結構範例

以「台灣鬼怪故事」為例，系統會產出類似以下結構（全中文）：

```
總覽/
  世界觀總覽.md

宇宙觀/
  概述.md
  起源/
    創世神話.md
    宇宙結構.md
  超自然/
    靈力系統.md
    禁術.md
  死後世界/
    輪迴機制.md
    陰間結構.md

地理/
  概述.md
  區域/
    北部.md
    中部.md
    南部.md
    東部.md
    離島.md
  靈異地標/
    紅衣小女孩步道.md
    ...

歷史/
  年表.md
  時代/
    原住民時期/
    荷西殖民時期/
    清領時期/
    日治時期/
    ...

種族/
  概述.md
  人類族群/
  超自然存在/

文化/
  概述.md
  信仰/
    道教.md
    佛教.md
    民間信仰.md
  語言/
  日常生活/

權力結構/
  概述.md
  神明體系/
  陰間官僚/
  ...

角色/
  鬼魂與靈體/
    林投姐.md
    椅仔姑.md
    ...
  神明/
    城隍爺.md
    媽祖.md
    ...
  人類主角/
    ...

物品/
  概述.md
  法器/
  護身符/
  ...

怪獸圖鑑/
  概述.md
  鬼怪類/
    魔神仔.md
    水鬼.md
    ...
  妖魔類/
    ...
  靈異植物/
    ...

敘事/
  概述.md
  衝突/
  預言/
  故事線/
  謎團/

參考資料/
  詞彙表.md
```

每個 .md 檔案包含 800-2000+ 字的詳細內容，並在底部附上參考資料來源。

## 測試

```bash
uv run pytest -v
```

## 專案結構

```
src/slima_agents/
├── cli.py                          # CLI 入口（Click + Rich）
├── config.py                       # 設定：env vars + ~/.slima/credentials.json
├── slima/
│   ├── client.py                   # Slima REST API 非同步客戶端
│   └── types.py                    # Pydantic 回應模型
├── agents/
│   ├── claude_runner.py            # claude -p subprocess 執行器（含重試 + 取消處理）
│   ├── base.py                     # BaseAgent ABC — 組合 prompt → ClaudeRunner
│   ├── context.py                  # WorldContext 共享狀態（asyncio.Lock 保護）
│   └── tools.py                    # MCP 工具名稱常數（--allowedTools）
└── worldbuild/
    ├── orchestrator.py             # 管線協調器（階段排程 + 結構注入）
    ├── research.py                 # Research Agent（分析需求 + 生成書名）
    ├── validator.py                # Validation Agent（一致性檢查）
    ├── templates.py                # 所有 Agent 的 prompt 模板
    └── specialists/                # 10 個專家 Agent
        ├── cosmology.py
        ├── geography.py
        ├── history.py
        ├── peoples.py
        ├── cultures.py
        ├── power_structures.py
        ├── characters.py
        ├── items.py
        ├── bestiary.py
        └── narrative.py

tests/
├── test_base_agent.py              # BaseAgent + ResearchAgent 單元測試
├── test_orchestrator.py            # Orchestrator 整合測試
└── test_slima_client.py            # SlimaClient API 測試
```

## 技術規格

- **Python 3.11+**
- **依賴**：httpx, pydantic, click, rich, python-dotenv
- **不需要** `anthropic` SDK — 透過 Claude CLI 執行
- **Slima API**：`https://api.slima.ai`
- **Agent 執行**：`claude -p` subprocess（每個 Agent 一個獨立 session）
- **MCP 工具**：`mcp__slima__create_file`, `write_file`, `read_file`, `edit_file`, `get_book_structure`, `search_content`
