import json
from review_engine import cli
from review_engine.models import Finding

def test_cli_runs_engine_and_prints_findings(fixture_repo, fixture_graph_dir, monkeypatch, capsys):
    monkeypatch.setattr(cli.review, "run",
                        lambda *a, **k: [Finding(severity="major", file="/r/util.py",
                                                 line=1, title="t", rationale="r", premise="p",
                                                 confirmed=True)])
    rc = cli.main(["--repo", str(fixture_repo), "--base", "HEAD~1",
                   "--data-dir", str(fixture_graph_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "major" in out and "t" in out

def test_cli_baseline_mode_skips_graph(fixture_repo, monkeypatch, capsys):
    # baseline = diff-only; must not require a graph/data-dir
    called = {"engine": False}
    monkeypatch.setattr(cli.review, "run", lambda *a, **k: called.__setitem__("engine", True) or [])
    monkeypatch.setattr(cli, "_diff_only_findings", lambda repo, base, llm=None: [])
    rc = cli.main(["--repo", str(fixture_repo), "--base", "HEAD~1", "--baseline"])
    assert rc == 0
    assert called["engine"] is False        # engine path not used in baseline
