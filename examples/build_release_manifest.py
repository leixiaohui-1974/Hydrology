#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble a ReleaseManifest from Hydrology workflow/review artifacts."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

HELPER_PATH = BASE_DIR / "common" / "program_contract_outputs.py"
spec = importlib.util.spec_from_file_location("program_contract_outputs", HELPER_PATH)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)

build_artifact_payload = module.build_artifact_payload
build_release_manifest_payload = module.build_release_manifest_payload
default_release_manifest_output = module.default_release_manifest_output
write_release_manifest_metadata = module.write_release_manifest_metadata


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _workspace_root() -> Path:
    return BASE_DIR.parent


def _to_workspace_rel(path: str | Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return str(candidate.resolve().relative_to(_workspace_root()))
        except ValueError:
            return str(candidate.resolve())
    return str(candidate)


def _load_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    return _load_json(path)


def _normalize_artifact_payload(artifact: dict) -> dict:
    normalized = dict(artifact)
    path = normalized.get("path")
    if path is not None:
        normalized["path"] = _to_workspace_rel(path)
    return normalized


def _collect_release_ready_artifact_paths(case_id: str) -> list[str]:
    contracts_dir = _workspace_root() / "cases" / case_id / "contracts"
    autorun_report = contracts_dir / "autonomy_autorun.latest.json"
    if not autorun_report.exists():
        return []

    detail_report = _load_json_if_exists(autorun_report)
    launch_review = detail_report.get("launch_review_path", {}) if isinstance(detail_report, dict) else {}
    launch_review = launch_review if isinstance(launch_review, dict) else {}

    collected = [
        f"cases/{case_id}/contracts/autonomy_autorun.latest.json",
        f"cases/{case_id}/contracts/autonomy_autorun.latest.md",
        f"cases/{case_id}/contracts/autonomy_assessment.latest.json",
        f"cases/{case_id}/contracts/autonomy_assessment.latest.md",
        "reports/acceptance/strict_revalidation_summary.json",
        f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
        f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.md",
        f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
        f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
        f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
    ]
    review_sequence = launch_review.get("review_sequence", [])
    if isinstance(review_sequence, list):
        collected.extend(str(item) for item in review_sequence if isinstance(item, str))
    strict_summary = launch_review.get("strict_revalidation_summary")
    if isinstance(strict_summary, str):
        collected.append(strict_summary)
    for key in ("live_dashboard", "verification_assets"):
        values = launch_review.get(key, [])
        if isinstance(values, list):
            collected.extend(str(item) for item in values if isinstance(item, str))

    workspace_root = _workspace_root()
    existing: list[str] = []
    for rel_path in _unique_preserve_order([_to_workspace_rel(item) for item in collected]):
        if (workspace_root / rel_path).exists():
            existing.append(rel_path)
    return existing


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a ReleaseManifest from Hydrology outputs.")
    parser.add_argument("--case-id", required=True, help="Case identifier")
    parser.add_argument("--version", required=True, help="Release version")
    parser.add_argument("--workflow-run", required=True, help="Path to workflow_run.json")
    parser.add_argument("--review-bundle", required=True, help="Path to review_bundle.json")
    parser.add_argument("--channel", default="staging", help="Release channel")
    parser.add_argument("--status", default="published", help="Release status")
    parser.add_argument("--output", default=None, help="Output path for release_manifest.json")
    parser.add_argument("--artifact", action="append", default=[], help="Additional artifact path(s) to include")
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    workflow_run_path = Path(args.workflow_run)
    review_bundle_path = Path(args.review_bundle)

    workflow_run = _load_json(workflow_run_path)
    review_bundle = _load_json(review_bundle_path)

    release_id = f"release-{args.case_id}-{args.version}"
    artifacts = [
        build_artifact_payload(
            artifact_id=f"{release_id}:workflow-run",
            artifact_type="workflow_run",
            path=workflow_run_path,
            metadata={"role": "workflow_run_metadata"},
        ),
        build_artifact_payload(
            artifact_id=f"{release_id}:review-bundle",
            artifact_type="review_bundle",
            path=review_bundle_path,
            metadata={"role": "review_bundle_metadata"},
        ),
    ]

    for report_artifact in review_bundle.get("report_artifacts", []):
        artifacts.append(_normalize_artifact_payload(report_artifact))

    seen_paths = {str(item.get("path")) for item in artifacts if item.get("path")}
    release_ready_paths = _collect_release_ready_artifact_paths(args.case_id)
    for release_ready_path in release_ready_paths:
        normalized_path = _to_workspace_rel(release_ready_path)
        if normalized_path in seen_paths:
            continue
        path_obj = Path(normalized_path)
        artifacts.append(
            build_artifact_payload(
                artifact_id=f"{release_id}:{path_obj.stem}",
                artifact_type=path_obj.suffix.lstrip(".") or "file",
                path=normalized_path,
                metadata={"role": "release_ready_artifact"},
            )
        )
        seen_paths.add(normalized_path)
    for extra_path_str in args.artifact:
        normalized_path = _to_workspace_rel(extra_path_str)
        if normalized_path in seen_paths:
            continue
        extra_path = Path(normalized_path)
        artifacts.append(
            build_artifact_payload(
                artifact_id=f"{release_id}:{extra_path.stem}",
                artifact_type=extra_path.suffix.lstrip(".") or "file",
                path=normalized_path,
                metadata={"role": "extra_artifact"},
            )
        )
        seen_paths.add(normalized_path)

    payload = build_release_manifest_payload(
        release_id=release_id,
        case_id=args.case_id,
        version=args.version,
        channel=args.channel,
        status=args.status,
        included_runs=[workflow_run["run_id"]],
        review_refs=[review_bundle["review_id"]],
        artifacts=artifacts,
        metadata={
            "source": "Hydrology.examples.build_release_manifest",
            "workflow_type": workflow_run.get("workflow_type"),
            **({"release_ready_path": release_ready_paths} if release_ready_paths else {}),
        },
    )

    output_path = Path(args.output) if args.output else default_release_manifest_output(review_bundle_path)
    write_release_manifest_metadata(output_path, payload)
    print(f"Release manifest: {output_path}")


if __name__ == "__main__":
    main()
