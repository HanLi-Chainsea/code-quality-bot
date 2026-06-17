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

def test_bundle_large_changeset_degrades_to_excerpts_with_note(fixture_repo, fixture_graph_dir):
    # a budget too small for the full changed file forces excerpt mode; the degradation must be
    # NOTED (no silent truncation) so the model knows it isn't seeing whole files.
    b = context.build_bundle(str(fixture_repo), "HEAD~1", str(fixture_graph_dir), token_budget=10)
    assert b.notes and any("大改動" in n for n in b.notes)
