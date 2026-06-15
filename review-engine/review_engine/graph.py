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
