# Slima Agents 桌面分發計畫書

> Claude CLI 路線 — 完整技術計畫
> 日期：2026-02-26
> 分支：`features/agent-ui`

---

## 1. 專案總覽

### 1.1 目標

讓不懂程式的創作者（小說家、遊戲設計師）能在 Slima Writing Studio 桌面 App 裡一鍵執行世界觀建構 Agent，無需接觸終端機。

### 1.2 三個 Repo

| Repo | 語言 | 說明 |
|------|------|------|
| `slima_agents` | Python | 世界觀建構 Agent 管線（本 Repo） |
| `slima-mcp-server` | TypeScript | Slima MCP server（npm 發布） |
| `slima_vue` | Vue + Electron | Writing Studio 桌面 App（Windows/macOS/Linux） |

### 1.3 核心決策：為什麼用 Claude CLI 而非 API

| | Claude Pro 訂閱 ($20/月) | Claude API (Opus) |
|---|---|---|
| 跑 1 次 worldbuild | $0（含在訂閱內） | 估 $5–15+ |
| 跑 10 次/月 | 還是 $20/月 | $50–150 |
| 跑 30 次/月 | 還是 $20/月 | $150–450 |
| 使用者門檻 | 需安裝 Claude CLI | 需要信用卡綁定 API key |

**結論**：使用 `claude -p`（Claude CLI subprocess），讓使用者用自己的訂閱方案。API 費用太高，不適合創作者使用場景。

---

## 2. 架構設計

### 2.1 整體架構

```
┌─────────────────────────────────────────────────┐
│  slima_vue (Electron App)                       │
│  ┌───────────────────────────────────────────┐  │
│  │  Vue Frontend                             │  │
│  │  ├── Writing Studio（現有功能）             │  │
│  │  └── Agent Panel（新增）                   │  │
│  │      ├── 角色卡片（12 個 Agent）            │  │
│  │      ├── 執行面板（進度 + 日誌）            │  │
│  │      └── 環境設定引導                      │  │
│  └───────────────┬───────────────────────────┘  │
│                  │ IPC                           │
│  ┌───────────────▼───────────────────────────┐  │
│  │  Electron Main Process                    │  │
│  │  └── agentService.ts                      │  │
│  │      ├── checkDependencies()              │  │
│  │      ├── runAgent(prompt, options)         │  │
│  │      └── parseProgress(ndjsonLine)        │  │
│  └───────────────┬───────────────────────────┘  │
│                  │ child_process.spawn            │
│  ┌───────────────▼───────────────────────────┐  │
│  │  slima-agents binary (extraResources)     │  │
│  │  (Nuitka compiled, per-platform)          │  │
│  │  └── worldbuild --json-progress "prompt"  │  │
│  └───────────────┬───────────────────────────┘  │
│                  │ subprocess                     │
│  ┌───────────────▼───────────────────────────┐  │
│  │  claude -p (使用者本機安裝)                 │  │
│  │  └── Claude Pro 訂閱                      │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
         │
         │ HTTPS (Slima API)
         ▼
┌─────────────────┐
│  api.slima.ai   │
│  (書籍儲存)      │
└─────────────────┘
```

### 2.2 資料流

```
使用者點「建構世界觀」
  → Vue 透過 IPC 呼叫 agentService.runAgent(prompt)
    → Electron spawn slima-agents binary
      → slima-agents spawn claude -p（12 個階段，每階段一次）
        → claude 透過 MCP 寫檔到 Slima API
      → stdout 輸出 NDJSON 事件
    → agentService 逐行解析，透過 IPC 推送到 Vue
  → Vue 即時更新 Agent 角色卡片動畫 + 進度條
```

### 2.3 NDJSON Event Schema（已實作）

```jsonl
{"event":"pipeline_start","timestamp":"...","prompt":"...","total_stages":12}
{"event":"stage_start","timestamp":"...","stage":1,"name":"research","agents":["ResearchAgent"]}
{"event":"agent_start","timestamp":"...","stage":1,"agent":"ResearchAgent"}
{"event":"agent_complete","timestamp":"...","stage":1,"agent":"ResearchAgent","duration_s":133.2,"timed_out":false,"summary":"...","num_turns":5,"cost_usd":0.12}
{"event":"stage_complete","timestamp":"...","stage":1,"name":"research","duration_s":133.5}
{"event":"book_created","timestamp":"...","book_token":"bk_abc123","title":"...","description":"..."}
{"event":"file_created","timestamp":"...","path":"世界觀/宇宙觀/創世神話.md"}
{"event":"error","timestamp":"...","stage":2,"agent":"GeographyAgent","message":"..."}
{"event":"pipeline_complete","timestamp":"...","book_token":"bk_abc123","total_duration_s":1800.0,"success":true}
```

---

## 3. 實作步驟

### Step 1: `--json-progress` 結構化輸出 ✅ 已完成

**狀態**：已實作並通過 45 個測試。

**變更摘要**：

| 檔案 | 操作 | 說明 |
|------|------|------|
| `src/slima_agents/progress.py` | 新增 | ProgressEmitter（disabled 時零開銷） |
| `src/slima_agents/agents/claude_runner.py` | 修改 | 新增 RunOutput dataclass，回傳 cost_usd |
| `src/slima_agents/agents/base.py` | 修改 | AgentResult 新增 num_turns / cost_usd / duration_s |
| `src/slima_agents/worldbuild/orchestrator.py` | 修改 | 12 stage emitter 呼叫 + file diff |
| `src/slima_agents/cli.py` | 修改 | `--json-progress` flag |
| `tests/test_progress.py` | 新增 | 13 個 ProgressEmitter 測試 |
| `tests/test_base_agent.py` | 修改 | mock RunOutput |
| `tests/test_orchestrator.py` | 修改 | emitter 整合測試 + _flatten_paths 測試 |

**驗證**：
```bash
uv run pytest -v                                    # 45 tests passed
uv run slima-agents worldbuild --json-progress "test" 2>/dev/null | head -5
```

---

### Step 1b: `slima-agents ask` 輕量測試指令

**目的**：提供一個輕量指令，直接將 prompt 傳給 `claude -p` 並回傳結果，支援 MCP 工具操作。省去跑完整 worldbuild 管線（12 階段、20-40 分鐘）的時間。

**使用場景**：
```bash
slima-agents ask "列出我所有的書"
slima-agents ask "檢查 bk_abc123 的章節結構"
slima-agents ask "搜尋 bk_abc123 裡提到龍的段落"
slima-agents ask --book bk_abc123 "這本書的地理章節寫了什麼？"
slima-agents ask --book bk_abc123 --writable "幫我建一個 notes.md 檔案"
```

#### 1b.1 擴充 `tools.py` — 新增 `SLIMA_MCP_ALL_READ_TOOLS`

新增包含 `list_books`、`get_book`、`get_writing_stats`、`get_chapter` 的完整唯讀工具列表：

```python
# All read-only tools including library-level (list/get books) and book-level operations.
# Superset of SLIMA_MCP_READ_TOOLS — used by AskAgent for general-purpose queries.
SLIMA_MCP_ALL_READ_TOOLS: list[str] = [
    "mcp__slima__list_books",
    "mcp__slima__get_book",
    "mcp__slima__get_book_structure",
    "mcp__slima__get_writing_stats",
    "mcp__slima__get_chapter",
    "mcp__slima__read_file",
    "mcp__slima__search_content",
]
```

> 註：現有 `SLIMA_MCP_READ_TOOLS`（3 個書籍內唯讀工具）目前未被任何檔案 import，保持不動。

#### 1b.2 新增 `AskAgent`

**檔案**：`src/slima_agents/agents/ask.py`（新增）

繼承 `BaseAgent`，使用 `**kwargs` 慣例（與 `ValidationAgent`、`ResearchAgent` 一致）：

```python
from __future__ import annotations

from .base import BaseAgent
from .tools import SLIMA_MCP_ALL_READ_TOOLS, SLIMA_MCP_TOOLS


class AskAgent(BaseAgent):
    """Passes a user prompt directly to claude with Slima MCP tools.

    Unlike worldbuild specialists, this agent does not use WorldContext
    content or pipeline stages. It is a simple one-shot query agent.
    """

    def __init__(self, *, prompt: str = "", writable: bool = False, **kwargs):
        kwargs.setdefault("timeout", 300)
        super().__init__(**kwargs)
        self._prompt = prompt
        self._writable = writable

    @property
    def name(self) -> str:
        return "AskAgent"

    def system_prompt(self) -> str:
        lines = [
            "You are a helpful assistant with access to Slima book management tools.",
            "Help the user query, inspect, or manage their books.",
            "Always respond in the same language as the user's prompt.",
        ]
        if self.book_token:
            lines.append(f"\nTarget book token: {self.book_token}")
        return "\n".join(lines)

    def initial_message(self) -> str:
        return self._prompt

    def allowed_tools(self) -> list[str]:
        if self._writable:
            return SLIMA_MCP_TOOLS
        return SLIMA_MCP_ALL_READ_TOOLS
```

關鍵設計：
- **`**kwargs` 模式**：與 `ValidationAgent` / `ResearchAgent` 一致，`kwargs.setdefault("timeout", 300)` 預設 5 分鐘但可被外部覆蓋
- **`--writable` flag**：預設唯讀（安全），加 flag 才允許寫入
- **book_token 可選**：有傳就注入到 system prompt，沒傳就讓 claude 自己用 `list_books` 找
- **不需要 WorldContext 內容**：傳空 context，不注入任何世界觀資料

#### 1b.3 新增 CLI `ask` 指令

**重要**：`ask` 不需要 `SlimaClient`（不呼叫 Slima HTTP API），MCP 工具由 claude CLI 自己透過 MCP server 處理。因此**不使用 `Config.load()`**（它會強制要求 `SLIMA_API_TOKEN`），改為直接解析 model。

```python
import os

from .config import DEFAULT_MODEL


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="指定 Claude 模型。")
@click.option("--book", "-b", default=None, help="指定書籍 token（如 bk_abc123）。")
@click.option("--writable", "-w", is_flag=True, default=False,
              help="允許建立/編輯檔案（預設唯讀）。")
def ask(prompt, model, book, writable):
    """快速提問或操作 Slima 書籍（輕量版，不跑完整管線）。"""
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
        console.print(result.full_output)
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消。[/yellow]")
        raise SystemExit(130)
    except Exception as e:
        console.print(f"[red]錯誤：[/red] {e}")
        raise SystemExit(1)
```

> 為什麼不用 `Config.load()`：`config.py:38-41` 在找不到 `SLIMA_API_TOKEN` 時會拋 `ConfigError`，
> 但 `ask` 完全不需要 Slima HTTP API token。使用者只要有 Claude CLI + slima-mcp 設定好就能用。

#### 1b.4 新增測試

**檔案**：`tests/test_ask_agent.py`（新增）

```
測試項目（8 個）：
1. test_ask_agent_returns_result     — mock ClaudeRunner，驗證回傳 AgentResult + name == "AskAgent"
2. test_ask_agent_readonly_tools     — 預設 allowed_tools() 回傳 SLIMA_MCP_ALL_READ_TOOLS
3. test_ask_agent_writable_tools     — writable=True 時回傳 SLIMA_MCP_TOOLS
4. test_ask_agent_with_book_token    — book_token 出現在 system_prompt()
5. test_ask_agent_without_book_token — 不帶 book 時 system_prompt() 不含 "book_token"
6. test_ask_agent_timeout_default    — 不傳 timeout 時預設 300s
7. test_ask_agent_timeout_override   — 可透過 timeout=600 覆蓋預設值
8. test_ask_agent_initial_message    — initial_message() 原封不動回傳 prompt 字串
```

#### 1b.5 檔案變更清單

| 檔案 | 操作 | 說明 |
|------|------|------|
| `src/slima_agents/agents/tools.py` | 修改 | 新增 `SLIMA_MCP_ALL_READ_TOOLS`（7 個唯讀工具） |
| `src/slima_agents/agents/ask.py` | **新增** | AskAgent 類別 |
| `src/slima_agents/cli.py` | 修改 | 新增 `ask` 指令（不依賴 `Config.load()`） |
| `tests/test_ask_agent.py` | **新增** | AskAgent 單元測試（8 個） |

#### 1b.6 驗證方式

```bash
# 1. 測試通過
uv run pytest tests/test_ask_agent.py -v

# 2. 全部測試不受影響
uv run pytest -v

# 3. 實際使用（需 claude CLI + Slima MCP）
slima-agents ask "列出我所有的書"
slima-agents ask --book bk_xxx "這本書有哪些章節？"
slima-agents ask --book bk_xxx --writable "幫我建一個 notes.md 檔案"
```

#### 1b.7 Review 修正紀錄

| 嚴重度 | 原問題 | 修正內容 |
|--------|--------|---------|
| 高 | `Config.load()` 強制要求 `SLIMA_API_TOKEN`，但 `ask` 不需要 token | CLI 改用 `model or os.getenv("SLIMA_AGENTS_MODEL", DEFAULT_MODEL)`，不經過 `Config.load()` |
| 中 | `__init__` 用位置參數呼叫 `super()`，不符 `ValidationAgent`/`ResearchAgent` 的 `**kwargs` 慣例 | 改為 `def __init__(self, *, prompt, writable, **kwargs)` + `kwargs.setdefault("timeout", 300)` |
| 低 | 唯讀工具列表缺少 `get_chapter` | 加入 `mcp__slima__get_chapter`，共 7 個唯讀工具 |
| 低 | CLI 虛擬碼不完整 | 補回完整實作，含 error handling 和 `KeyboardInterrupt` |
| 低 | 測試只有 6 個，缺少 timeout 覆蓋和 initial_message 驗證 | 增加到 8 個測試 |

---

### Step 2: Nuitka 編譯 + GitHub Actions CI

**目的**：將 Python 原始碼編譯為平台原生二進位檔，保護 prompt 模板和編排邏輯。

#### 2.1 為什麼不用 PyPI

- PyPI 發布的是 `.tar.gz` / `.whl`，所有 `.py` 原始碼完全公開
- 包含所有 prompt 模板（`templates.py`）、編排策略（`orchestrator.py`）
- 任何人 `pip install` 後都能看到全部原始碼
- **Nuitka 將 Python 編譯為 C → 機器碼**，原始碼不可逆向

#### 2.2 Nuitka 編譯設定

```bash
# 安裝
pip install nuitka ordered-set

# 編譯指令（以 Linux 為例）
python -m nuitka \
  --standalone \
  --onefile \
  --output-filename=slima-agents \
  --include-package=slima_agents \
  --include-package-data=slima_agents \
  --nofollow-import-to=pytest \
  --nofollow-import-to=tests \
  src/slima_agents/cli.py
```

**產出**：單一執行檔 `slima-agents`（Linux）/ `slima-agents.exe`（Windows）/ `slima-agents`（macOS）

#### 2.3 GitHub Actions CI（3 平台）

Nuitka **不支援交叉編譯**，必須在目標平台上編譯。

```yaml
# .github/workflows/build-binary.yml
name: Build Binary

on:
  push:
    tags: ["v*"]

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: ubuntu-22.04
            artifact: slima-agents-linux-x64
          - os: windows-latest
            artifact: slima-agents-windows-x64.exe
          - os: macos-14
            artifact: slima-agents-macos-arm64

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install nuitka ordered-set
          pip install -e .

      - name: Build with Nuitka
        run: |
          python -m nuitka \
            --standalone \
            --onefile \
            --output-filename=${{ matrix.artifact }} \
            --include-package=slima_agents \
            src/slima_agents/cli.py

      - name: Upload to Release
        uses: softprops/action-gh-release@v2
        with:
          files: ${{ matrix.artifact }}
```

#### 2.4 版本管理

```bash
git tag v0.1.0
git push origin v0.1.0
# → CI 自動編譯 3 個平台 → 上傳到 GitHub Release
```

slima_vue 的 Electron 打包流程從 GitHub Release 下載對應平台的 binary。

#### 2.5 程式碼簽章

| 平台 | 方案 | 費用 |
|------|------|------|
| Windows | Microsoft Trusted Signing | ~$120/年 |
| macOS | Apple Developer Program | $99/年 |
| Linux | 不需要 | $0 |

**短期策略**：binary 打包在已簽章的 Electron App（`extraResources`）裡，可能不需要單獨簽章。Windows SmartScreen 和 macOS Gatekeeper 檢查的是外層 App 的簽章。需實測確認。

**長期**：如果使用者報告安全警告，再投資獨立簽章。

---

### Step 3: Electron agentService

**目的**：在 slima_vue 的 Electron main process 新增服務，管理 slima-agents binary 的生命週期。

#### 3.1 Binary 放置位置

```
slima_vue/
├── electron/
│   ├── main/
│   │   └── index.ts          # 現有
│   └── services/
│       └── agentService.ts   # 新增
├── extraResources/
│   └── bin/
│       ├── slima-agents           # Linux
│       ├── slima-agents-macos     # macOS
│       └── slima-agents.exe       # Windows
└── src/                          # Vue 前端
```

Electron 打包時，`extraResources/` 會被複製到 App 外部（不進 ASAR），可以直接執行。

#### 3.2 agentService.ts 介面設計

```typescript
// electron/services/agentService.ts

interface AgentProgress {
  event: string;
  timestamp: string;
  [key: string]: any;
}

interface AgentOptions {
  model?: string;
  onProgress: (event: AgentProgress) => void;
  onError: (error: string) => void;
  onComplete: (bookToken: string) => void;
}

class AgentService {
  private process: ChildProcess | null = null;

  /** 取得 binary 路徑（依平台） */
  private getBinaryPath(): string {
    const binName = process.platform === 'win32'
      ? 'slima-agents.exe'
      : process.platform === 'darwin'
        ? 'slima-agents-macos'
        : 'slima-agents';

    // 開發模式 vs 打包模式
    const basePath = app.isPackaged
      ? path.join(process.resourcesPath, 'bin')
      : path.join(__dirname, '../../extraResources/bin');

    return path.join(basePath, binName);
  }

  /** 檢查環境依賴 */
  async checkDependencies(): Promise<{
    binary: boolean;    // slima-agents binary 存在
    claude: boolean;    // claude CLI 可用
    slimaAuth: boolean; // Slima API 已認證
  }> { ... }

  /** 啟動世界觀建構 */
  async runWorldbuild(prompt: string, options: AgentOptions): Promise<void> {
    const binary = this.getBinaryPath();
    this.process = spawn(binary, [
      'worldbuild', '--json-progress', prompt,
      ...(options.model ? ['--model', options.model] : []),
    ]);

    // 逐行讀取 stdout（NDJSON）
    const rl = readline.createInterface({ input: this.process.stdout });
    rl.on('line', (line) => {
      try {
        const event = JSON.parse(line);
        options.onProgress(event);

        if (event.event === 'pipeline_complete') {
          options.onComplete(event.book_token);
        }
        if (event.event === 'error') {
          options.onError(event.message);
        }
      } catch { /* ignore non-JSON lines */ }
    });

    // stderr → 日誌（Rich 輸出）
    this.process.stderr?.on('data', (data) => {
      console.log('[agent stderr]', data.toString());
    });
  }

  /** 取消執行 */
  cancel(): void {
    this.process?.kill('SIGTERM');
    this.process = null;
  }
}
```

#### 3.3 IPC 通道

```typescript
// electron/main/index.ts — 註冊 IPC handlers

ipcMain.handle('agent:check-deps', () => agentService.checkDependencies());

ipcMain.handle('agent:run-worldbuild', (_, prompt, model) => {
  agentService.runWorldbuild(prompt, {
    model,
    onProgress: (event) => mainWindow.webContents.send('agent:progress', event),
    onError: (msg) => mainWindow.webContents.send('agent:error', msg),
    onComplete: (token) => mainWindow.webContents.send('agent:complete', token),
  });
});

ipcMain.handle('agent:cancel', () => agentService.cancel());
```

#### 3.4 Slima 認證整合

slima_vue 已有 Slima API 認證（token 存在 Electron store）。需要：
1. 將 Slima token 傳給 slima-agents binary（環境變數 `SLIMA_API_TOKEN`）
2. 或者讓 binary 讀取 `~/.slima/credentials.json`（slima-mcp auth 已建立的檔案）

**建議方案**：環境變數注入，最簡單且不依賴檔案系統。

```typescript
spawn(binary, args, {
  env: {
    ...process.env,
    SLIMA_API_TOKEN: store.get('slimaToken'),
    SLIMA_BASE_URL: 'https://api.slima.ai',
  },
});
```

---

### Step 4: Vue Agent UI

**目的**：在 Writing Studio 新增視覺化 Agent 面板，讓使用者看到每個 Agent 的角色、狀態、進度。

#### 4.1 Agent 角色設定（12 個）

| Agent | 角色名稱 | 性格描述 | 圖標 |
|-------|---------|---------|------|
| ResearchAgent | 學者 | 博學多聞的研究員，負責蒐集靈感 | 📚 |
| CosmologyAgent | 造物主 | 掌管宇宙法則與創世神話 | 🌌 |
| GeographyAgent | 製圖師 | 描繪大陸、海洋、地形 | 🗺️ |
| HistoryAgent | 史官 | 記錄文明興衰與重大事件 | 📜 |
| PeoplesAgent | 人類學家 | 研究種族、民族、物種 | 👥 |
| CulturesAgent | 民俗學家 | 記錄信仰、習俗、藝術 | 🎭 |
| PowerStructuresAgent | 政治家 | 建構政治、經濟、權力體系 | ⚖️ |
| CharactersAgent | 說書人 | 塑造關鍵角色與人物關係 | 🎭 |
| ItemsAgent | 鍛造師 | 創造神器、寶物、道具 | ⚔️ |
| BestiaryAgent | 獸醫 | 記錄奇獸、怪物、生態 | 🐉 |
| NarrativeAgent | 編劇 | 編織故事線與衝突 | ✍️ |
| ValidationAgent | 審查官 | 檢查一致性、修復矛盾 | 🔍 |

#### 4.2 UI 元件結構

```
src/components/shared/AgentPanel/
├── AgentPanel.vue              # 主面板（包含所有子元件）
├── AgentCard.vue               # 單一 Agent 角色卡片
├── AgentTimeline.vue           # 執行時間軸
├── AgentProgressBar.vue        # 全域進度條
├── EnvironmentSetup.vue        # 環境依賴檢查/引導
└── WorldbuildPromptInput.vue   # 提示詞輸入 + 模型選擇
```

#### 4.3 Pinia Store

```typescript
// src/stores/agentStore.ts

interface AgentState {
  status: 'idle' | 'running' | 'completed' | 'error';
  currentStage: number;
  totalStages: number;
  agents: Record<string, {
    name: string;
    status: 'pending' | 'running' | 'completed' | 'error';
    duration_s?: number;
    summary?: string;
  }>;
  bookToken?: string;
  filesCreated: string[];
  errors: string[];
  totalDuration_s?: number;
}

export const useAgentStore = defineStore('agent', {
  state: (): AgentState => ({ ... }),

  actions: {
    handleProgress(event: AgentProgress) {
      switch (event.event) {
        case 'pipeline_start':
          this.status = 'running';
          this.totalStages = event.total_stages;
          break;
        case 'agent_start':
          this.agents[event.agent].status = 'running';
          break;
        case 'agent_complete':
          this.agents[event.agent].status = 'completed';
          this.agents[event.agent].duration_s = event.duration_s;
          this.agents[event.agent].summary = event.summary;
          break;
        case 'file_created':
          this.filesCreated.push(event.path);
          break;
        case 'pipeline_complete':
          this.status = event.success ? 'completed' : 'error';
          this.bookToken = event.book_token;
          break;
        // ...
      }
    }
  }
});
```

#### 4.4 UI 狀態流程

```
環境檢查頁 → [全部通過] → 提示詞輸入頁 → [開始] → 執行面板
                                                     ├── 12 張角色卡片（亮起/暗下）
                                                     ├── 全域進度條
                                                     ├── 檔案建立日誌
                                                     └── [完成] → 跳轉到書籍頁面
```

#### 4.5 環境引導頁

使用者首次使用時，引導安裝：

```
1. Claude CLI
   [ ] 安裝 Claude CLI（顯示安裝指令 or 下載連結）
   [ ] 登入 Claude（claude login）
   [檢查] → ✅ 已安裝 v1.x.x

2. Slima 帳號
   [ ] 已登入 Slima（App 內已有）
   [檢查] → ✅ 已認證

3. slima-agents
   [✅ 內建]（已包含在 App 內）
```

---

## 4. 使用者體驗流程

### 首次使用

```
1. 使用者下載 Slima Writing Studio
2. 開啟 App → 看到 Agent 面板
3. 點擊「建構世界觀」
4. 環境檢查：
   ├── Claude CLI 未安裝 → 顯示安裝引導
   ├── Claude 未登入 → 顯示 `claude login` 指令
   └── 全部通過 → 進入提示詞頁面
5. 輸入「台灣鬼怪世界觀」→ 點擊「開始」
6. 12 個 Agent 角色卡片依序亮起
   ├── 學者正在研究... (2-3 分鐘)
   ├── 造物主正在建構宇宙... (3-5 分鐘)
   ├── ... (總計 20-40 分鐘)
   └── 審查官正在最終確認...
7. 完成 → 「世界觀已建立！」→ 跳轉到書籍頁面
```

### 使用者需要安裝的東西

| 項目 | 安裝方式 | 說明 |
|------|---------|------|
| Claude CLI | `npm install -g @anthropic-ai/claude-code` | 需 Node.js |
| Claude 登入 | `claude login` | 需 Claude Pro/Max 訂閱 |

**不需要安裝**：
- ~~Python~~ — binary 已編譯
- ~~uv~~ — binary 已編譯
- ~~slima-agents~~ — 打包在 App 裡
- ~~Slima MCP~~ — App 已有 API 認證

---

## 5. 風險評估

### 5.1 Claude CLI 風險

| 風險 | 嚴重度 | 說明 | 緩解方案 |
|------|--------|------|---------|
| Windows stream-json bug | 高 | GitHub issue #14442：Windows 上 `--output-format stream-json` 可能有 parsing 問題 | 需實測；ClaudeRunner 已有 fallback（timeout 視為部分成功） |
| Claude Desktop PATH 衝突 | 中 | GitHub issue #25075：Claude Desktop 安裝的 claude 與 npm 版本衝突 | 環境引導頁提示使用者檢查 `which claude` |
| Claude CLI 版本升級 | 中 | stream-json 格式可能變更 | ClaudeRunner 的 `_read_stream` 已設計為容錯（忽略未知事件類型） |
| 訂閱速率限制 | 低 | Pro 方案有每日 token 上限 | 在 UI 顯示預估用量；建議 Max 方案用於重度使用 |
| Claude CLI 需要 Node.js | 中 | 使用者可能沒裝 Node.js | 環境引導頁加入 Node.js 檢查 + 安裝引導 |

### 5.2 Nuitka 編譯風險

| 風險 | 嚴重度 | 說明 | 緩解方案 |
|------|--------|------|---------|
| Binary 體積過大 | 中 | standalone binary 可能 50-100MB | `--onefile` 壓縮；或接受體積（Electron 本身已 100MB+） |
| 編譯時間長 | 低 | CI 上 10-20 分鐘 | 只在 tag push 時觸發，不影響日常開發 |
| 平台相容性 | 中 | macOS arm64 vs x86_64 | CI matrix 覆蓋；macOS 14+ runner 預設 arm64 |
| C 編譯器依賴 | 低 | CI runner 需有 gcc/MSVC/clang | GitHub Actions 預裝；macOS 需 `xcode-select --install` |

### 5.3 整合風險

| 風險 | 嚴重度 | 說明 | 緩解方案 |
|------|--------|------|---------|
| 子程序管理 | 中 | Electron App 關閉時 binary 還在跑 | `app.on('before-quit')` 發 SIGTERM |
| NDJSON 解析失敗 | 低 | stderr 混入 stdout | `--json-progress` 已將 Rich 轉到 stderr |
| Windows 防毒攔截 | 中 | 未簽章 binary 可能被攔截 | 打包在已簽章 Electron 內；長期投資 code signing |

---

## 6. 未來擴展：API Fallback

### 6.1 架構預留

目前的 `ClaudeRunner` 是一個可替換的模組：

```
BaseAgent.run()
  → ClaudeRunner.run()    ← 目前：claude -p subprocess
  → ApiRunner.run()       ← 未來：Anthropic API 直接呼叫
```

只需新增 `ApiRunner` 並在 `BaseAgent.__init__` 加一個 `runner` 參數即可切換。

### 6.2 何時切換

- 如果 Claude CLI 在 Windows 上問題太多
- 如果使用者願意付 API 費用（企業/工作室客戶）
- 如果 Anthropic 推出更便宜的 batch API

### 6.3 ApiRunner 初步設計

```python
class ApiRunner:
    """使用 Anthropic Python SDK 直接呼叫 API。"""

    @staticmethod
    async def run(
        prompt: str,
        system_prompt: str,
        allowed_tools: list[str],  # 需轉換為 API tool definitions
        model: str = "claude-opus-4-6",
        max_turns: int = 50,
    ) -> RunOutput:
        # 使用 anthropic SDK 的 tool_use loop
        # 需要自行實作 MCP tool → API tool 的轉換層
        ...
```

**注意**：API 模式需要自行處理 tool-use loop（目前 Claude CLI 自動處理）。這是最大的實作成本。

---

## 7. 時程估計

| 步驟 | 內容 | 依賴 |
|------|------|------|
| ✅ Step 1 | `--json-progress` 結構化輸出 | 無 |
| Step 1b | `slima-agents ask` 輕量測試指令 | 無 |
| Step 2 | Nuitka 編譯 + GitHub Actions CI | Step 1 |
| Step 3 | Electron agentService | Step 2（需要 binary） |
| Step 4 | Vue Agent UI | Step 3（需要 IPC 通道） |

---

## 8. 檔案清單

### slima_agents（本 Repo）

| 檔案 | 操作 | 步驟 |
|------|------|------|
| `src/slima_agents/progress.py` | ✅ 已新增 | Step 1 |
| `src/slima_agents/agents/claude_runner.py` | ✅ 已修改 | Step 1 |
| `src/slima_agents/agents/base.py` | ✅ 已修改 | Step 1 |
| `src/slima_agents/worldbuild/orchestrator.py` | ✅ 已修改 | Step 1 |
| `src/slima_agents/cli.py` | ✅ 已修改 | Step 1 |
| `src/slima_agents/agents/tools.py` | 待修改 | Step 1b |
| `src/slima_agents/agents/ask.py` | 待新增 | Step 1b |
| `src/slima_agents/cli.py` | 待修改 | Step 1b |
| `tests/test_ask_agent.py` | 待新增 | Step 1b |
| `.github/workflows/build-binary.yml` | 待新增 | Step 2 |
| `nuitka.config` or `pyproject.toml [nuitka]` | 待新增 | Step 2 |

### slima_vue（另一個 Repo）

| 檔案 | 操作 | 步驟 |
|------|------|------|
| `electron/services/agentService.ts` | 待新增 | Step 3 |
| `electron/main/index.ts` | 修改（IPC） | Step 3 |
| `extraResources/bin/` | 待新增 | Step 3 |
| `src/stores/agentStore.ts` | 待新增 | Step 4 |
| `src/components/shared/AgentPanel/` | 待新增 | Step 4 |
| `src/router/` | 修改（新路由） | Step 4 |

---

## 附錄 A：Stage 編號對照表

| Stage | 名稱 | Agent(s) | 平行 |
|-------|------|----------|------|
| 1 | research | ResearchAgent | 否 |
| 2 | book_creation | （建立書籍） | 否 |
| 3 | overview | （建立 overview 檔案） | 否 |
| 4 | foundation | Cosmology + Geography + History | 是 |
| 5 | culture | Peoples + Cultures | 是 |
| 6 | power | PowerStructures | 否 |
| 7 | detail | Characters + Items + Bestiary | 是 |
| 8 | narrative | Narrative | 否 |
| 9 | glossary | （建立 glossary 檔案） | 否 |
| 10 | validation_r1 | ValidationAgent R1 | 否 |
| 11 | validation_r2 | ValidationAgent R2 | 否 |
| 12 | readme | （建立 README） | 否 |

## 附錄 B：環境變數

| 變數 | 用途 | 來源 |
|------|------|------|
| `SLIMA_API_TOKEN` | Slima API 認證 | Electron 注入 or `~/.slima/credentials.json` |
| `SLIMA_BASE_URL` | Slima API URL | 預設 `https://api.slima.ai` |
| `SLIMA_AGENTS_MODEL` | Claude 模型 | 選填，預設 `claude-sonnet-4-6` |
| `MAX_THINKING_TOKENS` | 停用 extended thinking | ClaudeRunner 自動設為 `0` |
