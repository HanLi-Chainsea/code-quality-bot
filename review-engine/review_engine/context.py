import subprocess, pathlib
from .models import Bundle
from . import graph

def _approx_tokens(s: str) -> int:
    return max(1, len(s) // 4)   # ~4 chars/token; good enough for budgeting

def _read(path: str) -> str:
    try:
        return pathlib.Path(path).read_text(errors="replace")
    except OSError:
        return ""

def _snippet(node) -> str:
    src = _read(node.file_path).splitlines()
    lo = max(0, node.line_start - 1); hi = min(len(src), node.line_end)
    body = "\n".join(src[lo:hi])
    return f"# {node.qualified_name} ({node.file_path}:{node.line_start})\n{body}"

def _git_diff(repo: str, base: str) -> str:
    return subprocess.run(["git", "-C", repo, "diff", base, "--"],
                          capture_output=True, text=True).stdout

def build_bundle(repo: str, base: str, data_dir: str, token_budget: int = 24_000) -> Bundle:
    changed = graph.detect_changes(repo, base, data_dir)
    b = Bundle(diff=_git_diff(repo, base))

    # 1) full changed files (highest priority — never dropped first)
    for cf in changed:
        if cf.file_path not in b.changed_files:
            b.changed_files[cf.file_path] = _read(cf.file_path)

    # 2) context inlining: 1-hop callers + callees of each changed function
    for cf in changed:
        r = graph.blast_radius(cf.qualified_name, data_dir)
        for node in (*r.callers, *r.callees):
            if node.qualified_name not in b.related and node.file_path not in b.changed_files:
                b.related[node.qualified_name] = _snippet(node)

    # 3) token budget: changed files first; drop related (lowest risk_score-adjacent first) until under budget
    def total():
        return (_approx_tokens(b.diff)
                + sum(_approx_tokens(v) for v in b.changed_files.values())
                + sum(_approx_tokens(v) for v in b.related.values()))
    # drop related entries until we fit (changed files + diff are kept)
    keys = list(b.related.keys())
    while total() > token_budget and keys:
        b.related.pop(keys.pop())
    b.est_tokens = total()
    if b.est_tokens > token_budget:
        import sys
        print(f"warning: context {b.est_tokens} tok exceeds budget {token_budget} "
              f"(changed files alone); review may exceed the model window", file=sys.stderr)
    return b
