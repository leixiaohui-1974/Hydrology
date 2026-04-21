from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import run_python
from workflows.report_stack_rollups import build_report_stack_artifacts, build_report_stack_rollup


def _canonical_release_manifest_output(case_id: str) -> Path:
    return BASE_DIR / "cases" / case_id / "contracts" / "release_manifest.json"


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


def enrich_release_manifest_metadata(path: str | Path, *, case_id: str, workspace_root: str | Path | None = None) -> Path:
    output_path = Path(path).resolve()
    if not output_path.is_file():
        return output_path
    workspace = Path(workspace_root).expanduser().resolve() if workspace_root is not None else BASE_DIR
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    payload.setdefault("metadata", {})
    payload["metadata"]["report_stack"] = build_report_stack_rollup(case_id, workspace)
    payload.setdefault("artifacts", [])
    existing_paths = {str(item.get("path") or "") for item in payload.get("artifacts") or [] if isinstance(item, dict)}
    for item in build_report_stack_artifacts(case_id, workspace):
        if str(item.get("path") or "") in existing_paths:
            continue
        payload["artifacts"].append(item)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    args = _build_parser().parse_args()
    candidates = [
        BASE_DIR / "examples" / "build_release_manifest.py",
        BASE_DIR.parents[1] / "Hydrology" / "examples" / "build_release_manifest.py",
    ]
    module_path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
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
    output_path = Path(args.output).resolve() if args.output else _canonical_release_manifest_output(args.case_id)
    enrich_release_manifest_metadata(output_path, case_id=args.case_id, workspace_root=BASE_DIR)


if __name__ == "__main__":
    main()
