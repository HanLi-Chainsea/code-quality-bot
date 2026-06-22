"""Maintain a per-repo persistent clone + code-review-graph and produce blast-radius context, all
under a per-repo lock so concurrent MR webhooks can't see a worktree/graph mid-flipped by another
request. Credentials are passed to git via an env-reading credential helper (never in argv or
.git/config). Best-effort: callers treat any failure as "no enrichment", never fatal."""
import os, re, sys, subprocess, pathlib, hashlib, fcntl, contextlib
from review_engine import context, graph

_SHA_RE = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")   # full SHA-1 / SHA-256 only (no short SHAs)
# git auth via env: the helper echoes the token from $CQB_GITLAB_TOKEN at run time, so the token is
# NOT in argv (ps) and NOT written to .git/config. `-c` config is command-scoped, never persisted.
_CRED = ["-c", "credential.helper=!f() { echo username=oauth2; echo \"password=$CQB_GITLAB_TOKEN\"; }; f"]

def _log(msg: str) -> None:
    print(f"[cqb-patch] {msg}", file=sys.stderr, flush=True)

def _git(args, timeout=120):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, timeout=timeout)

@contextlib.contextmanager
def prepared(clone_url: str, head_sha: str, base_dir: str):
    """Yield (repo_dir, data_dir) checked out at head_sha, holding a per-repo lock for the WHOLE
    block (so reads of the worktree/graph by the caller are race-free vs concurrent webhooks).
    `clone_url` must be a clean http(s) URL with NO token in it."""
    if not _SHA_RE.fullmatch(head_sha or ""):
        raise ValueError(f"refusing unsafe head_sha: {head_sha!r}")
    if not str(clone_url).startswith(("https://", "http://")):
        raise ValueError(f"refusing unsafe clone_url scheme: {clone_url!r}")
    key = hashlib.sha1(clone_url.encode()).hexdigest()[:16]
    repo_dir = str(pathlib.Path(base_dir) / key)
    data_dir = str(pathlib.Path(base_dir) / f"{key}.graph")
    os.makedirs(base_dir, exist_ok=True)
    with open(pathlib.Path(base_dir) / f"{key}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not pathlib.Path(repo_dir, ".git").exists():
            _git([*_CRED, "clone", "--quiet", "--", clone_url, repo_dir], timeout=600)
        _git(["-C", repo_dir, *_CRED, "fetch", "--quiet", "origin", head_sha], timeout=300)
        _git(["-C", repo_dir, "checkout", "--quiet", head_sha])
        yield repo_dir, data_dir

def blast_local(repo_dir: str, data_dir: str, base_sha: str, token_budget: int = 8_000) -> str:
    """Build/update the graph for an ALREADY-checked-out local repo and return the inlined
    caller/callee context for the changes vs base_sha. No clone — directly unit-testable."""
    if (pathlib.Path(data_dir) / "graph.db").exists():
        graph.update(repo_dir, data_dir)
    else:
        graph.build(repo_dir, data_dir)
    bundle = context.build_bundle(repo_dir, base_sha, data_dir, token_budget=token_budget)
    if not bundle.related:
        return ""
    parts = ["## 跨檔上下游（caller/callee，由 blast-radius 引擎提供）"]
    parts += list(bundle.related.values())
    return "\n\n".join(parts)

def blast_context(clone_url: str, head_sha: str, base_sha: str, base_dir: str,
                  token_budget: int = 8_000) -> str:
    """Live path: prepare the repo+graph under the lock, then build the context. '' on any failure
    (logged, never fatal). `base_sha` is validated like head_sha."""
    try:
        if not _SHA_RE.fullmatch(base_sha or ""):
            raise ValueError(f"refusing unsafe base_sha: {base_sha!r}")
        with prepared(clone_url, head_sha, base_dir) as (repo_dir, data_dir):
            return blast_local(repo_dir, data_dir, base_sha, token_budget)
    except Exception as e:
        _log(f"blast_context failed ({type(e).__name__}: {e})")
        return ""
