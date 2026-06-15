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
