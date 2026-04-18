from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from common.program_contract_outputs import (
    default_governance_gates_ref_for_release,
    write_release_manifest_metadata,
    write_review_bundle_metadata,
    write_workflow_run_metadata,
)
from workflows._shared import WORKSPACE, load_json, write_json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (WORKSPACE / path).resolve()


def _workspace_rel_or_abs(path: Path, workspace_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(workspace_root)).replace("\\", "/")
    except ValueError:
        return str(resolved)


def _safe_load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _load_pipedream_contract_adapters_module() -> Any | None:
    module_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "contract_adapters.py"
    if not module_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("pipedream_contract_adapters", module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def _default_source_candidates(case_id: str, workspace_root: Path) -> dict[str, list[Path]]:
    module = _load_pipedream_contract_adapters_module()
    reports_root: Path | None = None
    internal_case_code = case_id
    if module is not None:
        try:
            spec = module.case_spec_for(case_id)
            reports_root = Path(spec.reports_root)
            internal_case_code = str(spec.internal_case_code)
        except Exception:
            reports_root = None

    if reports_root is None:
        reports_root = workspace_root / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id

    acceptance_root = workspace_root / "reports" / "acceptance"
    e2e_acceptance_root = workspace_root / "E2EControl" / "reports" / "acceptance"
    return {
        "pipeline_summary": [
            reports_root / f"{internal_case_code}_pipeline_summary.json",
            reports_root / "full_pipeline" / "pipeline_summary.json",
        ],
        "sil_results": [
            reports_root / "sil_results.json",
            reports_root / "full_pipeline" / "phase5_sil.json",
        ],
        "odd_results": [
            reports_root / "full_pipeline" / "phase6_odd.json",
            reports_root / "phase6_odd.json",
        ],
        "control_report": [
            acceptance_root / "control_effectiveness_analysis.json",
            e2e_acceptance_root / "control_effectiveness_analysis.json",
        ],
        "strict_revalidation": [
            acceptance_root / "strict_revalidation_summary.json",
            e2e_acceptance_root / "strict_revalidation_summary.json",
        ],
    }


def _first_existing(paths: list[Path], explicit: str | Path | None) -> Path | None:
    if explicit:
        candidate = _resolve_path(explicit)
        return candidate if candidate.is_file() else candidate
    for candidate in paths:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _artifact_ref(artifact_id: str, artifact_type: str, path: Path, workspace_root: Path, **metadata: Any) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "path": _workspace_rel_or_abs(path, workspace_root),
        "uri": None,
        "checksum": None,
        "metadata": metadata,
    }


def _artifact_type_for_path(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".json": "json",
        ".md": "md",
        ".html": "html",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".csv": "csv",
        ".txt": "text",
    }.get(suffix, "artifact")


def _normalize_artifact_list(
    items: Any,
    *,
    case_id: str,
    workspace_root: Path,
    owner: str,
    direction: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items or [], start=1):
        if isinstance(item, dict):
            normalized.append(item)
            continue
        if isinstance(item, str) and item.strip():
            raw_path = item.strip()
            resolved = Path(raw_path) if Path(raw_path).is_absolute() else (workspace_root / raw_path)
            normalized.append(
                _artifact_ref(
                    f"{case_id}:{owner}:{direction}:{index}",
                    _artifact_type_for_path(raw_path),
                    resolved,
                    workspace_root,
                    role=f"legacy_{direction}",
                    legacy_ref=True,
                )
            )
    return normalized


def _normalize_legacy_workflow_run_payload(
    payload: dict[str, Any],
    *,
    case_id: str,
    workspace_root: Path,
) -> dict[str, Any]:
    normalized = dict(payload or {})
    normalized["inputs"] = _normalize_artifact_list(
        normalized.get("inputs"),
        case_id=case_id,
        workspace_root=workspace_root,
        owner="workflow_run",
        direction="input",
    )
    normalized["outputs"] = _normalize_artifact_list(
        normalized.get("outputs"),
        case_id=case_id,
        workspace_root=workspace_root,
        owner="workflow_run",
        direction="output",
    )

    normalized_steps: list[dict[str, Any]] = []
    for step in normalized.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_payload = dict(step)
        step_id = str(step_payload.get("step_id") or "legacy_step")
        step_payload["inputs"] = _normalize_artifact_list(
            step_payload.get("inputs"),
            case_id=case_id,
            workspace_root=workspace_root,
            owner=step_id,
            direction="input",
        )
        step_payload["outputs"] = _normalize_artifact_list(
            step_payload.get("outputs"),
            case_id=case_id,
            workspace_root=workspace_root,
            owner=step_id,
            direction="output",
        )
        normalized_steps.append(step_payload)
    normalized["steps"] = normalized_steps
    return normalized


def _dedupe_by_key(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    ordered: list[str] = []
    for item in items:
        value = str(item.get(key) or "")
        if not value:
            continue
        if value not in seen:
            ordered.append(value)
        seen[value] = item
    return [seen[value] for value in ordered]


def _step_status(ok: bool | None, *, warning: bool = False) -> str:
    if ok is True and not warning:
        return "completed"
    if ok is True and warning:
        return "completed_with_findings"
    if ok is False:
        return "failed"
    return "missing"


def _merge_workflow_status(current: str, overall_status: str) -> str:
    normalized = str(current or "").strip() or "completed_with_review"
    if overall_status == "ready":
        return normalized
    if normalized in {"completed", "pass", "published", "released"}:
        return "completed_with_findings"
    return normalized


def _strict_revalidation_status(summary: dict[str, Any]) -> str:
    if not isinstance(summary, dict):
        return "missing"
    for key in ("overall_status", "quality_status"):
        value = str(summary.get(key) or "").strip().lower()
        if value:
            return value
    quality_gate = summary.get("quality_gate")
    if isinstance(quality_gate, dict):
        value = str(quality_gate.get("status") or "").strip().lower()
        if value:
            return value
    if summary.get("quality_gate_passed") is True:
        return "passed"
    if summary.get("quality_gate_passed") is False:
        return "failed"
    return "missing"


def _build_control_validation_payload(
    *,
    case_id: str,
    workspace_root: Path,
    pipeline_summary_path: Path | None,
    sil_results_path: Path | None,
    odd_results_path: Path | None,
    control_report_path: Path | None,
    strict_revalidation_path: Path | None,
) -> dict[str, Any]:
    pipeline_summary = _safe_load_json(pipeline_summary_path) if pipeline_summary_path else {}
    sil_results = _safe_load_json(sil_results_path) if sil_results_path else {}
    odd_results = _safe_load_json(odd_results_path) if odd_results_path else {}
    control_report = _safe_load_json(control_report_path) if control_report_path else {}
    strict_revalidation = _safe_load_json(strict_revalidation_path) if strict_revalidation_path else {}

    control_metrics = control_report.get("report") or control_report.get("summary") or {}
    control_total = int(control_metrics.get("total_tests") or 0)
    control_passed = int(control_metrics.get("passed_tests") or 0)
    control_pass_rate = (
        float(control_metrics.get("pass_rate"))
        if control_metrics.get("pass_rate") is not None
        else (control_passed / control_total if control_total else None)
    )

    sil_pass_rate = float(
        sil_results.get("pass_rate")
        if sil_results.get("pass_rate") is not None
        else ((pipeline_summary.get("sil_verification") or {}).get("pass_rate") or 0.0)
    )
    sil_scenarios = int(
        sil_results.get("n_scenarios")
        if sil_results.get("n_scenarios") is not None
        else ((pipeline_summary.get("sil_verification") or {}).get("n_scenarios") or 0)
    )
    sil_passed = int(
        sil_results.get("n_passed")
        if sil_results.get("n_passed") is not None
        else round(sil_pass_rate * sil_scenarios)
    )
    odd_validated = bool(
        odd_results.get("validated_in_simulation")
        if odd_results
        else ((pipeline_summary.get("odd_validation") or {}).get("validated_in_simulation"))
    )
    odd_match_rate = float(
        odd_results.get("odd_validation_match")
        if odd_results.get("odd_validation_match") is not None
        else (1.0 if odd_validated else 0.0)
    )
    odd_transition_count = int(
        len(odd_results.get("fsm_transitions") or [])
        if odd_results.get("fsm_transitions") is not None
        else ((pipeline_summary.get("odd_validation") or {}).get("n_transitions") or 0)
    )
    strict_status = _strict_revalidation_status(strict_revalidation)

    blockers: list[str] = []
    if pipeline_summary_path is None or not pipeline_summary_path.is_file():
        blockers.append("缺少 pipedream pipeline_summary")
    if sil_pass_rate < 1.0:
        blockers.append(f"SIL 通过率不足 100%（当前 {sil_pass_rate:.0%}）")
    if not odd_validated:
        blockers.append("ODD 未通过 validated_in_simulation")
    if strict_status not in {"passed", "success", "ok", "missing"}:
        blockers.append(f"strict_revalidation 状态为 {strict_status}")
    if control_pass_rate is not None and control_pass_rate < 1.0:
        blockers.append(f"控制有效性通过率不足 100%（当前 {control_pass_rate:.0%}）")

    overall_status = "ready" if not blockers else "attention_required"
    review_verdict = "pass" if overall_status == "ready" else "pass_with_comments"

    return {
        "case_id": case_id,
        "generated_at": utc_now_iso(),
        "sources": {
            "pipeline_summary": _workspace_rel_or_abs(pipeline_summary_path, workspace_root)
            if pipeline_summary_path and pipeline_summary_path.is_file()
            else "",
            "sil_results": _workspace_rel_or_abs(sil_results_path, workspace_root)
            if sil_results_path and sil_results_path.is_file()
            else "",
            "odd_results": _workspace_rel_or_abs(odd_results_path, workspace_root)
            if odd_results_path and odd_results_path.is_file()
            else "",
            "control_report": _workspace_rel_or_abs(control_report_path, workspace_root)
            if control_report_path and control_report_path.is_file()
            else "",
            "strict_revalidation": _workspace_rel_or_abs(strict_revalidation_path, workspace_root)
            if strict_revalidation_path and strict_revalidation_path.is_file()
            else "",
        },
        "control": {
            "status": "pass" if control_pass_rate in (None, 1.0) else "warning",
            "controller_backend": control_metrics.get("controller_backend") or "unknown",
            "physics_backend": control_metrics.get("physics_backend") or "unknown",
            "total_tests": control_total,
            "passed_tests": control_passed,
            "failed_tests": int(control_metrics.get("failed_tests") or 0),
            "pass_rate": control_pass_rate,
            "average_tracking_error": control_metrics.get("average_tracking_error"),
        },
        "sil": {
            "status": "pass" if sil_pass_rate >= 1.0 else "warning",
            "pass_rate": sil_pass_rate,
            "scenario_count": sil_scenarios,
            "passed_count": sil_passed,
            "scene_coverage": sil_results.get("scene_coverage"),
        },
        "odd": {
            "status": "validated" if odd_validated else "failed",
            "validated_in_simulation": odd_validated,
            "scenario_count": int(
                odd_results.get("n_scenarios_passed")
                if odd_results.get("n_scenarios_passed") is not None
                else ((pipeline_summary.get("odd_validation") or {}).get("n_scenarios") or 0)
            ),
            "boundary_condition_count": int(
                odd_results.get("n_boundary_conditions")
                if odd_results.get("n_boundary_conditions") is not None
                else ((pipeline_summary.get("odd_validation") or {}).get("n_boundary_conditions") or 0)
            ),
            "match_rate": odd_match_rate,
            "transition_count": odd_transition_count,
        },
        "strict_revalidation": {
            "status": strict_status,
            "control_pass_rate": (((strict_revalidation.get("modules") or {}).get("control") or {}).get("pass_rate")),
            "failed_tests": (((strict_revalidation.get("modules") or {}).get("control") or {}).get("failed_tests")),
        },
        "summary": {
            "overall_status": overall_status,
            "review_verdict": review_verdict,
            "blockers": blockers,
            "source_count": sum(1 for value in (
                pipeline_summary_path,
                sil_results_path,
                odd_results_path,
                control_report_path,
                strict_revalidation_path,
            ) if value and value.is_file()),
        },
        "schema_version": "0.1.0",
    }


def _control_source_artifacts(
    *,
    case_id: str,
    workspace_root: Path,
    control_validation_path: Path,
    pipeline_summary_path: Path | None,
    sil_results_path: Path | None,
    odd_results_path: Path | None,
    control_report_path: Path | None,
    strict_revalidation_path: Path | None,
) -> list[dict[str, Any]]:
    artifacts = [
        _artifact_ref(
            f"{case_id}:control-validation",
            "control_validation_summary",
            control_validation_path,
            workspace_root,
            role="control_validation_summary",
        )
    ]
    if pipeline_summary_path and pipeline_summary_path.is_file():
        artifacts.append(
            _artifact_ref(
                f"{case_id}:pipedream-pipeline-summary",
                "pipeline_summary_json",
                pipeline_summary_path,
                workspace_root,
                role="pipedream_pipeline_summary",
            )
        )
    if sil_results_path and sil_results_path.is_file():
        artifacts.append(
            _artifact_ref(
                f"{case_id}:sil-results",
                "sil_results_json",
                sil_results_path,
                workspace_root,
                role="sil_results",
            )
        )
    if odd_results_path and odd_results_path.is_file():
        artifacts.append(
            _artifact_ref(
                f"{case_id}:odd-results",
                "odd_results_json",
                odd_results_path,
                workspace_root,
                role="odd_results",
            )
        )
    if control_report_path and control_report_path.is_file():
        artifacts.append(
            _artifact_ref(
                f"{case_id}:control-effectiveness",
                "control_effectiveness_report_json",
                control_report_path,
                workspace_root,
                role="control_effectiveness_report",
            )
        )
    if strict_revalidation_path and strict_revalidation_path.is_file():
        artifacts.append(
            _artifact_ref(
                f"{case_id}:strict-revalidation",
                "strict_revalidation_report_json",
                strict_revalidation_path,
                workspace_root,
                role="strict_revalidation_report",
            )
        )
    return artifacts


def sync_control_review_contracts(
    *,
    case_id: str,
    case_root: str | Path | None = None,
    workspace_root: str | Path | None = None,
    pipeline_summary_path: str | Path | None = None,
    sil_results_path: str | Path | None = None,
    odd_results_path: str | Path | None = None,
    control_report_path: str | Path | None = None,
    strict_revalidation_path: str | Path | None = None,
    release_version: str = "v0.1.0-control",
) -> dict[str, str]:
    workspace = _resolve_path(workspace_root) if workspace_root else WORKSPACE
    root = _resolve_path(case_root) if case_root else workspace / "cases" / case_id
    contracts_dir = root / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    candidates = _default_source_candidates(case_id, workspace)
    pipeline_summary = _first_existing(candidates["pipeline_summary"], pipeline_summary_path)
    sil_results = _first_existing(candidates["sil_results"], sil_results_path)
    odd_results = _first_existing(candidates["odd_results"], odd_results_path)
    control_report = _first_existing(candidates["control_report"], control_report_path)
    strict_revalidation = _first_existing(candidates["strict_revalidation"], strict_revalidation_path)

    control_validation_path = contracts_dir / "control_validation.latest.json"
    control_validation = _build_control_validation_payload(
        case_id=case_id,
        workspace_root=workspace,
        pipeline_summary_path=pipeline_summary,
        sil_results_path=sil_results,
        odd_results_path=odd_results,
        control_report_path=control_report,
        strict_revalidation_path=strict_revalidation,
    )
    write_json(control_validation_path, control_validation)

    source_artifacts = _control_source_artifacts(
        case_id=case_id,
        workspace_root=workspace,
        control_validation_path=control_validation_path,
        pipeline_summary_path=pipeline_summary,
        sil_results_path=sil_results,
        odd_results_path=odd_results,
        control_report_path=control_report,
        strict_revalidation_path=strict_revalidation,
    )

    workflow_run_path = contracts_dir / "workflow_run.json"
    workflow_run = _normalize_legacy_workflow_run_payload(
        _safe_load_json(workflow_run_path),
        case_id=case_id,
        workspace_root=workspace,
    )
    workflow_run["run_id"] = f"{case_id}-control-review"
    workflow_run["case_id"] = case_id
    workflow_run["workflow_type"] = "control_review_pipeline"
    workflow_run["status"] = _merge_workflow_status(
        str(workflow_run.get("status") or ""),
        str((control_validation.get("summary") or {}).get("overall_status") or ""),
    )
    workflow_run.setdefault("inputs", [])
    workflow_run["outputs"] = _dedupe_by_key(
        list(workflow_run.get("outputs") or []) + source_artifacts,
        "path",
    )
    workflow_run.setdefault("steps", [])
    workflow_run["steps"] = _dedupe_by_key(
        list(workflow_run.get("steps") or [])
        + [
            {
                "step_id": "control_execution",
                "status": _step_status(control_report is not None and control_report.is_file(), warning=((control_validation["control"].get("pass_rate") or 1.0) < 1.0)),
                "inputs": [],
                "outputs": [_artifact_ref(f"{case_id}:control-effectiveness", "control_effectiveness_report_json", control_report, workspace, role="control_effectiveness_report")] if control_report and control_report.is_file() else [],
                "started_at": None,
                "completed_at": control_validation["generated_at"],
                "metadata": control_validation["control"],
            },
            {
                "step_id": "sil_verification",
                "status": _step_status(sil_results is not None and sil_results.is_file(), warning=control_validation["sil"]["status"] != "pass"),
                "inputs": [],
                "outputs": [_artifact_ref(f"{case_id}:sil-results", "sil_results_json", sil_results, workspace, role="sil_results")] if sil_results and sil_results.is_file() else [],
                "started_at": None,
                "completed_at": control_validation["generated_at"],
                "metadata": control_validation["sil"],
            },
            {
                "step_id": "odd_validation",
                "status": _step_status(control_validation["odd"]["validated_in_simulation"], warning=control_validation["odd"]["status"] != "validated"),
                "inputs": [],
                "outputs": [_artifact_ref(f"{case_id}:odd-results", "odd_results_json", odd_results, workspace, role="odd_results")] if odd_results and odd_results.is_file() else [],
                "started_at": None,
                "completed_at": control_validation["generated_at"],
                "metadata": control_validation["odd"],
            },
            {
                "step_id": "strict_revalidation",
                "status": _step_status(strict_revalidation is not None and strict_revalidation.is_file(), warning=control_validation["strict_revalidation"]["status"] not in {"missing", "passed", "success", "ok"}),
                "inputs": [],
                "outputs": [_artifact_ref(f"{case_id}:strict-revalidation", "strict_revalidation_report_json", strict_revalidation, workspace, role="strict_revalidation_report")] if strict_revalidation and strict_revalidation.is_file() else [],
                "started_at": None,
                "completed_at": control_validation["generated_at"],
                "metadata": control_validation["strict_revalidation"],
            },
        ],
        "step_id",
    )
    workflow_run.setdefault("metadata", {})
    workflow_run["metadata"]["control_validation"] = control_validation["summary"]
    workflow_run["metadata"]["control_validation_paths"] = control_validation["sources"]
    workflow_run.setdefault("schema_version", "0.1.0")
    write_workflow_run_metadata(workflow_run_path, workflow_run)

    review_bundle_path = contracts_dir / "review_bundle.json"
    review_bundle = _safe_load_json(review_bundle_path)
    review_bundle["review_id"] = f"review-{case_id}-control"
    review_bundle["run_id"] = str(workflow_run.get("run_id") or f"{case_id}-control-review")
    review_bundle["case_id"] = case_id
    review_bundle["verdict"] = control_validation["summary"]["review_verdict"]
    review_bundle.setdefault("findings", [])
    review_findings = list(review_bundle.get("findings") or [])
    if control_validation["sil"]["status"] != "pass":
        review_findings.append(
            {
                "finding_id": f"{case_id}:sil:coverage",
                "severity": "medium",
                "summary": f"SIL 通过率为 {control_validation['sil']['pass_rate']:.0%}",
                "artifact_refs": [
                    _artifact_ref(f"{case_id}:control-validation", "control_validation_summary", control_validation_path, workspace, role="control_validation_summary")
                ],
                "metadata": {"section": "sil"},
            }
        )
    if control_validation["odd"]["status"] != "validated":
        review_findings.append(
            {
                "finding_id": f"{case_id}:odd:validation",
                "severity": "high",
                "summary": "ODD validated_in_simulation 为 false",
                "artifact_refs": [
                    _artifact_ref(f"{case_id}:control-validation", "control_validation_summary", control_validation_path, workspace, role="control_validation_summary")
                ],
                "metadata": {"section": "odd"},
            }
        )
    if control_validation["strict_revalidation"]["status"] not in {"missing", "passed", "success", "ok"}:
        review_findings.append(
            {
                "finding_id": f"{case_id}:strict:status",
                "severity": "medium",
                "summary": f"strict_revalidation 状态为 {control_validation['strict_revalidation']['status']}",
                "artifact_refs": [
                    _artifact_ref(f"{case_id}:control-validation", "control_validation_summary", control_validation_path, workspace, role="control_validation_summary")
                ],
                "metadata": {"section": "strict_revalidation"},
            }
        )
    review_bundle["findings"] = _dedupe_by_key(review_findings, "finding_id")
    review_bundle.setdefault("report_artifacts", [])
    review_bundle["report_artifacts"] = _dedupe_by_key(
        list(review_bundle.get("report_artifacts") or [])
        + [
            _artifact_ref(
                f"{case_id}:control-validation",
                "control_validation_summary",
                control_validation_path,
                workspace,
                role="control_validation_summary",
            )
        ],
        "path",
    )
    review_bundle.setdefault("metadata", {})
    review_bundle["metadata"]["control_validation"] = control_validation["summary"]
    review_bundle["metadata"]["control_validation_paths"] = control_validation["sources"]
    review_bundle.setdefault("schema_version", "0.1.0")
    write_review_bundle_metadata(review_bundle_path, review_bundle)

    release_manifest_path = contracts_dir / "release_manifest.json"
    release_manifest = _safe_load_json(release_manifest_path)
    release_manifest["release_id"] = f"release-{case_id}-{release_version}"
    release_manifest["case_id"] = case_id
    release_manifest["version"] = release_version
    release_manifest.setdefault("channel", "staging")
    release_manifest.setdefault("status", "published")
    release_manifest["included_runs"] = [str(workflow_run.get("run_id") or f"{case_id}-control-review")]
    release_manifest["review_refs"] = [str(review_bundle.get("review_id") or f"review-{case_id}-control")]
    release_manifest.setdefault("artifacts", [])
    release_manifest["artifacts"] = _dedupe_by_key(
        list(release_manifest.get("artifacts") or []) + source_artifacts,
        "path",
    )
    release_manifest.setdefault("metadata", {})
    release_manifest["metadata"]["control_validation"] = control_validation["summary"]
    release_manifest["metadata"]["control_validation_paths"] = control_validation["sources"]
    release_manifest.setdefault("schema_version", "0.1.0")
    release_manifest.setdefault("governance_gates", default_governance_gates_ref_for_release())
    write_release_manifest_metadata(release_manifest_path, release_manifest)

    return {
        "case_id": case_id,
        "control_validation": str(control_validation_path),
        "workflow_run": str(workflow_run_path),
        "review_bundle": str(review_bundle_path),
        "release_manifest": str(release_manifest_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unify control/SIL/ODD outputs into canonical case contracts.")
    parser.add_argument("--case-id", required=True, help="Case identifier")
    parser.add_argument("--case-root", default=None, help="Override case root directory")
    parser.add_argument("--workspace-root", default=None, help="Override workspace root")
    parser.add_argument("--pipeline-summary", default=None, help="Override pipedream pipeline summary path")
    parser.add_argument("--sil-results", default=None, help="Override SIL results path")
    parser.add_argument("--odd-results", default=None, help="Override ODD results path")
    parser.add_argument("--control-report", default=None, help="Override E2EControl control effectiveness report path")
    parser.add_argument("--strict-revalidation", default=None, help="Override strict revalidation summary path")
    parser.add_argument("--release-version", default="v0.1.0-control", help="Release manifest version tag")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    payload = sync_control_review_contracts(
        case_id=args.case_id,
        case_root=args.case_root,
        workspace_root=args.workspace_root,
        pipeline_summary_path=args.pipeline_summary,
        sil_results_path=args.sil_results,
        odd_results_path=args.odd_results,
        control_report_path=args.control_report,
        strict_revalidation_path=args.strict_revalidation,
        release_version=args.release_version,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
