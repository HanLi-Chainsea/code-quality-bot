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

## Pending (needs a human /review trigger — agent cannot post to GitLab)
Comment `/review` on a real aipoolserver MR and confirm: (a) the review reasons across files
(references caller/callee behaviour), and (b) a diff-myopia finding like the `Asserts.fail`
"keeps running" claim (the #425 false positive) is dropped by grounded-refutation verify.
