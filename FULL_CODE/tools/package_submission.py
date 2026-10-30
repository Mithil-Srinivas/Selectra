"""Check the submission file, then zip a fresh git clone of the project as <TEAM>_R3.zip (README §7).

    uv run python tools/package_submission.py --team TEAM123          (from FULL_CODE/)

Commit your work first: the zip is made from a clone, so only committed files are included.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {"question_id", "action", "answer_text", "cited_product_ids", "cited_policy_sections", "stated_prices",
            "latency_ms", "tokens_in", "tokens_out"}


def check_predictions() -> None:
    pred_path = ROOT / "submission" / "R3_predictions.jsonl"
    if not pred_path.exists():
        sys.exit(f"missing {pred_path}: run src.submission.predict on questions_test.csv first")
    rows = [json.loads(l) for l in pred_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for i, r in enumerate(rows, 1):
        if missing := REQUIRED - r.keys():
            sys.exit(f"line {i}: missing keys {sorted(missing)}")
        if r["action"] not in ("answer", "clarify", "refuse"):
            sys.exit(f"line {i}: bad action {r['action']!r}")
    test_q = ROOT / "data" / "questions_test.csv"
    if test_q.exists():
        with test_q.open(encoding="utf-8") as f:
            wanted = {row["question_id"] for row in csv.DictReader(f)}
        if gaps := wanted - {r["question_id"] for r in rows}:
            sys.exit(f"{len(gaps)} test questions have no prediction, e.g. {sorted(gaps)[:3]}")
    print(f"ok: {len(rows)} predictions with all required keys")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", required=True, help="your team ID, used in the zip name")
    args = ap.parse_args()
    check_predictions()
    if subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout.strip():
        print("warning: uncommitted changes are NOT included in the zip (it is built from a fresh clone)")
    name = f"{args.team}_R3"
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / name
        subprocess.run(["git", "clone", "--quiet", str(ROOT), str(clone)], check=True)
        out = ROOT / f"{name}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(clone.rglob("*")):
                # skip git's own metadata (deleting it fails on Windows: its object files are read-only)
                if p.is_file() and ".git" not in p.relative_to(clone).parts:
                    z.write(p, Path(name) / p.relative_to(clone))
    top = sorted({Path(n).parts[1] for n in zipfile.ZipFile(out).namelist() if len(Path(n).parts) > 1})
    print(f"wrote {out}; top level: {top}")


if __name__ == "__main__":
    main()
