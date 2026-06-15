"""A/B: blast-radius engine vs diff-only baseline on one repo+base. Prints both, side by side."""
import argparse, subprocess, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from review_engine import cli

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args()
    print("=" * 30, "DIFF-ONLY BASELINE", "=" * 30)
    cli.main(["--repo", a.repo, "--base", a.base, "--baseline"])
    print("\n" + "=" * 30, "BLAST-RADIUS ENGINE", "=" * 30)
    cli.main(["--repo", a.repo, "--base", a.base])

if __name__ == "__main__":
    main()
