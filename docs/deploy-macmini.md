# Deploy to a Mac mini — cloud GitLab + Cloudflare Tunnel

## What you'll have
Mac mini runs 2 containers (litellm→MiniMax + pr-agent webhook). A Cloudflare Tunnel gives the
webhook a public HTTPS URL. Your cloud GitLab calls that URL on every MR → PR-Agent reviews it
(via MiniMax) and posts the review back into the MR. Colleagues install nothing.

```
gitlab.com ──webhook HTTPS──▶ Cloudflare Tunnel ──▶ Mac mini pr-agent(:3033) ─▶ litellm ─▶ MiniMax
   ▲ pr-agent fetches diff + posts comment (outbound HTTPS) ───────────────────────────────┘
```

## Prereqs
- Mac mini (Intel or Apple Silicon — pr-agent runs emulated on Apple Silicon, fine for a webhook svc).
- Docker Desktop for Mac (set: General → Start Docker Desktop when you log in).
- A MiniMax API key (works on api.minimax.io).
- Cloud GitLab admin/owner of the group you want reviewed (to add a webhook + a bot token).
- A Cloudflare account (free) + a domain on Cloudflare (or use a free *.trycloudflare quick tunnel for testing).

## Step 1 — keep the Mac awake
System Settings → Energy → "Prevent automatic sleeping when the display is off" = ON.
(Or run `caffeinate -dimsu &` / a launchd job.)

## Step 2 — copy the deploy package + fill secrets
Copy the `deploy/` folder to the Mac mini, then:
```
cd deploy
cp .env.example .env          # set MINIMAX_API_KEY + LITELLM_MASTER_KEY
cp pr_agent.gitlab.toml.example pr_agent.gitlab.toml && chmod 600 pr_agent.gitlab.toml   # real secrets; gitignored
# then edit pr_agent.gitlab.toml:
#   [openai] key      = same as LITELLM_MASTER_KEY
#   [gitlab] url      = https://gitlab.com  (or your cloud GitLab)
#   [gitlab] personal_access_token = a bot token (see Step 4)
#   [gitlab] shared_secret = a random string (you'll paste the same into GitLab in Step 5)
```

## Step 3 — start the 2 containers
```
docker compose up -d
docker compose logs -f pr-agent     # should show: Uvicorn running on http://0.0.0.0:3000
curl -i http://127.0.0.1:3033/      # should reach the server; 405 is OK for a GET
```

## Step 4 — make a GitLab bot token
GitLab → your Group → Settings → Access Tokens → create a token:
- name: `code-quality-bot`, role: Developer (or Reporter+), scope: **api**.
Paste it into `pr_agent.gitlab.toml` → `[gitlab] personal_access_token`. Re-run `docker compose up -d`.
This token is the identity the AI review is posted as.

## Step 5 — expose the webhook with Cloudflare Tunnel
```
brew install cloudflared
cloudflared tunnel login                       # opens browser, pick your domain
cloudflared tunnel create cqb
cloudflared tunnel route dns cqb cqb.YOURDOMAIN.com
# run it (point the public hostname at the local pr-agent port):
cloudflared tunnel --url http://127.0.0.1:3033 run cqb
# (for a permanent service: `cloudflared service install` + a config.yml mapping cqb.YOURDOMAIN.com -> http://127.0.0.1:3033)
```
Now `https://cqb.YOURDOMAIN.com/webhook` reaches the Mac mini.
(Quick test alternative, no domain: `cloudflared tunnel --url http://127.0.0.1:3033` prints a temporary https URL.)

## Step 6 — register the webhook in GitLab (once, group-level = all repos covered)
GitLab → Group → Settings → Webhooks → Add:
- URL: `https://cqb.YOURDOMAIN.com/webhook`
- Secret token: the SAME string as `[gitlab] shared_secret`
- Trigger: **Merge request events** (uncheck the rest)
- SSL verification: on
Save → "Test" → Merge request events.

## Step 7 — try it
Open a Merge Request in any repo in that group. Within ~30s PR-Agent posts a review into the MR.
Devs can also type `/review`, `/improve`, `/ask "..."` in MR comments.

## Ops notes
- Cost guard: `config.yaml` caps MiniMax spend at $100/mo (raise/lower as needed).
- Update: `docker compose pull && docker compose up -d`.
- Security: keep `.env` + `pr_agent.gitlab.toml` private (gitignored); least-privilege GitLab token; the webhook is only reachable via the tunnel + secret token.
- Apple Silicon: if pr-agent image is amd64-only, Docker Desktop runs it under emulation automatically — no action needed.

## Alternative (no tunnel): GitLab CI runner on the Mac mini
Register a self-hosted GitLab runner on the Mac mini and add a `.gitlab-ci.yml` job that runs PR-Agent
on `merge_request` pipelines. Runner polls GitLab (outbound only) → no inbound/tunnel. Trade-off: needs a
CI-config in each repo (less "zero-touch" than a group webhook). Use this if you can't/won't run a tunnel.

## Swapping the model later (the built-in "口")
LiteLLM is the swap seam. **PR-Agent always calls the stable alias `reviewer`** (`pr_agent.gitlab.toml`,
`model = "openai/reviewer"`) — you never touch PR-Agent when changing models.

To switch:
1. In `deploy/config.yaml`, repoint the `reviewer` block to another backend (a ready-to-uncomment
   "SWAP OPTIONS" panel is in the file: Claude / OpenAI / Gemini / DeepSeek / local Ollama / local vLLM).
2. Put that provider's key in `deploy/.env` (local models need none).
3. `docker compose up -d --force-recreate litellm` (put the provider key in `.env` first; PR-Agent keeps running).

### Go fully local (nothing leaves the Mac mini — solves the "diff goes to MiniMax" privacy concern)
1. On the Mac mini host: `brew install ollama && ollama pull qwen2.5-coder:14b && ollama serve`.
2. In `config.yaml`, use the LOCAL Ollama `reviewer` block (api_base `http://host.docker.internal:11434/v1`).
3. `docker compose up -d --force-recreate litellm`. Now the diff → Mac mini → local model. Zero data leaves the box.
   (Trade-off: local model quality/speed depends on the Mac mini's RAM/GPU; try a few sizes.)

### Per-repo / per-team different models (optional)
Register multiple aliases in `config.yaml` (e.g. `reviewer`, `reviewer-cheap`) and set PR-Agent's
`model` per deployment, or override via the MR command `/review --config.model=openai/reviewer-cheap`.

## ⚠️ Production hardening & known limitations (dual-model review, 2026-06)
This package is a working starting point, not a hardened multi-tenant service. Before/while running for a real team:

**Secrets & tokens**
- `pr_agent.gitlab.toml` (filled) and `.env` are gitignored — keep them `chmod 600`, never commit. Only `*.example` are tracked.
- GitLab token: prefer a **project access token** over a group token; role **Developer**, scope **api** (do NOT grant `write_repository`); set an **expiry** and a rotation reminder.

**Webhook ingress (the one public surface)**
- Always use an HTTPS tunnel (Cloudflare Tunnel / Tailscale Funnel are HTTPS) — **never a quick/temporary tunnel in prod**.
- Put **Cloudflare Access / a reverse proxy** in front for rate-limit + source allowlist. PR-Agent answers `200` before validating the token and uses a static (replayable) secret — treat the endpoint as semi-exposed.
- If you want MR comment commands (`/review`, `/ask`), also enable **Note events** on the webhook (Merge-request-events alone won't deliver them).

**Cost control**
- The `max_budget` in `config.yaml` is **best-effort** (in-memory, resets on restart; MiniMax isn't in LiteLLM's cost map). Set a **hard spend limit on the MiniMax side** + a billing alert as the real guard. For accurate tracking, point LiteLLM at a Postgres `database_url`.

**Reliability**
- PR-Agent returns `200` then processes in the background, so a crash/restart **drops that MR's review** (GitLab won't resend). For now: rely on the healthcheck + re-trigger by re-opening/`/review`. A durable queue is a future upgrade.
- Images are pinned by digest. Re-pin (`docker compose pull` is disabled by digest) only after testing a new version in staging.

**Lab vs prod**
- `scripts/setup.sh`, `scripts/seed-gitlab.sh`, the root `docker-compose.yml` (with GitLab CE), and `runners/*` are **LAB ONLY** (throwaway GitLab CE, fixed admin token, shell-interpolated args). Never run them against production. Production = `deploy/` only.
