# Blast-Radius Review Engine — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An offline CLI that, given a cloned repo and a git base ref, builds a code-review-graph, computes the blast radius (changed functions + callers/callees) of the diff, assembles a context-inlined bundle, runs a two-stage (find → grounded-refutation verify) review through the LiteLLM `reviewer` alias, and prints findings — plus an A/B mode against a diff-only baseline. No webhook.

**Architecture:** `code-review-graph` (CLI) builds the graph and reports changed functions; we query its SQLite `edges` table directly for the caller/callee blast radius (no MCP). A context assembler inlines the changed files + 1-hop caller/callee bodies under a token budget. A two-stage reviewer calls MiniMax-M2.1 via the existing LiteLLM gateway: stage 1 finds candidates (high recall), stage 2 refutes each candidate against the real source it depends on (high precision), surfacing only survivors. The whole thing is a Python package run from the host.

**Tech Stack:** Python 3.11 (`/opt/homebrew/bin/python3.11` — system 3.9 is too old), `code-review-graph==2.3.6`, stdlib `sqlite3`/`subprocess`/`urllib`, `pytest`. LLM via LiteLLM proxy (`reviewer` alias → `minimax/MiniMax-M2.1`, `reasoning_split` already on).

**North-star (from [docs/review-engine-plan.md](review-engine-plan.md) §2):** a senior engineer can fully trust it raises exactly the risks they would — bidirectional (不漏 recall + 不吵 precision). Phase 1 Go/No-Go is judged against that bar (§8 there).

---

## Verified facts (spiked 2026-06-15, do not re-question)

- `code-review-graph==2.3.6` installs on Python 3.11, not 3.9 ("No matching distribution" on 3.9).
- `code-review-graph build --repo PATH --data-dir DIR` — builds graph, stores DB at `DIR/graph.db`.
- `code-review-graph detect-changes --repo PATH --base REF` — prints **full JSON** to stdout (no `--brief`). Top-level keys: `summary`, `risk_score`, `changed_functions[]`, `affected_flows[]`, `test_gaps[]`, `review_priorities[]`, `functions_truncated`, `context_savings`. Each `changed_functions[]` item: `{id, kind, name, qualified_name, file_path, line_start, line_end, language, is_test, risk_score}`.
- `detect-changes` does NOT list callers/callees. Get the blast radius from `graph.db`:
  - Table `nodes`: `id, kind, name, qualified_name, file_path, line_start, line_end, language, params, signature, is_test, ...`
  - Table `edges`: `id, kind, source_qualified, target_qualified, file_path, line, confidence, confidence_tier`. `kind` ∈ {`CALLS`, `IMPORTS_FROM`, `CONTAINS`}.
  - **Callers** of `X` = `SELECT source_qualified FROM edges WHERE kind='CALLS' AND target_qualified=X`.
  - **Callees** of `X` = `SELECT target_qualified FROM edges WHERE kind='CALLS' AND source_qualified=X`.
  - Map a qualified_name → source via `nodes.file_path` + `line_start/line_end`.
- LiteLLM proxy port 4000 is NOT published to the host (compose has no host port mapping → host curl gets connection refused). Task 1 publishes it on loopback.

---

## File structure

```
code-quality-bot/
  review-engine/
    pyproject.toml          # package metadata + deps + pytest config
    review_engine/
      __init__.py
      graph.py              # code-review-graph wrapper: build/update + detect-changes + edges blast radius
      context.py            # context-inlined, token-budgeted bundle assembler
      prompt.py             # focused review prompt (zh-TW, severity schema, block-worthy)
      review.py             # two-stage find → grounded-refutation verify, via LiteLLM reviewer
      llm.py                # thin LiteLLM HTTP client (mockable)
      models.py            # dataclasses: ChangedFunction, Node, Finding, Bundle
      cli.py                # `review <repo> <base> [--baseline]`
    tests/
      conftest.py           # builds the tiny fixture repo + graph once per session
      test_graph.py
      test_context.py
      test_prompt.py
      test_review.py
      test_cli.py
    eval/
      run_ab.py             # A/B: engine vs diff-only on a real MR
      SENIOR_COMPARE.md     # template: senior lists their own risks, compare both ways
  var/                      # gitignored: cloned repos + graph DBs
    repos/                  # cloned repos under review
    graphs/                 # graph.db per repo
```

Run everything with the package venv: `review-engine/.venv` (Python 3.11). All `pytest`/`python` commands below assume `review-engine/.venv/bin` is used.

---

## Task 0: Scaffold the package + venv + gitignore

**Files:**
- Create: `review-engine/pyproject.toml`
- Create: `review-engine/review_engine/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create the package metadata**

Create `review-engine/pyproject.toml`:

```toml
[project]
name = "review-engine"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "code-review-graph==2.3.6",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.setuptools.packages.find]
where = ["."]
include = ["review_engine*"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

Create `review-engine/review_engine/__init__.py`:

```python
"""Blast-radius review engine (Phase 1 offline slice)."""
__version__ = "0.1.0"
```

- [ ] **Step 2: Ignore the venv and var workspace**

Add to `.gitignore` (append):

```
# review-engine local
review-engine/.venv/
review-engine/**/__pycache__/
var/
```

- [ ] **Step 3: Create the venv with Python 3.11 and install**

Run:
```bash
cd review-engine
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -q -e ".[dev]"
```
Expected: installs without "No matching distribution" (would fail on 3.9). `.venv/bin/code-review-graph --version` prints `code-review-graph 2.3.6`.

- [ ] **Step 4: Verify the tool is callable**

Run: `cd review-engine && .venv/bin/code-review-graph --version`
Expected: `code-review-graph 2.3.6`

- [ ] **Step 5: Commit**

```bash
git add review-engine/pyproject.toml review-engine/review_engine/__init__.py .gitignore
git commit -m "feat(review-engine): scaffold py3.11 package + code-review-graph dep"
```

---

## Task 1: Publish LiteLLM on loopback so the host engine can call it

**Files:**
- Modify: `deploy/docker-compose.yml` (the `litellm` service)

- [ ] **Step 1: Add a loopback host port mapping**

In `deploy/docker-compose.yml`, under the `litellm` service, add a `ports` entry binding to loopback only (find the service block; it currently exposes 4000 only inside the compose network). Add:

```yaml
    ports:
      - "127.0.0.1:4000:4000"   # loopback only — lets the host-run review-engine reach the reviewer alias
```

- [ ] **Step 2: Recreate litellm and verify from the host**

Run:
```bash
cd deploy && docker compose up -d litellm
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4000/health/liveliness
```
Expected: `200` (previously connection-refused / 000 from the host).

- [ ] **Step 3: Commit**

```bash
git add deploy/docker-compose.yml
git commit -m "chore(deploy): publish litellm on 127.0.0.1:4000 for local review-engine"
```

---

## Task 2: Test fixture — a tiny repo with a cross-file call + built graph

**Files:**
- Create: `review-engine/tests/conftest.py`

- [ ] **Step 1: Write the fixture builder**

Create `review-engine/tests/conftest.py`:

```python
import subprocess, sys, os, pathlib, pytest

CRG = str(pathlib.Path(sys.executable).parent / "code-review-graph")

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory):
    """A 2-file repo where main.run() calls util.add(); util.add's signature changes in HEAD."""
    repo = tmp_path_factory.mktemp("crg_fixture")
    (repo / "util.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "main.py").write_text("from util import add\ndef run():\n    return add(1, 2)\n")
    _git(repo, "init"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A"); _git(repo, "commit", "-m", "init")
    # change the signature -> blast radius should include main.run() as a caller
    (repo / "util.py").write_text("def add(a, b, c):\n    return a + b + c\n")
    _git(repo, "add", "-A"); _git(repo, "commit", "-m", "change add signature")
    return repo

@pytest.fixture(scope="session")
def fixture_graph_dir(fixture_repo, tmp_path_factory):
    graph_dir = tmp_path_factory.mktemp("crg_graph")
    subprocess.run([CRG, "build", "--repo", str(fixture_repo), "--data-dir", str(graph_dir)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert (graph_dir / "graph.db").exists()
    return graph_dir
```

- [ ] **Step 2: Verify the fixtures load**

Run: `cd review-engine && .venv/bin/pytest tests/conftest.py -q` (collects nothing, but import must succeed)
Expected: `no tests ran` with exit 0 (no import/collection error).

- [ ] **Step 3: Commit**

```bash
git add review-engine/tests/conftest.py
git commit -m "test(review-engine): fixture repo with cross-file call + built graph"
```

---

## Task 3: `models.py` — data shapes

**Files:**
- Create: `review-engine/review_engine/models.py`
- Test: `review-engine/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `review-engine/tests/test_models.py`:

```python
from review_engine.models import ChangedFunction, Node, Finding

def test_changed_function_from_crg_dict():
    cf = ChangedFunction.from_crg({
        "qualified_name": "/r/util.py::add", "name": "add",
        "file_path": "/r/util.py", "line_start": 1, "line_end": 2,
        "language": "python", "is_test": False, "risk_score": 0.58,
    })
    assert cf.qualified_name == "/r/util.py::add"
    assert cf.line_start == 1 and cf.line_end == 2

def test_finding_roundtrip():
    f = Finding(severity="major", file="/r/util.py", line=1,
                title="signature change breaks caller", rationale="x",
                premise="main.run calls add(1,2) with 2 args")
    assert f.severity == "major"
    assert f.to_dict()["premise"].startswith("main.run")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd review-engine && .venv/bin/pytest tests/test_models.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review_engine.models'`

- [ ] **Step 3: Write minimal implementation**

Create `review-engine/review_engine/models.py`:

```python
from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class ChangedFunction:
    qualified_name: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    language: str = ""
    is_test: bool = False
    risk_score: float = 0.0

    @classmethod
    def from_crg(cls, d: dict) -> "ChangedFunction":
        return cls(
            qualified_name=d["qualified_name"], name=d["name"],
            file_path=d["file_path"], line_start=d["line_start"], line_end=d["line_end"],
            language=d.get("language", ""), is_test=d.get("is_test", False),
            risk_score=d.get("risk_score", 0.0),
        )

@dataclass
class Node:
    qualified_name: str
    kind: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    signature: str = ""

@dataclass
class Finding:
    severity: str            # "blocker" | "major" | "minor"
    file: str
    line: int
    title: str
    rationale: str
    premise: str = ""        # what off-diff fact the finding assumes (verified in stage 2)
    confirmed: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class Bundle:
    changed_files: dict = field(default_factory=dict)   # path -> full source
    related: dict = field(default_factory=dict)         # qualified_name -> source snippet
    diff: str = ""
    est_tokens: int = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd review-engine && .venv/bin/pytest tests/test_models.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add review-engine/review_engine/models.py review-engine/tests/test_models.py
git commit -m "feat(review-engine): core data models"
```

---

## Task 4: `graph.py` — build + detect-changes wrapper

**Files:**
- Create: `review-engine/review_engine/graph.py`
- Test: `review-engine/tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

Create `review-engine/tests/test_graph.py`:

```python
from review_engine import graph

def test_detect_changes_returns_changed_add(fixture_repo, fixture_graph_dir):
    changed = graph.detect_changes(str(fixture_repo), base="HEAD~1", data_dir=str(fixture_graph_dir))
    names = {c.name for c in changed}
    assert "add" in names
    add = next(c for c in changed if c.name == "add")
    assert add.file_path.endswith("util.py")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd review-engine && .venv/bin/pytest tests/test_graph.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review_engine.graph'`

- [ ] **Step 3: Write minimal implementation**

Create `review-engine/review_engine/graph.py`:

```python
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
```

Note: `detect-changes` runs against the existing graph; if the graph is stale, call `update()` first. `_db` is used by Task 5.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd review-engine && .venv/bin/pytest tests/test_graph.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add review-engine/review_engine/graph.py review-engine/tests/test_graph.py
git commit -m "feat(review-engine): code-review-graph build + detect-changes wrapper"
```

---

## Task 5: `graph.py` — blast radius (callers/callees) via edges query

**Files:**
- Modify: `review-engine/review_engine/graph.py`
- Test: `review-engine/tests/test_graph.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `review-engine/tests/test_graph.py`:

```python
def test_blast_radius_finds_caller(fixture_repo, fixture_graph_dir):
    # add()'s caller is main.run() — must show up as a 1-hop caller
    radius = graph.blast_radius("/private" + str(fixture_repo) + "/util.py::add"
                                if str(fixture_repo).startswith("/") and not str(fixture_repo).startswith("/private")
                                else str(fixture_repo) + "/util.py::add",
                                data_dir=str(fixture_graph_dir))
    caller_names = {n.name for n in radius.callers}
    assert "run" in caller_names

def test_blast_radius_by_changed_function(fixture_repo, fixture_graph_dir):
    changed = graph.detect_changes(str(fixture_repo), "HEAD~1", str(fixture_graph_dir))
    add = next(c for c in changed if c.name == "add")
    radius = graph.blast_radius(add.qualified_name, data_dir=str(fixture_graph_dir))
    assert any(n.name == "run" for n in radius.callers)
```

(The second test is robust: it uses the qualified_name straight from `detect_changes`, avoiding path-prefix guessing. Keep both; the second is the canonical usage.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd review-engine && .venv/bin/pytest tests/test_graph.py -q`
Expected: FAIL with `AttributeError: module 'review_engine.graph' has no attribute 'blast_radius'`

- [ ] **Step 3: Write minimal implementation**

Append to `review-engine/review_engine/graph.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd review-engine && .venv/bin/pytest tests/test_graph.py -q`
Expected: PASS (3 passed). If `test_blast_radius_finds_caller` is flaky on path prefixes, rely on `test_blast_radius_by_changed_function` and delete the first.

- [ ] **Step 5: Commit**

```bash
git add review-engine/review_engine/graph.py review-engine/tests/test_graph.py
git commit -m "feat(review-engine): blast radius via graph edges (callers/callees)"
```

---

## Task 6: `context.py` — context-inlined, token-budgeted bundle

**Files:**
- Create: `review-engine/review_engine/context.py`
- Test: `review-engine/tests/test_context.py`

- [ ] **Step 1: Write the failing test**

Create `review-engine/tests/test_context.py`:

```python
from review_engine import graph, context

def test_bundle_includes_changed_file_and_caller(fixture_repo, fixture_graph_dir):
    b = context.build_bundle(str(fixture_repo), "HEAD~1", str(fixture_graph_dir), token_budget=100_000)
    # changed file present in full
    assert any(p.endswith("util.py") for p in b.changed_files)
    assert "def add(a, b, c)" in next(v for p, v in b.changed_files.items() if p.endswith("util.py"))
    # caller body inlined as related context
    related_src = "\n".join(b.related.values())
    assert "def run" in related_src

def test_bundle_respects_token_budget(fixture_repo, fixture_graph_dir):
    tiny = context.build_bundle(str(fixture_repo), "HEAD~1", str(fixture_graph_dir), token_budget=5)
    # changed files are kept first; related dropped when budget is tiny
    assert tiny.est_tokens <= 5 or tiny.related == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd review-engine && .venv/bin/pytest tests/test_context.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review_engine.context'`

- [ ] **Step 3: Write minimal implementation**

Create `review-engine/review_engine/context.py`:

```python
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
    return b
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd review-engine && .venv/bin/pytest tests/test_context.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add review-engine/review_engine/context.py review-engine/tests/test_context.py
git commit -m "feat(review-engine): context-inlined token-budgeted bundle"
```

---

## Task 7: `prompt.py` — focused review prompt

**Files:**
- Create: `review-engine/review_engine/prompt.py`
- Test: `review-engine/tests/test_prompt.py`

- [ ] **Step 1: Write the failing test**

Create `review-engine/tests/test_prompt.py`:

```python
from review_engine.models import Bundle
from review_engine import prompt

def test_find_prompt_has_guardrails_and_context():
    b = Bundle(changed_files={"/r/util.py": "def add(a,b,c): ..."},
               related={"/r/main.py::run": "def run(): add(1,2)"}, diff="--- diff ---")
    p = prompt.find_prompt(b)
    assert "blocker" in p and "major" in p and "minor" in p
    assert "擋下" in p or "block" in p.lower()            # block-worthy framing
    assert "def add(a,b,c)" in p and "def run" in p       # context inlined
    assert "JSON" in p                                     # structured output required

def test_verify_prompt_demands_grounding():
    p = prompt.verify_prompt(finding_title="add() breaks caller",
                             premise="main.run calls add with 2 args",
                             source="def run():\n    return add(1, 2, 3)")
    assert "前提" in p or "premise" in p.lower()
    assert "add(1, 2, 3)" in p                             # the real source is included
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd review-engine && .venv/bin/pytest tests/test_prompt.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review_engine.prompt'`

- [ ] **Step 3: Write minimal implementation**

Create `review-engine/review_engine/prompt.py`:

```python
from .models import Bundle

SYSTEM_FIND = (
    "你是一位資深工程師在 review 一個 merge request。用繁體中文。\n"
    "只報你願意『因此擋下這個 merge』的問題：真 bug、資料正確性、安全、並行/競態、"
    "錯誤處理缺失、會破壞 caller 的 breaking change。\n"
    "不要報純風格、命名、格式、個人偏好。寧缺勿濫。\n"
    "每條發現必須標 severity（blocker / major / minor），並寫出 premise："
    "這條發現假設了哪些『diff 以外』的事實（例如某 caller 怎麼呼叫、某值不可能為 null）。\n"
    "只輸出 JSON：{\"findings\":[{\"severity\":..,\"file\":..,\"line\":..,\"title\":..,"
    "\"rationale\":..,\"premise\":..}]}。沒有問題就回 {\"findings\":[]}。"
)

def _render_context(b: Bundle) -> str:
    parts = ["## 改動 diff", b.diff, "\n## 改動檔（全文）"]
    for path, src in b.changed_files.items():
        parts.append(f"### {path}\n{src}")
    if b.related:
        parts.append("\n## 相關上下游（caller/callee，用於判斷影響）")
        for qn, snip in b.related.items():
            parts.append(snip)
    return "\n".join(parts)

def find_prompt(b: Bundle) -> str:
    return f"{SYSTEM_FIND}\n\n{_render_context(b)}"

def verify_prompt(finding_title: str, premise: str, source: str) -> str:
    return (
        "你在對一條 code review 發現做『落地反證』。用繁體中文，只輸出 JSON。\n"
        f"發現：{finding_title}\n"
        f"它依賴的前提：{premise}\n"
        "下面是這條前提實際對應的源碼。請順著前提去讀真實源碼，判斷前提是否成立。\n"
        "如果源碼顯示『其實已經處理了／情況不是它講的那樣』，前提不成立 → confirmed=false。\n"
        "不確定就 confirmed=false（寧可放過）。\n"
        f"\n## 實際源碼\n{source}\n\n"
        "輸出：{\"confirmed\": true|false, \"reason\": \"...\"}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd review-engine && .venv/bin/pytest tests/test_prompt.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add review-engine/review_engine/prompt.py review-engine/tests/test_prompt.py
git commit -m "feat(review-engine): focused find + grounded-refutation verify prompts"
```

---

## Task 8: `llm.py` — LiteLLM client (mockable)

**Files:**
- Create: `review-engine/review_engine/llm.py`
- Test: `review-engine/tests/test_review.py` (the unit tests mock this)

- [ ] **Step 1: Write the failing test**

Create `review-engine/tests/test_review.py` (start with the llm contract):

```python
from review_engine import llm

def test_llm_client_reads_env(monkeypatch):
    monkeypatch.setenv("REVIEWER_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("REVIEWER_API_KEY", "sk-test")
    c = llm.Client.from_env()
    assert c.base_url == "http://127.0.0.1:4000/v1"
    assert c.model == "reviewer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd review-engine && .venv/bin/pytest tests/test_review.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review_engine.llm'`

- [ ] **Step 3: Write minimal implementation**

Create `review-engine/review_engine/llm.py`:

```python
import os, json, urllib.request
from dataclasses import dataclass

@dataclass
class Client:
    base_url: str
    api_key: str
    model: str = "reviewer"

    @classmethod
    def from_env(cls) -> "Client":
        return cls(
            base_url=os.environ.get("REVIEWER_BASE_URL", "http://127.0.0.1:4000/v1"),
            api_key=os.environ.get("REVIEWER_API_KEY", ""),
            model=os.environ.get("REVIEWER_MODEL", "reviewer"),
        )

    def complete(self, system_and_user: str, max_tokens: int = 2000) -> str:
        """Single-shot completion; returns clean `content` (reasoning_split keeps <think> out)."""
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": system_and_user}],
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(self.base_url.rstrip("/") + "/chat/completions",
            data=body, headers={"Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.load(r)
        return d["choices"][0]["message"].get("content") or ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd review-engine && .venv/bin/pytest tests/test_review.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add review-engine/review_engine/llm.py review-engine/tests/test_review.py
git commit -m "feat(review-engine): mockable LiteLLM reviewer client"
```

---

## Task 9: `review.py` — two-stage find → grounded-refutation verify

**Files:**
- Create: `review-engine/review_engine/review.py`
- Test: `review-engine/tests/test_review.py` (append)

- [ ] **Step 1: Write the failing test (mock the LLM)**

Append to `review-engine/tests/test_review.py`:

```python
import json
from review_engine import review
from review_engine.models import Bundle

class FakeLLM:
    """Returns find JSON first, then a verify verdict per finding."""
    def __init__(self, find_payload, verify_payloads):
        self._find = json.dumps(find_payload)
        self._verify = [json.dumps(v) for v in verify_payloads]
        self.calls = 0
    def complete(self, prompt, max_tokens=2000):
        self.calls += 1
        if self.calls == 1:
            return self._find
        return self._verify.pop(0)

def test_review_keeps_confirmed_drops_refuted(fixture_repo, fixture_graph_dir):
    from review_engine import context
    b = context.build_bundle(str(fixture_repo), "HEAD~1", str(fixture_graph_dir))
    fake = FakeLLM(
        find_payload={"findings": [
            {"severity": "major", "file": "/r/util.py", "line": 1,
             "title": "breaks caller", "rationale": "x", "premise": "main.run passes 2 args"},
            {"severity": "minor", "file": "/r/util.py", "line": 1,
             "title": "nit", "rationale": "y", "premise": "none"},
        ]},
        verify_payloads=[{"confirmed": True, "reason": "caller still passes 2 args"},
                         {"confirmed": False, "reason": "source disproves it"}],
    )
    findings = review.run(b, str(fixture_graph_dir), llm=fake)
    titles = {f.title for f in findings}
    assert "breaks caller" in titles          # confirmed kept
    assert "nit" not in titles                 # refuted dropped

def test_review_default_severity_gate_drops_minor(fixture_repo, fixture_graph_dir):
    from review_engine import context
    b = context.build_bundle(str(fixture_repo), "HEAD~1", str(fixture_graph_dir))
    fake = FakeLLM(
        find_payload={"findings": [
            {"severity": "minor", "file": "/r/util.py", "line": 1,
             "title": "style", "rationale": "z", "premise": "n/a"}]},
        verify_payloads=[{"confirmed": True, "reason": "ok"}],
    )
    findings = review.run(b, str(fixture_graph_dir), llm=fake, min_severity="major")
    assert findings == []                      # minor gated out before verify
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd review-engine && .venv/bin/pytest tests/test_review.py -q`
Expected: FAIL with `AttributeError: module 'review_engine.review' has no attribute 'run'`

- [ ] **Step 3: Write minimal implementation**

Create `review-engine/review_engine/review.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd review-engine && .venv/bin/pytest tests/test_review.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add review-engine/review_engine/review.py review-engine/tests/test_review.py
git commit -m "feat(review-engine): two-stage find + grounded-refutation verify"
```

---

## Task 10: `cli.py` — entrypoint with `--baseline` A/B

**Files:**
- Create: `review-engine/review_engine/cli.py`
- Test: `review-engine/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `review-engine/tests/test_cli.py`:

```python
import json
from review_engine import cli
from review_engine.models import Finding

def test_cli_runs_engine_and_prints_findings(fixture_repo, fixture_graph_dir, monkeypatch, capsys):
    monkeypatch.setattr(cli.review, "run",
                        lambda *a, **k: [Finding(severity="major", file="/r/util.py",
                                                 line=1, title="t", rationale="r", premise="p",
                                                 confirmed=True)])
    rc = cli.main(["--repo", str(fixture_repo), "--base", "HEAD~1",
                   "--data-dir", str(fixture_graph_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "major" in out and "t" in out

def test_cli_baseline_mode_skips_graph(fixture_repo, monkeypatch, capsys):
    # baseline = diff-only; must not require a graph/data-dir
    called = {"engine": False}
    monkeypatch.setattr(cli.review, "run", lambda *a, **k: called.__setitem__("engine", True) or [])
    monkeypatch.setattr(cli, "_diff_only_findings", lambda repo, base, llm=None: [])
    rc = cli.main(["--repo", str(fixture_repo), "--base", "HEAD~1", "--baseline"])
    assert rc == 0
    assert called["engine"] is False        # engine path not used in baseline
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd review-engine && .venv/bin/pytest tests/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review_engine.cli'`

- [ ] **Step 3: Write minimal implementation**

Create `review-engine/review_engine/cli.py`:

```python
import argparse, json, sys, pathlib
from . import graph, context, review, prompt
from .llm import Client

def _diff_only_findings(repo: str, base: str, llm=None):
    """Baseline: feed ONLY the diff (no graph, no inlined context) — what plain PR-Agent sees."""
    import subprocess
    llm = llm or Client.from_env()
    diff = subprocess.run(["git", "-C", repo, "diff", base, "--"],
                          capture_output=True, text=True).stdout
    from .models import Bundle
    b = Bundle(diff=diff)  # changed_files/related empty on purpose
    return review.run(b, data_dir="", llm=llm)

def _print(findings):
    for f in findings:
        print(f"[{f.severity}] {f.file}:{f.line}  {f.title}")
        print(f"    {f.rationale}")
    print(f"\n{len(findings)} finding(s).")

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="review-engine")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", default="HEAD~1")
    ap.add_argument("--data-dir", default="")
    ap.add_argument("--baseline", action="store_true",
                    help="diff-only baseline (no graph) for A/B comparison")
    ap.add_argument("--min-severity", default="major", choices=["minor", "major", "blocker"])
    args = ap.parse_args(argv)

    if args.baseline:
        _print(_diff_only_findings(args.repo, args.base))
        return 0

    data_dir = args.data_dir or str(pathlib.Path(args.repo) / ".crg-data")
    if not (pathlib.Path(data_dir) / "graph.db").exists():
        graph.build(args.repo, data_dir)
    else:
        graph.update(args.repo, data_dir)
    bundle = context.build_bundle(args.repo, args.base, data_dir)
    _print(review.run(bundle, data_dir, min_severity=args.min_severity))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd review-engine && .venv/bin/pytest tests/test_cli.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite + commit**

```bash
cd review-engine && .venv/bin/pytest -q
```
Expected: all tests pass.

```bash
git add review-engine/review_engine/cli.py review-engine/tests/test_cli.py
git commit -m "feat(review-engine): CLI with diff-only baseline for A/B"
```

---

## Task 11: Live smoke test on a real MR + A/B harness + senior template

**Files:**
- Create: `review-engine/eval/run_ab.py`
- Create: `review-engine/eval/SENIOR_COMPARE.md`

- [ ] **Step 1: One real end-to-end call (gated, not a unit test)**

With litellm reachable (Task 1) and a real repo cloned into `var/repos/<name>`:

```bash
cd review-engine
export REVIEWER_API_KEY="$(grep '^LITELLM_MASTER_KEY' ../deploy/.env | cut -d= -f2)"
.venv/bin/python -m review_engine.cli --repo ../var/repos/<name> --base origin/main
```
Expected: prints confirmed findings in zh-TW; no `<think>` leakage (reasoning_split). Note the wall-clock + rough token use.

- [ ] **Step 2: Write the A/B harness**

Create `review-engine/eval/run_ab.py`:

```python
"""A/B: blast-radius engine vs diff-only baseline on one repo+base. Prints both, side by side."""
import argparse, subprocess, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from review_engine import cli

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args()
    print("=" * 30, "DIFF-ONLY BASELINE", "=" * 30)
    cli.main(["--repo", a.repo, "--base", a.base, "--baseline"])
    print("\n" + "=" * 30, "BLAST-RADIUS ENGINE", "=" * 30)
    cli.main(["--repo", a.repo, "--base", a.base])

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write the senior-comparison template**

Create `review-engine/eval/SENIOR_COMPARE.md`:

```markdown
# Senior comparison — <repo> @ <base>..<head>

> 對齊北極星：先由資深工程師獨立寫下「我會提出的風險」，再跟引擎輸出比對兩個方向。

## A) 資深工程師會提出的風險（先寫，別偷看引擎輸出）
- [ ] (severity) file:line — 描述
- ...

## B) 引擎輸出（貼上 run_ab.py 的 BLAST-RADIUS 段）
...

## C) 比對
- **不漏 (recall)**：A 有、引擎也抓到 ___ / ___ 條（blocker/major 要逼近全中）
  - 漏掉的：（是 context 不夠？還是被 verify 誤殺？）
- **不吵 (precision)**：引擎提的，資深認同「值得提」___ / ___ 條（目標 FP < 10%）
  - 其中「聽起來合理、源碼一讀就垮」(diff-myopia) ___ 條
- **深度佐證**：引擎抓到、DIFF-ONLY baseline 漏掉的跨檔/影響風險 ___ 條

## D) 判定（Phase 1 Go/No-Go）
- [ ] 資深能說「這些我都認同，而且我會抓的它沒漏」→ 可完全信任 → **GO**
- [ ] 否 → 記錄主要失效模式，回 §9 風險調整
```

- [ ] **Step 4: Run the A/B on the real repo and fill the template**

```bash
cd review-engine && .venv/bin/python eval/run_ab.py --repo ../var/repos/<name> --base origin/main
```
Copy both outputs into a filled copy of `SENIOR_COMPARE.md`; the senior fills sections A and C.

- [ ] **Step 5: Commit**

```bash
git add review-engine/eval/run_ab.py review-engine/eval/SENIOR_COMPARE.md
git commit -m "feat(review-engine): A/B harness + senior-comparison eval template"
```

---

## Self-review notes (spec coverage)

- **深度 / blast radius** → Tasks 4–6 (detect-changes + edges callers/callees + context inlining).
- **不吵 / two-stage + grounded refutation** → Tasks 7, 9 (find prompt guardrails, verify against real source, severity gate).
- **diff-myopia FP** → Task 9 `_premise_source` + verify prompt; Task 11 template counts it separately.
- **不漏 / recall vs senior** → Task 11 SENIOR_COMPARE.md sections A/C.
- **A/B vs diff-only** → Task 10 `--baseline`, Task 11 `run_ab.py`.
- **in-project + var/ split** → Task 0 layout + gitignore.
- **Go/No-Go = north-star** → Task 11 section D.

## Out of scope (Phase 2+, do NOT build here)
Webhook/GitLab posting, multi-tenant, Jira, persistent daemon, N-hop (>1) radius, embeddings/semantic search. Keep Phase 1 to the offline A/B proof.
```
