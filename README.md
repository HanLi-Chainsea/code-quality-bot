# code-quality-bot

> English version: [README.en.md](README.en.md)

自架的 PR-Agent（GitLab MR 自動 review）+ LiteLLM gateway → MiniMax。
最初是 PR-Agent / Qodo Cover / Diffblue 三方評測；最後只有 PR-Agent 留下來能免費自架（詳見 [JOURNAL.md](JOURNAL.md) 的 `Track-1 summary`）。

## 現在實際在跑什麼

```
gitlab.com MR
   ↓ webhook (HTTPS tunnel)
cqb-pr-agent      127.0.0.1:3033 → :3000   (codiumai/pr-agent 容器)
   ↓
cqb-litellm       :4000                     (LiteLLM，對外提供穩定的 "reviewer" alias)
   ↓
MiniMax API       api.minimax.io
```

PR-Agent 會自動把 `describe` / `review` / `improve` 三種產出貼進 MR。  
開發者也能在 MR 留言區輸入 `/review`、`/improve`、`/ask "..."` 觸發。

## 檔案地圖 — 改什麼動什麼

| 路徑 | 用途 | 模式 |
|---|---|---|
| **[deploy/](deploy/)** | **正式環境跑的東西**：兩個容器 + 設定檔 | **PROD** |
| `deploy/.env` | `LITELLM_MASTER_KEY` + 供應商 API key（`MINIMAX_API_KEY` 等） | 機密，chmod 600，gitignored |
| `deploy/pr_agent.gitlab.toml` | GitLab base URL + bot token + webhook `shared_secret` + LiteLLM key | 機密，chmod 600，gitignored |
| `deploy/config.yaml` | LiteLLM 路由 — **換模型改這裡**，內有「SWAP OPTIONS」面板列各家寫法 | 本機，gitignored（從 `config.yaml.example` 複製，模型選擇不進 VC） |
| `deploy/docker-compose.yml` | 容器 image digest pin、資源上限 | 非機密 |
| [docs/deploy-macmini.md](docs/deploy-macmini.md) | 首次部署完整步驟（含 Cloudflare Tunnel） | — |
| [docs/litellm-minimax.md](docs/litellm-minimax.md)、[docs/pr-agent.md](docs/pr-agent.md) | 元件層細節筆記 | — |
| [JOURNAL.md](JOURNAL.md) | 評測歷程、決策、踩過的坑 | — |
| `samples/`、`eval/`、`runners/`、`pr-agent/`、`litellm/`、`scripts/`、根目錄 `docker-compose.yml` | **LAB ONLY** — 評測 / 拋棄式 GitLab CE。**絕對不要**對 prod 跑。 | LAB |

## Day-1 第一次部署到新主機

完整版見 [docs/deploy-macmini.md](docs/deploy-macmini.md)。簡短版：

1. 安裝 Docker Desktop 並啟動。
2. `cp deploy/.env.example deploy/.env` → 填 `MINIMAX_API_KEY` 與 `LITELLM_MASTER_KEY`（任意 `sk-cqb-...` 隨機字串都可以）。
   接著 `cp deploy/config.yaml.example deploy/config.yaml` → 在 `reviewer` 區塊選你要的模型（此檔 gitignored，模型選擇留本機）。
3. `cp deploy/pr_agent.gitlab.toml.example deploy/pr_agent.gitlab.toml` → 填：
   - `[openai] key` = 同 `LITELLM_MASTER_KEY`
   - `[gitlab] personal_access_token` = Project / Group / Personal Access Token，scope 選 `api`
   - `[gitlab] shared_secret` = 32 字以上隨機字串（要跟 GitLab webhook 那邊填一樣）
4. `chmod 600 deploy/.env deploy/pr_agent.gitlab.toml`
5. `cd deploy && docker compose up -d`
6. 把 `:3033` 用 Cloudflare Tunnel 對外（正式用建議：named tunnel + 自己的網域）。
7. 設定 GitLab webhook（建議掛 **Group 層**一次覆蓋所有 repo）→ 完整步驟見 [docs/gitlab-webhook-setup.md](docs/gitlab-webhook-setup.md)：
   - URL：`https://<tunnel>/webhook`
   - Secret token：同 `shared_secret`
   - Trigger：**勾 Merge request events ＋ Comments**（Comments 才能在留言區用 `/review`、`/improve`、`/ask`）
   - SSL verification：開
8. 開一個測試 MR → ~30 秒內 PR-Agent 會貼 review。

## Day-2 日常運維備忘錄

下列指令都在 `deploy/` 目錄下執行。

| 想做的事 | 指令 |
|---|---|
| 服務在不在？ | `docker compose ps` |
| 看最近活動 / 錯誤？ | `docker compose logs pr-agent --tail=50 -f` |
| 過去一小時有錯嗎？ | `docker compose logs --since 1h \| grep -iE 'error\|exception\|401\|403\|500'` |
| 對漏掉的 MR 重跑 review | 在那個 MR 留言區打 `/review` |
| 重啟 pr-agent | `docker compose restart pr-agent` |
| 整套重起 | `docker compose down && docker compose up -d` |
| 升級 image（先在 staging 試過再做） | 改 `docker-compose.yml` 內的 digest → `docker compose up -d` |

## 常見變更

### 換模型（MiniMax → Claude / OpenAI / Gemini / 本機 Ollama）

編輯 `deploy/config.yaml`。檔案內有註解版「SWAP OPTIONS」面板列每家寫法。把 `reviewer` 那塊指到新供應商，新 key 放進 `deploy/.env`，然後 `docker compose up -d --force-recreate litellm`。**PR-Agent 完全不用動** — 它永遠呼叫穩定的 `openai/reviewer` alias。

### Rotate GitLab token

產新 PAT → 更新 `pr_agent.gitlab.toml` 的 `[gitlab] personal_access_token` → `docker compose restart pr-agent` → 在 GitLab 撤銷舊 token。

### Rotate webhook shared secret

更新 `pr_agent.gitlab.toml` 的 `[gitlab] shared_secret` → `docker compose restart pr-agent` → 把同樣的新值貼到 GitLab webhook 的「Secret token」欄位。

### 換對外 webhook URL

把每個 GitLab project 的 webhook URL 改掉就好，**不用重啟容器**。

### 換輸出語言

預設是繁體中文（`response_language = "zh-TW"` 在 `pr_agent.gitlab.toml` 的 `[config]` 區塊）。要改：
- 英文 → `"en-US"`
- 簡體中文 → `"zh-CN"`
- 日文 → `"ja-JP"`（其餘 ISO 代碼比照辦理）

改完 `docker compose restart pr-agent`。下一筆 MR 就會用新語言輸出。

## 出問題時怎麼查

| 症狀 | 最可能原因 | 第一步動作 |
|---|---|---|
| 所有 MR 都沒 review | tunnel 斷了 **或** pr-agent crash | `docker compose ps` + 看 tunnel 的 terminal/service |
| log 出現 401 / 403 | PAT 過期或 scope 不夠 | rotate token |
| 換模型後跳 500 | `.env` 裡的 key 錯，或 `reviewer` 區塊打字錯 | `docker compose logs litellm` |
| Webhook 顯示 "couldn't connect" | tunnel URL 換了（例如 trycloudflare 重啟） | 拿新 URL → 更新 GitLab webhook |
| cloudflared 顯示 `dial tcp [::1]:3033: connect: connection refused` | tunnel 指到 `localhost`，但 compose 只綁 `127.0.0.1:3033` | tunnel URL 改成 `http://127.0.0.1:3033` |
| 啟動時跳 `JSONDecodeError` | `personal_access_token` 還是 placeholder 沒換 | 把真的 `glpat-...` 填進 toml |
| MiniMax 帳單暴衝 | LiteLLM 的 `max_budget` 只是 best-effort | 到 MiniMax 後台設 hard cap |

## 已知限制（不是 bug，是設計取捨）

下列幾條是當初部署時就已知的、不需要修，但接手的人要心裡有數：

- **容器 crash 會掉那筆 MR 的 review。** PR-Agent 先回 GitLab 200 才開始 async 處理。如果處理一半容器重啟，那個 MR 就沒 review 了（GitLab 不會重送 webhook）。解法：去 MR 留言 `/review` 補。
- **`max_budget` 是 best-effort。** LiteLLM 的 spend 是 in-memory（重啟歸零），而且不知道 MiniMax 的計價。真正的花費上限要去 **MiniMax 後台**設 hard cap。
- **Webhook 端點半曝光。** PR-Agent 先回 200 才驗 `shared_secret`，所以任何知道 URL 的人都能戳到 200。正式 prod 建議在前面套 Cloudflare Access（要登入）+ 速率限制。
- **trycloudflare URL 是臨時的。** 試水溫可以，正式環境一定要用 named tunnel + 自己網域。
- **Token 等於 comment 作者。** 如果用個人 PAT，留言會以那個人名字出現。等 project Owner 有空，請他建一個 Project Access Token（會自動建立 bot user）替換掉。

## 還可以看

- [docs/deploy-macmini.md](docs/deploy-macmini.md) — 首次部署 + Cloudflare Tunnel 完整步驟
- [docs/pr-agent.md](docs/pr-agent.md) — PR-Agent 細節 + local-mode 筆記
- [docs/litellm-minimax.md](docs/litellm-minimax.md) — LiteLLM ↔ MiniMax 設定
- [JOURNAL.md](JOURNAL.md) — 部署過程 / 決策 / 踩坑紀錄
