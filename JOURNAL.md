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

## 2026-06-03 — Task 8: PR-Agent on real GitLab MR (Track 2) — WORKS
- PR-Agent CLI with git_provider=gitlab + --pr_url=<MR url> reviewed real MR #1 on root/petclinic and POSTED
  the review INTO the MR (note by root: PR Reviewer Guide, effort 2/5, focus areas with line-links to
  DiscountService.java#L3-4) + set MR label "Review effort 2/5". Saved: eval/out/pr-agent-gitlab-mr-review.md.
- Webhook AUTO-trigger gotcha: GitLab CE rejects local-network webhook URLs ("Invalid url given") even with
  allow_local_requests_from_web_hooks_and_services=true (CE local-address validation quirk). The pr-agent
  webhook server itself runs fine (uvicorn :3000, GET / =200). In production (real hostname/DNS) the webhook
  works; for the lab the CLI-against-MR-URL proves the review+post. Auto-trigger = a deployment detail.
FINDING: PR-Agent in-MR review on self-managed GitLab = WORKS and is good. Recommend deploy via real hostname.

## 2026-06-12 — Production deploy package + hardening (deploy/)
Two-container prod stack for REAL cloud GitLab (no GitLab CE): cqb-litellm + cqb-pr-agent.
- Model-swap panel in config.yaml: PR-Agent always calls a stable `reviewer` alias; swap the model in ONE place.
- Hardening (addresses a codex+gemini review): secrets gitignored + *.example templates, image digests pinned,
  healthcheck/mem/log limits, no-new-privileges, explicit network, LAB-only guards on the bake-off dirs.
- Ops handbook rewrite (bilingual README), default output zh-TW, cross-platform setup.sh.

## 2026-06-15 — Production go-live tuning
- Model MiniMax-Text-01 → MiniMax-M2.1 (code/agent model). custom_model_max_tokens 32k → 200k.
- GOTCHA (thinking models): M2.1 wraps reasoning in `<think>…</think>` INSIDE `content` → breaks PR-Agent's YAML
  parser (and our engine's JSON parse). FIX: LiteLLM native `minimax/` provider + `extra_body: {reasoning_split: true}`
  → reasoning goes to a separate `reasoning_content` field, `content` stays clean. Verified (content='OK', no leak).
  Kept thinking ON (it's the quality) rather than rolling back to a weaker non-thinking model.
- config.yaml made a gitignored LOCAL copy (model choice must not be enshrined in VC — goes stale) + a
  model-agnostic config.yaml.example template. Same pattern as the secrets files.
- Cloudflare NAMED tunnel cqb.chainseaclaw.win → 127.0.0.1:3033 (stable URL replaces ephemeral trycloudflare).
  GOTCHA 1: `sudo cloudflared service install` wrote a BARE plist (ran `cloudflared` with no args, because root's
  home has no config.yml) → tunnel never ran. FIX: explicit launchd plist with `--config <abs path> tunnel run cqb`.
  GOTCHA 2: `localhost` resolves to IPv6 `[::1]` → connection refused; the service binds IPv4 `127.0.0.1` only.
  Always point cloudflared at `127.0.0.1`, never `localhost`.
- GitLab webhook owner guide: enable BOTH "Merge request events" AND "Comments" (the latter is what makes
  `/review` `/improve` `/ask` work in MR comments — previously omitted, leaving only auto-review).

## 2026-06-15 — Phase 1: blast-radius review engine (review-engine/)
WHY: PR-Agent reads only the diff → shallow + noisy → worthless to a senior. NORTH-STAR: a senior can FULLY TRUST
it raises exactly the risks they would — bidirectional: 不漏 (recall vs senior) + 不吵 (precision, FP < 10%).
WHAT: code-review-graph builds a code graph; blast radius (callers/callees) read from graph.db `edges` (kind=CALLS)
— NOT via MCP; context inlining (full changed files + 1-hop caller/callee bodies, token-budgeted); two-stage
find → grounded-refutation verify via the LiteLLM `reviewer` alias. Offline CLI + diff-only `--baseline` for A/B.
19 unit tests (TDD). Plan/design in docs/review-engine-plan.md + docs/review-engine-phase1-plan.md.

code-review-graph gotchas: needs Python 3.10+ (system 3.9 → "No matching distribution"); `build --repo --data-dir`;
`detect-changes --base` returns JSON `changed_functions` but NO callers → query graph.db `edges` directly
(callers = `WHERE kind='CALLS' AND target_qualified=X`). Build is fast: 1314 Java files → 4s, even resolves Spring
DI CALLS edges.

LIVE-TRIAL findings (each a real bug the trial surfaced + fixed):
- max_tokens=2000 truncated the reasoning model's JSON (finish_reason=length) → partial JSON → silent 0 findings.
  → raise to 8000 (reasoning + answer share the completion budget).
- verify conflated a PARSE FAILURE (technical miss) with a refutation → silently dropped real findings.
  → keep-by-default: drop ONLY on explicit confirmed=false; parse-miss surfaces as unverified (北極星 不漏).
- the find LLM emits shortened/relative file paths → verifier read EMPTY source → wrongly refuted (false negative).
  → resolve finding.file back to the bundle's absolute paths.

MODEL A/B (key finding): swapped `reviewer` to MiniMax-M3 (strongest, SWE-Bench Pro 59%, 1M ctx). M3 has a higher
ceiling (found a TOCTOU race M2.1 missed) BUT is erratic (0/1/3 findings across 3 runs), slow (2–3 min/call),
token-hungry (10–16k reasoning tokens/call). CONCLUSION: the quality bottleneck is the HARNESS (prompt + aggregation),
NOT model size. M2.1 + harness ≈ M3 depth, faster + more consistent. Reverted live to M2.1.

QUALITY LEVERS (the harness that hits the north-star):
- Multi-lens find: run find once per lens (general / breaking-change·cross-file / concurrency·TOCTOU /
  behaviour-change) → union → dedup. Diverse angles surface deeper issues + several passes stabilise recall.
- Verify keep-by-default (above) — protects recall after multi-pass raises it.
- Consolidation pass: merge same-root-cause findings (one logic change reported at N trigger points) into one and
  list every trigger; SAFETY NET keeps any finding the model fails to group (can de-dup, never silently drop).
- Parallelise lens + verify calls (ThreadPoolExecutor) → ~1 min/review.

RESULTS (aipoolserver, real changesets):
- a17d79e9b (AILE JWT login, 2 files): diff-only baseline = 0; engine caught breaking changes (JWT sub→mobile,
  lookup key originalAccountId→phone), a TOCTOU race, the removed last-login-tenant regression, and a non-idempotent
  create in the *callee* — senior-grade cross-file depth. Posted as a real review comment on the commit.
- f393f3325 (auth filter, 1 file): engine found a real fail-open auth-bypass; 8 redundant findings → 1 consolidated
  finding + trigger points.

STATUS: offline CLI, Phase 1 merged to main. LIMITS for Phase 2: large changesets (dozens of files) blow the
full-changed-file token budget → need summarisation/selection; only 3 changesets audited so far; needs real
colleague feedback to calibrate the north-star; not yet wired into the live MR flow.
