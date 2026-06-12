#!/usr/bin/env bash
# Track-1 local review: diffs the repo's current branch against <target_branch>.
# Usage: run-pr-agent.sh <repo_path> [command] [target_branch]
set -euo pipefail
REPO="${1:?repo path}"; CMD="${2:-review}"; TARGET="${3:-master}"
OUT="eval/out/pr-agent-$(basename "$REPO")-$CMD.txt"
mkdir -p eval/out
sg docker -c "docker run --rm --network code-quality-bot_default \
  --entrypoint bash \
  -v $(pwd)/pr-agent/.pr_agent.local.toml:/app/pr_agent/settings/.secrets.toml:ro \
  -v $(realpath "$REPO"):/repo \
  codiumai/pr-agent:latest -c 'git config --global --add safe.directory /repo && cd /repo && PYTHONPATH=/app python /app/pr_agent/cli.py --pr_url=$TARGET $CMD'" 2>&1 | tee "$OUT"
echo "saved: $OUT"
