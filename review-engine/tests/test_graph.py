from review_engine import graph

def test_detect_changes_returns_changed_add(fixture_repo, fixture_graph_dir):
    changed = graph.detect_changes(str(fixture_repo), base="HEAD~1", data_dir=str(fixture_graph_dir))
    names = {c.name for c in changed}
    assert "add" in names
    add = next(c for c in changed if c.name == "add")
    assert add.file_path.endswith("util.py")

def test_blast_radius_finds_caller(fixture_repo, fixture_graph_dir):
    # add()'s caller is main.run() — must show up as a 1-hop caller
    radius = graph.blast_radius("/private" + str(fixture_repo) + "/util.py::add"
                                if str(fixture_repo).startswith("/") and not str(fixture_repo).startswith("/private")
                                else str(fixture_repo) + "/util.py::add",
                                data_dir=str(fixture_graph_dir))
    caller_names = {n.name for n in radius.callers}
    assert "run" in caller_names

def test_blast_radius_by_changed_function(fixture_repo, fixture_graph_dir):
    changed = graph.detect_changes(str(fixture_repo), "HEAD~1", str(fixture_graph_dir))
    add = next(c for c in changed if c.name == "add")
    radius = graph.blast_radius(add.qualified_name, data_dir=str(fixture_graph_dir))
    assert any(n.name == "run" for n in radius.callers)

def test_detect_changes_no_changes_returns_empty(fixture_repo, fixture_graph_dir):
    # CRG prints "No changes detected." (non-JSON) for an empty changeset -> must be [], not a raise
    assert graph.detect_changes(str(fixture_repo), "HEAD", str(fixture_graph_dir)) == []
