import subprocess, sys, os, pathlib, pytest

CRG = str(pathlib.Path(sys.executable).parent / "code-review-graph")

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory):
    """A 2-file repo where main.run() calls util.add(); util.add's signature changes in HEAD."""
    repo = tmp_path_factory.mktemp("crg_fixture")
    (repo / "util.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "main.py").write_text("from util import add\ndef run():\n    return add(1, 2)\n")
    _git(repo, "init"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A"); _git(repo, "commit", "-m", "init")
    # change the signature -> blast radius should include main.run() as a caller
    (repo / "util.py").write_text("def add(a, b, c):\n    return a + b + c\n")
    _git(repo, "add", "-A"); _git(repo, "commit", "-m", "change add signature")
    return repo

@pytest.fixture(scope="session")
def fixture_graph_dir(fixture_repo, tmp_path_factory):
    graph_dir = tmp_path_factory.mktemp("crg_graph")
    subprocess.run([CRG, "build", "--repo", str(fixture_repo), "--data-dir", str(graph_dir)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert (graph_dir / "graph.db").exists()
    return graph_dir
