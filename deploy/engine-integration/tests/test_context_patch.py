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
