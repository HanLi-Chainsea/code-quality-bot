# Implementation Journal
## 2026-06-03 — Task 1: scaffold
Created project skeleton, git init.

## 2026-06-03 — Task 2: LiteLLM->MiniMax
Proxy up on :4000 (container cqb-litellm). /v1/chat/completions returns "pong" via MiniMax (model=minimax). NOTE: compose network = code-quality-bot_default (not cqb_default); runners must use this name.

## 2026-06-03 — Task 3: PR-Agent CLI (Track1 review) — WORKS
Local-mode review via MiniMax produced a meaningful review on samples/review-sample
(caught: discount pct>100→negative price + float-money; fetchUser URL injection).
Config gotchas discovered (→ docs/pr-agent.md):
1. Local mode needs git_provider="local" IN config file (dotted env CONFIG.GIT_PROVIDER does NOT work).
2. Entrypoint runs `python pr_agent/cli.py` relative → must override entrypoint, cd into repo, PYTHONPATH=/app.
3. `--pr_url=<target_branch>` (NOT a URL) = the base branch to diff current branch against.
4. Mounted repo triggers git "dubious ownership" → must `git config --global --add safe.directory /repo`.
5. Repo must be CLEAN (no uncommitted changes) — used a dedicated clean samples/review-sample, not ChainThings.
6. Custom model needs `custom_model_max_tokens` in [config] (else MAX_TOKENS error).
7. Model name must match the LiteLLM proxy model: use `openai/minimax` (proxy model_name=minimax).
8. publish_output=true → local provider writes review to <repo>/review.md.
Verdict so far: PR-Agent review quality on MiniMax = good (caught real issues). Token use small (~1.5k diff).
