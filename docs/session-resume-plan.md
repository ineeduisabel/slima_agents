# Session Resume 架構設計

> 日期：2026-02-27
> 分支：`features/agent-ui`
> 前置：agent-ui-dev.md 中的 UI 整合計畫

---

## 問題分析

### 問題 1：每個 Agent 是一次性 Process

```
目前架構：
Orchestrator → claude -p "寫宇宙觀" → process exit → 結束
                                        ↑ Agent 如果反問「你想放哪裡？」
                                          使用者沒辦法回答，conversation 已結束
```

每個 Agent 是一次 `claude -p` 呼叫，收到 `{"type":"result"}` 就結束。沒有對話延續能力。

### 問題 2：冗餘 MCP 讀取

每個 Agent 獨立執行時：

```
1. 系統從 system_prompt 獲得完整序列化 context（20-30KB，越後面越大）
2. Agent 仍然呼叫 get_book_structure()（因為它想「確認」有什麼）
3. Agent 呼叫 read_file() 讀取它想參考的檔案（即使 system_prompt 已有摘要）
4. 每個 Agent 重複以上循環
```

**量化冗餘**（以 Worldbuild 12 階段管線為例）：

| 階段 | Agent 數 | 預估 MCP calls/agent | 階段合計 |
|------|---------|---------------------|---------|
| 4 (基礎) | 3 並行 | ~3-4 (structure + reads) | ~10 |
| 5 (文化) | 2 並行 | ~3-4 | ~7 |
| 6 (權力) | 1 | ~4 | ~4 |
| 7 (細節) | 3 並行 | ~4-5 | ~13 |
| 8 (敘事) | 1 | ~5 | ~5 |
| 10 (驗證R1) | 1 | ~15-20 (讀全部) | ~18 |
| 11 (驗證R2) | 1 | ~15-20 (讀全部) | ~18 |
| **合計** | | | **~75** |

Orchestrator 自己在階段間也呼叫 `get_book_structure()` × 5 次 + `_get_all_file_paths()` × 12 次。

**其中 R1 和 R2 讀取完全重疊** — R2 重新讀一遍 R1 已經讀過的所有檔案。

### 問題 3：Context 膨脹

`serialize_for_prompt()` 回傳的字串隨管線進度成長：

| 階段 | system_prompt 約大小 |
|------|-------------------|
| ResearchAgent | ~2KB (指令) |
| CosmologyAgent (階段4) | ~15-20KB (指令 + 12 sections) |
| NarrativeAgent (階段8) | ~25-30KB (指令 + 大量前置內容) |
| ValidationAgent (階段10) | ~30KB+ |

每個 Agent 都接收**完整** context，即使它只需要部分 sections。

### 問題 4：Mystery 管線恢復模式的脆弱性

目前 `_restore_context_from_book()` 透過逐個讀取檔案重建 context：

```python
# 分別讀取：overview, crime_design, characters (N個), plot, chapters (12個)
# 總共 ~15-20 次 REST API 呼叫
# 用 filename 猜 act1/act2/act3 歸屬（脆弱）
```

---

## Claude CLI `--resume` 能力分析

### 基本語法

```bash
# 一次性（目前用法）
claude -p "prompt" --output-format stream-json

# 延續最近一次對話
claude -p "繼續" --continue --output-format stream-json

# 指定 session 延續
claude -p "繼續" --resume <session-id> --output-format stream-json
```

### 關鍵限制

| 特性 | 說明 |
|------|------|
| System prompt | **固定**，resume 時不能改變 |
| 對話記憶 | 保留完整歷史（包含 tool calls 和結果） |
| Compaction | 對話過長時 Claude CLI 自動壓縮舊訊息 |
| Session 儲存 | 存在 `~/.claude/` 本地目錄 |
| stream-json 輸出 | **待確認**：result event 是否包含 `session_id` |

### 核心約束：System Prompt 不可變

這是最關鍵的限制。`--resume` 延續同一個 session，system prompt 保持不變。

這意味著：
- **可以** chain 同一個 Agent 的多輪（例如 Validation R1 → R2，同一個 system prompt）
- **不能** chain 不同 Agent（CosmologyAgent → GeographyAgent 有不同 system prompt）
- **可以** 用於互動式對話（Ask Agent，system prompt 固定為通用查詢指令）

---

## Session Resume 適用場景分析

### 適用（直接受益）

#### A. Validation R1 → R2 Session Chain

```
目前：
  R1 = claude -p "檢查一致性" → 讀取全部檔案 → 修復問題 → exit
  R2 = claude -p "確認修復"   → 讀取全部檔案 → 驗證修復 → exit
                                 ↑ 重複讀取 15-20 個檔案

改後：
  R1 = claude -p "檢查一致性" → 讀取全部 → 修復 → exit (回傳 session_id)
  R2 = claude -p "確認修復" --resume <session_id> → 不需重讀，已在 context → 驗證 → exit
```

- **節省**：~15-20 次 MCP read_file
- **改動量**：小（ClaudeRunner 擷取 session_id + BaseAgent 支援 resume）
- **風險**：低（Validation 已是同一個 Agent class，同一個 system prompt）

#### B. Interactive Ask Agent

```
Round 1：
  ask = claude -p "分析角色關係" → 讀取角色檔案 → 回答 → exit (session_id = "abc123")

Round 2（使用者追問）：
  ask = claude -p "那反派呢？" --resume "abc123" → 角色資料已在 context → 直接回答
                                                   ↑ 不需重讀檔案
```

- **節省**：每次追問省 3-5 次 MCP read_file
- **使用者體驗**：大幅提升（連續對話 vs 每次重新開始）
- **改動量**：中（ClaudeRunner + CLI + 前端 session 管理）

#### C. Agent 失敗恢復

```
目前（timeout）：
  Agent timed out → 回傳 partial success → 從下一階段開始

改後（timeout）：
  Agent timed out → 回傳 partial success + session_id
  恢復時：claude -p "繼續你的工作" --resume <session_id>
  → Agent 記得之前做了什麼 → 繼續完成
```

- **節省**：避免從頭重跑整個 Agent
- **改動量**：中

### 部分適用（需要架構調整）

#### D. 合併 Act Writer（Act1 + Act2 + Act3 → 單一 Agent）

```
目前：3 個獨立 Agent，各有不同 system prompt
  ACT1_INSTRUCTIONS → 寫 ch1-4
  ACT2_INSTRUCTIONS → 寫 ch5-8（需重讀 ch1-4）
  ACT3_INSTRUCTIONS → 寫 ch9-12（需重讀 ch1-8）

合併方案：1 個 ActWriterAgent + 統一 system prompt
  Round 1：claude -p "寫第一幕 ch1-4" → session_id
  Round 2：claude -p "寫第二幕 ch5-8" --resume → 已有 ch1-4 在 context
  Round 3：claude -p "寫第三幕 ch9-12" --resume → 已有 ch1-8 在 context
```

- **節省**：Act2 省讀 4 章 + Act3 省讀 8 章（每章讀取 = 1 MCP call）
- **改動量**：**大**（重構 3 個 Agent → 1 個，統一 system prompt，改 orchestrator）
- **風險**：統一 system prompt 可能降低各幕的寫作品質（指令不夠針對性）
- **替代方案**：在 Act2 的 system prompt 裡直接嵌入 Act1 的摘要（現在已部分實作：`_summarize_chapters()`）

### 不適用

#### E. 不同 Specialist Agent 之間

```
❌ CosmologyAgent → GeographyAgent
   不同 system prompt，不能用 --resume
```

#### F. 並行 Agent 之間

```
❌ Cosmology ⟶
   Geography ⟶  各自獨立 session
   History   ⟶
```

---

## Compaction（對話壓縮）處理策略

### Compaction 的本質

Claude CLI 在對話過長（接近 context window 上限）時，會自動壓縮（summarize）較早的訊息。這是 Claude CLI 內建行為，不可關閉。

### 對不同場景的影響

| 場景 | 對話長度 | Compaction 風險 | 影響 |
|------|---------|----------------|------|
| 單一 Specialist Agent | 10-30 turns | 低 | 幾乎不會觸發 |
| Validation R1→R2 | 30-60 turns | 中 | R1 尾端的修復細節可能被壓縮 |
| Act Writer 合併 | 60-100+ turns | **高** | Act1 的章節內容可能被壓縮掉 |
| Interactive Ask (長對話) | 不定 | 高（20+ 輪後） | 早期討論細節會丟失 |

### 因應策略

```
策略 1：信任檔案儲存（最關鍵）
  ├── 所有重要產出都已寫入 Slima 書籍（MCP write_file/create_file）
  ├── Compaction 壓縮的是「對話歷史」，不是「檔案內容」
  └── Agent 隨時可以重新 read_file() 取回原始內容

策略 2：System Prompt 錨定
  ├── System prompt 永遠不會被 compaction
  ├── 把最關鍵的指令放在 system prompt（已經是這樣）
  └── Context snapshot 也可以嵌入 system prompt

策略 3：定期檢查點
  ├── 在 Session Chain 中，每 N 輪後寫一個「狀態摘要」到書籍
  └── 如果 compaction 造成遺漏，Agent 可以從檢查點檔案恢復

策略 4：不要 chain 太長
  ├── Validation R1→R2 = 2 輪，安全
  ├── Act Writer 合併 = 3 輪，borderline
  └── Interactive Ask = 預期 compaction，設計上容忍它
```

### 前端 Compaction 呈現

```
┌─ Ask 對話 ──────────────────────────────────────────────┐
│                                                          │
│  [系統提示] 部分早期對話已被壓縮以節省 context              │
│                                                          │
│  ─── 壓縮區域 ─────────────────                          │
│  （前 12 則訊息已摘要）                                    │
│  摘要：討論了角色關係圖，確認了偵探和嫌疑犯的動機連結          │
│  ───────────────────────────────                          │
│                                                          │
│  [使用者] 那兇器的部分呢？                                 │
│  [Agent]  根據犯罪設計檔案...                              │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**但實務上**：Claude CLI 的 compaction 是透明的，不會在 stream-json 產生特殊事件。前端可能不知道 compaction 發生了。最好的策略是**設計上容忍 compaction** — 依賴檔案而非對話記憶。

---

## 降低冗餘讀取的其他策略（不依賴 Session Resume）

Session Resume 只解決部分問題（同 Agent 多輪）。以下策略解決跨 Agent 冗餘：

### 策略 A：Context 選擇性序列化

目前每個 Agent 都收到完整 12 sections。但不是每個都需要全部：

```python
# 目前：
def system_prompt(self) -> str:
    ctx = self.context.serialize_for_prompt()  # 全部 12 sections
    return f"{COSMOLOGY_INSTRUCTIONS}\n\n{ctx}"

# 改為：
def system_prompt(self) -> str:
    ctx = self.context.serialize_sections(
        ["overview", "cosmology", "naming_conventions", "book_structure"]
    )
    return f"{COSMOLOGY_INSTRUCTIONS}\n\n{ctx}"
```

每個 Agent 只接收它需要的 sections：

| Agent | 需要的 Sections |
|-------|----------------|
| Cosmology | overview, naming_conventions, book_structure |
| Geography | overview, cosmology, naming_conventions, book_structure |
| History | overview, cosmology, geography, naming_conventions, book_structure |
| Characters | overview, peoples, cultures, power_structures, naming, book_structure |
| Validation | **全部**（它要檢查一致性） |

**效果**：system_prompt 大小從 ~30KB 降到 ~10-15KB（後期 Agent）

### 策略 B：Context Snapshot 檔案

在書籍內維護一個 JSON 快照，取代逐檔重建：

```python
# Orchestrator 在每個階段完成後：
async def _save_context_snapshot(self, book_token: str) -> None:
    snapshot = {
        section: getattr(self.context, section)
        for section in self.context.SECTIONS
        if getattr(self.context, section)
    }
    snapshot["user_prompt"] = self.context.user_prompt
    await self.slima.write_file(
        book_token,
        path="agent-log/context-snapshot.json",
        content=json.dumps(snapshot, ensure_ascii=False),
    )

# 恢復時：
async def _restore_from_snapshot(self, book_token: str) -> None:
    resp = await self.slima.read_file(book_token, "agent-log/context-snapshot.json")
    snapshot = json.loads(resp.content)
    for section, value in snapshot.items():
        if section == "user_prompt":
            self.context.user_prompt = value
        elif section in self.context.SECTIONS:
            await self.context.write(section, value)
```

**效果**：恢復模式從 ~20 REST calls → 1 REST call

### 策略 C：Orchestrator 層 Book Structure 快取

```python
# 目前：每個 Agent 階段前後各呼叫一次 get_book_structure
# 每個 Agent 內部又呼叫一次 get_book_structure

# 改為：Orchestrator 維護記憶體快取
class OrchestratorAgent:
    def __init__(self):
        self._cached_structure = None
        self._structure_dirty = True

    async def _inject_book_structure(self, book_token):
        # 只在 dirty 時重新讀取
        if self._structure_dirty:
            structure = await self.slima.get_book_structure(book_token)
            self._cached_structure = structure
            self._structure_dirty = False
        tree_str = format_structure_tree(self._cached_structure)
        await self.context.write("book_structure", tree_str)

    # Agent 完成後標記 dirty（因為可能建立了新檔案）
```

這只節省 Orchestrator 層的呼叫。Agent 內部的 MCP `get_book_structure()` 由 Claude 自己決定是否呼叫，無法從 Orchestrator 控制。

---

## 分層實作計畫

### Layer 0：確認 Claude CLI 行為（前置條件）

需要確認：
1. `claude -p --output-format stream-json` 的 result event 是否包含 `session_id`
2. `--resume <session_id>` 搭配 `-p` 和 `--output-format stream-json` 是否正常運作
3. `--resume` 時是否可以指定不同的 `--allowedTools`（理論上不行，但需確認）

```bash
# 測試指令
claude -p "hello" --output-format stream-json 2>/dev/null | grep session
claude -p "continue" --resume <id> --output-format stream-json
```

### Layer 1：ClaudeRunner Session ID 擷取

**檔案變更**：`src/slima_agents/agents/claude_runner.py`

```python
@dataclass
class RunOutput:
    text: str
    num_turns: int = 0
    cost_usd: float = 0.0
    timed_out: bool = False
    session_id: str = ""          # ← 新增

class ClaudeRunner:
    @staticmethod
    async def run(
        prompt: str,
        system_prompt: str,
        ...,
        resume_session: str = "",   # ← 新增：傳入 session_id 來延續
    ) -> RunOutput:
        cmd = ["claude", "-p", prompt, ...]
        if resume_session:
            cmd.extend(["--resume", resume_session])
        ...
```

**stream reader 修改**：

```python
elif etype == "result":
    result_text = event.get("result", "")
    num_turns = event.get("num_turns", 0)
    cost_usd = event.get("total_cost_usd", 0.0)
    session_id = event.get("session_id", "")  # ← 擷取 session_id
```

### Layer 2：BaseAgent + AgentResult 支援 Session

**檔案變更**：`src/slima_agents/agents/base.py`

```python
class AgentResult:
    def __init__(self, ..., session_id: str = ""):
        ...
        self.session_id = session_id

class BaseAgent:
    def __init__(self, ..., resume_session: str = ""):
        ...
        self.resume_session = resume_session

    async def run(self) -> AgentResult:
        ...
        output = await ClaudeRunner.run(
            ...,
            resume_session=self.resume_session,
        )
        return AgentResult(
            ...,
            session_id=output.session_id,
        )
```

### Layer 3：Validation R1 → R2 Session Chain

**檔案變更**：`src/slima_agents/worldbuild/orchestrator.py` + `src/slima_agents/mystery/orchestrator.py`

```python
# Worldbuild orchestrator
r1_agent = ValidationAgent(**agent_kwargs, validation_round=1)
r1_result = await r1_agent.run()
r1_session = r1_result.session_id

# R2 延續 R1 的 session
r2_agent = ValidationAgent(
    **agent_kwargs,
    validation_round=2,
    resume_session=r1_session,  # ← 延續 R1
)
r2_result = await r2_agent.run()
```

**注意**：如果 `--resume` 時 system_prompt 被忽略（因為 session 已有），R2 的 initial_message() 需要包含 "Now verify your fixes" 的指令，不能只依賴 system_prompt。

### Layer 4：Context Snapshot 持久化

**新增檔案**：無（修改 orchestrator）

在 orchestrator 的每個階段完成後，儲存 context snapshot：

```python
# orchestrator.py
async def _save_context_snapshot(self, book_token: str) -> None:
    """Save context as JSON for O(1) resume loading."""
    import json
    snapshot = {"user_prompt": self.context.user_prompt}
    for section in self.context.SECTIONS:
        value = getattr(self.context, section)
        if value:
            snapshot[section] = value
    await self.slima.write_file(
        book_token,
        path="agent-log/context-snapshot.json",
        content=json.dumps(snapshot, ensure_ascii=False, indent=2),
        commit_message="Update context snapshot",
    )
```

取代 `_restore_context_from_book()` 的脆弱邏輯。

### Layer 5：Interactive Ask Agent Session Management

**CLI 層面**：

```python
# cli.py
@cli.command()
@click.option("--session", default="", help="Resume a previous session")
def ask(prompt, book, session, ...):
    ...
    result = await ask_agent.run()
    # 在 NDJSON 或 exit 時輸出 session_id
    if result.session_id:
        emit({"event": "session_id", "session_id": result.session_id})
```

**前端層面**：

```typescript
// agentStore.ts
interface AgentRun {
  ...
  sessionId?: string  // ← 新增
}

// 追問時帶上 session
async runAsk(prompt, opts) {
  const args = ['ask', prompt]
  if (opts.session) args.push('--session', opts.session)
  ...
}
```

### Layer 6（未來）：選擇性 Context 序列化

```python
# context.py
def serialize_sections(self, sections: list[str]) -> str:
    parts = []
    if self.user_prompt:
        parts.append(f"## User Request\n{self.user_prompt}")
    for section in sections:
        value = getattr(self, section)
        if value:
            header = section.replace("_", " ").title()
            parts.append(f"## {header}\n{value}")
    return "\n\n".join(parts) or "(No context populated yet.)"

# 各 Agent 定義自己需要的 sections
class CosmologyAgent(BaseAgent):
    RELEVANT_SECTIONS = ["overview", "naming_conventions", "book_structure"]

    def system_prompt(self) -> str:
        ctx = self.context.serialize_sections(self.RELEVANT_SECTIONS)
        return f"{COSMOLOGY_INSTRUCTIONS}\n\n{ctx}"
```

---

## Worldbuild 管線：Session Resume 不是主要解法

使用者問到「worldbuild agent 似乎一直獨立運作，能不能用 session 減少重複 read？」

**回答**：Worldbuild 管線有 10 個不同 Specialist Agent，各有不同 system prompt。`--resume` 無法跨 Agent 使用。

Worldbuild 管線降低冗餘讀取的正確策略是：

| 策略 | 影響 | 優先度 |
|------|------|--------|
| Validation R1→R2 session chain | 省 ~18 MCP calls | **P1** |
| Context snapshot 取代逐檔恢復 | 省 ~20 REST calls（恢復模式） | **P1** |
| 選擇性 context 序列化 | 省 ~40% system prompt tokens | P2 |
| Orchestrator structure 快取 | 省 ~5 REST calls | P3 |
| Agent 內部 MCP calls | **無法控制**（Claude 自行決定） | - |

**核心認知**：Agent 在 Claude session 內呼叫 MCP 工具（`get_book_structure`, `read_file`）是 Claude 模型自行決定的行為，我們只能透過 system prompt 指引它，不能強制禁止。即使 system prompt 已包含 book structure，Claude 可能仍然呼叫 `get_book_structure()` 來「確認」。

---

## Mystery 管線：Session Resume 的最佳受益者

Mystery 管線是**全部依序**，且有恢復模式。Session Resume 在此更有價值：

| 改善 | 說明 |
|------|------|
| Validation R1→R2 chain | 同 worldbuild，省 ~18 calls |
| Context snapshot | 取代脆弱的 `_restore_context_from_book()`，1 call vs ~20 calls |
| 合併 Act Writer（可選） | 單一 session 寫 3 幕，省重讀 ~12 章，但需統一 system prompt |

### 合併 Act Writer 的取捨

```
合併：
  ✅ Act2 不需重讀 Act1 的 4 章（已在 session context）
  ✅ Act3 不需重讀 Act1+2 的 8 章
  ✅ 故事連貫性更好（同一個 Claude instance 寫三幕）
  ❌ 統一 system prompt 失去各幕的針對性指令
  ❌ Session 越長，compaction 風險越高（可能壓掉 Act1 的章節細節）
  ❌ 如果 Act2 timeout，無法只重跑 Act2

不合併（維持現狀 + _summarize_chapters）：
  ✅ 各幕有針對性 system prompt
  ✅ 可以單獨重跑某一幕
  ✅ Compaction 不是問題（每幕是獨立 session）
  ❌ Act2 需重讀 Act1（~4 MCP calls）
  ❌ Act3 需重讀 Act1+2（~8 MCP calls）
```

**建議**：先不合併 Act Writer。`_summarize_chapters()` 已經提供了合理的上下文傳遞。合併帶來的架構風險大於 ~12 次 MCP read 的節省。

---

## 實作優先順序

```
Phase 0: 確認 Claude CLI --resume 行為        ← 前置，blocking
    │
    ├─► Phase 1: ClaudeRunner session_id 擷取  (1 file, ~30 lines)
    │       │
    │       ├─► Phase 2: BaseAgent + AgentResult 支援 session (1 file, ~20 lines)
    │       │       │
    │       │       ├─► Phase 3a: Validation R1→R2 chain (2 files, ~15 lines each)
    │       │       │
    │       │       └─► Phase 3b: Ask Agent session (1 file + CLI, ~40 lines)
    │       │
    │       └─► Phase 4: Context Snapshot (2 files, ~50 lines)
    │
    └─► Phase 5 (未來): 選擇性 context 序列化 (context.py + 10 agents)
```

### 預估改動量

| Phase | 檔案數 | 新增/修改行數 | 測試 |
|-------|--------|-------------|------|
| 1 | 1 (claude_runner.py) | ~30 | 修改 test_claude_runner mock |
| 2 | 1 (base.py) | ~20 | 修改 test_base_agent |
| 3a | 2 (orchestrators) | ~30 | 修改 test_orchestrator × 2 |
| 3b | 2 (cli.py + ask) | ~40 | 新增 test_ask_session |
| 4 | 2 (orchestrators) | ~50 | 修改 test_orchestrator × 2 |
| 5 | 11 (context + 10 agents) | ~100 | 修改各 agent test |

---

## 前端整合（Agent UI）

### Session 管理在 agentStore.ts

```typescript
interface AgentRun {
  // ... existing fields
  sessionId?: string           // ← Claude CLI session ID
  conversationHistory: Array<{
    role: 'user' | 'assistant'
    content: string
    timestamp: string
  }>
}
```

### Ask Agent 對話流程

```
┌─ Ask 對話 ──────────────────────────────────────────────┐
│                                                          │
│  Book: [海賊王世界觀 ▾]    ☐ 允許寫入                      │
│                                                          │
│  [使用者] 分析角色之間的關係                                 │
│  [Agent]  根據角色檔案，主要關係如下...                      │
│            Session: sess_abc123 (internal)                │
│                                                          │
│  [使用者] 那魔王和勇者的宿命對比呢？                         │
│  [Agent]  (--resume sess_abc123)                         │
│           從已讀取的角色檔案來看...                          │
│           ↑ 不需重讀檔案，直接引用 R1 的 context             │
│                                                          │
│  ┌──────────────────────────────────────────────┐ [送出] │
│  │ 追問...                                       │       │
│  └──────────────────────────────────────────────┘       │
│                                                          │
│  💡 長時間對話後，早期討論會被自動摘要。                      │
│     Agent 仍可重新讀取書籍檔案來確認細節。                    │
│                                            [新對話]       │
└──────────────────────────────────────────────────────────┘
```

### Worldbuild 進度面板（無變化）

Worldbuild 管線的前端進度 UI 不受 session resume 影響。管線仍然是階段制，每個階段顯示 Agent 卡片。

唯一變化：Validation 階段從「R1 完成 → R2 開始」變為「R1 完成 → R2 延續」，但 UI 表現相同（都是 agent_start → agent_complete）。

---

## 總結

### Session Resume 的核心價值

1. **Interactive Ask**：使用者可以連續對話，不需每次重新開始 — **體驗提升**
2. **Validation Chain**：R2 延續 R1，省去重複讀取全部檔案 — **效率提升**
3. **Failure Recovery**：timeout 後可以延續而非重跑 — **可靠性提升**

### 不是 Session Resume 的場景

1. **跨 Agent 冗餘讀取**：需要「選擇性 context 序列化」
2. **恢復模式效率**：需要「Context Snapshot」
3. **Agent 內部 MCP 行為**：無法控制（Claude 自行決定）

### 最重要的認知

> Session Resume 解決的是「同一個 Agent 的多輪對話」問題。
> 跨 Agent 的冗餘讀取需要其他策略（context 過濾、snapshot 快取）。
> 兩者互補，不是替代關係。
