import subprocess, pathlib
from functools import lru_cache
from .models import Bundle
from . import graph

def _approx_tokens(s: str) -> int:
    return max(1, len(s) // 4)   # ~4 chars/token; good enough for budgeting

@lru_cache(maxsize=512)
def _read(path: str) -> str:
    # cached: a changed file is read once even when several of its functions are inlined.
    # Safe for one-shot CLI/build runs (working tree is static during a review).
    if not path:
        return ""
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

def _excerpt(path: str, line_start: int, line_end: int, ctx: int = 2) -> str:
    src = _read(path).splitlines()
    lo = max(0, line_start - 1 - ctx); hi = min(len(src), line_end + ctx)
    return "\n".join(src[lo:hi])

def build_bundle(repo: str, base: str, data_dir: str, token_budget: int = 24_000) -> Bundle:
    changed = graph.detect_changes(repo, base, data_dir)
    b = Bundle(diff=_git_diff(repo, base))

    # 1) changed-file context, ADAPTIVE to changeset size:
    #    - small/medium: full files (best context; the proven default)
    #    - large changeset (full files blow the budget): only the changed-FUNCTION bodies, highest
    #      risk_score first, and NOTE what was summarised/skipped (no silent truncation).
    full = {}
    for cf in changed:
        full.setdefault(cf.file_path, _read(cf.file_path))
    changed_budget = int(token_budget * 0.6)   # leave room for the diff + related context
    if sum(_approx_tokens(v) for v in full.values()) <= changed_budget:
        b.changed_files = full
    else:
        used = included = dropped = 0
        per_file = {}
        for cf in sorted(changed, key=lambda c: -c.risk_score):
            ex = _excerpt(cf.file_path, cf.line_start, cf.line_end)
            t = _approx_tokens(ex)
            if used + t > changed_budget:
                dropped += 1
                continue
            per_file.setdefault(cf.file_path, []).append(
                f"# {cf.qualified_name} ({cf.line_start}-{cf.line_end}, risk {cf.risk_score:.2f})\n{ex}")
            used += t; included += 1
        b.changed_files = {p: "\n\n".join(v) for p, v in per_file.items()}
        b.notes.append(
            f"大改動：{len(full)} 個改動檔全文超出預算，改為只納入 {included} 個高風險改動函式的片段"
            f"（依 risk_score 排序），略過 {dropped} 個較低風險函式。完整 diff 仍在上方。")

    # 2) context inlining: 1-hop callers + callees of each changed function
    for cf in changed:
        r = graph.blast_radius(cf.qualified_name, data_dir)
        for node in (*r.callers, *r.callees):
            if node.qualified_name not in b.related and node.file_path not in b.changed_files:
                b.related[node.qualified_name] = _snippet(node)

    # 3) token budget: evict related first; truncate the diff only as a last resort (both noted).
    def total():
        return (_approx_tokens(b.diff)
                + sum(_approx_tokens(v) for v in b.changed_files.values())
                + sum(_approx_tokens(v) for v in b.related.values()))
    keys = list(b.related.keys())
    while total() > token_budget and keys:
        b.related.pop(keys.pop())
    if total() > token_budget:
        fixed = total() - _approx_tokens(b.diff)
        keep_chars = max(0, (token_budget - fixed) * 4)
        if len(b.diff) > keep_chars:
            b.diff = b.diff[:keep_chars] + "\n…（diff 過大，已截斷以符合 token 預算）"
            b.notes.append("diff 過大，已截斷。")
    b.est_tokens = total()
    return b
