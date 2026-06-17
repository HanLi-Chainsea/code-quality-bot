import pytest
from cqb_patch import repo_graph

def test_ensure_repo_rejects_unsafe_inputs(tmp_path):
    # argv flag-smuggling defence: a non-SHA head or non-http scheme must be refused before git runs
    with pytest.raises(ValueError):
        repo_graph.ensure_repo("https://x/y.git", "--upload-pack=evil", str(tmp_path))
    with pytest.raises(ValueError):
        repo_graph.ensure_repo("ext::sh -c evil", "a1b2c3d", str(tmp_path))

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
