from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
SCRIPTS_DIR = BASE_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from export_case_platform_readiness import DEFAULT_RULES, run_readiness  # noqa: E402
from workflows._shared import normalize_serialized_paths  # noqa: E402


WORKSPACE = BASE_DIR.parent
DEFAULT_CONFIG = BASE_DIR / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
DEFAULT_FINAL_REPORT_GOVERNANCE = BASE_DIR / "configs" / "final_report_governance.yaml"
FINAL_REPORT_SCHEMA_VERSION = "final_report.v1"


def _canonical_contracts_dir(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts"


def _canonical_final_report_output(case_id: str) -> Path:
    return _canonical_contracts_dir(case_id) / "final_report.latest.json"


def _workspace_rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE))
    except ValueError:
        return str(path.resolve())


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_contract_path(case_id: str, explicit: str | None, filename: str) -> Path:
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_absolute():
            candidate = (WORKSPACE / candidate).resolve()
        return candidate
    return _canonical_contracts_dir(case_id) / filename


def _eval_release_gate_not_blocked(rollout_case_row: dict[str, Any], fr_gov: dict[str, Any]) -> bool:
    """True only when board 有匹配 case 行且 release_gate.status 在允许集合内且非 blocked。"""
    cfg = fr_gov.get("release_gate_assertion")
    cfg = cfg if isinstance(cfg, dict) else {}
    require_row = cfg.get("require_rollout_board_row")
    if require_row is None:
        require_row = True
    allowed_raw = cfg.get("allowed_non_blocked_statuses") or cfg.get("allowed_statuses")
    if isinstance(allowed_raw, list) and allowed_raw:
        allowed = {str(x).strip().lower() for x in allowed_raw if str(x).strip()}
    else:
        allowed = {"needs-review", "release-ready"}
    if require_row and not str(rollout_case_row.get("case_id") or "").strip():
        return False
    rb = rollout_case_row.get("release_gate")
    release_board = rb if isinstance(rb, dict) else {}
    status = str(release_board.get("status") or "").strip().lower()
    if not status:
        return False
    if status == "blocked":
        return False
    return status in allowed


def load_final_report_governance(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"final_report_governance yaml not found: {resolved}")
    data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("final_report_governance root must be a mapping")
    return data


def _derive_promotion_semantics(
    review_bundle: dict[str, Any],
    release_manifest: dict[str, Any],
    rollout_case_row: dict[str, Any],
    gov: dict[str, Any],
) -> dict[str, Any]:
    verdict = str(review_bundle.get("verdict") or "").strip()
    table = gov.get("review_verdict_semantics") or {}
    entry = table.get(verdict) if isinstance(table.get(verdict), dict) else None
    if entry is None:
        entry = table.get("_default") or {}
    semantic_lane = str(entry.get("semantic_lane") or "unspecified")
    labels = entry.get("labels") if isinstance(entry.get("labels"), dict) else {}
    manifest_status = str(release_manifest.get("status") or "").strip()
    board_gate = str((rollout_case_row.get("release_gate") or {}).get("status") or "").strip()
    notes: list[dict[str, Any]] = []
    cm = entry.get("compatible_manifest_statuses")
    if isinstance(cm, list) and cm and manifest_status and manifest_status not in cm:
        notes.append(
            {
                "code": "manifest_status_not_in_compatible_set",
                "actual": manifest_status,
                "expected_any_of": cm,
            }
        )
    cb = entry.get("compatible_release_board_gate_statuses")
    if isinstance(cb, list) and cb and board_gate and board_gate not in cb:
        notes.append(
            {
                "code": "release_board_gate_not_in_compatible_set",
                "actual": board_gate,
                "expected_any_of": cb,
            }
        )
    return {
        "review_verdict": verdict,
        "semantic_lane": semantic_lane,
        "labels": labels,
        "consistency_notes": notes,
        "observed_manifest_status": manifest_status or None,
        "observed_release_board_gate_status": board_gate or None,
    }


def _load_rollout_case_row(path: Path, case_id: str) -> dict[str, Any]:
    payload = _load_json(path)
    board = payload.get("readiness_release_board")
    if not isinstance(board, dict):
        return {
            "case_id": case_id,
            "release_gate": {
                "status": "rollout-board-missing",
                "summary": "rollout readiness board missing; release gate cannot pass",
            },
            "dimensions": {},
        }
    for row in board.get("cases") or []:
        if isinstance(row, dict) and row.get("case_id") == case_id:
            return row
    return {
        "case_id": case_id,
        "release_gate": {
            "status": "rollout-case-row-missing",
            "summary": f"rollout readiness board missing case row for {case_id}; release gate cannot pass",
        },
        "dimensions": {},
    }


def _assertion_summary(assertions: list[dict[str, Any]]) -> dict[str, int]:
    passed = sum(1 for item in assertions if item.get("passed"))
    failed = len(assertions) - passed
    return {
        "total": len(assertions),
        "passed": passed,
        "failed": failed,
    }


def _zero_hardcoding_gate_passed(
    verification: dict[str, Any],
    coverage: dict[str, Any],
) -> bool:
    gate = str(verification.get("zero_hardcoding_gate") or "").strip().lower()
    if gate:
        return gate in {"passed", "pass", "ok", "ready", "green"}

    stage3 = verification.get("stage3_outcome_quality") or {}
    coverage_report = stage3.get("coverage_report") or {}
    verification_gate_status = str(coverage_report.get("gate_status") or "").strip().lower()
    if verification_gate_status:
        return verification_gate_status != "failed_by_hardcoding_linter"

    coverage_gate_status = str(coverage.get("gate_status") or "").strip().lower()
    if coverage_gate_status:
        return coverage_gate_status != "failed_by_hardcoding_linter"

    return False


def _artifact_has_acceptance_role(artifact: Any) -> bool:
    if not isinstance(artifact, dict):
        return False
    metadata = artifact.get("metadata") or {}
    role = str(metadata.get("role") or "").strip().lower()
    if role == "acceptance_report":
        return True
    artifact_type = str(artifact.get("artifact_type") or "").strip().lower()
    return artifact_type == "html_report" and "acceptance" in str(artifact.get("artifact_id") or "").lower()


def _acceptance_artifact_present(
    review_bundle: dict[str, Any],
    release_manifest: dict[str, Any],
) -> bool:
    review_artifacts = review_bundle.get("report_artifacts") or []
    release_artifacts = release_manifest.get("artifacts") or []
    return any(_artifact_has_acceptance_role(item) for item in [*review_artifacts, *release_artifacts])


def _build_assertions(
    *,
    platform_readiness: dict[str, Any],
    rollout_case_row: dict[str, Any],
    review_bundle: dict[str, Any],
    release_manifest: dict[str, Any],
    coverage: dict[str, Any],
    verification: dict[str, Any],
    fr_gov: dict[str, Any],
) -> list[dict[str, Any]]:
    readiness_summary = platform_readiness.get("summary") or {}
    integrity = verification.get("stage2_execution_integrity") or {}
    pending_workflows = integrity.get("pending_workflows") or []

    return [
        {
            "key": "pipeline_contract_ready",
            "passed": bool(readiness_summary.get("pipeline_contract_ready")),
            "source": "platform_readiness.summary.pipeline_contract_ready",
        },
        {
            "key": "verification_closure_check_passed",
            "passed": bool(integrity.get("closure_check_passed")),
            "source": "e2e_outcome_verification_report.stage2_execution_integrity.closure_check_passed",
        },
        {
            "key": "verification_pending_workflows_empty",
            "passed": len(pending_workflows) == 0,
            "source": "e2e_outcome_verification_report.stage2_execution_integrity.pending_workflows",
        },
        {
            "key": "zero_hardcoding_gate_passed",
            "passed": _zero_hardcoding_gate_passed(verification, coverage),
            "source": "e2e_outcome_verification_report.zero_hardcoding_gate | stage3_outcome_quality.coverage_report.gate_status",
        },
        {
            "key": "acceptance_artifact_present",
            "passed": _acceptance_artifact_present(review_bundle, release_manifest),
            "source": "review_bundle.report_artifacts | release_manifest.artifacts[].metadata.role=acceptance_report",
        },
        {
            "key": "review_bundle_verdict_present",
            "passed": bool(str(review_bundle.get("verdict") or "").strip()),
            "source": "review_bundle.verdict",
        },
        {
            "key": "release_manifest_present",
            "passed": bool(release_manifest),
            "source": "release_manifest",
        },
        {
            "key": "release_gate_not_blocked",
            "passed": _eval_release_gate_not_blocked(rollout_case_row, fr_gov),
            "source": "rollout_readiness_baseline.readiness_release_board.cases[].release_gate.status",
        },
    ]


def build_final_report(
    *,
    case_id: str,
    output_path: str | Path | None = None,
    workflow_run_path: str | None = None,
    review_bundle_path: str | None = None,
    release_manifest_path: str | None = None,
    coverage_path: str | None = None,
    verification_path: str | None = None,
    readiness_config: str | Path = DEFAULT_CONFIG,
    readiness_rules: str | Path = DEFAULT_RULES,
    rollout_board_path: str | Path | None = None,
    final_report_governance_path: str | Path | None = None,
) -> dict[str, Any]:
    workflow_run_file = _resolve_contract_path(case_id, workflow_run_path, "workflow_run.json")
    review_bundle_file = _resolve_contract_path(case_id, review_bundle_path, "review_bundle.json")
    release_manifest_file = _resolve_contract_path(case_id, release_manifest_path, "release_manifest.json")
    coverage_file = _resolve_contract_path(case_id, coverage_path, "outcome_coverage_report.latest.json")
    verification_file = _resolve_contract_path(case_id, verification_path, "e2e_outcome_verification_report.json")
    final_report_file = (
        Path(output_path).resolve()
        if output_path is not None
        else _canonical_final_report_output(case_id).resolve()
    )
    rollout_board_value = rollout_board_path or (WORKSPACE / "cases" / "rollout_readiness_baseline.latest.json")
    rollout_board_file = Path(rollout_board_value)
    if not rollout_board_file.is_absolute():
        rollout_board_file = (WORKSPACE / rollout_board_file).resolve()

    readiness_config_path = Path(readiness_config)
    if not readiness_config_path.is_absolute():
        readiness_config_path = (WORKSPACE / readiness_config_path).resolve()
    readiness_rules_path = Path(readiness_rules)
    if not readiness_rules_path.is_absolute():
        readiness_rules_path = (WORKSPACE / readiness_rules_path).resolve()

    gov_path = Path(final_report_governance_path or DEFAULT_FINAL_REPORT_GOVERNANCE)
    if not gov_path.is_absolute():
        gov_path = (WORKSPACE / gov_path).resolve()
    fr_gov = load_final_report_governance(gov_path)

    workflow_run = _load_json(workflow_run_file)
    review_bundle = _load_json(review_bundle_file)
    release_manifest = _load_json(release_manifest_file)
    coverage = _load_json(coverage_file)
    verification = _load_json(verification_file)
    platform_readiness = run_readiness(case_id, readiness_config_path, readiness_rules_path)
    rollout_case_row = _load_rollout_case_row(rollout_board_file, case_id)
    assertions = _build_assertions(
        platform_readiness=platform_readiness,
        rollout_case_row=rollout_case_row,
        review_bundle=review_bundle,
        release_manifest=release_manifest,
        coverage=coverage,
        verification=verification,
        fr_gov=fr_gov,
    )
    promotion_semantics = _derive_promotion_semantics(
        review_bundle,
        release_manifest,
        rollout_case_row,
        fr_gov,
    )
    artifact_scope = fr_gov.get("artifact_acceptance_scope")
    if not isinstance(artifact_scope, str) or not str(artifact_scope).strip():
        artifact_scope = "case"
    else:
        artifact_scope = str(artifact_scope).strip()

    payload = {
        "_auto_generated": True,
        "_generator": "build_final_report.py",
        "schema_version": FINAL_REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "case_id": case_id,
        "acceptance_scope": artifact_scope,
        "contracts": {
            "workflow_run": {
                "path": _workspace_rel_or_abs(workflow_run_file),
                "present": workflow_run_file.is_file(),
            },
            "review_bundle": {
                "path": _workspace_rel_or_abs(review_bundle_file),
                "present": review_bundle_file.is_file(),
            },
            "release_manifest": {
                "path": _workspace_rel_or_abs(release_manifest_file),
                "present": release_manifest_file.is_file(),
            },
            "coverage_report": {
                "path": _workspace_rel_or_abs(coverage_file),
                "present": coverage_file.is_file(),
            },
            "verification_report": {
                "path": _workspace_rel_or_abs(verification_file),
                "present": verification_file.is_file(),
            },
            "final_report": {
                "path": _workspace_rel_or_abs(final_report_file),
                "present": True,
            },
        },
        "readiness": {
            "platform": normalize_serialized_paths(platform_readiness),
            "release_board": {
                "status": (rollout_case_row.get("release_gate") or {}).get("status"),
                "summary": (rollout_case_row.get("release_gate") or {}).get("summary"),
                "dimensions": rollout_case_row.get("dimensions") or {},
            },
        },
        "review": {
            "review_id": review_bundle.get("review_id"),
            "run_id": review_bundle.get("run_id"),
            "verdict": review_bundle.get("verdict"),
            "finding_count": len(review_bundle.get("findings") or []),
            "report_artifact_count": len(review_bundle.get("report_artifacts") or []),
        },
        "release": {
            "release_id": release_manifest.get("release_id"),
            "version": release_manifest.get("version"),
            "status": release_manifest.get("status"),
            "channel": release_manifest.get("channel"),
            "included_runs": release_manifest.get("included_runs") or [],
            "review_refs": release_manifest.get("review_refs") or [],
        },
        "business_metrics": {
            "outcomes_generated": coverage.get("outcomes_generated"),
            "total_executed": coverage.get("total_executed"),
            "normalized_outcome_coverage": coverage.get("outcome_coverage"),
            "schema_valid_count": coverage.get("schema_valid_count"),
            "evidence_bound_count": coverage.get("evidence_bound_count"),
            "verification_generated_at": verification.get("generated_at"),
        },
        "assertions": assertions,
        "assertion_summary": _assertion_summary(assertions),
        "overall_status": "pass" if all(item.get("passed") for item in assertions) else "attention_required",
        "governance": {
            "final_report_governance_path": _workspace_rel_or_abs(gov_path),
            "schema_version": fr_gov.get("schema_version"),
            "promotion_semantics": promotion_semantics,
        },
    }

    final_report_file.parent.mkdir(parents=True, exist_ok=True)
    final_report_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build final report contract for one case")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--workflow-run", default=None)
    parser.add_argument("--review-bundle", default=None)
    parser.add_argument("--release-manifest", default=None)
    parser.add_argument("--coverage-report", default=None)
    parser.add_argument("--verification-report", default=None)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    parser.add_argument("--rollout-board", default=None)
    parser.add_argument(
        "--governance",
        default=str(DEFAULT_FINAL_REPORT_GOVERNANCE),
        help="YAML: review verdict → semantic_lane + compatibility hints",
    )
    parser.add_argument("--output", default=None)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    payload = build_final_report(
        case_id=args.case_id,
        output_path=args.output,
        workflow_run_path=args.workflow_run,
        review_bundle_path=args.review_bundle,
        release_manifest_path=args.release_manifest,
        coverage_path=args.coverage_report,
        verification_path=args.verification_report,
        readiness_config=args.config,
        readiness_rules=args.rules,
        rollout_board_path=args.rollout_board,
        final_report_governance_path=args.governance,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
