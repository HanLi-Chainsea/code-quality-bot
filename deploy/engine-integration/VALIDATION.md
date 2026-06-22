# Phase 3 — go-live validation

## Image / deploy
- `cqb-pr-agent-engine:local` built FROM the pinned `codiumai/pr-agent` digest + `review_engine` +
  `cqb_patch` + an **isolated** code-review-graph venv (`/opt/crg-venv`, via `CQB_CRG_BIN`).
  Isolating CRG was required: pip-installing it into PR-Agent's python upgraded starlette
  0.48→1.3.1 and crashed the webhook server (`Router(on_startup=...)` removed) — see `f4f8610`.
- prod compose runs this image; container boots clean:
  `[cqb-patch] context patch applied` / `[cqb-patch] verify patch applied` / `Uvicorn running`.
- tunnel `https://cqb.chainseaclaw.win/webhook` → HTTP 405 (reachable end-to-end).

## In-container enrichment path (the heavy, previously-unproven part)
Ran `repo_graph.blast_context()` inside the live `cqb-pr-agent` container for aipoolserver
`a17d79e9b` (base = its parent `d2eae468a`):
- cloned the repo in-container (clean URL; token supplied via env credential helper),
- built the graph with the isolated CRG venv,
- produced **3957 chars** of cross-file context including the callee
  `AuthUtil.getAccountTenantUserVoByPhone` (exactly the off-diff context diff-only review lacks).
- **No token leaked** to `.git/config` (`grep glpat /cqb/repos` → none). ~22s, clone now warm.

## Rollback
Set the `pr-agent` image back to `codiumai/pr-agent@sha256:a5741a479f...e6f`, re-add the
`entrypoint: ["python","-m","pr_agent.servers.gitlab_webhook"]` line, set `PYTHONPATH: "/app"`,
drop the `CQB_*` env + `cqb_repos` volume → vanilla PR-Agent. (Patches are also best-effort: any
runtime failure falls back to the original diff/flow, so a bad enrichment never blocks a review.)

## Correction — verify was a silent no-op until the REVIEWER_* wiring (2026-06-22)
The container never set `REVIEWER_*`, so `Client.from_env()` defaulted to `127.0.0.1:4000` —
which **inside this container** is its own localhost, NOT `cqb-litellm`. Every verify call hit
connection-refused → per-issue except → finding kept (不漏 default). So **verify never actually
ran in prod**; any earlier "the #425 Asserts.fail FP was dropped by verify" claim was wrong —
that MR's 0 findings came from PR-Agent's own find (with blast-radius context), not verify.

## Verify now runs on the LOCAL MLX model (thinking-on)
`docker-compose.yml` wires the engine's verify to the host's oMLX server (`Qwen3.5-9B-MLX-4bit`)
via `host.docker.internal:31968`. FIND stays on PR-Agent's MiniMax; only VERIFY is local.
- thinking stays ON — the engine's tolerant `_parse_json` filters the reasoning prose and
  salvages findings from malformed/truncated JSON, so we never disable the model's thinking.
- env knobs (`REVIEWER_TIMEOUT=900`, `REVIEWER_VERIFY_MAX_TOKENS=20000`, `REVIEWER_MAX_WORKERS=2`)
  give the slow local reasoner room without thrashing the Mac mini.
- In-container proof: fed the exact #425 `Asserts.fail` "keeps running" premise + the real
  `Asserts.fail` source (`throw new ApiException`). Local thinking-on model returned
  **confirmed=false** ("前提與事實不符") in **77s** — the diff-myopia FP is now genuinely refuted.

## Pending (needs a human /review trigger — agent cannot post to GitLab)
Comment `/review` on a real aipoolserver MR and confirm the live verify drops a diff-myopia
finding (watch for `[cqb-patch] verify DROPPED ...` in the container logs).
