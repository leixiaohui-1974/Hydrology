from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import run_python


def _canonical_release_manifest_output(case_id: str) -> Path:
    return BASE_DIR.parent / "cases" / case_id / "contracts" / "release_manifest.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a deterministic release manifest from workflow outputs.")
    parser.add_argument("--case-id", required=True, help="Case identifier")
    parser.add_argument("--version", required=True, help="Release version")
    parser.add_argument("--workflow-run", required=True, help="WorkflowRun JSON")
    parser.add_argument("--review-bundle", required=True, help="ReviewBundle JSON")
    parser.add_argument("--channel", default="staging", help="Release channel")
    parser.add_argument("--status", default="published", help="Release status")
    parser.add_argument("--output", default=None, help="Release manifest output path")
    parser.add_argument("--artifact", action="append", default=[], help="Additional artifact paths")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    module_path = Path(__file__).resolve().parents[1] / "examples" / "build_release_manifest.py"
    cli_args = [
        "--case-id",
        args.case_id,
        "--version",
        args.version,
        "--workflow-run",
        args.workflow_run,
        "--review-bundle",
        args.review_bundle,
        "--channel",
        args.channel,
        "--status",
        args.status,
        "--output",
        str(Path(args.output).resolve() if args.output else _canonical_release_manifest_output(args.case_id)),
    ]
    for artifact in args.artifact:
        cli_args.extend(["--artifact", artifact])
    run_python(module_path, cli_args)


if __name__ == "__main__":
    main()
