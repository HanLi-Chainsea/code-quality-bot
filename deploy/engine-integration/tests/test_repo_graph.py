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
