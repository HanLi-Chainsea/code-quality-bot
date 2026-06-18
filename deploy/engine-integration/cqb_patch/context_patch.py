"""Wrap pr_processing.get_pr_diff so its returned diff carries blast-radius context. Because every
PR-Agent tool calls get_pr_diff, this single seam enriches review AND describe/improve/etc."""
import os, functools
from . import repo_graph

CLONE_BASE = os.environ.get("CQB_CLONE_BASE", "/cqb/repos")

def clone_url(gp) -> str:
    """CLEAN https URL with NO token (the token is supplied to git via an env credential helper in
    repo_graph, so it never lands in argv or .git/config)."""
    return f"{gp.gl.url.rstrip('/')}/{gp.id_project}.git"

def wrap_get_pr_diff(original):
    @functools.wraps(original)
    def wrapper(git_provider, token_handler, model, *args, **kwargs):
        diff = original(git_provider, token_handler, model, *args, **kwargs)
        if not isinstance(diff, str) or not diff.strip():
            return diff                               # multi-patch/empty path: leave untouched
        try:
            refs = git_provider.mr.diff_refs
            ctx = repo_graph.blast_context(clone_url(git_provider), refs["head_sha"],
                                           refs["base_sha"], CLONE_BASE)
            if ctx:
                return diff + "\n\n" + ctx
        except Exception as e:
            repo_graph._log(f"context enrichment skipped ({type(e).__name__}: {e})")
        return diff
    return wrapper
