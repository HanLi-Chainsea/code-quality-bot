# Phase 3 — Wire the blast-radius engine into PR-Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PR-Agent's review (and, for free, its describe/improve) use the blast-radius engine — by injecting cross-file context into the one function every tool shares, and adding a grounded-refutation verify pass to the reviewer — without forking PR-Agent's source.

**Architecture:** A small `cqb_patch` package **monkeypatches** two PR-Agent seams at process start: (1) wraps `pr_agent.algo.pr_processing.get_pr_diff` to append blast-radius context (caller/callee bodies of the changed functions) — this single seam feeds review **and** describe/improve/etc., since all tools call it; (2) wraps `PRReviewer` to drop review findings whose premise the real source refutes (kills diff-myopia false positives like the #425 `Asserts.fail` one). Both reuse the existing `review_engine` package (graph + context.build_bundle + verify prompt). A lazily-maintained persistent clone + code-review-graph (in a Docker volume, no separate daemon) supplies the source/graph. Shipped as a thin image `FROM` the pinned PR-Agent digest. Apache-2.0 permits this; we keep the LICENSE and note our changes.

**Tech Stack:** Python 3.12 (PR-Agent image), `code-review-graph`, the existing `review_engine` package, `git` (present in image), Docker. Monkeypatch via a bootstrap entrypoint. LLM via the same LiteLLM `reviewer` alias.

---

## Verified PR-Agent internals (spiked 2026-06-17, do not re-question)

- `get_pr_diff(git_provider, token_handler, model, ...)` in `pr_agent/algo/pr_processing.py` returns the diff **string** (line 76 `return "\n".join(patches_extended)` under the token limit; line 140 `return final_diff` when pruned). It is imported and called by **every** tool: `pr_reviewer`, `pr_description`, `pr_code_suggestions` (improve), `pr_add_docs`, `pr_generate_labels`, `pr_questions`, `pr_update_changelog`, `pr_line_questions`. In `pr_reviewer` the return becomes `self.patches_diff` → `variables["diff"]` → the prompt. **One wrapper here reaches all tools.**
- `PRReviewer.run()` (`pr_agent/tools/pr_reviewer.py`) flow: `await self._prepare_prediction(model)` sets `self.prediction` (raw YAML) → `self._prepare_pr_review()` does `load_yaml(self.prediction)` → publish. The review YAML is `data['review']['key_issues_to_review']`, a list of `{relevant_file, issue_header, issue_content, start_line, end_line}`. **Filtering that list in `self.prediction` before `_prepare_pr_review` is the verify seam.**
- `git_provider` (GitLabProvider) exposes: `git_provider.mr.diff_refs['base_sha']` and `['head_sha']`; `git_provider.gl.url` (e.g. `https://gitlab.com`) and `git_provider.id_project` (e.g. `aile_cloud/aipool/aipoolserver`); `git_provider.get_diff_files()` → `FilePatchInfo` with `filename`, `head_file` (full new content), `patch`. So clone URL = `{gl.url}/{id_project}.git`, and base/head SHAs are available.
- Image has `/usr/bin/git` and Python 3.12.10. The webhook entrypoint is `python -m pr_agent.servers.gitlab_webhook`.
- `review_engine` already provides: `context.build_bundle(repo, base, data_dir)` (does detect-changes + blast radius + inlining + token budget → `Bundle.related` is the caller/callee context), `graph.build/update`, `review._premise_source`/`prompt.verify_prompt`/`llm.Client` (grounded refutation), `models.Finding`.

---

## File structure

```
deploy/engine-integration/
  Dockerfile                 # FROM pinned pr-agent digest; add review_engine + cqb_patch; pip install code-review-graph
  NOTICE                     # Apache-2.0 change notice (what we patched)
  cqb_patch/
    __init__.py
    repo_graph.py            # lazy persistent clone + graph update; -> blast-radius context str + source-for-verify
    context_patch.py         # wrap get_pr_diff to append the blast-radius context
    verify_patch.py          # wrap PRReviewer to drop source-refuted findings
    bootstrap.py             # apply both patches, then run the gitlab webhook server
  tests/
    conftest.py              # fake git_provider + reuse review_engine fixture repo
    test_repo_graph.py
    test_context_patch.py
    test_verify_patch.py
review-engine/               # reused as-is (copied into the image)
deploy/docker-compose.yml    # pr-agent service: build the new image + clone/graph volume + token env
```

`cqb_patch` imports `review_engine` (same repo). Keep each patch file single-purpose.

Run tests with the review-engine venv (it has `code-review-graph` + `pytest`): `review-engine/.venv/bin/pytest deploy/engine-integration/tests`. Add `deploy/engine-integration` to its path via a conftest insert.

---

## Task 0: Scaffold cqb_patch package + test wiring

**Files:**
- Create: `deploy/engine-integration/cqb_patch/__init__.py`
- Create: `deploy/engine-integration/tests/conftest.py`

- [ ] **Step 1: Create the package init**

`deploy/engine-integration/cqb_patch/__init__.py`:
```python
"""Monkeypatches that inject the blast-radius engine into PR-Agent (Apache-2.0; see ../NOTICE)."""
```

- [ ] **Step 2: Create conftest that exposes the package + reuses the engine fixture**

`deploy/engine-integration/tests/conftest.py`:
```python
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]          # deploy/engine-integration
REPO = ROOT.parents[1]                                       # repo root
sys.path.insert(0, str(ROOT))                               # import cqb_patch
sys.path.insert(0, str(REPO / "review-engine"))            # import review_engine

# reuse the engine's fixture_repo / fixture_graph_dir
from review_engine_test_fixtures import *  # noqa  (created in Step 3)
```

- [ ] **Step 3: Re-export the engine fixtures for reuse**

Create `deploy/engine-integration/tests/review_engine_test_fixtures.py`:
```python
# Re-use the exact fixtures from review-engine/tests/conftest.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "review-engine" / "tests"))
from conftest import fixture_repo, fixture_graph_dir  # noqa: F401
```

- [ ] **Step 4: Verify collection works**

Run: `review-engine/.venv/bin/pytest deploy/engine-integration/tests -q`
Expected: exit code 5 ("no tests ran") — imports resolve, no collection error.

- [ ] **Step 5: Commit**

```bash
git add deploy/engine-integration/cqb_patch/__init__.py deploy/engine-integration/tests/conftest.py deploy/engine-integration/tests/review_engine_test_fixtures.py
git commit -m "feat(phase3): scaffold cqb_patch package + test wiring"
```

---

## Task 1: `repo_graph.py` — lazy clone + graph + blast-radius context

**Files:**
- Create: `deploy/engine-integration/cqb_patch/repo_graph.py`
- Test: `deploy/engine-integration/tests/test_repo_graph.py`

- [ ] **Step 1: Write the failing test**

`deploy/engine-integration/tests/test_repo_graph.py`:
```python
from cqb_patch import repo_graph

def test_blast_context_for_local_repo(fixture_repo, tmp_path):
    # fixture_repo: HEAD changes util.add(); main.run() calls it. base = HEAD~1.
    base = "HEAD~1"
    ctx = repo_graph.blast_context(
        repo_dir=str(fixture_repo), base_sha=base, work_dir=str(tmp_path), token_budget=50_000)
    assert "def run" in ctx           # the caller body is inlined
    assert ctx.strip()                # non-empty

def test_blast_context_empty_when_no_changed_functions(tmp_path, fixture_repo):
    # base == HEAD -> no diff -> empty context, never raises
    ctx = repo_graph.blast_context(
        repo_dir=str(fixture_repo), base_sha="HEAD", work_dir=str(tmp_path))
    assert ctx == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `review-engine/.venv/bin/pytest deploy/engine-integration/tests/test_repo_graph.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'cqb_patch.repo_graph'`

- [ ] **Step 3: Write the implementation**

`deploy/engine-integration/cqb_patch/repo_graph.py`:
```python
"""Given a local repo + base ref, produce the blast-radius context string by reusing the engine.
For the live path, ensure_repo() lazily maintains a persistent clone + graph keyed by project."""
import os, subprocess, pathlib, hashlib, fcntl
from review_engine import context, graph

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
    key = hashlib.sha1(clone_url.encode()).hexdigest()[:16]
    repo_dir = str(pathlib.Path(base_dir) / key)
    os.makedirs(base_dir, exist_ok=True)
    lock_path = pathlib.Path(base_dir) / f"{key}.lock"
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not pathlib.Path(repo_dir, ".git").exists():
            subprocess.run(["git", "clone", "--quiet", clone_url, repo_dir], check=True,
                           capture_output=True, text=True)
        subprocess.run(["git", "-C", repo_dir, "fetch", "--quiet", "origin", head_sha],
                       check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", repo_dir, "checkout", "--quiet", head_sha],
                       check=True, capture_output=True, text=True)
    return repo_dir
```

- [ ] **Step 4: Run to verify it passes**

Run: `review-engine/.venv/bin/pytest deploy/engine-integration/tests/test_repo_graph.py -q`
Expected: PASS (2 passed). `ensure_repo` is exercised live in Task 7 (needs network), not unit-tested here.

- [ ] **Step 5: Commit**

```bash
git add deploy/engine-integration/cqb_patch/repo_graph.py deploy/engine-integration/tests/test_repo_graph.py
git commit -m "feat(phase3): lazy clone+graph + blast-radius context helper (reuses engine)"
```

---

## Task 2: `context_patch.py` — wrap `get_pr_diff` (cross-cutting)

**Files:**
- Create: `deploy/engine-integration/cqb_patch/context_patch.py`
- Test: `deploy/engine-integration/tests/test_context_patch.py`

- [ ] **Step 1: Write the failing test**

`deploy/engine-integration/tests/test_context_patch.py`:
```python
from cqb_patch import context_patch

class FakeMR:
    diff_refs = {"base_sha": "BASE", "head_sha": "HEAD"}

class FakeGP:
    mr = FakeMR()
    gl = type("g", (), {"url": "https://gitlab.example.com"})()
    id_project = "grp/proj"

def test_wrapper_appends_context(monkeypatch):
    # original get_pr_diff returns a plain diff string
    def fake_original(git_provider, token_handler, model, **kw):
        return "DIFF-BODY"
    # stub the repo prep + context so no network/graph is needed
    monkeypatch.setattr(context_patch.repo_graph, "ensure_repo", lambda url, sha, base: "/tmp/repo")
    monkeypatch.setattr(context_patch.repo_graph, "blast_context", lambda **kw: "BLAST-CTX")
    wrapped = context_patch.wrap_get_pr_diff(fake_original)
    out = wrapped(FakeGP(), token_handler=None, model="m")
    assert out.startswith("DIFF-BODY")
    assert "BLAST-CTX" in out

def test_wrapper_is_transparent_on_failure(monkeypatch):
    def fake_original(git_provider, token_handler, model, **kw):
        return "DIFF-ONLY"
    monkeypatch.setattr(context_patch.repo_graph, "ensure_repo",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("clone failed")))
    wrapped = context_patch.wrap_get_pr_diff(fake_original)
    out = wrapped(FakeGP(), token_handler=None, model="m")
    assert out == "DIFF-ONLY"        # enrichment failure leaves the original diff untouched
```

- [ ] **Step 2: Run to verify it fails**

Run: `review-engine/.venv/bin/pytest deploy/engine-integration/tests/test_context_patch.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'cqb_patch.context_patch'`

- [ ] **Step 3: Write the implementation**

`deploy/engine-integration/cqb_patch/context_patch.py`:
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `review-engine/.venv/bin/pytest deploy/engine-integration/tests/test_context_patch.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add deploy/engine-integration/cqb_patch/context_patch.py deploy/engine-integration/tests/test_context_patch.py
git commit -m "feat(phase3): wrap get_pr_diff to append blast-radius context (all tools)"
```

---

## Task 3: `verify_patch.py` — grounded refutation on review findings

**Files:**
- Create: `deploy/engine-integration/cqb_patch/verify_patch.py`
- Test: `deploy/engine-integration/tests/test_verify_patch.py`

- [ ] **Step 1: Write the failing test**

`deploy/engine-integration/tests/test_verify_patch.py`:
```python
import yaml
from cqb_patch import verify_patch

PREDICTION = """\
review:
  key_issues_to_review:
  - relevant_file: src/A.java
    issue_header: Possible Bug
    issue_content: after Asserts.fail the code keeps running
    start_line: 10
    end_line: 12
  - relevant_file: src/A.java
    issue_header: Real Bug
    issue_content: null deref on cold cache path
    start_line: 40
    end_line: 41
"""

def test_filter_drops_refuted_keeps_others(monkeypatch):
    # verdict: first issue REFUTED (confirmed false), second has no verdict -> kept
    verdicts = iter([{"confirmed": False, "reason": "Asserts.fail throws"}, {}])
    monkeypatch.setattr(verify_patch, "_verdict", lambda issue, repo_dir: next(verdicts))
    new_pred = verify_patch.filter_prediction(PREDICTION, repo_dir="/tmp/repo")
    data = yaml.safe_load(new_pred)
    headers = [i["issue_header"] for i in data["review"]["key_issues_to_review"]]
    assert "Real Bug" in headers
    assert "Possible Bug" not in headers          # explicitly refuted -> dropped

def test_filter_is_transparent_on_parse_failure():
    assert verify_patch.filter_prediction("not: [valid", repo_dir="/x") == "not: [valid"
```

- [ ] **Step 2: Run to verify it fails**

Run: `review-engine/.venv/bin/pytest deploy/engine-integration/tests/test_verify_patch.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'cqb_patch.verify_patch'`

- [ ] **Step 3: Write the implementation**

`deploy/engine-integration/cqb_patch/verify_patch.py`:
```python
"""Drop review findings whose premise the real source refutes (grounded refutation). Reuses the
engine's verify prompt + LLM client. Only an EXPLICIT confirmed=false drops a finding; parse
failures / uncertainty keep it (北極星 不漏)."""
import pathlib, yaml
from review_engine import review, prompt
from review_engine.llm import Client

def _read_span(repo_dir, relevant_file, start_line, end_line, ctx=40):
    p = pathlib.Path(repo_dir) / str(relevant_file).lstrip("/")
    try:
        lines = p.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    lo = max(0, int(start_line) - 1 - ctx); hi = min(len(lines), int(end_line) + ctx)
    return "\n".join(lines[lo:hi])

def _verdict(issue: dict, repo_dir: str) -> dict:
    src = _read_span(repo_dir, issue.get("relevant_file", ""),
                     issue.get("start_line", 1), issue.get("end_line", 1))
    if not src:
        return {}                                    # no source -> can't refute -> keep (不漏)
    title = issue.get("issue_header", ""); premise = issue.get("issue_content", "")
    return review._parse_json(Client.from_env().complete(
        prompt.verify_prompt(title, premise, src), max_tokens=review.VERIFY_MAX_TOKENS))

def filter_prediction(prediction_yaml: str, repo_dir: str) -> str:
    """Return the review YAML with source-refuted key_issues removed; unchanged on any parse issue."""
    try:
        data = yaml.safe_load(prediction_yaml)
        issues = data["review"]["key_issues_to_review"]
        assert isinstance(issues, list)
    except Exception:
        return prediction_yaml
    kept = []
    for issue in issues:
        v = _verdict(issue, repo_dir)
        if v.get("confirmed") is False:              # ONLY explicit refutation drops
            continue
        kept.append(issue)
    data["review"]["key_issues_to_review"] = kept
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
```

- [ ] **Step 4: Run to verify it passes**

Run: `review-engine/.venv/bin/pytest deploy/engine-integration/tests/test_verify_patch.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add deploy/engine-integration/cqb_patch/verify_patch.py deploy/engine-integration/tests/test_verify_patch.py
git commit -m "feat(phase3): grounded-refutation filter for review findings"
```

---

## Task 4: `bootstrap.py` — apply patches, then run the webhook server

**Files:**
- Create: `deploy/engine-integration/cqb_patch/bootstrap.py`

- [ ] **Step 1: Write the implementation (no unit test — it wires real PR-Agent modules; covered live in Task 7)**

`deploy/engine-integration/cqb_patch/bootstrap.py`:
```python
"""Entrypoint: monkeypatch PR-Agent, then hand off to its gitlab webhook server.
Run as: python -m cqb_patch.bootstrap"""
import os, runpy
from pr_agent.algo import pr_processing
from pr_agent.tools import pr_reviewer
from . import context_patch, verify_patch, repo_graph

# 1) cross-cutting context: wrap the shared diff builder
pr_processing.get_pr_diff = context_patch.wrap_get_pr_diff(pr_processing.get_pr_diff)
# pr_reviewer imported get_pr_diff by name at module load -> rebind that reference too
pr_reviewer.get_pr_diff = pr_processing.get_pr_diff

# 2) review-only verify: filter self.prediction before _prepare_pr_review
_orig_prepare = pr_reviewer.PRReviewer._prepare_pr_review
def _prepare_with_verify(self):
    try:
        mr = self.git_provider.mr
        repo_dir = repo_graph.ensure_repo(
            context_patch._clone_url(self.git_provider),
            mr.diff_refs["head_sha"], context_patch.CLONE_BASE)
        if self.prediction:
            self.prediction = verify_patch.filter_prediction(self.prediction, repo_dir)
    except Exception:
        pass   # verify is best-effort; never block publishing
    return _orig_prepare(self)
pr_reviewer.PRReviewer._prepare_pr_review = _prepare_with_verify

if __name__ == "__main__":
    runpy.run_module("pr_agent.servers.gitlab_webhook", run_name="__main__")
```

- [ ] **Step 2: Syntax check**

Run: `review-engine/.venv/bin/python -c "import ast; ast.parse(open('deploy/engine-integration/cqb_patch/bootstrap.py').read())"`
Expected: no output (valid syntax). It cannot be imported outside the image (needs `pr_agent`), so we only parse-check here.

- [ ] **Step 3: Commit**

```bash
git add deploy/engine-integration/cqb_patch/bootstrap.py
git commit -m "feat(phase3): bootstrap entrypoint applies patches then runs webhook server"
```

---

## Task 5: Dockerfile — thin image over the pinned PR-Agent digest

**Files:**
- Create: `deploy/engine-integration/Dockerfile`
- Create: `deploy/engine-integration/NOTICE`

- [ ] **Step 1: Write the NOTICE (Apache-2.0 change notice)**

`deploy/engine-integration/NOTICE`:
```
This image is built FROM codiumai/pr-agent (Apache-2.0). Modifications by code-quality-bot:
- runtime monkeypatch of pr_agent.algo.pr_processing.get_pr_diff (append blast-radius context)
- runtime monkeypatch of pr_agent.tools.pr_reviewer.PRReviewer._prepare_pr_review (grounded-
  refutation filter on review findings)
No PR-Agent source files are modified. See deploy/engine-integration/cqb_patch/.
```

- [ ] **Step 2: Write the Dockerfile**

`deploy/engine-integration/Dockerfile`:
```dockerfile
# Pin the SAME digest the prod compose uses, so the base stays controlled.
FROM codiumai/pr-agent@sha256:a5741a479f21d20a9bbeca7847a720f92ac6f427e8dc0920fefa039ecafd5e6f

# our engine + patches (build context = repo root)
COPY review-engine/review_engine /app/cqb/review_engine
COPY deploy/engine-integration/cqb_patch /app/cqb/cqb_patch
COPY deploy/engine-integration/NOTICE /app/cqb/NOTICE

# code-review-graph + make our packages importable
RUN pip install --no-cache-dir "code-review-graph==2.3.6"
ENV PYTHONPATH=/app/cqb

# patched entrypoint: apply monkeypatches, then run the same webhook server
ENTRYPOINT ["python", "-m", "cqb_patch.bootstrap"]
```

- [ ] **Step 3: Build the image**

Run (from repo root, with Docker up):
```bash
docker build -f deploy/engine-integration/Dockerfile -t cqb-pr-agent-engine:local .
```
Expected: build succeeds; `code-review-graph` installs (Python 3.12 base satisfies >=3.10).

- [ ] **Step 4: Smoke-check the image imports the patches**

Run:
```bash
docker run --rm cqb-pr-agent-engine:local python -c "import cqb_patch.context_patch, cqb_patch.verify_patch, review_engine.context; print('patches import OK')"
```
Expected: `patches import OK`

- [ ] **Step 5: Commit**

```bash
git add deploy/engine-integration/Dockerfile deploy/engine-integration/NOTICE
git commit -m "feat(phase3): thin image FROM pinned pr-agent digest + engine + patches"
```

---

## Task 6: Wire the image into docker-compose

**Files:**
- Modify: `deploy/docker-compose.yml` (the `pr-agent` service)

- [ ] **Step 1: Point pr-agent at the built image + add the clone volume + token env**

In `deploy/docker-compose.yml`, change the `pr-agent` service: replace the `image:` line with a `build:` (or keep `image: cqb-pr-agent-engine:local` after building), add a named volume for clones/graphs, and pass the GitLab token + clone base. Apply this diff to the `pr-agent` service block:

```yaml
  pr-agent:
    build:
      context: ..                          # repo root, relative to deploy/docker-compose.yml (review-engine + deploy both needed)
      dockerfile: deploy/engine-integration/Dockerfile
    container_name: cqb-pr-agent
    # entrypoint is set in the Dockerfile (cqb_patch.bootstrap) — remove any entrypoint override here
    environment:
      CQB_GITLAB_TOKEN: ${CQB_GITLAB_TOKEN}
      CQB_CLONE_BASE: /cqb/repos
    volumes:
      - ./pr_agent.gitlab.toml:/app/pr_agent/settings/.secrets.toml:ro
      - cqb_repos:/cqb/repos
```

Add to the top-level `volumes:` key (create it if absent):
```yaml
volumes:
  cqb_repos:
```

- [ ] **Step 2: Provide the token to compose**

The patch clones with `CQB_GITLAB_TOKEN`. Reuse the same PAT already in the toml. Add to `deploy/.env`:
```
CQB_GITLAB_TOKEN=<same glpat as [gitlab] personal_access_token in pr_agent.gitlab.toml>
```
(Do NOT commit `.env` — it is gitignored.)

- [ ] **Step 3: Bring it up and confirm it serves**

Run:
```bash
cd deploy && docker compose up -d --build pr-agent
docker compose logs pr-agent --tail=20
```
Expected: log shows `Uvicorn running on http://0.0.0.0:3000` (same server, now patched). `curl -s -o /dev/null -w "%{http_code}\n" https://cqb.chainseaclaw.win/webhook` → `405`.

- [ ] **Step 4: Commit**

```bash
git add deploy/docker-compose.yml
git commit -m "chore(phase3): run pr-agent from the engine-integrated image + clone volume"
```

---

## Task 7: Live integration test on a real MR (with-engine vs baseline)

**Files:**
- Create: `deploy/engine-integration/VALIDATION.md` (record the comparison)

- [ ] **Step 1: Capture the diff-only baseline**

On a real aipoolserver MR (e.g. a fresh test MR, or re-run on #425), BEFORE deploying the patched image (or on the un-patched container), comment `/review` and save the posted "PR Reviewer Guide" into `VALIDATION.md` under "Baseline (diff-only)".

- [ ] **Step 2: Deploy the patched image and re-review**

With the patched image running (Task 6), comment `/review` again on the same MR. Save the new guide under "With blast-radius engine".

- [ ] **Step 3: Verify the #425-class false positive is gone**

Confirm: (a) the review now reasons across files (references caller/callee behaviour), and (b) a diff-myopia finding like the `Asserts.fail` "keeps running" claim is NOT present (grounded refutation drops it). Note wall-clock (expect +~5–10s for clone-fetch + graph update + verify calls).

- [ ] **Step 4: Confirm describe/improve also got richer context**

Comment `/describe` and `/improve`; confirm they still work (the appended context flows through `get_pr_diff` for them too). They must not error.

- [ ] **Step 5: Commit the validation record**

```bash
git add deploy/engine-integration/VALIDATION.md
git commit -m "docs(phase3): live validation — engine-integrated review vs diff-only baseline"
```

---

## Self-review notes (spec coverage)

- **Cross-cutting context (describe/review/improve)** → Task 2 wraps `get_pr_diff` (the one shared seam); Task 4 rebinds it; Task 7 Step 4 checks describe/improve.
- **Grounded-refutation verify (kills #425-class FP)** → Task 3 + Task 4 `_prepare_pr_review` wrap; Task 7 Step 3.
- **Reuse the engine, don't reimplement** → repo_graph/verify import `review_engine.context`/`review`/`prompt`/`llm`.
- **No fork of PR-Agent source** → monkeypatch at runtime (Task 4); no PR-Agent `.py` edited.
- **No separate sidecar daemon** → lazy `ensure_repo` in-process with a file lock (Task 1).
- **Apache-2.0 compliance** → Task 5 NOTICE; base digest preserved.
- **Best-effort, never break PR-Agent** → every patch wraps its body in try/except returning the original (Tasks 1/2/3/4).

## Out of scope (deferred — avoid over-engineering)
Large-PR multi-patch path (`get_pr_multi_diffs`, the `return ""` branch); describe/improve-specific prompt tuning; incremental-review interaction; a persistent graph daemon; per-file inline verify of `/improve` suggestions. Ship the two seams first, measure on real MRs, then decide.
