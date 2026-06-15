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
    findings = review.run(b, str(fixture_graph_dir), llm=fake, min_severity="minor")
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
    assert fake.calls == 1

def test_premise_source_pulls_real_source(fixture_repo, fixture_graph_dir):
    from review_engine.models import Finding
    f = Finding(severity="major", file=str(fixture_repo / "util.py"), line=1,
                title="t", rationale="r", premise="p")
    src = review._premise_source(f, str(fixture_graph_dir))
    assert "def add" in src
