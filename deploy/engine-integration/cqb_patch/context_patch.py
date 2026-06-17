"""Wrap pr_processing.get_pr_diff so its returned diff carries blast-radius context. Because every
PR-Agent tool calls get_pr_diff, this single seam enriches review AND describe/improve/etc."""
import os, functools
from . import repo_graph

CLONE_BASE = os.environ.get("CQB_CLONE_BASE", "/cqb/repos")

def _clone_url(gp) -> str:
    token = os.environ.get("CQB_GITLAB_TOKEN", "")
    base = gp.gl.url.rstrip("/")                      # https://gitlab.com
    host = base.split("://", 1)[-1]
    scheme = base.split("://", 1)[0]
    return f"{scheme}://oauth2:{token}@{host}/{gp.id_project}.git"

def wrap_get_pr_diff(original):
    @functools.wraps(original)
    def wrapper(git_provider, token_handler, model, *args, **kwargs):
        diff = original(git_provider, token_handler, model, *args, **kwargs)
        if not isinstance(diff, str) or not diff.strip():
            return diff                               # multi-patch/empty path: leave untouched
        try:
            mr = git_provider.mr
            base_sha = mr.diff_refs["base_sha"]; head_sha = mr.diff_refs["head_sha"]
            repo_dir = repo_graph.ensure_repo(_clone_url(git_provider), head_sha, CLONE_BASE)
            ctx = repo_graph.blast_context(repo_dir=repo_dir, base_sha=base_sha,
                                           work_dir=repo_dir + ".work")
            if ctx:
                return diff + "\n\n" + ctx
        except Exception:
            pass                                      # never break the existing diff path
        return diff
    return wrapper
