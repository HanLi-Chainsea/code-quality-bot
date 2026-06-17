"""Drop review findings whose premise the real source refutes (grounded refutation). Reuses the
engine's verify prompt + LLM client. Only an EXPLICIT confirmed=false drops a finding; parse
failures / uncertainty keep it (北極星 不漏)."""
import pathlib, yaml
from review_engine import review, prompt
from review_engine.llm import Client

def _read_span(repo_dir, relevant_file, start_line, end_line, ctx=40):
    p = pathlib.Path(repo_dir) / str(relevant_file).lstrip("/")
    try:
        lines = p.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    lo = max(0, int(start_line) - 1 - ctx); hi = min(len(lines), int(end_line) + ctx)
    return "\n".join(lines[lo:hi])

def _verdict(issue: dict, repo_dir: str) -> dict:
    src = _read_span(repo_dir, issue.get("relevant_file", ""),
                     issue.get("start_line", 1), issue.get("end_line", 1))
    if not src:
        return {}                                    # no source -> can't refute -> keep (不漏)
    title = issue.get("issue_header", ""); premise = issue.get("issue_content", "")
    return review._parse_json(Client.from_env().complete(
        prompt.verify_prompt(title, premise, src), max_tokens=review.VERIFY_MAX_TOKENS))

def filter_prediction(prediction_yaml: str, repo_dir: str) -> str:
    """Return the review YAML with source-refuted key_issues removed; unchanged on any parse issue."""
    try:
        data = yaml.safe_load(prediction_yaml)
        issues = data["review"]["key_issues_to_review"]
        assert isinstance(issues, list)
    except Exception:
        return prediction_yaml
    kept = []
    for issue in issues:
        v = _verdict(issue, repo_dir)
        if v.get("confirmed") is False:              # ONLY explicit refutation drops
            continue
        kept.append(issue)
    data["review"]["key_issues_to_review"] = kept
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
