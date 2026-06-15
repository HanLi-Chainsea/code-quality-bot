import json, re, pathlib
from typing import List, Optional
from .models import Finding, Bundle
from . import prompt, graph
from .llm import Client

_SEV_ORDER = {"minor": 0, "major": 1, "blocker": 2}

def _parse_json(text: str) -> dict:
    """Tolerate models that wrap JSON in prose/fences."""
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}

def _read(path: str) -> str:
    try:
        return pathlib.Path(path).read_text(errors="replace")
    except OSError:
        return ""

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
    return "\n\n".join(p for p in parts if p)

def run(bundle: Bundle, data_dir: str, llm: Optional[Client] = None,
        min_severity: str = "major") -> List[Finding]:
    llm = llm or Client.from_env()

    # Stage 1 — find (high recall)
    found = _parse_json(llm.complete(prompt.find_prompt(bundle))).get("findings", [])
    candidates = [Finding(**{k: f.get(k) for k in
                  ("severity", "file", "line", "title", "rationale", "premise")})
                  for f in found]

    # severity gate (drop below threshold before paying for verify)
    floor = _SEV_ORDER.get(min_severity, 1)
    candidates = [c for c in candidates if _SEV_ORDER.get(c.severity, 0) >= floor]

    # Stage 2 — grounded refutation (high precision)
    confirmed: List[Finding] = []
    for c in candidates:
        src = _premise_source(c, data_dir)
        verdict = _parse_json(llm.complete(
            prompt.verify_prompt(c.title, c.premise or "", src)))
        c.confirmed = bool(verdict.get("confirmed"))
        if c.confirmed:
            confirmed.append(c)
    return confirmed
