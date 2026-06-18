import yaml
from cqb_patch import verify_patch

PREDICTION = """\
review:
  key_issues_to_review:
  - relevant_file: src/A.java
    issue_header: Possible Bug
    issue_content: after Asserts.fail the code keeps running
    start_line: 10
    end_line: 12
  - relevant_file: src/A.java
    issue_header: Real Bug
    issue_content: null deref on cold cache path
    start_line: 40
    end_line: 41
"""

def test_filter_drops_refuted_keeps_others(monkeypatch):
    # verdict: first issue REFUTED (confirmed false), second has no verdict -> kept
    verdicts = iter([{"confirmed": False, "reason": "Asserts.fail throws"}, {}])
    monkeypatch.setattr(verify_patch, "_verdict", lambda issue, repo_dir: next(verdicts))
    new_pred = verify_patch.filter_prediction(PREDICTION, repo_dir="/tmp/repo")
    data = yaml.safe_load(new_pred)
    headers = [i["issue_header"] for i in data["review"]["key_issues_to_review"]]
    assert "Real Bug" in headers
    assert "Possible Bug" not in headers          # explicitly refuted -> dropped

def test_filter_is_transparent_on_parse_failure():
    assert verify_patch.filter_prediction("not: [valid", repo_dir="/x") == "not: [valid"

def test_read_span_rejects_out_of_repo_path(tmp_path):
    # a malicious relevant_file from the model YAML must not read files outside the repo dir
    (tmp_path / "inside.txt").write_text("line1\nline2\nline3\n")
    assert verify_patch._read_span(str(tmp_path), "inside.txt", 1, 1)            # in-repo OK
    assert verify_patch._read_span(str(tmp_path), "../../../../etc/passwd", 1, 1) == ""
    assert verify_patch._read_span(str(tmp_path), "/etc/passwd", 1, 1) == ""

def test_per_issue_verify_error_keeps_the_finding(monkeypatch):
    # a single verify exception (e.g. 401) must NOT drop the finding (北極星 不漏)
    def boom(issue, repo_dir):
        raise RuntimeError("401")
    monkeypatch.setattr(verify_patch, "_verdict", boom)
    out = verify_patch.filter_prediction(PREDICTION, repo_dir="/tmp/repo")
    assert "Possible Bug" in out and "Real Bug" in out      # both kept despite verify failing
