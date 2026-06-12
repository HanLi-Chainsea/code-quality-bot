# PR-Agent (Qodo Merge OSS) — BUILD & USAGE   [STATUS: ✅ WORKS with MiniMax]
## BUILD
1. Image: `codiumai/pr-agent:latest` (free, Apache-2.0).
2. Local-CLI config `pr-agent/.pr_agent.local.toml`:
   `[config] model="openai/minimax", git_provider="local", custom_model_max_tokens=32000, publish_output=true`
   `[openai] api_base="http://cqb-litellm:4000", key="sk-cqb-localdev"`.
## USAGE (Track-1 local review)
`bash runners/run-pr-agent.sh <repo_path> review <target_branch>`
- Reviews the repo's CURRENT branch vs <target_branch>; writes review to `<repo>/review.md`.
- Other commands: `improve` (code suggestions), `describe`, `ask`.
## GOTCHAS (hard-won — all required)
1. `git_provider="local"` must be IN the config file (dotted env `CONFIG.GIT_PROVIDER` does NOT work).
2. Entrypoint runs `python pr_agent/cli.py` relative → override entrypoint, `cd /repo`, `PYTHONPATH=/app`.
3. `--pr_url=<target_branch>` is the BASE branch name, not a URL.
4. Mounted repo → `git config --global --add safe.directory /repo` (else "dubious ownership").
5. Repo must be CLEAN (no uncommitted changes) — use a dedicated clean repo/branch.
6. Custom model needs `custom_model_max_tokens` (else MAX_TOKENS error).
7. Model name must match the LiteLLM proxy model: `openai/minimax`.
8. `publish_output=true` → local provider writes `<repo>/review.md`.
## Track-2 (real GitLab MR) — DEFERRED (see plan Task 8): image `codiumai/pr-agent:latest-gitlab_webhook`.
