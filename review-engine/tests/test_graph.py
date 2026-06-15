from review_engine import graph

def test_detect_changes_returns_changed_add(fixture_repo, fixture_graph_dir):
    changed = graph.detect_changes(str(fixture_repo), base="HEAD~1", data_dir=str(fixture_graph_dir))
    names = {c.name for c in changed}
    assert "add" in names
    add = next(c for c in changed if c.name == "add")
    assert add.file_path.endswith("util.py")
