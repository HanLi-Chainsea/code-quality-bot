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
# edit pr_agent.gitlab.toml:
#   [openai] key      = same as LITELLM_MASTER_KEY
#   [gitlab] url      = https://gitlab.com  (or your cloud GitLab)
#   [gitlab] personal_access_token = a bot token (see Step 4)
#   [gitlab] shared_secret = a random string (you'll paste the same into GitLab in Step 5)
```

## Step 3 — start the 2 containers
```
docker compose up -d
docker compose logs -f pr-agent     # should show: Uvicorn running on http://0.0.0.0:3000
curl -s localhost:3033/             # should return 200
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
cloudflared tunnel --url http://localhost:3033 run cqb
# (for a permanent service: `cloudflared service install` + a config.yml mapping cqb.YOURDOMAIN.com -> http://localhost:3033)
```
Now `https://cqb.YOURDOMAIN.com/webhook` reaches the Mac mini.
(Quick test alternative, no domain: `cloudflared tunnel --url http://localhost:3033` prints a temporary https URL.)

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
