from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import run_python


def _canonical_review_paths(case_id: str) -> tuple[Path, Path]:
    contracts_dir = BASE_DIR.parent / "cases" / case_id / "contracts"
    return (
        contracts_dir / "e2e_review_bundle.html",
        contracts_dir / "review_bundle.json",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic review metadata and report artifacts.")
    parser.add_argument("--case-id", required=True, help="Case identifier")
    parser.add_argument("--run-id", required=True, help="Workflow run id to review")
    parser.add_argument("--report-output", default=None, help="HTML report output path")
    parser.add_argument("--review-output", default=None, help="ReviewBundle JSON output path")
    parser.add_argument("--review-id", default=None, help="Override review id")
    parser.add_argument("--verdict", default="pass_with_comments", help="Review verdict")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    module_path = Path(__file__).resolve().parents[1] / "examples" / "generate_html_report.py"
    default_report_output, default_review_output = _canonical_review_paths(args.case_id)
    report_output = Path(args.report_output).resolve() if args.report_output else default_report_output
    review_output = Path(args.review_output).resolve() if args.review_output else default_review_output
    cli_args = [
        "--case-id",
        args.case_id,
        "--run-id",
        args.run_id,
        "--report-output",
        str(report_output),
        "--verdict",
        args.verdict,
        "--review-output",
        str(review_output),
    ]
    if args.review_id:
        cli_args.extend(["--review-id", args.review_id])
    run_python(module_path, cli_args)


if __name__ == "__main__":
    main()
