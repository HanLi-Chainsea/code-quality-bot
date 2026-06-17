"""Given a local repo + base ref, produce the blast-radius context string by reusing the engine.
For the live path, ensure_repo() lazily maintains a persistent clone + graph keyed by project."""
import os, re, subprocess, pathlib, hashlib, fcntl
from review_engine import context, graph

_SHA_RE = re.compile(r"[0-9a-fA-F]{7,64}")  # a git SHA — never a flag/path, blocks argv smuggling

def blast_context(repo_dir: str, base_sha: str, work_dir: str, token_budget: int = 8_000) -> str:
    """Build the graph for `repo_dir` (HEAD) and return the inlined caller/callee context for the
    changes vs `base_sha`. Returns '' when there are no changed functions or anything fails — this
    is best-effort enrichment, never fatal to the review."""
    try:
        data_dir = str(pathlib.Path(work_dir) / "graph")
        os.makedirs(data_dir, exist_ok=True)
        if (pathlib.Path(data_dir) / "graph.db").exists():
            graph.update(repo_dir, data_dir)
        else:
            graph.build(repo_dir, data_dir)
        bundle = context.build_bundle(repo_dir, base_sha, data_dir, token_budget=token_budget)
        if not bundle.related:
            return ""
        parts = ["## 跨檔上下游（caller/callee，用於判斷影響；由 blast-radius 引擎提供）"]
        parts += list(bundle.related.values())
        return "\n\n".join(parts)
    except Exception:
        return ""   # enrichment must never break PR-Agent's existing flow

def ensure_repo(clone_url: str, head_sha: str, base_dir: str) -> str:
    """Lazily maintain ONE persistent clone per repo under base_dir; fetch + checkout head_sha.
    Serialised by a per-repo file lock so concurrent MR webhooks don't corrupt the working copy.
    Returns the local repo path (checked out at head_sha)."""
    # validate untrusted inputs before they reach git (defence-in-depth vs argv flag-smuggling):
    # head_sha must be a bare SHA; clone_url must be an http(s) URL we built.
    if not _SHA_RE.fullmatch(head_sha or ""):
        raise ValueError(f"refusing unsafe head_sha: {head_sha!r}")
    if not str(clone_url).startswith(("https://", "http://")):
        raise ValueError(f"refusing unsafe clone_url scheme: {clone_url!r}")
    key = hashlib.sha1(clone_url.encode()).hexdigest()[:16]
    repo_dir = str(pathlib.Path(base_dir) / key)
    os.makedirs(base_dir, exist_ok=True)
    lock_path = pathlib.Path(base_dir) / f"{key}.lock"
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not pathlib.Path(repo_dir, ".git").exists():
            subprocess.run(["git", "clone", "--quiet", "--", clone_url, repo_dir], check=True,
                           capture_output=True, text=True)
        subprocess.run(["git", "-C", repo_dir, "fetch", "--quiet", "origin", head_sha],
                       check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", repo_dir, "checkout", "--quiet", head_sha],
                       check=True, capture_output=True, text=True)
    return repo_dir
