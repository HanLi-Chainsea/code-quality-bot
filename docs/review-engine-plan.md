# Blast-Radius Review Engine — 設計與計劃

> 狀態：草案（待 review）。日期：2026-06-15。
> 目標讀者：接手這套 code-review bot 的人。

## 1. 問題

現役 PR-Agent **只讀 diff hunk** —— 看不到完整改動檔、看不到跨檔影響。結果：

- **深度不足**：review 都是泛泛之談，在資深工程師眼裡無價值（「換什麼模型都救不了，因為餵進去的資訊本身就不夠」）。
- **訊噪比差**：一堆 style nitpick 淹沒真正該擋的問題（真 bug / 安全 / breaking change）。

換模型（已換 MiniMax-M2.1）只是其次。核心是 **餵給模型的 context 本身要對**。

## 2. 目標 / 非目標

**目標**
- **深度**：review 要有跨檔、影響範圍（blast radius）的認知，能判斷「這個改動會波及哪裡」。
- **訊號**：只報**值得擋 merge** 的發現。量化目標 **FP 率 < 10%**（見 §4 研究依據：>10% 工程師就嫌吵，>50% 直接無視）。

**非目標（現階段）**
- 不重寫 PR-Agent 的 GitLab 串接（webhook 驗證 / 貼文）。
- 不做整個 repo 塞進 prompt 的 brute-force RAG。
- 不在第一階段碰 webhook（先離線證明價值）。

## 3. 核心洞察（為什麼這樣設計）

研究商用 SOTA 與學術後的結論：**槓桿是「聚焦的全局 context」，不是更大的模型、也不是更多的原始 context。**

- **Greptile**（獨立 benchmark bug catch 率 82%，最高）：建整個 codebase 的語義圖 → multi-hop 調查 → 平行 agent 評估「diff 以外的影響」。
- **Qodo Merge**：multi-agent + RAG 撈相關片段。
- **CodeRabbit**：diff + repo context，低 FP，2–4 分鐘。
- **共同模式** = code graph 算影響範圍 → 只餵相關的 → 平行找 → 驗證後才貼。

這正是 §5 的架構。把「整個 repo 27,700 檔」收斂到「~15 個結構相關檔」，同時解決深度（看得到相關全貌）與噪聲（沒餵無關的東西進去）。

## 4. 降噪策略（達成 < 10% FP）

研究關鍵（[behavioral thresholds](https://www.augmentcode.com/guides/deep-code-review-recall-vs-precision)、[hybrid LLM 降 FP](https://arxiv.org/pdf/2509.15433)）：

- **工程師的容忍門檻**：FP < 10% 才會被認真看待；10–30% 被貼「noisy」標籤；> 50% 預設無視、只在擋 merge 時才看。
- **兩階段：recall 先、precision 後**。找的時候追求高 recall（寧可多找），再用**對抗式驗證/排序**把沒把握的砍掉，只**浮出高信心**的。混合式（LLM + 靜態分析）可砍掉 94–98% FP 而保住 recall。

落地手法：
1. **Prompt 框架**：「只報你願意**因此擋下這個 merge** 的問題」；嚴重度分級 `blocker / major / minor`；明確指示**不要**報純風格 / 命名 / 格式。
2. **兩階段 pipeline**：find（高 recall）→ verify（每個發現獨立對抗式查證「這真的成立嗎？能重現嗎？」）→ 只貼通過驗證的。
3. **嚴重度 gating**：預設只貼 `blocker`+`major`，`minor` 收進折疊區或丟棄。

## 5. 架構（三個元件）

```
(cloned repo + diff)
      │
      ▼
┌─────────────────┐   code-review-graph：build → detect-changes(JSON)
│ ① Context 引擎  │   算 blast radius（caller/callee/test/dependent）
│                 │   context inlining：改動函式 + 上游 caller + 下游 callee
└────────┬────────┘   token-budgeted（~24k / 200k 視窗），超預算先砍依賴方
         │ focused context bundle
         ▼
┌─────────────────┐   聚焦 prompt（zh-TW、只報 block-worthy、嚴重度 schema）
│ ② Review 腦     │   兩階段：find(recall) → verify(precision)
└────────┬────────┘   呼叫 LiteLLM `reviewer`（現 MiniMax-M2.1）
         │ 確認過的發現
         ▼
┌─────────────────┐   Phase 1：印到 stdout / 檔（離線）
│ ③ 交付          │   Phase 2：貼回 GitLab MR
└─────────────────┘
```

### 與 code-review-graph 的整合方式
- 介面：**CLI**（`code-review-graph build` 一次、之後 `update` 增量、`detect-changes` 拿影響集 JSON）或 **MCP HTTP**（`serve --http :5555`，有 `get_impact_radius` / `get_review_context`）。**無公開 Python API**，所以 shell 整合、解析 JSON。
- 它在 CWD 的 repo 上運作、圖存該 repo 的 `.code-review-graph/` → 我們 `cd` 進 `var/repos/<repo>` 跑，圖跟著 cloned repo 放在 gitignored 的 `var/`。

## 6. 目錄佈局（包在本專案內維護）

```
code-quality-bot/
  review-engine/                ← 引擎，進版控、本專案維護
    graph.py    — 包 code-review-graph：build/update + diff→影響集 JSON
    context.py  — 組 bundle：改動檔全文 + 上下游（context inlining），卡 token 預算
    prompt.py   — 聚焦 review prompt（zh-TW、block-worthy、嚴重度 schema）
    review.py   — 兩階段 find→verify，呼叫 LiteLLM reviewer，回結構化發現
    cli.py      — review <repo> <base>..<head> [--baseline]
    eval/       — 真實 MR 樣本 + 評分 rubric（depth / FP 率）
  var/                          ← gitignored：cloned repo + SQLite 圖 + 暫存
```

## 7. 分階段計劃

### Phase 0 — 線上 PR-Agent 調教（✅ 已完成）
換 MiniMax-M2.1、reasoning_split 處理 `<think>`、context 200k、固定 Cloudflare tunnel。已實測：content 乾淨、tunnel HTTP 405 通到底。這是基線，不是終點。

### Phase 1 — 離線垂直切片（下一步，最大風險先證）
建 `review-engine/`，在**一個真實 MR** 上跑通「code-review-graph 影響集 → context inlining → 兩階段聚焦 prompt → review」，並 A/B 對照 diff-only baseline。**完全不碰 webhook。**
- **Go/No-Go**：blast-radius 版在真 MR 上**至少多抓 1 個 diff-only 漏掉的跨檔/影響問題**，且**純 nitpick 明顯變少（朝 < 10% FP）**。人眼判。
- 過了才往下；沒過就便宜地學到「這條路不夠」。

### Phase 2 — 接進 GitLab MR 流程
webhook → 引擎 → 貼回 MR。此時決定：**沿用 PR-Agent 當交付層**（只換它的 context 來源），還是**自寫薄 service 取代**。Phase 1 的整合經驗會給答案。

### Phase 3 — Jira 整合（之後說不定會用到）
兩條路，依需求取：
- **快速版**：開 PR-Agent/Qodo Merge **內建的 Jira ticket 合規分析**（[Qodo Jira compliance](https://www.qodo.ai/blog/qodo-merge-jira-ensuring-code-quality-through-ticket-compliance/)）—— 靠 branch 名 `ISSUE-123-...` 或 MR 連結認 ticket，自動抓 acceptance criteria，給 Fully/Partially/Not compliant 標籤。多半只是設定 + Jira app 授權。
- **引擎深度版**：把 ticket 的驗收標準**餵進 blast-radius context**，讓 review 同時做「程式碼層」+「需求 conformance」判斷；可選做 PR→ticket（把確認的發現開成 Jira issue）。
- 也可接 han-agents 的 task hierarchy / 既有 Atlassian 工具。

## 8. 成功指標
- **深度**：能產出 diff-only 拿不到的跨檔 / 影響型發現。
- **噪聲**：FP 率 **< 10%**（人工標註 N 個真 MR 的發現算）。
- **A/B**：同一批真 MR，blast-radius 版 vs diff-only 版，人眼盲評哪個對資深工程師更有用。

## 9. 風險與未決
- **code-review-graph 路徑/儲存**：文件沒寫怎麼指定外部 repo 路徑/圖位置 → 用 `cd` 進 cloned repo 跑來規避；Phase 1 要實測確認。
- **每個 MR 即時建圖的延遲**：大 repo 首次 `build` 慢 → 靠 `update` 增量 + 圖持久化在 `var/`。
- **M2.1 在 200k context 的成本/延遲** → context bundle 實際只用 ~24k；MiniMax 後台設 hard cap。
- **語言覆蓋**：code-review-graph 支援 30+ 語言 —— 仍以待審 repo 的實際語言為準（Phase 1 樣本決定，先確認該語言的 caller/callee 解析品質）。

## 10. 參考
- code-review-graph：[repo](https://github.com/tirth8205/code-review-graph) · [CLI docs](https://deepwiki.com/tirth8205/code-review-graph/4.1-cli-commands)
- Understand-Anything：[repo](https://github.com/Lum1104/Understand-Anything)
- RepoGraph（repo 級 code graph）：[arXiv](https://arxiv.org/html/2410.14684v1) · Context Inlining：[arXiv](https://arxiv.org/html/2601.00376v1)
- 降噪 / recall vs precision：[Augment](https://www.augmentcode.com/guides/deep-code-review-recall-vs-precision) · [hybrid SAST](https://arxiv.org/pdf/2509.15433) · [Datadog](https://www.datadoghq.com/blog/using-llms-to-filter-out-false-positives/)
- 商用對照：[Greptile](https://www.greptile.com/) · [Qodo Merge](https://www.qodo.ai/blog/qodo-merge-solving-key-challenges-in-ai-assisted-code-reviews/)
- Jira：[Qodo ticket context](https://qodo-merge-docs.qodo.ai/core-abilities/fetching_ticket_context/) · [PR→ticket](https://qodo-merge-docs.qodo.ai/tools/pr_to_ticket/)
