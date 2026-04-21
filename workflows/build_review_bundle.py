from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import run_python
from workflows.report_stack_rollups import build_report_stack_rollup


def _canonical_review_paths(case_id: str) -> tuple[Path, Path]:
    contracts_dir = BASE_DIR / "cases" / case_id / "contracts"
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


def enrich_review_bundle_metadata(path: str | Path, *, case_id: str, workspace_root: str | Path | None = None) -> Path:
    review_output = Path(path).resolve()
    if not review_output.is_file():
        return review_output
    workspace = Path(workspace_root).expanduser().resolve() if workspace_root is not None else BASE_DIR
    payload = json.loads(review_output.read_text(encoding="utf-8"))
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata["report_stack"] = build_report_stack_rollup(case_id, workspace)
    payload["metadata"] = metadata
    review_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return review_output


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
    enrich_review_bundle_metadata(review_output, case_id=args.case_id, workspace_root=BASE_DIR)


if __name__ == "__main__":
    main()
