# 前端整合指南：plan-build + status

> 適用於 `slima_vue`（Electron + Vue 3 + Pinia）
> 最後更新：2026-03-02

---

## 指令總覽

| 指令 | 用途 | stdin | stdout | 串流 |
|------|------|-------|--------|------|
| `status` | 檢查環境（Slima token + API + Model） | — | Rich text (stderr) | 否 |
| `plan-build` | 自然語言 → 驗證過的 TaskPlan JSON | 可選：既有 plan JSON | TaskPlan JSON 或 NDJSON | 可選 |
| `task-pipeline` | 執行多階段管線 | **必要**：TaskPlan JSON | NDJSON 事件流 | 是 |
| `task` | 單次 Agent 對話 | — | 文字或 JSON | 可選 |

---

## 1. `status` — 環境檢查

### 功能

驗證三件事：
1. Slima API token 是否存在且有效
2. Slima API 是否可連線（會實際呼叫 `list_books()`）
3. 當前使用的 model 名稱

### 呼叫方式

```typescript
const proc = spawn(binaryPath, ["status"], {
  env: { ...process.env, SLIMA_API_TOKEN: token },
});
```

### 輸出格式

`status` 使用 Rich console 輸出到 **stdout**（不是 NDJSON）：

```
Slima Token: ...abc12345
Slima URL: https://api.slima.ai
Model: claude-opus-4-6
Slima API: OK (7 books)
```

### Exit Code

| Code | 含義 |
|------|------|
| `0` | 全部通過 |
| `1` | Config 錯誤（token 不存在）或連線失敗 |

### 前端串接

```typescript
// electron/services/agentService.ts

async checkStatus(): Promise<{
  ok: boolean;
  output: string;
  error?: string;
}> {
  return new Promise((resolve) => {
    const proc = spawn(this.getBinaryPath(), ["status"], {
      env: { ...process.env, SLIMA_API_TOKEN: this.getToken() },
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    proc.stderr.on("data", (chunk) => { stderr += chunk.toString(); });

    proc.on("close", (code) => {
      if (code === 0) {
        resolve({ ok: true, output: stdout });
      } else {
        resolve({ ok: false, output: stdout, error: stderr || stdout });
      }
    });
  });
}
```

### 前端 UI 建議

環境檢查頁面（首次使用或設定頁）：

```
┌─ 環境檢查 ───────────────────────────────────────────┐
│                                                       │
│  ✅  Slima 認證     ...abc12345                       │
│  ✅  Slima API      OK (7 books)                      │
│  ✅  模型           claude-opus-4-6                   │
│                                                       │
│  一切就緒！                                            │
│                                                       │
│                              [重新檢查]                │
└───────────────────────────────────────────────────────┘
```

失敗時：

```
│  ❌  Slima 認證     找不到 token                       │
│      請在設定中輸入 Slima API Token                    │
│      或執行 slima-mcp auth                            │
│                              [重新檢查]                │
```

### 注意事項

- `status` **不需要 Claude CLI**（它只測 Slima API）
- 如果要額外檢查 Claude CLI，前端可自行 `spawn("claude", ["--version"])`
- `status` 的 stdout 包含 ANSI 顏色碼（Rich console），前端解析時建議 strip 顏色碼或使用 `--no-color` 環境變數：
  ```typescript
  env: { ...process.env, NO_COLOR: "1", SLIMA_API_TOKEN: token }
  ```

---

## 2. `plan-build` — 產生 TaskPlan JSON

### 功能

使用者用自然語言描述需求（如「建構一個奇幻世界觀」），AI 自動產生一個驗證過的 TaskPlan JSON。
此 JSON 可直接傳給 `task-pipeline` 執行。

### 核心特性

- **永遠只輸出 JSON** — stdout 只有 TaskPlan JSON（非串流模式）或 NDJSON 事件（串流模式）
- **錯誤輸出到 stderr** — 不會污染 stdout 的 JSON
- **支援修改既有 plan** — 透過 stdin 傳入既有 JSON，AI 會在此基礎上修改
- **Pydantic 驗證** — 輸出的 JSON 保證符合 TaskPlan schema

### CLI 介面

```
slima-agents plan-build [OPTIONS] PROMPT

Options:
  --model, -m          指定 Claude 模型
  --json-progress      輸出 NDJSON 串流事件（含 plan_build_result）
  --timeout            超時秒數（預設 300）
```

### 使用模式

#### 模式 A：簡單模式（stdout 直接輸出 JSON）

適合「產生後等完再處理」的場景。

```typescript
async planBuild(
  prompt: string,
  existingPlan?: string,
): Promise<{ ok: boolean; plan?: TaskPlan; error?: string }> {
  return new Promise((resolve) => {
    const args = ["plan-build", prompt];

    const proc = spawn(this.getBinaryPath(), args, {
      env: { ...process.env, SLIMA_API_TOKEN: this.getToken() },
    });

    // 如果有既有 plan，透過 stdin 傳入
    if (existingPlan) {
      proc.stdin.write(existingPlan);
    }
    proc.stdin.end();

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    proc.stderr.on("data", (chunk) => { stderr += chunk.toString(); });

    proc.on("close", (code) => {
      if (code === 0) {
        try {
          const plan = JSON.parse(stdout.trim());
          resolve({ ok: true, plan });
        } catch {
          resolve({ ok: false, error: "Failed to parse JSON output" });
        }
      } else {
        resolve({ ok: false, error: stderr || "plan-build failed" });
      }
    });
  });
}
```

#### 模式 B：串流模式（NDJSON 事件）

適合「即時顯示 AI 在想什麼」的場景。啟用 `--json-progress` 後，stdout 輸出 NDJSON 事件流。

```typescript
async planBuildStreaming(
  prompt: string,
  existingPlan?: string,
  callbacks: {
    onTextDelta?: (text: string) => void;
    onToolUse?: (toolName: string) => void;
    onResult?: (plan: TaskPlan, meta: PlanBuildMeta) => void;
    onError?: (error: string) => void;
  },
): Promise<void> {
  const args = ["plan-build", "--json-progress", prompt];

  const proc = spawn(this.getBinaryPath(), args, {
    env: { ...process.env, SLIMA_API_TOKEN: this.getToken() },
  });

  if (existingPlan) {
    proc.stdin.write(existingPlan);
  }
  proc.stdin.end();

  const rl = createInterface({ input: proc.stdout });

  rl.on("line", (line) => {
    try {
      const event = JSON.parse(line);

      switch (event.event) {
        case "text_delta":
          callbacks.onTextDelta?.(event.text);
          break;

        case "tool_use":
          callbacks.onToolUse?.(event.tool_name);
          break;

        case "plan_build_result":
          // plan_json 是驗證過的 TaskPlan JSON 字串
          const plan = JSON.parse(event.plan_json);
          callbacks.onResult?.(plan, {
            sessionId: event.session_id,
            numTurns: event.num_turns,
            costUsd: event.cost_usd,
            durationS: event.duration_s,
          });
          break;

        case "error":
          callbacks.onError?.(event.message);
          break;
      }
    } catch {
      // 非 JSON 行，忽略
    }
  });

  // stderr = Rich console 日誌
  proc.stderr.on("data", (chunk) => {
    const text = chunk.toString();
    if (text.includes("JSON extraction error:") || text.includes("Validation error:")) {
      callbacks.onError?.(text);
    }
  });

  return new Promise((resolve) => {
    proc.on("close", () => resolve());
  });
}
```

### NDJSON 事件流（`--json-progress`）

串流模式下，stdout 的事件順序：

```jsonc
// 1. AI 產生文字時（即時串流）
{"event": "text_delta", "agent": "PlanBuilder", "text": "```json\n{..."}

// 2. AI 使用工具時（plan-build 用 tool_set="none"，通常只有 WebSearch/WebFetch）
{"event": "tool_use", "agent": "PlanBuilder", "tool_name": "WebSearch"}

// 3. 最終結果（驗證過的 TaskPlan JSON）
{
  "event": "plan_build_result",
  "timestamp": "2026-03-02T10:30:00.000000+00:00",
  "plan_json": "{\"title\":\"奇幻世界觀\",\"book_token\":\"\",\"stages\":[...]}",
  "session_id": "sess_abc123",
  "num_turns": 3,
  "cost_usd": 0.0321,
  "duration_s": 45.68
}
```

### `plan_build_result` 事件欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `event` | string | 固定為 `"plan_build_result"` |
| `timestamp` | string | ISO 8601 UTC 時間 |
| `plan_json` | string | **驗證過的 TaskPlan JSON 字串**（需再 `JSON.parse` 一次） |
| `session_id` | string | Claude session ID（可用於 debug） |
| `num_turns` | int | AI 使用的回合數 |
| `cost_usd` | float | 預估費用（USD） |
| `duration_s` | float | 耗時（秒） |

### TaskPlan JSON 格式

`plan_json` 解析後的結構：

```typescript
interface TaskPlan {
  title: string;       // 非空 → 自動建書；空 → 不建書
  book_token: string;  // 非空 → 用既有書；空 → 不指定
  stages: TaskStageDefinition[];  // 至少 1 個
}

interface TaskStageDefinition {
  number: number;           // 執行順序（同 number = 平行）
  name: string;             // 機器 ID（snake_case）
  display_name?: string;    // 人類可讀名稱
  prompt: string;           // 給 Agent 的指令
  system_prompt?: string;   // 自訂 system prompt
  tool_set?: string;        // "write" | "read" | "all" | "none"（預設 "read"）
  plan_first?: boolean;     // 先規劃再執行
  context_section?: string; // 存結果到此 context section
  chain_to_previous?: boolean; // 接續前一 stage 的 session
  timeout?: number;         // 超時秒數（預設 3600）
}
```

### Exit Code

| Code | 含義 |
|------|------|
| `0` | 成功，stdout 有合法的 TaskPlan JSON |
| `1` | 失敗：AI 回了非 JSON / schema 不對 / timeout / 其他錯誤 |
| `130` | 使用者取消（Ctrl+C / SIGTERM） |

### 錯誤處理

所有錯誤輸出到 **stderr**，格式為 Rich console 文字：

```
JSON extraction error: No valid JSON object found in text
```
```
Validation error: stages must contain at least 1 stage
```
```
Error: Timed out after 300s
```

### 修改既有 plan

使用者在 UI 上編輯完 plan 後想用 AI 微調：

```typescript
// 使用者說「把第二階段的 prompt 改得更詳細」
const existingPlan = JSON.stringify(currentPlan);
const result = await planBuild("把第二階段的 prompt 改得更詳細", existingPlan);
// result.plan 是修改後的 TaskPlan
```

AI 會看到既有 plan 的完整 JSON，並根據使用者的自然語言指令修改。

---

## 3. 完整工作流：plan-build → task-pipeline

```
使用者輸入需求                     前端 UI                      Binary
─────────────────────────────────────────────────────────────────────────
"建構一個奇幻世界觀"
       │
       ▼
  [plan-build]  ─────────────→  spawn plan-build ──────→  AI 產生 plan
                                     │
                                     │ plan_build_result
                                     ▼
                                顯示 plan 給使用者
                                     │
                                使用者可：
                                ├─ ✅ 直接執行
                                ├─ ✏️  手動編輯 JSON
                                └─ 🤖 再次 plan-build 修改
                                     │
                                     ▼ (確認)
  [task-pipeline] ───────────→  spawn task-pipeline ──→  依序/平行執行
                                stdin: plan JSON           stages
                                     │
                                     │ NDJSON 事件流
                                     ▼
                                即時更新進度 UI
                                     │
                                     │ pipeline_complete
                                     ▼
                                完成！顯示書籍連結
```

### 前端完整範例

```typescript
// src/stores/agentStore.ts

export const useAgentStore = defineStore("agent", () => {
  const plan = ref<TaskPlan | null>(null);
  const planMeta = ref<PlanBuildMeta | null>(null);
  const status = ref<"idle" | "planning" | "plan_ready" | "executing" | "done" | "error">("idle");
  const error = ref<string>("");
  const planningText = ref<string>("");  // AI 思考過程（串流用）

  // Step 1: 產生 plan
  async function generatePlan(prompt: string, existingPlan?: string) {
    status.value = "planning";
    planningText.value = "";
    error.value = "";

    await window.electronAPI.agent.planBuildStreaming(prompt, existingPlan, {
      onTextDelta(text) {
        planningText.value += text;  // 顯示 AI 思考過程
      },
      onResult(resultPlan, meta) {
        plan.value = resultPlan;
        planMeta.value = meta;
        status.value = "plan_ready";
      },
      onError(err) {
        error.value = err;
        status.value = "error";
      },
    });
  }

  // Step 2: 修改 plan（用 AI）
  async function refinePlan(feedback: string) {
    if (!plan.value) return;
    await generatePlan(feedback, JSON.stringify(plan.value));
  }

  // Step 3: 執行 plan
  async function executePlan() {
    if (!plan.value) return;
    status.value = "executing";

    await window.electronAPI.agent.runTaskPipeline(
      JSON.stringify(plan.value),
      {
        onPipelineStart(totalStages) { /* 初始化進度 UI */ },
        onStageStart(stage, name, agents) { /* 更新階段 */ },
        onAgentComplete(stage, agent, duration, summary) { /* 更新 agent 卡片 */ },
        onBookCreated(bookToken, title) { /* 記錄 book */ },
        onFileCreated(path) { /* 更新檔案列表 */ },
        onPipelineComplete(bookToken, duration, success) {
          status.value = success ? "done" : "error";
        },
        onError(message) { error.value = message; },
      },
    );
  }

  return { plan, planMeta, status, error, planningText, generatePlan, refinePlan, executePlan };
});
```

### UI 狀態機

```
┌──────────┐  generatePlan()  ┌──────────┐  onResult  ┌────────────┐
│   idle   │ ───────────────→ │ planning │ ─────────→ │ plan_ready │
└──────────┘                  └──────────┘            └─────┬──────┘
                                   │                        │
                                onError                  三個選項：
                                   │                   ┌────┴────────────┐
                                   ▼                   │                 │
                              ┌──────────┐    refinePlan()         executePlan()
                              │  error   │         │                   │
                              └──────────┘         ▼                   ▼
                                              回到 planning      ┌───────────┐
                                                                 │ executing │
                                                                 └─────┬─────┘
                                                                       │
                                                              pipeline_complete
                                                                       │
                                                                       ▼
                                                                 ┌──────────┐
                                                                 │   done   │
                                                                 └──────────┘
```

### Plan 編輯 UI 建議

```
┌─ Pipeline Plan ───────────────────────────────────────────────┐
│                                                                │
│  📖 Title: 奇幻世界觀                                          │
│                                                                │
│  ┌─ Stage 1 ──────────────────────────────────────────────┐   │
│  │ 🔍 research (需求分析)         tool_set: none          │   │
│  │ prompt: 分析奇幻世界觀的核心元素...                      │   │
│  │ context_section: overview                               │   │
│  └────────────────────────────────────────────────────────┘   │
│                          ↓                                     │
│  ┌─ Stage 2a ─────────────────┐  ┌─ Stage 2b ──────────────┐ │
│  │ ✏️ cosmology (宇宙觀)       │  │ ✏️ geography (地理)       │ │
│  │ tool_set: write             │  │ tool_set: write          │ │
│  │ (平行執行)                   │  │ (平行執行)                │ │
│  └─────────────────────────────┘  └──────────────────────────┘ │
│                          ↓                                     │
│  ┌─ Stage 3 ──────────────────────────────────────────────┐   │
│  │ ✏️ characters (角色設計)      tool_set: write           │   │
│  │ plan_first: true                                        │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                │
│  耗時: 45.7s  費用: $0.032  AI 回合: 3                         │
│                                                                │
│  [🤖 AI 修改]  [✏️ 手動編輯 JSON]  [▶️ 開始執行]                 │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. TypeScript 型別定義

```typescript
// src/types/agent.ts

// ===== TaskPlan（對應 Python TaskPlan） =====

export interface TaskStageDefinition {
  number: number;
  name: string;
  display_name?: string;
  prompt: string;
  system_prompt?: string;
  tool_set?: "write" | "read" | "all" | "none";
  plan_first?: boolean;
  context_section?: string;
  chain_to_previous?: boolean;
  timeout?: number;
}

export interface TaskPlan {
  title: string;
  book_token: string;
  stages: TaskStageDefinition[];
}

// ===== NDJSON Events =====

export interface PlanBuildMeta {
  sessionId: string;
  numTurns: number;
  costUsd: number;
  durationS: number;
}

export interface NdjsonBaseEvent {
  event: string;
  timestamp: string;
}

export interface PlanBuildResultEvent extends NdjsonBaseEvent {
  event: "plan_build_result";
  plan_json: string;       // JSON string → JSON.parse() → TaskPlan
  session_id: string;
  num_turns: number;
  cost_usd: number;
  duration_s: number;
}

export interface TextDeltaEvent extends NdjsonBaseEvent {
  event: "text_delta";
  agent: string;
  text: string;
  stage?: number;
}

export interface ToolUseEvent extends NdjsonBaseEvent {
  event: "tool_use";
  agent: string;
  tool_name: string;
  stage?: number;
}

export interface PipelineStartEvent extends NdjsonBaseEvent {
  event: "pipeline_start";
  prompt: string;
  total_stages: number;
}

export interface StageStartEvent extends NdjsonBaseEvent {
  event: "stage_start";
  stage: number;
  name: string;
  agents: string[];
}

export interface StageCompleteEvent extends NdjsonBaseEvent {
  event: "stage_complete";
  stage: number;
  name: string;
  duration_s: number;
}

export interface AgentStartEvent extends NdjsonBaseEvent {
  event: "agent_start";
  stage: number;
  agent: string;
}

export interface AgentCompleteEvent extends NdjsonBaseEvent {
  event: "agent_complete";
  stage: number;
  agent: string;
  duration_s: number;
  timed_out: boolean;
  summary: string;
  num_turns: number;
  cost_usd: number;
}

export interface BookCreatedEvent extends NdjsonBaseEvent {
  event: "book_created";
  book_token: string;
  title: string;
  description: string;
}

export interface FileCreatedEvent extends NdjsonBaseEvent {
  event: "file_created";
  path: string;
}

export interface TaskResultEvent extends NdjsonBaseEvent {
  event: "task_result";
  session_id: string;
  result: string;
  num_turns: number;
  cost_usd: number;
  duration_s: number;
}

export interface PipelineCompleteEvent extends NdjsonBaseEvent {
  event: "pipeline_complete";
  book_token: string;
  total_duration_s: number;
  success: boolean;
}

export interface ErrorEvent extends NdjsonBaseEvent {
  event: "error";
  message: string;
  stage?: number;
  agent?: string;
}

export type NdjsonEvent =
  | PlanBuildResultEvent
  | TextDeltaEvent
  | ToolUseEvent
  | PipelineStartEvent
  | StageStartEvent
  | StageCompleteEvent
  | AgentStartEvent
  | AgentCompleteEvent
  | BookCreatedEvent
  | FileCreatedEvent
  | TaskResultEvent
  | PipelineCompleteEvent
  | ErrorEvent;
```

---

## 5. Preload IPC 介面建議

```typescript
// electron/preload.ts — agent namespace

agent: {
  // 環境檢查
  checkStatus(): Promise<{ ok: boolean; output: string; error?: string }>;

  // Plan 產生（簡單模式）
  planBuild(prompt: string, existingPlan?: string): Promise<{
    ok: boolean;
    plan?: TaskPlan;
    error?: string;
  }>;

  // Plan 產生（串流模式）— 需要 event listener
  planBuildStreaming(prompt: string, existingPlan?: string): void;
  onPlanBuildText(callback: (text: string) => void): () => void;
  onPlanBuildResult(callback: (plan: TaskPlan, meta: PlanBuildMeta) => void): () => void;
  onPlanBuildError(callback: (error: string) => void): () => void;

  // Pipeline 執行
  runTaskPipeline(planJson: string): void;
  onProgress(callback: (event: NdjsonEvent) => void): () => void;
  onExit(callback: (info: { code: number }) => void): () => void;

  // 取消
  cancel(): void;
}
```

---

## 6. 環境變數

spawn binary 時需注入的環境變數：

| 變數 | 必要 | 說明 |
|------|------|------|
| `SLIMA_API_TOKEN` | **是** | Slima API token（從 Electron authService 取得） |
| `SLIMA_AGENTS_MODEL` | 否 | 覆蓋預設模型（或用 `--model` flag） |
| `NO_COLOR` | 建議 | 設為 `"1"` 可關閉 Rich ANSI 顏色碼，方便解析 stderr |

```typescript
const env = {
  ...process.env,
  SLIMA_API_TOKEN: token,
  NO_COLOR: "1",  // 避免 ANSI 碼干擾 stderr 解析
};
```

---

## 7. 錯誤處理摘要

| 場景 | Exit Code | stderr 訊息 | 前端處理 |
|------|-----------|-------------|---------|
| Token 不存在 | 1 | `Config error: ...` | 引導設定 token |
| API 連線失敗 | 1 | `Connection error: ...` | 提示網路問題 |
| AI 回非 JSON | 1 | `JSON extraction error: ...` | 提示重試 |
| JSON schema 不合法 | 1 | `Validation error: ...` | 提示重試 |
| Timeout | 1 | `Error: Timed out...` | 提示增加 timeout 或簡化需求 |
| 使用者取消 | 130 | `Cancelled.` | 回到 idle |
| Binary 不存在 | — | spawn ENOENT | 引導下載 binary |
