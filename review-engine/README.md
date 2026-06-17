# review-engine — blast-radius 程式碼審查引擎

修正 PR-Agent「只讀 diff」造成的淺薄審查:先用 code graph 算出改動的**波及範圍(blast radius)**,把相關上下游餵進去,再做**多視角 find → 落地反證 verify** 的兩階段 review。

> 設計與計畫:[../docs/review-engine-plan.md](../docs/review-engine-plan.md)(北極星與分階段)、
> [../docs/review-engine-phase1-plan.md](../docs/review-engine-phase1-plan.md)(Phase 1 逐步實作)。

## 北極星

**一位資深工程師可以完全信任:凡是他會提出的風險,這套也會提出。** 雙向、缺一不可:

- **不漏(recall)**:資深會抓的跨檔/影響型風險,它也要抓到 —— 否則不是安全網。
- **不吵(precision)**:它提的,資深都認同值得提 —— 否則雜訊侵蝕信任。

## 架構(資料流)

```
(cloned repo + git base ref)
   │
   ▼  graph.py        code-review-graph 建圖；改動函式(detect-changes)+ blast radius(查 graph.db 的 CALLS edges)
   ▼  context.py      context inlining：完整改動檔 + 1-hop caller/callee 片段，卡 token 預算
   │                  └─ 大改動自適應：全文超預算 → 改納高風險函式片段，明確標註取捨(不靜默截斷)
   ▼  review.py       ① 多視角 find(general / breaking-change / 並行競態 / 行為變更)→ union → 去重
   │                  ② 落地反證 verify：每條發現拉真實源碼背書，只在【明確】反證才砍(不漏優先)
   │                  ③ consolidate：同根因(共用 code symbol)合併成一條 + 列觸發點(確定性，無 LLM)
   │                  find / verify 皆平行(上限 6),單次失敗只降級該條、不炸全場
   ▼  cli.py          review <repo> <base> [--baseline]   （--baseline = diff-only,給 A/B 對照）
   ▼  輸出            [severity] ✓verified/?unverified  file:line  title + rationale (+觸發點)
```

LLM 走 LiteLLM 的 `reviewer` alias(目前 MiniMax-M2.1,reasoning_split 已處理 `<think>`)。

## 怎麼跑

需要 **Python 3.11+**(`code-review-graph` 要 3.10+,系統 3.9 不行)。

```bash
cd review-engine
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# LiteLLM reviewer 端點(本機 prod gateway)
export REVIEWER_API_KEY="$(grep '^LITELLM_MASTER_KEY' ../deploy/.env | cut -d= -f2)"
#（可選）REVIEWER_BASE_URL 預設 http://127.0.0.1:4000/v1、REVIEWER_MODEL 預設 reviewer

# 對一個改動跑 review（repo 先 checkout 到目標 commit）
.venv/bin/python -m review_engine.cli --repo <repo路徑> --base <base-ref>

# A/B：diff-only baseline vs blast-radius 引擎
.venv/bin/python eval/run_ab.py --repo <repo路徑> --base <base-ref>
```

CLI 參數:`--repo`(必填)、`--base`(預設 HEAD~1)、`--data-dir`(圖庫位置,預設 `<repo>/.crg-data`)、
`--baseline`(只讀 diff)、`--min-severity`(minor/major/blocker,預設 major)。

## 檔案結構

```
review_engine/
  graph.py     code-review-graph 包裝 + graph.db edges 查 blast radius
  context.py   context inlining + token 預算 + 大改動自適應
  prompt.py    find 多視角 prompt + verify(落地反證)prompt
  review.py    兩階段 find→verify + 確定性 consolidation（核心）
  llm.py       LiteLLM reviewer HTTP client（可 mock）
  models.py    ChangedFunction / Node / Finding / Bundle
  cli.py       入口 + --baseline
tests/         pytest（fixture repo 會實際建一張圖）
eval/          run_ab.py（A/B）+ SENIOR_COMPARE.md（北極星比對模板）
```

測試:`.venv/bin/pytest -q`

## 實證(aipoolserver 真實 changeset)

- `a17d79e9b`(JWT 登入):diff-only baseline = 0;引擎抓到 breaking change(JWT sub→mobile、查詢鍵改變)、TOCTOU 競態、移除 last-login-tenant 退步、JWT 簽名未驗證認證繞過。
- `f393f3325`(auth filter):fail-open 認證繞過,8 條重複 → consolidation 收成 1 條。
- `24e8a6ece`(46 檔型別改動):自適應 context 不爆預算,抓到 `IdGeneratorService→IdUtil.objectId` 的多實例 ID 碰撞,16 條 → 2 條。

## 已知限制 / 後續

- 目前是**離線 CLI**;接 GitLab MR 即時流程是 **Phase 3**。
- 樣本仍少,北極星的最終校準需要**資深/同事真人回饋**。
- consolidation 的觸發點清單偶有瑕疵;大改動的 context 仍是「函式片段」而非完整檔。
