import json, re, pathlib
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from .models import Finding, Bundle
from . import prompt, graph
from .llm import Client

_SEV_ORDER = {"minor": 0, "major": 1, "blocker": 2}

# Reasoning models spend completion budget on thinking before the JSON answer; keep headroom.
FIND_MAX_TOKENS = 8000
VERIFY_MAX_TOKENS = 8000
# Cap the source fed to the verifier so a huge file + all callers/callees can't blow the
# completion budget (which truncates the verdict and silently loses the finding).
VERIFY_SOURCE_MAX_CHARS = 12000

def _parse_json(text: str) -> dict:
    """Tolerate models that wrap JSON in prose/fences; never raise on bad output."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}

def _read(path: str) -> str:
    if not path:
        return ""
    try:
        return pathlib.Path(path).read_text(errors="replace")
    except OSError:
        return ""

def _resolve_path(path: str, known: list) -> str:
    """LLMs often emit a shortened/relative file path; map it back to the real absolute
    path from the bundle so the verifier reads actual source and graph lookups match.
    Falls back to the original path when the match is missing or ambiguous."""
    if not path or path in known:
        return path
    cands = [k for k in known if k.endswith(path)]
    if not cands:
        base = path.rsplit("/", 1)[-1]
        cands = [k for k in known if k.rsplit("/", 1)[-1] == base]
    return cands[0] if len(cands) == 1 else path

def _premise_source(finding: Finding, data_dir: str) -> str:
    """Source the verifier reads to confirm/refute the premise: the finding's own file,
    plus — when a graph exists — the 1-hop caller/callee bodies of functions in that file
    (so 'the caller already handles it' claims can be checked against real callers).
    Crash-safe when data_dir is empty / graph.db is absent (baseline mode)."""
    parts = [_read(finding.file)]
    db = (pathlib.Path(data_dir) / "graph.db") if data_dir else None
    if db and db.exists():
        conn = graph._db(data_dir)
        try:
            qns = [r[0] for r in conn.execute(
                "SELECT qualified_name FROM nodes WHERE file_path=? AND kind='Function'",
                (finding.file,))]
        finally:
            conn.close()
        for qn in qns:
            r = graph.blast_radius(qn, data_dir)
            for node in (*r.callers, *r.callees):
                src = _read(node.file_path).splitlines()
                lo = max(0, node.line_start - 1); hi = min(len(src), node.line_end)
                parts.append(f"# {node.qualified_name}\n" + "\n".join(src[lo:hi]))
    return "\n\n".join(p for p in parts if p)[:VERIFY_SOURCE_MAX_CHARS]

def _title_sig(title: str) -> str:
    # signature = first 8 non-space chars, lowercased; merges "normalizePhone 缺驗證" vs
    # "normalizePhone 格式缺口" (same subject) but keeps distinct subjects apart. More robust
    # than line proximity, which splits one issue across lines and merges different issues nearby.
    return re.sub(r"\s+", "", (title or "").lower())[:8]

def _dedup(cands: List[Finding]) -> List[Finding]:
    """Merge duplicate findings about the same subject (same file + title signature) that
    different lenses surfaced; keep the highest-severity instance."""
    out = {}
    for c in cands:
        key = (c.file.rsplit("/", 1)[-1], _title_sig(c.title))
        cur = out.get(key)
        if cur is None or _SEV_ORDER.get(c.severity, 0) > _SEV_ORDER.get(cur.severity, 0):
            out[key] = c
    return list(out.values())

def run(bundle: Bundle, data_dir: str, llm: Optional[Client] = None,
        min_severity: str = "major", lenses: Optional[List[str]] = None) -> List[Finding]:
    llm = llm or Client.from_env()
    lenses = prompt.FIND_LENSES if lenses is None else lenses

    # Stage 1 — multi-pass find (one pass per lens), then UNION. Diverse lenses surface deeper
    # issues (concurrency, breaking changes, behaviour regressions) and several passes stabilise
    # recall against the model's run-to-run variance (北極星「不漏」). max_tokens stays generous:
    # reasoning models spend completion budget thinking before the JSON, and truncation -> 0 findings.
    def _find_pass(lens):
        return _parse_json(
            llm.complete(prompt.find_prompt(bundle, lens), max_tokens=FIND_MAX_TOKENS)
        ).get("findings", [])
    raw = []
    with ThreadPoolExecutor(max_workers=max(1, len(lenses))) as ex:
        for findings in ex.map(_find_pass, lenses):   # concurrent; cuts wall-clock ~Nx
            raw.extend(findings)
    candidates = [Finding(**{k: f.get(k) for k in
                  ("severity", "file", "line", "title", "rationale", "premise")})
                  for f in raw]

    # drop malformed candidates (LLM may omit keys -> None) before we dereference them
    candidates = [c for c in candidates if c.severity and c.file and c.title]

    # resolve shortened/relative file paths back to the bundle's real absolute paths,
    # else the verifier reads empty source and wrongly refutes (false negative).
    known = list(bundle.changed_files.keys())
    for c in candidates:
        c.file = _resolve_path(c.file, known)

    candidates = _dedup(candidates)   # collapse cross-lens repeats of the same issue

    # severity gate (drop below threshold before paying for verify)
    floor = _SEV_ORDER.get(min_severity, 1)
    candidates = [c for c in candidates if _SEV_ORDER.get(c.severity, 0) >= floor]

    # Stage 2 — grounded refutation (high precision). Drop ONLY on an explicit refutation
    # (confirmed == false). A parse failure / missing verdict is a TECHNICAL miss, not a
    # refutation — surfacing the finding as unverified (confirmed=None) protects recall
    # (北極星「不漏」): a transient glitch must never silently hide a real finding.
    def _verify_one(c):
        src = _premise_source(c, data_dir)
        verdict = _parse_json(llm.complete(
            prompt.verify_prompt(c.title, c.premise or "", src), max_tokens=VERIFY_MAX_TOKENS))
        c.confirmed = verdict["confirmed"] if "confirmed" in verdict else None
        return c
    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=len(candidates)) as ex:   # verify all findings concurrently
        verified = list(ex.map(_verify_one, candidates))          # ex.map preserves order
    # keep confirmed (True) and unverified (None); drop only explicit False
    return [c for c in verified if c.confirmed is not False]

def _loc(f: Finding) -> str:
    return f"{f.file.rsplit('/', 1)[-1]}:{f.line}"

# A finding's "code symbols" = camelCase / PascalCase identifiers with an internal lower->upper
# hump (e.g. nextBizId, IdGeneratorService, normalizePhone). These are reliable root-cause keys;
# generic prose words, ALLCAPS (JWT), and single-cap words (Account) are intentionally excluded.
_IDENT_RE = re.compile(r'[A-Za-z][A-Za-z0-9]{2,}')

def _symbols(f: Finding) -> set:
    text = (f.title or "") + " " + (f.rationale or "")
    return {w.lower() for w in _IDENT_RE.findall(text) if re.search(r'[a-z][A-Z]', w)}

def _cluster(findings: List[Finding]) -> List[List[int]]:
    """Union-find cluster of finding indices that share a code symbol (same root cause across
    many files). Findings with no/unique symbols stay singletons. Fully deterministic."""
    n = len(findings)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        parent[find(a)] = find(b)
    seen = {}
    for i, f in enumerate(findings):
        for sym in _symbols(f):
            if sym in seen:
                union(i, seen[sym])
            else:
                seen[sym] = i
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())

def consolidate(findings: List[Finding], llm: Optional[Client] = None) -> List[Finding]:
    """Merge same-root-cause findings (one change reported at N trigger points across files) into
    one, listing every trigger location. DETERMINISTIC (shared-code-symbol clustering) — no LLM,
    no run-to-run variance, and never drops: every finding lands in exactly one cluster.
    (`llm` kept for signature compatibility; unused.)"""
    if len(findings) <= 1:
        for f in findings:
            f.locations = f.locations or [_loc(f)]
        return findings
    out = []
    for idxs in _cluster(findings):
        members = [findings[i] for i in idxs]
        primary = max(members, key=lambda f: _SEV_ORDER.get(f.severity, 0))
        primary.locations = sorted({_loc(f) for f in members})
        out.append(primary)
    return out
