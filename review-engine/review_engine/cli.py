import argparse, json, sys, pathlib
from . import graph, context, review, prompt
from .llm import Client

def _diff_only_findings(repo: str, base: str, llm=None):
    """Baseline: feed ONLY the diff (no graph, no inlined context) — what plain PR-Agent sees."""
    import subprocess
    llm = llm or Client.from_env()
    diff = subprocess.run(["git", "-C", repo, "diff", base, "--"],
                          capture_output=True, text=True).stdout
    from .models import Bundle
    b = Bundle(diff=diff)  # changed_files/related empty on purpose
    return review.run(b, data_dir="", llm=llm)

def _print(findings):
    for f in findings:
        print(f"[{f.severity}] {f.file}:{f.line}  {f.title}")
        print(f"    {f.rationale}")
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

    data_dir = args.data_dir or str(pathlib.Path(args.repo) / ".crg-data")
    if not (pathlib.Path(data_dir) / "graph.db").exists():
        graph.build(args.repo, data_dir)
    else:
        graph.update(args.repo, data_dir)
    bundle = context.build_bundle(args.repo, args.base, data_dir)
    _print(review.run(bundle, data_dir, min_severity=args.min_severity))
    return 0

if __name__ == "__main__":
    sys.exit(main())
