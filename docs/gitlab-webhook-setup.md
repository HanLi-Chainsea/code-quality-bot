# GitLab Webhook 設定（請 repo / group owner 做一次）

> **權限**：要 **Group Owner**（建議：group 層級 webhook，一次覆蓋底下所有 repo）或 **Project Maintainer**（單一 repo）才能設定。
> 若你不是 owner，把這頁整段傳給 owner 即可 —— 他只需要動一次。

## 要做的事

GitLab → **Group（或 Project）→ Settings → Webhooks → Add new webhook**
（若已存在，點進去 **Edit** 改即可）。填：

| 欄位 | 值 |
|---|---|
| **URL** | `https://<你的-tunnel-網域>/webhook` |
| **Secret token** | 跟 `deploy/pr_agent.gitlab.toml` 裡的 `shared_secret` **一模一樣** |
| **Trigger（勾這兩個）** | ☑ **Merge request events** ☑ **Comments** |
| **SSL verification** | 開（Enable） |
| **Active** | 開 |

按 **Add webhook / Save changes** 完成。

## 為什麼是這兩個 Trigger（完整功能）

- **Merge request events** — MR 開啟 / 更新時，自動貼 `describe` / `review` / `improve`（核心功能）。
- **Comments** — 讓開發者在 MR 留言區打 `/review`、`/improve`、`/ask "..."` 也能觸發。
  **不勾這個，手動指令完全不會生效**，只剩自動 review。要完整體驗一定要勾。

（不用勾 Push / Pipeline / Tag 等其餘事件 —— 多勾只是增加無用流量，PR-Agent 也不處理。）

## 之後換 tunnel / 換網域時

只改 webhook 的 **URL** 這一個欄位，Secret token / Trigger / SSL 全部不動。
用 named tunnel + 自有網域時 URL 是固定的，所以正常只需設定這一次，不會再來麻煩 owner。

## 測試有沒有通

設定完，在 webhook 頁面點 **Test → Merge request events**，或直接開一個測試 MR。
頁面下方 **Recent events** 會顯示回應碼：**200** = 服務有收到。
（注意：PR-Agent 是先回 200 再 async 處理，所以 200 只代表「打得到」，實際 review 看 MR 上有沒有貼出來。）

## （選用）乾淨的 bot 身分

預設 PR-Agent 用 `pr_agent.gitlab.toml` 裡的 token 發言 —— 留言會掛在那個 token 擁有者名下。
若想要一個獨立的 bot 帳號，請 owner 到 **Group → Settings → Access Tokens** 建一個
**Group Access Token**（scope 選 `api`，會自動產生一個 bot 使用者），把它填回 toml 的
`personal_access_token`，再 `docker compose restart pr-agent`。

---

> 本部署目前的值（填上面表格用）：
> - URL：`https://cqb.chainseaclaw.win/webhook`
> - Secret token：見 `deploy/pr_agent.gitlab.toml` 的 `shared_secret`（gitignored，不放這裡）
