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

## 2026-06-03 — Task 4: samples
Cloned spring-petclinic (Java/Maven). Compiled OK (target/classes present) → ready for Diffblue/Qodo Java test-gen.
ChainThings(TS) used in place for TS targets. (samples/* gitignored.)

## 2026-06-03 — Task 6: Diffblue — BLOCKED (license)
diffblue/cover-cli:latest pulls fine (803MB, bundles JDK17, dcover 2026.04.01). BUT `dcover create`
exits immediately demanding a paid license key (diffblue.com/pricing). The free Community Edition is an
IntelliJ plugin only — NOT the automatable CLI. => Diffblue autonomous Java test-gen is NOT free-to-self-host;
adoption requires buying a commercial license. (Quality not assessable in this bake-off without a license.)
FINDING for REPORT: Diffblue = strong Java/regression story but commercial-license gate; evaluate via trial.

## 2026-06-03 — Task 5: Qodo Cover (cover-agent) — BLOCKED (unmaintained + LLM base-url)
- No prebuilt image; install via `pip install git+https://github.com/qodo-ai/qodo-cover.git` (needs git in image).
- Repo is NO LONGER MAINTAINED (README: "fork it if you wish to continue").
- cover-agent runs but its LLM call gets [Errno 111] Connection refused even though the SAME LiteLLM SDK
  works with OPENAI_API_BASE in a bare probe (returns "Pong!"). cover-agent ignores OPENAI_API_BASE/OPENAI_BASE_URL
  and won't target a self-hosted OpenAI-compatible proxy (MiniMax via LiteLLM) without code changes.
FINDING for REPORT: Qodo Cover OSS = NOT usable out-of-box for self-hosted MiniMax; unmaintained.

## Track-1 summary (bake-off)
- PR-Agent: ✅ free, self-host, works with MiniMax via LiteLLM, good review (caught real bugs). WINNER for review.
- Diffblue: ⚠️ pulls free but `dcover create` requires a PAID license. Strong Java story but commercial gate.
- Qodo Cover OSS: ❌ unmaintained + can't point at self-hosted LLM proxy out-of-box.
=> Free test-gen for self-hosted Java/MiniMax is the real GAP. Review is solved (PR-Agent).

## 2026-06-03 — Task 7: GitLab CE (Track 2)
GitLab CE up on :8929 (~2 min boot, container cqb-gitlab). Gotchas:
- PAT via gitlab-rails runner REQUIRES expires_at (newer GitLab): `expires_at: Date.today + 365`.
- Shallow clone (--depth 1) is rejected on push ("shallow update not allowed") → `git fetch --unshallow` first.
Seeded root/petclinic with full history + known token 'cqb-root-token'.
