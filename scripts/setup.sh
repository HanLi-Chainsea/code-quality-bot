#!/usr/bin/env bash
# ╔════════════════════════════════════════════════════════════════════╗
# ║ LAB ONLY — do NOT run in production.                                ║
# ║ Spins up a throwaway GitLab CE with a FIXED admin token + force-    ║
# ║ push. For real deploy use deploy/ + docs/deploy-macmini.md.         ║
# ╚════════════════════════════════════════════════════════════════════╝
# One-command bring-up of the code-quality-bot bake-off lab.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "cp .env.example .env and set MINIMAX_API_KEY first"; exit 1; }
if command -v sg >/dev/null 2>&1 && getent group docker >/dev/null 2>&1; then
  DK(){ sg docker -c "$*"; }   # Linux host without docker-group membership
else
  DK(){ eval "$@"; }            # macOS (Docker Desktop) or Linux user already in docker group
fi

echo "▶ litellm + gitlab-ce..."
DK "docker compose up -d litellm gitlab-ce"
echo "▶ waiting for GitLab (first boot ~2-5 min)..."
until curl -s -o /dev/null -w "%{http_code}" http://localhost:8929/users/sign_in | grep -q 200; do sleep 15; done

echo "▶ root token (needs expires_at on modern GitLab)..."
DK "docker exec cqb-gitlab gitlab-rails runner \"u=User.find_by_username('root'); u.personal_access_tokens.where(name:'cqb').destroy_all; t=u.personal_access_tokens.create(scopes:['api','write_repository','read_repository'],name:'cqb',expires_at: Date.today+365); t.set_token('cqb-root-token'); t.save!\""
curl -s --header 'PRIVATE-TOKEN: cqb-root-token' -X PUT http://localhost:8929/api/v4/application/settings -d 'allow_local_requests_from_web_hooks_and_services=true' >/dev/null

echo "▶ seed petclinic..."
[ -d samples/petclinic ] || git clone https://github.com/spring-projects/spring-petclinic samples/petclinic
( cd samples/petclinic; test -f .git/shallow && git fetch --unshallow origin || true
  curl -s --header 'PRIVATE-TOKEN: cqb-root-token' -X POST http://localhost:8929/api/v4/projects -d 'name=petclinic&visibility=private' >/dev/null || true
  git remote remove cqb 2>/dev/null || true
  git remote add cqb http://root:cqb-root-token@localhost:8929/root/petclinic.git
  git push -u cqb HEAD:main -f )

echo "▶ pr-agent webhook server..."
DK "docker compose up -d pr-agent"
echo "✅ up. Track1: bash runners/run-pr-agent.sh <repo> review <base>"
echo "   Track2: open an MR on http://localhost:8929/root/petclinic then:"
echo "   sg docker -c \"docker run --rm --network code-quality-bot_default -v \$(pwd)/pr-agent/.pr_agent.gitlab.toml:/app/pr_agent/settings/.secrets.toml:ro codiumai/pr-agent:latest --pr_url=<MR_URL> review\""
