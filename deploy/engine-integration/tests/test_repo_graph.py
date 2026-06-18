import pytest
from cqb_patch import repo_graph

def test_prepared_rejects_unsafe_inputs(tmp_path):
    # argv flag-smuggling / scheme defence — validated before any git runs
    with pytest.raises(ValueError):
        with repo_graph.prepared("https://x/y.git", "--upload-pack=evil", str(tmp_path)):
            pass
    with pytest.raises(ValueError):
        with repo_graph.prepared("ext::sh -c evil", "a" * 40, str(tmp_path)):
            pass

def test_blast_local_for_local_repo(fixture_repo, tmp_path):
    # fixture_repo: HEAD changes util.add(); main.run() calls it. base = HEAD~1.
    ctx = repo_graph.blast_local(str(fixture_repo), str(tmp_path / "g"), "HEAD~1", token_budget=50_000)
    assert "def run" in ctx           # the caller body is inlined
    assert ctx.strip()

def test_blast_local_empty_when_no_changed_functions(fixture_repo, tmp_path):
    # base == HEAD -> no diff -> empty context, never raises
    ctx = repo_graph.blast_local(str(fixture_repo), str(tmp_path / "g"), "HEAD")
    assert ctx == ""
