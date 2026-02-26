# Agent UI 整合開發計畫

> 日期：2026-02-26
> 分支：`features/agent-ui`
> 前置完成：Step 1（json-progress）、Step 1b（ask）、Step 2（Nuitka CI + Release v0.1.0）

---

## 目標

在 slima_vue Writing Studio 側邊欄新增「Agents」入口，使用者可在 UI 中：
1. 執行 **worldbuild**（完整世界觀建構管線，20-40 分鐘）
2. 執行 **ask**（輕量查詢/操作，數秒到數分鐘）
3. 即時看到 NDJSON 進度事件驅動的 UI 更新
4. 查看歷史執行記錄

全部在本地完成，不經過 slima_rails。

**限制：僅 Electron 桌面版可用。** 網頁版無法 spawn 本地 process，需偵測 `window.electronAPI?.isElectron` 決定是否顯示 Agents 入口。

---

## 架構

```
slima_vue Renderer (Vue)          Electron Main Process              Local Binary
┌────────────────────┐           ┌───────────────────────┐         ┌──────────────────┐
│ AgentsView.vue     │           │ agentService.ts       │         │ slima-agents     │
│                    │──invoke──→│                       │──spawn─→│   worldbuild     │
│ agentStore.ts      │           │   child_process       │         │   --json-progress│
│   handleProgress() │←──send────│   readline stdout     │←─NDJSON─│                  │
│                    │           │                       │         │   claude -p      │
│ Agent cards +      │           │   env:                │         │   → Slima MCP    │
│ progress bar       │           │     SLIMA_API_TOKEN   │         └──────────────────┘
└────────────────────┘           └───────────────────────┘
                                          │
                                 首次使用時自動下載 binary
                                 from GitHub Release
```

---

## Phase A：Binary 自動下載 + Electron IPC 層

### A1. Binary 自動下載策略

**不打包在 extraResources/**，改為首次使用時從 GitHub Release 自動下載。

理由：
- Binary 約 50-100MB，打包進 Electron 會讓 App 體積翻倍
- slima_agents 版本更新頻繁，不想每次都重新發布 Electron App
- 可以獨立更新 agent binary 而不需更新 App

**下載流程**：

```
使用者點擊 Agents nav
  → agentService.ensureBinary()
    → 檢查 {userData}/slima-agents/bin/{binary} 是否存在
    → 不存在 → 下載畫面
      → GET https://api.github.com/repos/ineeduisabel/slima_agents/releases/latest
      → 找到對應平台 asset：
          win32  → slima-agents-windows-x64.exe
          darwin → slima-agents-macos-arm64
          linux  → slima-agents-linux-x64
      → 下載 binary 到 {userData}/slima-agents/bin/
      → Linux/macOS: chmod +x
      → 寫入 {userData}/slima-agents/version.json: { "version": "v0.1.0", "downloadedAt": "..." }
    → 存在 → 檢查版本（可選，背景靜默更新）
```

**存放位置**：
```
{app.getPath('userData')}/
└── slima-agents/
    ├── bin/
    │   └── slima-agents(.exe)     # 平台對應的 binary
    └── version.json                # { "version": "v0.1.0" }
```

**版本更新**：
- 每次開啟 Agents 頁面時，背景呼叫 GitHub API 檢查最新版本
- 有新版時顯示「有更新可用」提示，使用者點擊後下載
- 不自動靜默更新（避免跑到一半 binary 被換掉）

### A2. 新增 `electron/services/agentService.ts`

```typescript
// 核心職責：
// 1. 管理 binary 下載/更新
// 2. spawn binary + readline NDJSON
// 3. 透過 IPC 推送事件到 renderer

import { app, BrowserWindow } from 'electron'
import { spawn, ChildProcess } from 'child_process'
import { createInterface } from 'readline'
import { createWriteStream } from 'fs'
import path from 'path'
import fs from 'fs/promises'
import https from 'https'

// --- 常數 ---
const GITHUB_REPO = 'ineeduisabel/slima_agents'
const BINARY_NAMES: Record<string, string> = {
  win32:  'slima-agents-windows-x64.exe',
  darwin: 'slima-agents-macos-arm64',
  linux:  'slima-agents-linux-x64',
}

class AgentService {
  private process: ChildProcess | null = null
  private mainWindow: BrowserWindow | null = null

  setMainWindow(win: BrowserWindow) { this.mainWindow = win }

  // --- Binary 管理 ---

  private getBaseDir(): string {
    return path.join(app.getPath('userData'), 'slima-agents')
  }

  private getBinaryPath(): string {
    const name = process.platform === 'win32'
      ? 'slima-agents.exe'
      : 'slima-agents'
    return path.join(this.getBaseDir(), 'bin', name)
  }

  async ensureBinary(): Promise<{ ready: boolean; version?: string; needsDownload?: boolean }> {
    const binPath = this.getBinaryPath()
    const exists = await fs.access(binPath).then(() => true).catch(() => false)
    if (exists) {
      const versionInfo = await this.getLocalVersion()
      return { ready: true, version: versionInfo?.version }
    }
    return { ready: false, needsDownload: true }
  }

  async downloadBinary(
    onProgress: (percent: number) => void
  ): Promise<void> {
    // 1. 取得最新 Release
    // 2. 找到對應平台 asset
    // 3. 下載到 getBaseDir()/bin/
    // 4. chmod +x (unix)
    // 5. 寫入 version.json
  }

  async checkForUpdate(): Promise<{ hasUpdate: boolean; latest?: string; current?: string }> {
    // 比較 version.json vs GitHub latest release
  }

  // --- Agent 執行 ---

  async runWorldbuild(prompt: string, opts: { model?: string; token: string }): Promise<void> {
    const binPath = this.getBinaryPath()
    this.process = spawn(binPath, [
      'worldbuild', '--json-progress', prompt,
      ...(opts.model ? ['--model', opts.model] : []),
    ], {
      env: {
        ...process.env,
        SLIMA_API_TOKEN: opts.token,
      },
    })
    this.pipeEvents()
  }

  async runAsk(prompt: string, opts: { model?: string; token: string; book?: string; writable?: boolean }): Promise<void> {
    const binPath = this.getBinaryPath()
    const args = ['ask', prompt]
    if (opts.model)    args.push('--model', opts.model)
    if (opts.book)     args.push('--book', opts.book)
    if (opts.writable) args.push('--writable')
    // ask 目前無 --json-progress，輸出純文字

    this.process = spawn(binPath, args, {
      env: { ...process.env, SLIMA_API_TOKEN: opts.token },
    })
    this.pipeEvents()
  }

  cancel(): void {
    this.process?.kill('SIGTERM')
    this.process = null
    this.mainWindow?.webContents.send('agent:cancelled')
  }

  get isRunning(): boolean {
    return this.process !== null && !this.process.killed
  }

  // --- 內部 ---

  private pipeEvents(): void {
    if (!this.process?.stdout) return

    const rl = createInterface({ input: this.process.stdout })
    rl.on('line', (line) => {
      try {
        const event = JSON.parse(line)
        this.mainWindow?.webContents.send('agent:progress', event)
      } catch {
        // 非 JSON 行（ask 指令的純文字輸出）
        this.mainWindow?.webContents.send('agent:output', line)
      }
    })

    this.process.stderr?.on('data', (data) => {
      // Rich console 輸出（debug 用）
      this.mainWindow?.webContents.send('agent:stderr', data.toString())
    })

    this.process.on('close', (code) => {
      this.process = null
      this.mainWindow?.webContents.send('agent:exit', { code })
    })
  }

  private async getLocalVersion(): Promise<{ version: string } | null> {
    try {
      const data = await fs.readFile(
        path.join(this.getBaseDir(), 'version.json'), 'utf-8'
      )
      return JSON.parse(data)
    } catch { return null }
  }
}

export const agentService = new AgentService()
```

### A3. Preload 擴充

在 `electron/preload.ts` 新增 `agent` namespace：

```typescript
agent: {
  // Binary 管理
  ensureBinary():  Promise<{ ready: boolean; version?: string; needsDownload?: boolean }>
  downloadBinary(): Promise<void>           // 觸發下載，進度透過 onDownloadProgress 回傳
  checkForUpdate(): Promise<{ hasUpdate: boolean; latest?: string; current?: string }>

  // 執行
  runWorldbuild(prompt: string, model?: string): Promise<void>
  runAsk(prompt: string, opts?: { book?: string; writable?: boolean; model?: string }): Promise<void>
  cancel(): Promise<void>

  // 環境檢查
  checkEnvironment(): Promise<{
    binary:    { ok: boolean; version?: string }
    claudeCli: { ok: boolean; version?: string }
    slimaAuth: { ok: boolean }
  }>

  // 事件監聽（main → renderer）
  onProgress(callback: (event: NdjsonEvent) => void): () => void
  onOutput(callback: (line: string) => void): () => void
  onExit(callback: (info: { code: number }) => void): () => void
  onDownloadProgress(callback: (percent: number) => void): () => void
}
```

### A4. IPC 註冊

在 `electron/main.ts` 的 handler 註冊區塊加入：

```typescript
import { agentService } from './services/agentService'

// 在 createWindow 之後
agentService.setMainWindow(mainWindow)

// IPC handlers
ipcMain.handle('agent:ensure-binary',   () => agentService.ensureBinary())
ipcMain.handle('agent:download-binary', () => agentService.downloadBinary(...))
ipcMain.handle('agent:check-update',    () => agentService.checkForUpdate())
ipcMain.handle('agent:check-env',       () => agentService.checkEnvironment())
ipcMain.handle('agent:run-worldbuild',  (_, prompt, model) => {
  const token = await getToken()  // 從 authService 取得
  agentService.runWorldbuild(prompt, { model, token })
})
ipcMain.handle('agent:run-ask', (_, prompt, opts) => {
  const token = await getToken()
  agentService.runAsk(prompt, { ...opts, token })
})
ipcMain.handle('agent:cancel', () => agentService.cancel())
```

### A5. 認證整合

slima_agents binary 讀取 `SLIMA_API_TOKEN` env var。Electron 已有使用者 token（authService.getToken()），spawn 時注入：

```typescript
spawn(binary, args, {
  env: { ...process.env, SLIMA_API_TOKEN: token }
})
```

不需要改 slima_agents 的 config.py，現有的 env var 讀取已支援。

### A6. 環境檢查

`checkEnvironment()` 實作：

```typescript
async checkEnvironment() {
  // 1. Binary
  const bin = await this.ensureBinary()

  // 2. Claude CLI
  let claudeCli = { ok: false, version: undefined }
  try {
    const { stdout } = await execPromise('claude --version')
    claudeCli = { ok: true, version: stdout.trim() }
  } catch {}

  // 3. Slima Auth（檢查 Electron 內是否已登入）
  const token = await getToken()
  const slimaAuth = { ok: !!token }

  return { binary: bin, claudeCli, slimaAuth }
}
```

---

## Phase B：Sidebar + Route + View 骨架

### B1. MainNavbar.vue 新增 nav item

在 `nexus`（Team）和 `trash` 之間新增：

```typescript
// navItems computed 中新增
{
  key: 'agents',
  path: '/writing_studio/agents',
  icon: 'Bot',           // Lucide: Bot icon（機器人）
  label: t('nav.agents') // i18n: "AI Agents" / "虛擬員工"
}
```

- **僅 Electron 版顯示**：`v-if="isElectron"`（網頁版隱藏，或點擊後提示「需要桌面版」）
- Active 狀態：深色背景 + 左側 indigo 指示條（與其他 nav 一致）

### B2. Router 新增路由

```typescript
// src/router/index.ts
{
  path: '/writing_studio/agents',
  name: 'agents',
  component: () => import('@/views/agents/AgentsView.vue'),
  meta: { requiresAuth: true },
}
```

### B3. AgentsView.vue 骨架

```
src/views/agents/
├── AgentsView.vue              # 主頁面（狀態機：setup → idle → running → done）
└── components/
    ├── EnvironmentCheck.vue     # 環境檢查（binary + claude + auth）
    ├── BinaryDownload.vue       # Binary 下載進度
    ├── WorldbuildPanel.vue      # Worldbuild 指令面板
    ├── AskPanel.vue             # Ask 指令面板
    ├── AgentProgress.vue        # 執行中進度顯示（NDJSON 驅動）
    ├── AgentCard.vue            # 單一 Agent 角色卡片
    └── RunHistory.vue           # 歷史記錄列表
```

**AgentsView.vue 狀態機**：

```
┌─────────┐    binary 不存在    ┌──────────┐
│  setup  │◄────────────────────│  check   │（首次進入）
│ (下載)   │                    └──────────┘
└────┬────┘                         │ 全部通過
     │ 下載完成                      ▼
     │                        ┌──────────┐
     └───────────────────────→│   idle   │
                              │ (選指令)  │
                              └────┬─────┘
                                   │ 點擊「開始」
                                   ▼
                              ┌──────────┐
                              │ running  │ ← NDJSON events 驅動
                              │ (進度面板)│
                              └────┬─────┘
                                   │ pipeline_complete / exit
                                   ▼
                              ┌──────────┐
                              │   done   │ → 查看書籍 / 返回 idle
                              └──────────┘
```

---

## Phase C：進度 UI 元件（NDJSON 驅動）

### C1. agentStore.ts

```typescript
// src/stores/agentStore.ts

interface AgentRun {
  id: string                    // 隨機 UUID
  command: 'worldbuild' | 'ask'
  prompt: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  startedAt: string
  completedAt?: string

  // worldbuild 專用
  currentStage: number
  totalStages: number
  bookToken?: string
  bookTitle?: string
  agents: Record<string, {
    status: 'pending' | 'running' | 'completed' | 'error'
    duration_s?: number
    summary?: string
  }>
  filesCreated: string[]
  errors: string[]
  totalDuration_s?: number

  // ask 專用
  output?: string               // 純文字輸出
}

export const useAgentStore = defineStore('agent', () => {
  const currentRun = ref<AgentRun | null>(null)
  const history    = ref<AgentRun[]>([])     // 持久化到 IndexedDB
  const isRunning  = computed(() => currentRun.value?.status === 'running')

  function handleProgress(event: NdjsonEvent) {
    if (!currentRun.value) return

    switch (event.event) {
      case 'pipeline_start':
        currentRun.value.totalStages = event.total_stages
        break
      case 'book_created':
        currentRun.value.bookToken = event.book_token
        currentRun.value.bookTitle = event.title
        break
      case 'stage_start':
        currentRun.value.currentStage = event.stage
        for (const agent of event.agents) {
          currentRun.value.agents[agent] = { status: 'running' }
        }
        break
      case 'agent_complete':
        currentRun.value.agents[event.agent] = {
          status: event.timed_out ? 'error' : 'completed',
          duration_s: event.duration_s,
          summary: event.summary,
        }
        break
      case 'file_created':
        currentRun.value.filesCreated.push(event.path)
        break
      case 'error':
        currentRun.value.errors.push(event.message)
        break
      case 'pipeline_complete':
        currentRun.value.status = event.success ? 'completed' : 'failed'
        currentRun.value.bookToken = event.book_token
        currentRun.value.totalDuration_s = event.total_duration_s
        currentRun.value.completedAt = new Date().toISOString()
        history.value.unshift(currentRun.value)
        break
    }
  }

  return { currentRun, history, isRunning, handleProgress, ... }
})
```

### C2. NDJSON → UI 映射

| NDJSON Event | UI 更新 |
|---|---|
| `pipeline_start` | 顯示進度面板，設定 totalStages |
| `book_created` | 顯示書籍標題 + token 連結 |
| `stage_start` | 進度條前進，對應 agent 卡片亮起（running） |
| `stage_complete` | 階段完成指示 |
| `agent_start` | 單一 agent 卡片 → running 狀態（pulse 動畫） |
| `agent_complete` | agent 卡片 → completed（顯示 duration + summary） |
| `file_created` | 檔案列表即時新增一行 |
| `error` | 紅色 toast / 錯誤區塊 |
| `pipeline_complete` | 全部完成，顯示總時間 + 「查看書籍」按鈕 |

### C3. AgentProgress.vue 佈局

```
┌─ Worldbuild 進度 ────────────────────────────────────────┐
│                                                          │
│  📖 海賊王世界觀  (bk_abc123)                              │
│  ████████████░░░░░░░░  Stage 4/8  52%                    │
│                                                          │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
│  │  📚  │ │  🌌  │ │  🗺️  │ │  📜  │ │  👥  │ │  🎭  │ │
│  │ 研究  │ │ 宇宙 │ │ 地理  │ │ 歷史 │ │ 族群 │ │ 文化  │ │
│  │  ✅  │ │  ✅  │ │  ✅  │ │ 🔄   │ │ ⏳   │ │ ⏳   │ │
│  │ 2m3s │ │ 4m1s │ │ 3m8s │ │ run  │ │ wait │ │ wait │ │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
│  │  ⚖️  │ │  🎭  │ │  ⚔️  │ │  🐉  │ │  ✍️  │ │  🔍  │ │
│  │ 權力  │ │ 角色 │ │ 道具  │ │ 怪獸 │ │ 敘事 │ │ 驗證  │ │
│  │ ⏳   │ │ ⏳   │ │ ⏳   │ │ ⏳   │ │ ⏳   │ │ ⏳   │ │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ │
│                                                          │
│  已建立檔案 (7)：                                          │
│  ├── 世界觀/宇宙觀/創世神話.md                              │
│  ├── 世界觀/宇宙觀/魔法體系.md                              │
│  ├── 世界觀/地理/主要大陸.md                                │
│  └── ...                                                  │
│                                                          │
│                              [取消]                       │
└──────────────────────────────────────────────────────────┘
```

### C4. AskPanel.vue 佈局

```
┌─ Ask ────────────────────────────────────────────────────┐
│                                                          │
│  Book: [下拉選擇 or 不指定 ▾]    ☐ 允許寫入               │
│                                                          │
│  ┌──────────────────────────────────────────────┐ [送出] │
│  │ 這本書的地理章節寫了什麼？                        │       │
│  └──────────────────────────────────────────────┘       │
│                                                          │
│  ─── 回應 ─────────────────────────────────────────────  │
│                                                          │
│  地理章節包含以下內容：                                     │
│  1. 主要大陸：...                                         │
│  2. 海洋與水域：...                                       │
│  ...                                                     │
└──────────────────────────────────────────────────────────┘
```

---

## Phase D：Binary 下載 UI

### D1. BinaryDownload.vue

首次使用時顯示：

```
┌─ 準備 AI Agent 環境 ─────────────────────────────────────┐
│                                                          │
│  需要下載 AI Agent 引擎 (約 50-80MB)                       │
│                                                          │
│  ████████████████░░░░  78%   下載中...                    │
│                                                          │
│  版本：v0.1.0                                             │
│  來源：GitHub Release                                     │
│                                                          │
│                        [取消]                             │
└──────────────────────────────────────────────────────────┘
```

### D2. EnvironmentCheck.vue

```
┌─ 環境檢查 ───────────────────────────────────────────────┐
│                                                          │
│  ✅  AI Agent 引擎    v0.1.0                              │
│  ✅  Claude CLI        v1.x.x                            │
│  ✅  Slima 帳號        已登入                              │
│                                                          │
│  一切就緒！                                               │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

未通過時顯示安裝引導：

```
│  ❌  Claude CLI        未安裝                              │
│      安裝方式：npm install -g @anthropic-ai/claude-code    │
│      安裝後執行：claude login                              │
│      [重新檢查]                                           │
```

---

## Phase E：slima_agents 補充（如需要）

### E1. `ask --json-progress`

目前 `ask` 指令不支援 `--json-progress`。如果 UI 需要 ask 的即時進度（例如 tool call 追蹤），需要補上。

**但 ask 通常很快（數秒到 1 分鐘），純文字輸出可能就夠了。** 可先不做，看 UI 需求再決定。

### E2. 不需要改的

- `config.py` — 已支援 `SLIMA_API_TOKEN` env var
- `progress.py` — NDJSON schema 已完備
- `cli.py` — worldbuild `--json-progress` 已就緒

---

## 檔案變更清單

### slima_vue（主要工作量）

| 檔案 | 操作 | Phase | 說明 |
|------|------|-------|------|
| `electron/services/agentService.ts` | **新增** | A | Binary 管理 + spawn + NDJSON pipe |
| `electron/preload.ts` | 修改 | A | 新增 `agent` namespace |
| `electron/main.ts` | 修改 | A | 註冊 agent IPC handlers |
| `src/components/layout/MainNavbar.vue` | 修改 | B | 新增 agents nav item |
| `src/router/index.ts` | 修改 | B | 新增 `/writing_studio/agents` 路由 |
| `src/views/agents/AgentsView.vue` | **新增** | B | 主頁面（狀態機） |
| `src/views/agents/components/EnvironmentCheck.vue` | **新增** | B | 環境檢查 |
| `src/views/agents/components/BinaryDownload.vue` | **新增** | D | 下載進度 |
| `src/views/agents/components/WorldbuildPanel.vue` | **新增** | C | Worldbuild 指令 + 進度 |
| `src/views/agents/components/AskPanel.vue` | **新增** | C | Ask 指令面板 |
| `src/views/agents/components/AgentProgress.vue` | **新增** | C | NDJSON 進度 UI |
| `src/views/agents/components/AgentCard.vue` | **新增** | C | 單一 agent 角色卡片 |
| `src/views/agents/components/RunHistory.vue` | **新增** | C | 歷史記錄 |
| `src/stores/agentStore.ts` | **新增** | C | Agent 狀態管理 |
| `src/types/agent.ts` | **新增** | B | TypeScript 型別定義 |

### slima_agents（少量）

| 檔案 | 操作 | Phase | 說明 |
|------|------|-------|------|
| `src/slima_agents/cli.py` | 可能修改 | E | ask --json-progress（視需求） |

---

## 驗證方式

### Phase A 驗證
```bash
# 在 slima_vue 專案
# 1. Electron dev mode 啟動
pnpm dev

# 2. 開 DevTools console 測試 IPC
await window.electronAPI.agent.ensureBinary()
await window.electronAPI.agent.checkEnvironment()
await window.electronAPI.agent.runWorldbuild("測試", "claude-sonnet-4-6")
```

### Phase B 驗證
```
# 1. 側邊欄出現 Agents 圖示
# 2. 點擊 → 導航到 /writing_studio/agents
# 3. 環境檢查頁正確顯示三項狀態
```

### Phase C 驗證
```
# 1. 輸入 prompt → 點擊開始
# 2. Agent 卡片依序亮起
# 3. 進度條隨 stage 前進
# 4. 檔案列表即時更新
# 5. 完成後可跳轉到書籍頁面
```

### Phase D 驗證
```
# 1. 刪除 userData/slima-agents/bin/
# 2. 重新進入 Agents 頁面
# 3. 顯示下載畫面 → 下載完成 → 進入正常流程
```

---

## 不做的事

- **不走 slima_rails** — 全部本地執行
- **不做 WebSocket** — 純 Electron IPC，不需要
- **不做多任務併行** — 一次只能跑一個 agent（binary 是單一 process）
- **不做 API fallback** — 短期只支援 Claude CLI（未來再加）
- **不做 i18n** — 先用中文寫死，後續再抽 i18n keys
- **不做 agent 卡片自訂** — 12 個 agent 角色固定，不讓使用者改

---

## 開發順序與依賴

```
Phase A (Electron IPC)
    │
    ├── Phase B (Sidebar + Route + View 骨架)
    │       │
    │       └── Phase C (進度 UI)
    │
    └── Phase D (Binary 下載 UI)

Phase E (slima_agents 補充) ← 獨立，視需求進行
```

Phase A 是基礎，B 和 D 可以平行開發（B 只需要 IPC 存在，D 只需要 download API 存在），C 依賴 B 的 view 骨架。
