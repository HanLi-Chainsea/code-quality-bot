import argparse, sys, pathlib
from . import graph, context, review
from .llm import Client

def _diff_only_findings(repo: str, base: str, llm=None):
    """Baseline: feed ONLY the diff (no graph, no inlined context) — what plain PR-Agent sees."""
    from .models import Bundle
    llm = llm or Client.from_env()
    b = Bundle(diff=context._git_diff(repo, base))   # changed_files/related empty on purpose
    return review.run(b, data_dir="", llm=llm)

def _mark(f):
    return {True: "✓ verified", None: "? unverified", False: "✗ refuted"}.get(f.confirmed, "")

def _print(findings):
    for f in findings:
        print(f"[{f.severity}] {_mark(f)}  {f.file}:{f.line}  {f.title}")
        print(f"    {f.rationale}")
        if len(f.locations) > 1:
            print(f"    觸發點: {', '.join(f.locations)}")
    print(f"\n{len(findings)} finding(s).")

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="review-engine")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", default="HEAD~1")
    ap.add_argument("--data-dir", default="")
    ap.add_argument("--baseline", action="store_true",
                    help="diff-only baseline (no graph) for A/B comparison")
    ap.add_argument("--min-severity", default="major", choices=["minor", "major", "blocker"])
    args = ap.parse_args(argv)

    if args.baseline:
        _print(_diff_only_findings(args.repo, args.base))
        return 0

    import subprocess
    data_dir = args.data_dir or str(pathlib.Path(args.repo) / ".crg-data")
    try:
        if not (pathlib.Path(data_dir) / "graph.db").exists():
            graph.build(args.repo, data_dir)
        else:
            graph.update(args.repo, data_dir)
        bundle = context.build_bundle(args.repo, args.base, data_dir)
    except FileNotFoundError:
        print("error: `code-review-graph` not found — is the venv active / installed?", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as e:
        print(f"error: code-review-graph failed (check --repo path / --base ref).\n{e.stderr or e}",
              file=sys.stderr)
        return 2
    except RuntimeError as e:                      # detect_changes non-JSON (bad base ref)
        print(f"error: {e}", file=sys.stderr)
        return 2
    findings = review.run(bundle, data_dir, min_severity=args.min_severity)
    findings = review.consolidate(findings)   # merge same-root-cause findings, list trigger points
    _print(findings)
    return 0

if __name__ == "__main__":
    sys.exit(main())
