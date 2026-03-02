# TaskPipeline 前端整合指南

## 概念

`task-pipeline` 讓前端用 JSON 定義一組 stages，每個 stage 對應一個 `TaskAgent`。
Orchestrator 會依序/平行執行，並透過 NDJSON 串流事件回傳進度。

核心規則：**同 number = 平行，不同 number = 依序**。

## TaskPlan JSON Schema

```jsonc
{
  // 書名（有值 → 自動建書）
  "title": "奇幻世界觀",

  // 或用既有書（有值 → 跳過建書）
  // "book_token": "bk_abc123",

  // 都不填 = 無書模式（agents 不帶 book_token）

  "stages": [
    {
      "number": 1,             // 執行順序（必填，同 number = 平行）
      "name": "research",      // Machine ID（必填，唯一）
      "display_name": "需求分析", // 前端顯示名（選填，空 = 用 name）
      "prompt": "分析...",      // 給 agent 的 user message（必填）
      "system_prompt": "",     // 自訂 system prompt（選填，空 = 預設）
      "tool_set": "none",     // 工具集（選填，預設 "read"）
      "plan_first": false,     // 是否先規劃再執行（選填）
      "include_language_rule": true, // 加入多語言規則（選填）
      "context_section": "overview", // 寫入哪個 context section（選填）
      "chain_to_previous": false,    // 接續前一 stage 的 session（選填）
      "timeout": 3600          // 超時秒數（選填，預設 3600）
    }
  ]
}
```

## 每個欄位的對應關係

```
前端 JSON                    → TaskAgent 參數             → 實際效果
─────────────────────────────────────────────────────────────────────
prompt                       → TaskAgent._prompt          → claude -p 的 user message
system_prompt                → TaskAgent._system_prompt   → claude -p 的 --system-prompt
                               （空值 = 預設通用 prompt）     agent 會自動附加 context
tool_set                     → TaskAgent._tool_set        → --allowedTools 過濾
  "write"                      SLIMA_MCP_TOOLS + Web        可建檔/寫檔/讀檔/搜尋
  "read"                       SLIMA_MCP_ALL_READ + Web     只能讀（預設值）
  "all"                        SLIMA_MCP_ALL + Web          全部 Slima 工具
  "none"                       Web only                     只有 WebSearch/WebFetch
include_language_rule        → 加入 LANGUAGE_RULE          → 強制 agent 用 prompt 的語言
plan_first                   → 加入 Planning Mode 指引     → agent 會先列計畫再執行
context_section              → （orchestrator 處理）       → 完成後寫入 context
chain_to_previous            → resume_session=上一個 ID    → claude --resume（共用對話）
```

## Context 傳遞機制

每個 agent 的 system prompt 會**自動包含**：

```
1. [可選] LANGUAGE_RULE（if include_language_rule=true）
2. system_prompt 或 預設 prompt
3. [可選] Planning Mode 指引（if plan_first=true）
4. # Target Book
   book_token: bk_xxx
5. # Current Context          ← 這裡就是累積的 context
   ## Pipeline Info
   Title: 奇幻世界觀
   Book: bk_xxx
   Total stages: 4
   Stage plan:
     1. 需求分析 (research)
     2. 宇宙觀 (cosmology)
     ...

   ## Overview                ← Stage 1 的 handoff
   [Stage 1 'Research' completed]
   Files created: ...
   ---
   （Stage 1 的完整輸出）

   ## Cosmology               ← Stage 2a 的 handoff
   [Stage 2 'Cosmology' completed]
   ...

   ## Book Structure          ← 自動注入的檔案樹
   worldview/
   ├── overview.md
   ├── cosmology/
   │   ├── overview.md
   ...
```

### 傳遞規則

| 情境 | 傳遞方式 |
|------|---------|
| Stage 2 要看 Stage 1 的結果 | Stage 1 設 `context_section: "overview"` → Stage 2 的 system prompt 自動包含 |
| Stage 3 要看 Stage 1 + 2 的結果 | 兩個都設 `context_section` → Stage 3 看到全部 |
| 相鄰 stage 需要完整對話記憶 | Stage 2 設 `chain_to_previous: true` → 共用 Claude session |
| 所有 stage 都要知道書的結構 | 自動：每個 group 完成後會注入 `book_structure` |
| 所有 stage 都要知道整體計畫 | 自動：`_pipeline_info` 永遠存在 |

## 完整範例：複製 Worldbuild 管線

以下 JSON 完全複製 worldbuild 的 12 階段管線行為：

```json
{
  "title": "海盜與航海冒險世界設定",
  "stages": [
    {
      "number": 1,
      "name": "research",
      "display_name": "需求分析",
      "prompt": "Research and analyze this world-building prompt, then output a comprehensive world context document.\n\nUser prompt: \"海盜與航海冒險世界設定\"\n\nIMPORTANT: Write ALL content in the same language as the prompt above.\n\nOutput your findings organized with these exact section headers:\n\n## Title\n(Create a short, clear title that tells the reader what this world is about.)\n\n## Description\n(1-2 sentence description.)\n\n## Overview\n(300-500 words: world type, era, tone, core premise)\n\n## Cosmology\n(300-500 words: physics, supernatural, magic system if any)\n\n## Geography\n(300-500 words: major regions, terrain, climate)\n\n## History\n(300-500 words: timeline, key events, eras)\n\n## Peoples\n(300-500 words: species, ethnic groups, demographics)\n\n## Cultures\n(300-500 words: religions, traditions, daily life)\n\n## Power Structures\n(300-500 words: governments, factions, military)\n\n## Characters\n(300-500 words: key figures, 15-25 character concepts)\n\n## Items\n(300-500 words: notable objects, artifacts, weapons)\n\n## Narrative\n(300-500 words: active conflicts, story hooks, mysteries)\n\n## Naming Conventions\n(naming patterns for each culture/region)",
      "system_prompt": "You are the Research Agent. Your job is to analyze the user's world-building prompt and produce a comprehensive research document covering all aspects of the world.\n\nDetermine the world type:\n- Known IP (game, novel, film, anime) → research canon material\n- Historical setting → research real historical facts\n- Original/fictional → design from genre conventions\n\nWrite 300-500+ words per section. Be specific, factual, and detailed.\nAt the end of each section, list 3-5 key reference sources.",
      "tool_set": "none",
      "include_language_rule": true,
      "context_section": "overview",
      "timeout": 3600
    },
    {
      "number": 2,
      "name": "cosmology",
      "display_name": "宇宙觀",
      "prompt": "Use the Slima MCP tools to create cosmology files in the target book.\n\nRead the existing book structure first, then create cosmology files organized in sub-folders:\n- overview.md (cosmological overview)\n- origin/ (creation myth, cosmological model)\n- supernatural/ (magic system, energy sources, forbidden arts)\n- afterlife/ (death cycle, spirit realms)\n- natural-laws.md\n\nCreate 6-12 files. Each file should be 800-2000+ words.\nWrite ALL content and file/folder names in the same language as the world context.",
      "system_prompt": "You are the Cosmology Specialist. Your job is to define the fundamental nature of this world.\n\nDefine what is physically possible and impossible. If magic/supernatural exists, define rules, costs, limitations in DETAIL. Explain the origin story. Detail the afterlife/death system. Define energy systems. Note forbidden practices.\n\n**Quality Standard:**\n- Create MANY files with sub-folders for organization.\n- Each file should be 800-2000+ words of rich, detailed content.\n- Cross-reference other world elements.\n- Add a References section at the bottom of every file with 3-8 sources.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "cosmology",
      "timeout": 3600
    },
    {
      "number": 2,
      "name": "geography",
      "display_name": "地理",
      "prompt": "Use the Slima MCP tools to create geography files in the target book.\n\nRead the existing book structure first, then create geography files:\n- overview.md (macro scale)\n- regions/ (one file per major region)\n- landmarks/ (one file per landmark)\n- climate-and-environment.md\n- strategic-locations.md\n\nCreate 8-15 files. Each file should be 800-2000+ words.\nWrite ALL content and file/folder names in the same language as the world context.",
      "system_prompt": "You are the Geography Specialist. Your job is to define the physical world.\n\nStart with a macro-scale overview, then create individual region files. Each region: terrain, climate, resources, population, strategic importance. Create 5-10 landmark files. Note how geography shapes culture, trade, and conflict. Include travel routes and distances.\n\n**Quality Standard:**\n- Create MANY files with sub-folders.\n- Each file 800-2000+ words.\n- Cross-reference other elements.\n- References section at bottom of every file.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "geography",
      "timeout": 3600
    },
    {
      "number": 2,
      "name": "history",
      "display_name": "歷史",
      "prompt": "Use the Slima MCP tools to create history files in the target book.\n\nRead the existing book structure first, then create history files:\n- timeline.md (master timeline)\n- Era sub-folders (each with overview.md + key events)\n- key-figures/ (one file per historical figure)\n\nCreate 10-18 files. Each file should be 800-2000+ words.\nWrite ALL content and file/folder names in the same language as the world context.",
      "system_prompt": "You are the History Specialist. Your job is to define the timeline of major events.\n\nCreate a master timeline first, then deep-dive per era. Each event: date, location, participants, cause, outcome, lasting impact. Create 5-10 historical figure files. Show cause-and-effect chains. Note documented vs mythologized events. Include the world's timekeeping system.\n\n**Quality Standard:**\n- Create MANY files with sub-folders.\n- Each file 800-2000+ words.\n- Cross-reference other elements.\n- References section at bottom of every file.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "history",
      "timeout": 3600
    },
    {
      "number": 3,
      "name": "peoples",
      "display_name": "種族與民族",
      "prompt": "Use the Slima MCP tools to create peoples files in the target book.\n\nRead the existing book structure first, then create peoples files:\n- overview.md (demographics)\n- human-groups/ (one file per group)\n- non-human/ (if applicable)\n- social-classes/\n- diaspora-and-migration.md\n\nCreate 8-15 files. Each 800-2000+ words.\nWrite ALL content in the same language as the world context.",
      "system_prompt": "You are the Peoples Specialist. Your job is to define species and ethnic groups.\n\nDemographics overview. Each group: physical traits, culture summary, abilities, territory, population. Inter-group relationships. Social class structures. Population trends. Connect to geography and history.\n\n**Quality Standard:**\n- Create MANY files with sub-folders.\n- Each file 800-2000+ words.\n- Cross-reference other elements.\n- References section at bottom of every file.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "peoples",
      "timeout": 3600
    },
    {
      "number": 3,
      "name": "cultures",
      "display_name": "文化",
      "prompt": "Use the Slima MCP tools to create culture files in the target book.\n\nRead the existing book structure first, then create culture files:\n- overview.md\n- individual-cultures/ (one file per culture)\n- religion/ (one file per belief system + rituals)\n- languages/\n- arts-and-entertainment/\n- daily-life/ (food, clothing, customs)\n\nCreate 10-18 files. Each 800-2000+ words.\nWrite ALL content in the same language as the world context.",
      "system_prompt": "You are the Cultures Specialist. Your job is to define the cultural landscape.\n\nEach major culture gets a deep-detail file. Each religion gets its own file. Cover daily life aspects. Describe language differences. Show cultural exchange and conflict. Note subcultures and generational differences.\n\n**Quality Standard:**\n- Create MANY files with sub-folders.\n- Each file 800-2000+ words.\n- Cross-reference other elements.\n- References section at bottom of every file.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "cultures",
      "timeout": 3600
    },
    {
      "number": 4,
      "name": "power_structures",
      "display_name": "權力結構",
      "prompt": "Use the Slima MCP tools to create power structure files in the target book.\n\nRead the existing book structure first, then create:\n- overview.md\n- political/ (governments)\n- factions/ (each faction)\n- military/\n- economic/\n- underworld/ (criminal organizations)\n\nCreate 10-18 files. Each 800-2000+ words.\nWrite ALL content in the same language as the world context.",
      "system_prompt": "You are the Power Structures Specialist. Your job is to define who holds power.\n\nEach government/faction/org gets its own file. For each: leadership, territory, goals, methods, membership, rivals, resources. Detail economic systems. Military and enforcement forces. Underground and criminal structures. Map alliances, rivalries, dependencies.\n\n**Quality Standard:**\n- Create MANY files with sub-folders.\n- Each file 800-2000+ words.\n- Cross-reference other elements.\n- References section at bottom of every file.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "power_structures",
      "timeout": 3600
    },
    {
      "number": 5,
      "name": "characters",
      "display_name": "角色",
      "prompt": "Use the Slima MCP tools to create character files in the target book.\n\nRead the existing book structure first, then create 15-25 character files in category sub-folders adapted to this world.\n\nEach character gets their own file with 1000-2000+ words of rich detail:\n- Header (name, title, classification)\n- Basic info\n- Physical description\n- Background (500+ words backstory)\n- Personality (traits, values, flaws, fears, desires)\n- Abilities/Skills\n- Relationships (all connections)\n- Possessions\n- Goals & Motivations\n- Character arc potential\n- Narrative hooks\n- Quotes (2-3)\n\nWrite ALL content in the same language as the world context.",
      "system_prompt": "You are the Characters Specialist. Your job is to define 15-25 key figures in this world.\n\nOrganize in sub-folders adapted to the world type. EVERY character gets their own dedicated file. Each file 1000-2000+ words.\n\n**Quality Standard:**\n- Create MANY files with sub-folders.\n- Cross-reference other world elements.\n- References section at bottom of every file.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "characters",
      "timeout": 3600
    },
    {
      "number": 5,
      "name": "items",
      "display_name": "物品與神器",
      "prompt": "Use the Slima MCP tools to create item files in the target book.\n\nRead the existing book structure first, then create 10-18 item files:\n- overview.md\n- legendary-artifacts/\n- weapons-and-armor/\n- ritual-objects/\n- materials/\n- everyday-items/\n\nEach item gets its own file with 800-1500+ words.\nWrite ALL content in the same language as the world context.",
      "system_prompt": "You are the Items Specialist. Your job is to define notable objects, artifacts, weapons, and materials.\n\nEach item gets its own file: name, classification, rarity, physical description (500+ words), origin story, powers/properties, current location/owner, historical significance, dangers/side effects, connections to characters/factions, cultural meaning.\n\n**Quality Standard:**\n- Create MANY files with sub-folders.\n- Each file 800-1500+ words.\n- Cross-reference other elements.\n- References section at bottom of every file.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "items",
      "timeout": 3600
    },
    {
      "number": 5,
      "name": "bestiary",
      "display_name": "怪獸圖鑑",
      "prompt": "Use the Slima MCP tools to create bestiary files in the target book.\n\nRead the existing book structure first, then create:\n- overview.md\n- Creature category sub-folders (12-20 creature files)\n- flora/ (5-10 plant files)\n- ecosystem.md\n\nEach creature/plant gets its own file with 800-1500+ words.\nWrite ALL content in the same language as the world context.",
      "system_prompt": "You are the Bestiary Specialist. Your job is to define creatures, monsters, supernatural beings, and flora.\n\nPer creature: name, classification, danger level, physical description (500+ words), habitat, behavior, abilities, weaknesses, uses/value, cultural significance, reproduction, notable encounters.\nPer plant: name, classification, rarity, description, habitat, properties, cultural uses, dangers.\n\n**Quality Standard:**\n- Create MANY files with sub-folders.\n- Each file 800-1500+ words.\n- Cross-reference other elements.\n- References section at bottom of every file.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "bestiary",
      "timeout": 3600
    },
    {
      "number": 6,
      "name": "narrative",
      "display_name": "敘事與故事線",
      "prompt": "Use the Slima MCP tools to create narrative files in the target book.\n\nRead the existing book structure first, then create:\n- overview.md\n- conflicts/ (major + minor conflicts)\n- prophecies/\n- story-arcs/\n- mysteries/\n- themes/\n\nCreate at least 12-18 files.\nWrite ALL content in the same language as the world context.",
      "system_prompt": "You are the Narrative Specialist. Your job is to define active story elements.\n\nConflict files: parties, stakes, root cause, current status, key battles, possible resolution paths (2-3 scenarios), connections to other conflicts.\nStory arc files: premise/hook, key characters, beginning/middle/end outline, twists, thematic resonance.\nMystery files: known vs unknown, competing theories, clues, potential revelations.\n\n**Quality Standard:**\n- Create MANY files with sub-folders.\n- Each file 800-2000+ words.\n- Cross-reference other elements.\n- References section at bottom of every file.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "narrative",
      "timeout": 3600
    },
    {
      "number": 7,
      "name": "validation_r1",
      "display_name": "驗證 R1",
      "prompt": "Read EVERY file in this book using MCP tools.\n\n1. Get book structure to see all files\n2. Read each file and check for:\n   - Name inconsistencies\n   - Timeline contradictions\n   - Faction/relationship conflicts\n   - Missing cross-references\n   - Geographic impossibilities\n   - Language consistency\n3. Check content completeness:\n   - Core topic coverage\n   - Enough entries per category\n   - Missing entries\n4. FIX all issues by editing affected files\n5. Create a preliminary consistency report at worldview/meta/consistency-report.md",
      "system_prompt": "You are the Validation Agent (Round 1). Your job is to read every file in the book, check for consistency issues and content completeness, FIX all problems found, and write a preliminary consistency report.\n\nBe thorough. Read every file. Cross-check names, dates, relationships, and facts across all files.",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "validation",
      "timeout": 3600
    },
    {
      "number": 8,
      "name": "validation_r2",
      "display_name": "驗證 R2",
      "prompt": "Read the preliminary consistency report.\n\n1. For every 'fixed' issue, verify the fix by reading the actual file\n2. Check for residual or newly introduced issues\n3. Fix remaining problems\n4. Overwrite the report with a FINAL status report:\n   - Per-folder completeness\n   - All-clear confirmation per category\n   - Final verdict: ALL CHECKS PASSED or remaining issues",
      "system_prompt": "You are the Verification Agent (Round 2). Your job is to verify that Round 1's fixes were applied correctly, fix any remaining issues, and produce the FINAL consistency report.\n\nYou have access to the full conversation from Round 1 via session chaining, so you already know what files exist and what was fixed.",
      "tool_set": "write",
      "include_language_rule": true,
      "chain_to_previous": true,
      "context_section": "validation",
      "timeout": 3600
    },
    {
      "number": 9,
      "name": "readme",
      "display_name": "README",
      "prompt": "Read the book structure, then create a README.md at the root of the book.\n\nInclude:\n- Book title and description\n- Table of contents based on actual file structure\n- How to navigate the world bible\n- Key entry points for readers",
      "system_prompt": "You are the Polish Agent. Create a polished README.md for this world bible book.",
      "tool_set": "write",
      "include_language_rule": true,
      "timeout": 1800
    }
  ]
}
```

## 執行流程視覺化

```
Number 1  ┌──────────┐
          │ Research  │ → context["overview"] = research output
          └────┬─────┘
               │
Number 2  ┌────┴──────┬────────────┬──────────┐
          │ Cosmology │ Geography  │ History  │  ← asyncio.gather（平行）
          └────┬──────┴─────┬──────┴────┬─────┘
               │            │           │
               └────────────┴───────────┘
               │ inject book_structure + save snapshot
               │
Number 3  ┌────┴──────┬──────────┐
          │ Peoples   │ Cultures │  ← asyncio.gather（平行）
          └────┬──────┴────┬─────┘
               │           │
Number 4  ┌────┴───────────┴──┐
          │ Power Structures  │  ← 單獨依序
          └────┬──────────────┘
               │
Number 5  ┌────┴──────┬──────────┬──────────┐
          │ Characters│ Items    │ Bestiary │  ← asyncio.gather（平行）
          └────┬──────┴────┬─────┴────┬─────┘
               │           │          │
Number 6  ┌────┴───────────┴──────────┴──┐
          │ Narrative                     │  ← 單獨依序（看得到所有前面的 context）
          └────┬─────────────────────────┘
               │
Number 7  ┌────┴───────────┐
          │ Validation R1  │  ← 讀所有檔案 + 修正 + 寫報告
          └────┬───────────┘
               │ session_id
Number 8  ┌────┴───────────┐
          │ Validation R2  │  ← chain_to_previous: true（共用 session）
          └────┬───────────┘
               │
Number 9  ┌────┴───────────┐
          │ README         │
          └────────────────┘
```

## 前端 UI 建議

### Stage 編輯器

每個 stage 是一張卡片，卡片包含：

```
┌─────────────────────────────────────────────┐
│ Stage 2: 宇宙觀 (cosmology)          [×刪除]│
│─────────────────────────────────────────────│
│ Number: [2]  Name: [cosmology]              │
│ Display Name: [宇宙觀]                       │
│─────────────────────────────────────────────│
│ Prompt:                                      │
│ ┌─────────────────────────────────────────┐ │
│ │ Use the Slima MCP tools to create      │ │
│ │ cosmology files in the target book...  │ │
│ └─────────────────────────────────────────┘ │
│─────────────────────────────────────────────│
│ System Prompt:                               │
│ ┌─────────────────────────────────────────┐ │
│ │ You are the Cosmology Specialist...    │ │
│ └─────────────────────────────────────────┘ │
│─────────────────────────────────────────────│
│ Tool Set: [write ▼]  Timeout: [3600]        │
│ ☑ Language Rule  ☐ Plan First               │
│ Context Section: [cosmology]                 │
│ ☐ Chain to Previous                          │
└─────────────────────────────────────────────┘
```

### 關鍵 UI 互動

1. **Number 欄位**：改 number 就改了執行順序。同 number 的卡片顯示在同一行（表示平行）
2. **拖拉排序**：拖動卡片到不同 number group
3. **複製 stage**：從範本庫選一個 specialist 快速新增
4. **預覽執行順序**：
   ```
   Step 1: Research (依序)
   Step 2: Cosmology + Geography + History (平行)
   Step 3: Peoples + Cultures (平行)
   Step 4: Power Structures (依序)
   ...
   ```

### Stage 範本庫

前端可提供預設範本，使用者點選後填入預設值：

| 範本 | tool_set | include_language_rule | 典型 context_section |
|------|----------|----------------------|---------------------|
| Research (純分析) | none | true | overview |
| Writer (寫檔案) | write | true | (自訂) |
| Reader (唯讀分析) | read | false | (自訂) |
| Validator R1 | write | true | validation |
| Validator R2 | write | true (+chain) | validation |
| Polish/README | write | true | — |

## NDJSON 事件串流

啟動方式：
```bash
slima-agents task-pipeline --plan stages.json --json-progress
```

前端透過 `spawn` + `stdout readline` 接收：

```jsonc
// Pipeline 開始
{"event": "pipeline_start", "prompt": "海盜世界觀", "total_stages": 13}

// Book 建立
{"event": "book_created", "book_token": "bk_xxx", "title": "海盜世界觀"}

// Stage 開始
{"event": "stage_start", "stage": 1, "name": "research", "agents": ["TaskAgent[research]"]}

// Agent 開始
{"event": "agent_start", "stage": 1, "agent": "TaskAgent[research]"}

// Agent 串流（即時文字 + 工具呼叫）
{"event": "text_delta", "agent": "TaskAgent[research]", "text": "分析中...", "stage": 1}
{"event": "tool_use", "agent": "TaskAgent[cosmology]", "tool_name": "create_file", "stage": 2}

// Agent 完成
{"event": "agent_complete", "stage": 1, "agent": "TaskAgent[research]", "duration_s": 45.2, "timed_out": false}

// Stage 完成
{"event": "stage_complete", "stage": 1, "name": "research", "duration_s": 45.5}

// 新檔案
{"event": "file_created", "path": "worldview/cosmology/overview.md"}

// Pipeline 完成
{"event": "pipeline_complete", "book_token": "bk_xxx", "total_duration_s": 1234.5, "success": true}
```

## 最小範例：3 步驟管線

```json
{
  "title": "快速角色設定",
  "stages": [
    {
      "number": 1,
      "name": "brainstorm",
      "display_name": "構思",
      "prompt": "幫我構思一個奇幻世界的 5 個主角，列出名字、背景、能力概述。",
      "tool_set": "none",
      "context_section": "characters"
    },
    {
      "number": 2,
      "name": "write_characters",
      "display_name": "寫角色檔案",
      "prompt": "根據構思結果，在書中建立角色檔案。每個角色一個 .md 檔案，放在 characters/ 資料夾。",
      "tool_set": "write",
      "include_language_rule": true,
      "context_section": "files"
    },
    {
      "number": 3,
      "name": "review",
      "display_name": "審閱",
      "prompt": "閱讀所有角色檔案，檢查一致性，修正任何問題。",
      "tool_set": "write",
      "chain_to_previous": true
    }
  ]
}
```
