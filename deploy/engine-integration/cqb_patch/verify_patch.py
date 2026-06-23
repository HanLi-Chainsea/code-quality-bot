"""Drop review findings whose premise the real source refutes (grounded refutation). Reuses the
engine's verify prompt + LLM client. Only an EXPLICIT confirmed=false drops a finding; parse
failures / uncertainty / per-issue errors keep it (北極星 不漏)."""
import pathlib, yaml
from review_engine import review, prompt
from review_engine.llm import Client
from .repo_graph import _log

_MAX_FILE_BYTES = 1_000_000   # don't slurp a huge/binary file into the prompt
_CTX = 15                     # lines of context around the issue span

# PR-Agent's models emit slightly-malformed YAML that plain yaml.safe_load chokes on; PR-Agent
# parses it with its OWN load_yaml(keys_fix_yaml=...). We MUST parse the same way or we silently
# fail to find key_issues_to_review and no-op. Import lazily so the unit tests (no pr_agent on the
# path) fall back to safe_load.
try:
    from pr_agent.algo.utils import load_yaml as _pr_load_yaml
except Exception:                                   # pragma: no cover - only in the live container
    _pr_load_yaml = None

_KEYS_FIX = ["ticket_compliance_check", "estimated_effort_to_review_[1-5]:", "security_concerns:",
             "key_issues_to_review:", "relevant_file:", "relevant_line:", "suggestion:"]

def _load_prediction(prediction_yaml: str) -> dict:
    if _pr_load_yaml is not None:
        return _pr_load_yaml(prediction_yaml.strip(), keys_fix_yaml=_KEYS_FIX,
                             first_key="review", last_key="security_concerns")
    return yaml.safe_load(prediction_yaml)

def _safe_path(repo_dir: str, relevant_file: str):
    """Resolve relevant_file UNDER repo_dir; reject absolute paths / traversal / symlink escape so a
    malicious `relevant_file` from the model YAML can't read files outside the repo."""
    root = pathlib.Path(repo_dir).resolve()
    target = (root / str(relevant_file)).resolve()
    if root != target and root not in target.parents:
        return None
    return target

def _read_span(repo_dir, relevant_file, start_line, end_line, ctx=_CTX) -> str:
    p = _safe_path(repo_dir, relevant_file)
    if p is None:
        _log(f"verify: rejected out-of-repo path {relevant_file!r}")
        return ""
    try:
        if p.stat().st_size > _MAX_FILE_BYTES:
            return ""
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
    """Return the review YAML with source-refuted key_issues removed; unchanged on any parse issue.
    A per-issue verify failure keeps that issue (a single 401/timeout never drops a real finding)."""
    try:
        data = _load_prediction(prediction_yaml)
        issues = data["review"]["key_issues_to_review"]
        assert isinstance(issues, list)
    except Exception as e:
        # was silently no-op'ing: if PR-Agent's prediction can't be parsed into a findings list,
        # SAY SO (else verify looks dead when it's just a parse miss). Keeps the review unchanged.
        _log(f"verify: no findings list to filter ({type(e).__name__}: {str(e)[:80]}) — review kept as-is")
        return prediction_yaml
    kept = []
    for issue in issues:
        try:
            v = _verdict(issue, repo_dir)
        except Exception as e:
            _log(f"verify failed for {str(issue.get('issue_header'))[:40]!r} ({type(e).__name__}); kept")
            v = {}
        if v.get("confirmed") is False:              # ONLY an explicit refutation drops
            _log(f"verify DROPPED {str(issue.get('issue_header'))[:50]!r}: "
                 f"{str(v.get('reason'))[:140]}")     # observability — never a silent drop
            continue
        kept.append(issue)
    _log(f"verify: {len(issues)} finding(s) in -> {len(kept)} kept, {len(issues) - len(kept)} dropped")
    data["review"]["key_issues_to_review"] = kept
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
