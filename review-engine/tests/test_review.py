from review_engine import llm

def test_llm_client_reads_env(monkeypatch):
    monkeypatch.setenv("REVIEWER_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("REVIEWER_API_KEY", "sk-test")
    c = llm.Client.from_env()
    assert c.base_url == "http://127.0.0.1:4000/v1"
    assert c.model == "reviewer"

import json
from review_engine import review
from review_engine.models import Bundle

import threading

class FakeLLM:
    """Prompt-aware, thread-safe fake (find/verify run concurrently in review.run):
    - find prompts -> the find payload
    - verify prompts -> the verdict whose title key appears in the prompt (order-independent,
      so it stays correct under parallel verify); no match -> '{}' (parse miss)."""
    def __init__(self, find_payload, verify_payloads):
        self._find = json.dumps(find_payload)
        self._verify = {k: json.dumps(v) for k, v in verify_payloads.items()}
        self.calls = 0
        self.find_calls = 0
        self._lock = threading.Lock()
    def complete(self, prompt, max_tokens=2000):
        is_verify = "落地反證" in prompt
        with self._lock:
            self.calls += 1
            if not is_verify:
                self.find_calls += 1
        if is_verify:
            for title, verdict in self._verify.items():
                if title in prompt:
                    return verdict
            return "{}"
        return self._find

def test_review_keeps_confirmed_drops_refuted(fixture_repo, fixture_graph_dir):
    from review_engine import context
    b = context.build_bundle(str(fixture_repo), "HEAD~1", str(fixture_graph_dir))
    fake = FakeLLM(
        find_payload={"findings": [
            {"severity": "major", "file": "/r/util.py", "line": 1,
             "title": "breaks caller", "rationale": "x", "premise": "main.run passes 2 args"},
            {"severity": "minor", "file": "/r/util.py", "line": 50,
             "title": "nit", "rationale": "y", "premise": "none"},
        ]},
        verify_payloads={"breaks caller": {"confirmed": True, "reason": "caller still passes 2 args"},
                         "nit": {"confirmed": False, "reason": "source disproves it"}},
    )
    findings = review.run(b, str(fixture_graph_dir), llm=fake, min_severity="minor", lenses=[""])
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
        verify_payloads={},   # minor is gated out before verify, so no verdict is consulted
    )
    findings = review.run(b, str(fixture_graph_dir), llm=fake, min_severity="major", lenses=[""])
    assert findings == []                      # minor gated out before verify
    assert fake.calls == 1                     # 1 find pass, 0 verify (gated before verify)

def test_premise_source_pulls_real_source(fixture_repo, fixture_graph_dir):
    from review_engine.models import Finding
    f = Finding(severity="major", file=str(fixture_repo / "util.py"), line=1,
                title="t", rationale="r", premise="p")
    src = review._premise_source(f, str(fixture_graph_dir))
    assert "def add" in src

def test_review_keeps_unverified_on_parse_miss(fixture_repo, fixture_graph_dir):
    # A verifier that returns no parseable verdict is a TECHNICAL miss, not a refutation.
    # The finding must be surfaced as unverified (confirmed=None), never silently dropped.
    from review_engine import context
    b = context.build_bundle(str(fixture_repo), "HEAD~1", str(fixture_graph_dir))
    fake = FakeLLM(
        find_payload={"findings": [
            {"severity": "major", "file": "/r/util.py", "line": 1,
             "title": "real bug", "rationale": "x", "premise": "p"}]},
        verify_payloads={"real bug": {}},   # no "confirmed" key -> parse yields {} -> technical miss
    )
    findings = review.run(b, str(fixture_graph_dir), llm=fake, lenses=[""])
    assert len(findings) == 1
    assert findings[0].confirmed is None

def test_review_multipass_unions_and_dedups(fixture_repo, fixture_graph_dir):
    # Two lenses each surface the same finding -> union (2 find passes) then dedup to one.
    from review_engine import context
    b = context.build_bundle(str(fixture_repo), "HEAD~1", str(fixture_graph_dir))
    fake = FakeLLM(
        find_payload={"findings": [
            {"severity": "major", "file": "/r/util.py", "line": 1,
             "title": "same issue", "rationale": "x", "premise": "p"}]},
        verify_payloads={"same issue": {"confirmed": True, "reason": "ok"}},
    )
    findings = review.run(b, str(fixture_graph_dir), llm=fake, lenses=["lensA", "lensB"])
    assert fake.find_calls == 2          # one find pass per lens
    assert len(findings) == 1            # the duplicate across lenses collapsed to one
    assert findings[0].title == "same issue"

def test_consolidate_merges_same_root_and_never_drops():
    from review_engine.models import Finding
    findings = [
        Finding(severity="major", file="/r/F.java", line=10, title="A trigger 1", rationale="x", confirmed=True),
        Finding(severity="blocker", file="/r/F.java", line=20, title="A trigger 2", rationale="y", confirmed=True),
        Finding(severity="major", file="/r/F.java", line=99, title="B distinct", rationale="z", confirmed=True),
    ]
    class CFake:   # groups 0+1 (same root) and intentionally omits 2 to exercise the safety net
        def complete(self, prompt, max_tokens=2000):
            return '{"groups":[{"title":"A merged","severity":"blocker","rationale":"m","members":[0,1]}]}'
    out = review.consolidate(findings, llm=CFake())
    assert len(out) == 2                                    # merged A(0+1) + B kept by safety net
    merged = next(f for f in out if f.title == "A merged")
    assert merged.severity == "blocker"
    assert sorted(merged.locations) == ["F.java:10", "F.java:20"]
    assert any(f.title == "B distinct" for f in out)        # ungrouped finding never dropped

def test_consolidate_single_finding_is_noop():
    from review_engine.models import Finding
    f = [Finding(severity="major", file="/r/F.java", line=10, title="solo", rationale="x", confirmed=True)]
    out = review.consolidate(f, llm=None)                   # must not call any LLM for <=1 finding
    assert len(out) == 1 and out[0].locations == ["F.java:10"]
