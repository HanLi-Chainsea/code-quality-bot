import json, subprocess, sys, pathlib, sqlite3
from typing import List
from .models import ChangedFunction, Node

CRG = str(pathlib.Path(sys.executable).parent / "code-review-graph")

def build(repo: str, data_dir: str) -> None:
    subprocess.run([CRG, "build", "--repo", repo, "--data-dir", data_dir],
                   check=True, capture_output=True, text=True)

def update(repo: str, data_dir: str) -> None:
    subprocess.run([CRG, "update", "--repo", repo, "--data-dir", data_dir],
                   check=True, capture_output=True, text=True)

def detect_changes(repo: str, base: str, data_dir: str) -> List[ChangedFunction]:
    out = subprocess.run([CRG, "detect-changes", "--repo", repo, "--base", base],
                         check=True, capture_output=True, text=True).stdout
    data = json.loads(out)
    return [ChangedFunction.from_crg(d) for d in data.get("changed_functions", [])]

def _db(data_dir: str) -> sqlite3.Connection:
    return sqlite3.connect(str(pathlib.Path(data_dir) / "graph.db"))

from dataclasses import dataclass

@dataclass
class Radius:
    target: str
    callers: list   # List[Node]
    callees: list   # List[Node]

def _node_by_qn(conn, qn: str):
    row = conn.execute(
        "SELECT qualified_name, kind, name, file_path, line_start, line_end, COALESCE(signature,'') "
        "FROM nodes WHERE qualified_name = ?", (qn,)).fetchone()
    return Node(*row) if row else None

def blast_radius(qualified_name: str, data_dir: str, min_confidence: float = 0.0) -> Radius:
    conn = _db(data_dir)
    try:
        caller_qns = [r[0] for r in conn.execute(
            "SELECT source_qualified FROM edges WHERE kind='CALLS' AND target_qualified=? "
            "AND confidence >= ?", (qualified_name, min_confidence))]
        callee_qns = [r[0] for r in conn.execute(
            "SELECT target_qualified FROM edges WHERE kind='CALLS' AND source_qualified=? "
            "AND confidence >= ?", (qualified_name, min_confidence))]
        callers = [n for n in (_node_by_qn(conn, q) for q in caller_qns) if n]
        callees = [n for n in (_node_by_qn(conn, q) for q in callee_qns) if n]
        return Radius(target=qualified_name, callers=callers, callees=callees)
    finally:
        conn.close()
