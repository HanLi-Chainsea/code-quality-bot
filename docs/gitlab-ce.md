# GitLab CE (Track 2 test instance) — BUILD & USAGE
## BUILD
- `docker compose up -d gitlab-ce` → http://localhost:8929 (boot ~2-5 min; container cqb-gitlab; ~4GB RAM).
## USAGE / seeding (gotchas baked into scripts/seed-gitlab.sh + setup.sh)
1. Root API token: via `gitlab-rails runner`, MUST set `expires_at: Date.today+365` (modern GitLab requires it).
   We pin token value 'cqb-root-token' via `t.set_token(...)`.
2. Push samples: a shallow clone (`--depth 1`) is REJECTED → `git fetch --unshallow origin` first.
3. Webhook to a local address: GitLab CE rejects it ("Invalid url given") even with
   `allow_local_requests_from_web_hooks_and_services=true` (single-label host / local-IP validation quirk).
   => For the lab, drive PR-Agent via the CLI against the MR URL instead of the auto webhook.
   In production, deploy pr-agent behind a real hostname/DNS so the webhook validates.
## Reviewing an MR
`docker run --rm --network code-quality-bot_default -v $(pwd)/pr-agent/.pr_agent.gitlab.toml:/app/pr_agent/settings/.secrets.toml:ro codiumai/pr-agent:latest --pr_url=http://cqb-gitlab:8929/root/petclinic/-/merge_requests/<iid> review`
