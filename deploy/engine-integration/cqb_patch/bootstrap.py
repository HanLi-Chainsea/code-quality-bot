"""Entrypoint: monkeypatch PR-Agent, then hand off to its gitlab webhook server.
Run as: python -m cqb_patch.bootstrap"""
import os, sys, runpy
from pr_agent.algo import pr_processing
from pr_agent.tools import pr_reviewer
from . import context_patch, verify_patch, repo_graph

def _log(msg):  # visible in container logs so a silently-failed patch is noticeable
    print(f"[cqb-patch] {msg}", file=sys.stderr, flush=True)

# Guard: if a future PR-Agent rename breaks a seam, fail LOUDLY at startup rather than silently
# running vanilla. (digest-pinned base makes this deterministic.)
assert hasattr(pr_processing, "get_pr_diff"), "cqb-patch: pr_processing.get_pr_diff missing — PR-Agent changed"
assert hasattr(pr_reviewer.PRReviewer, "_prepare_pr_review"), "cqb-patch: PRReviewer._prepare_pr_review missing"

# 1) cross-cutting context: wrap the shared diff builder
pr_processing.get_pr_diff = context_patch.wrap_get_pr_diff(pr_processing.get_pr_diff)
# pr_reviewer imported get_pr_diff by name at module load -> rebind that reference too
pr_reviewer.get_pr_diff = pr_processing.get_pr_diff
_log("context patch applied (get_pr_diff wrapped)")

# 2) review-only verify: filter self.prediction before _prepare_pr_review
_orig_prepare = pr_reviewer.PRReviewer._prepare_pr_review
def _prepare_with_verify(self):
    try:
        mr = self.git_provider.mr
        repo_dir = repo_graph.ensure_repo(
            context_patch._clone_url(self.git_provider),
            mr.diff_refs["head_sha"], context_patch.CLONE_BASE)
        if self.prediction:
            self.prediction = verify_patch.filter_prediction(self.prediction, repo_dir)
    except Exception:
        pass   # verify is best-effort; never block publishing
    return _orig_prepare(self)
pr_reviewer.PRReviewer._prepare_pr_review = _prepare_with_verify

if __name__ == "__main__":
    runpy.run_module("pr_agent.servers.gitlab_webhook", run_name="__main__")
