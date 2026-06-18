from cqb_patch import context_patch

class FakeMR:
    diff_refs = {"base_sha": "b" * 40, "head_sha": "h" * 40}

class FakeGP:
    mr = FakeMR()
    gl = type("g", (), {"url": "https://gitlab.example.com"})()
    id_project = "grp/proj"

def test_clone_url_is_clean(monkeypatch):
    monkeypatch.setenv("CQB_GITLAB_TOKEN", "secret-tok")
    url = context_patch.clone_url(FakeGP())
    assert url == "https://gitlab.example.com/grp/proj.git"
    assert "secret-tok" not in url          # token never embedded in the URL

def test_wrapper_appends_context(monkeypatch):
    def fake_original(git_provider, token_handler, model, **kw):
        return "DIFF-BODY"
    monkeypatch.setattr(context_patch.repo_graph, "blast_context", lambda *a, **k: "BLAST-CTX")
    wrapped = context_patch.wrap_get_pr_diff(fake_original)
    out = wrapped(FakeGP(), token_handler=None, model="m")
    assert out.startswith("DIFF-BODY")
    assert "BLAST-CTX" in out

def test_wrapper_is_transparent_on_failure(monkeypatch):
    def fake_original(git_provider, token_handler, model, **kw):
        return "DIFF-ONLY"
    monkeypatch.setattr(context_patch.repo_graph, "blast_context",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    wrapped = context_patch.wrap_get_pr_diff(fake_original)
    assert wrapped(FakeGP(), token_handler=None, model="m") == "DIFF-ONLY"
