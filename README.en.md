# code-quality-bot (English)

> 中文版（主）：[README.md](README.md)

Self-hosted PR-Agent (GitLab MR review) wired to MiniMax via LiteLLM.
Originally a bake-off vs. Qodo Cover / Diffblue — only PR-Agent survived as a
free self-hostable tool (see [JOURNAL.md](JOURNAL.md) `Track-1 summary`).

## What's actually deployed

```
gitlab.com MR
   ↓ webhook (HTTPS tunnel)
cqb-pr-agent      127.0.0.1:3033 → :3000   (codiumai/pr-agent)
   ↓
cqb-litellm       :4000                     (LiteLLM, exposes stable "reviewer" alias)
   ↓
MiniMax API       api.minimax.io
```

PR-Agent posts `describe` / `review` / `improve` artefacts into the MR.
Users in the MR can also type `/review`, `/improve`, `/ask "..."` as comments.

## Repo map — touch what for what

| Path | Purpose | Mode |
|---|---|---|
| **[deploy/](deploy/)** | **What's running in production.** Two containers + config. | **PROD** |
| `deploy/.env` | `LITELLM_MASTER_KEY` + provider API key (`MINIMAX_API_KEY` etc.) | secret, chmod 600, gitignored |
| `deploy/pr_agent.gitlab.toml` | GitLab base URL + bot token + webhook `shared_secret` + LiteLLM key | secret, chmod 600, gitignored |
| `deploy/config.yaml` | LiteLLM routing — **swap the model here**, panel of options in-file | not secret |
| `deploy/docker-compose.yml` | Container pinning (by digest), resource limits | not secret |
| [docs/deploy-macmini.md](docs/deploy-macmini.md) | Full step-by-step first-time setup | — |
| [docs/litellm-minimax.md](docs/litellm-minimax.md), [docs/pr-agent.md](docs/pr-agent.md) | Component-specific notes | — |
| [JOURNAL.md](JOURNAL.md) | History + decisions + gotchas hit during bake-off | — |
| `samples/`, `eval/`, `runners/`, `pr-agent/`, `litellm/`, `scripts/`, root `docker-compose.yml` | **LAB ONLY** — bake-off / throwaway GitLab CE. Do NOT run against prod. | LAB |

## Day-1 setup (new host)

The full guide is [docs/deploy-macmini.md](docs/deploy-macmini.md). Short version:

1. Install Docker Desktop, start it.
2. `cp deploy/.env.example deploy/.env` → fill `MINIMAX_API_KEY` + `LITELLM_MASTER_KEY` (any random `sk-cqb-...`).
3. `cp deploy/pr_agent.gitlab.toml.example deploy/pr_agent.gitlab.toml` → fill:
   - `[openai] key` = same as `LITELLM_MASTER_KEY`
   - `[gitlab] personal_access_token` = a Project/Group/Personal Access Token, scope `api`
   - `[gitlab] shared_secret` = random 32+ char string (paste the same into GitLab webhook)
4. `chmod 600 deploy/.env deploy/pr_agent.gitlab.toml`
5. `cd deploy && docker compose up -d`
6. Expose `:3033` via a Cloudflare Tunnel (preferred: named tunnel + your own domain).
7. In each GitLab project → Settings → Webhooks → add:
   - URL: `https://<tunnel>/webhook`
   - Secret token: same as `shared_secret`
   - Triggers: only **Merge request events**
   - SSL verification: ON
8. Open a test MR — PR-Agent posts within ~30s.

## Day-2 ops cheatsheet

All commands run from `deploy/`.

| Question | Command |
|---|---|
| Are services up? | `docker compose ps` |
| Recent activity / errors? | `docker compose logs pr-agent --tail=50 -f` |
| Errors in last hour? | `docker compose logs --since 1h \| grep -iE 'error\|exception\|401\|403\|500'` |
| Re-trigger review on a missed MR | Type `/review` in the MR comment box |
| Restart pr-agent | `docker compose restart pr-agent` |
| Restart everything | `docker compose down && docker compose up -d` |
| Update images (after testing new digest) | edit `docker-compose.yml` digest → `docker compose up -d` |

## Common changes

### Swap the LLM (MiniMax → Claude / OpenAI / Gemini / local Ollama)

Edit `deploy/config.yaml` — there is a commented "SWAP OPTIONS" panel for each provider. Repoint the `reviewer` block, put the new provider key in `deploy/.env`, then `docker compose up -d --force-recreate litellm`. **PR-Agent does not change** — it always calls the stable `openai/reviewer` alias.

### Rotate the GitLab token

Generate new PAT → update `[gitlab] personal_access_token` in `pr_agent.gitlab.toml` → `docker compose restart pr-agent` → revoke old token in GitLab.

### Rotate the webhook shared secret

Update `[gitlab] shared_secret` in `pr_agent.gitlab.toml` → `docker compose restart pr-agent` → paste the same new value into the GitLab webhook's "Secret token" field.

### Change the public webhook URL

Update each GitLab project's webhook URL. No container restart needed.

### Change the output language

Default is Traditional Chinese (`response_language = "zh-TW"` in the `[config]` block of `pr_agent.gitlab.toml`). To switch:
- English → `"en-US"`
- Simplified Chinese → `"zh-CN"`
- Japanese → `"ja-JP"` (any ISO locale code works)

`docker compose restart pr-agent` to apply. Takes effect on the next MR processed.

## Triage when things break

| Symptom | Likely cause | First action |
|---|---|---|
| Every MR misses review | tunnel down OR pr-agent crashed | `docker compose ps` + check tunnel terminal/service |
| 401 / 403 in logs | PAT expired or scope insufficient | rotate token |
| 500 after a model swap | wrong provider key in `.env`, or typo in `reviewer` block | `docker compose logs litellm` |
| Webhook says "couldn't connect" | tunnel URL changed (e.g. trycloudflare restarted) | get new URL → update GitLab webhook |
| `JSONDecodeError` at startup | placeholder still in `personal_access_token` | put real `glpat-...` in toml |
| MiniMax bill spiking | LiteLLM `max_budget` is best-effort only | set a hard cap in the MiniMax console |

## Known limits

These came up during bring-up and are not bugs to fix lightly — they're design trade-offs:

- **Crash drops a review.** PR-Agent returns `200` to GitLab then processes async. If the container restarts mid-process, that MR's review is silently lost (GitLab does not redeliver webhooks). Workaround: comment `/review` on the MR.
- **`max_budget` is best-effort.** LiteLLM tracks spend in memory (resets on restart) and doesn't know MiniMax pricing. The real spend guard is a hard cap set in the MiniMax billing console.
- **Webhook endpoint is semi-exposed.** PR-Agent answers `200` before validating the shared secret. Putting Cloudflare Access (or equivalent) in front for rate-limit / source allowlist is recommended for real prod.
- **trycloudflare URLs are ephemeral.** OK for spike testing; for real prod use a named `cloudflared` tunnel pointed at your own domain.
- **Token identity = comment author.** If the GitLab token belongs to a real user, reviews appear under that user's name. Prefer a Project Access Token (creates a dedicated bot user) once the project Owner is reachable.

## See also

- [docs/deploy-macmini.md](docs/deploy-macmini.md) — full first-time setup with Cloudflare Tunnel
- [docs/pr-agent.md](docs/pr-agent.md) — PR-Agent specifics + local-mode notes
- [docs/litellm-minimax.md](docs/litellm-minimax.md) — LiteLLM ↔ MiniMax config
- [JOURNAL.md](JOURNAL.md) — implementation history, decisions, gotchas
