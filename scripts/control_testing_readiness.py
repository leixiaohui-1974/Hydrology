#!/usr/bin/env python3
"""探源 (TanYuan) — Build a control-testing readiness contract for case-bound control lanes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _workspace_rel(path: Path, workspace: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def build_control_testing_readiness(case_id: str, workspace: Path) -> dict[str, Any] | None:
    contracts_dir = workspace / "cases" / case_id / "contracts"
    config_path = workspace / "Hydrology" / "configs" / f"{case_id}.yaml"
    station_topology_path = contracts_dir / "station_topology.latest.json"
    source_bundle_path = contracts_dir / "source_bundle.contract.json"
    source_import_session_path = contracts_dir / "source_import_session.latest.json"
    control_report_path = contracts_dir / "control_optimization_report.json"
    control_validation_path = contracts_dir / "control_validation.latest.json"
    sil_report_path = contracts_dir / "sil_verification_report.json"
    odd_report_path = contracts_dir / "odd_coverage_report.json"
    outlets_path = contracts_dir / "outlets.normalized.json"

    if not config_path.exists():
        return None
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    station_topology = _safe_load_json(station_topology_path)
    source_import_session = _safe_load_json(source_import_session_path)
    control_report = _safe_load_json(control_report_path)
    control_validation = _safe_load_json(control_validation_path)
    sil_report = _safe_load_json(sil_report_path)
    odd_report = _safe_load_json(odd_report_path)
    outlets = _safe_load_json(outlets_path)

    project_type = str(config.get("project_type") or "").strip()
    system_type = str(((config.get("topology") or {}).get("system_type")) or "").strip()
    station_count = int(((station_topology or {}).get("summary") or {}).get("station_count") or 0)
    outlet_count = int((outlets or {}).get("count") or 0) if isinstance(outlets, dict) else 0
    control_ready = str((control_report or {}).get("status") or "").strip().lower() == "ready"
    sil_ready = str((sil_report or {}).get("status") or "").strip().lower() == "ready"
    odd_present = isinstance(odd_report, dict) and bool(odd_report)

    ready_for = []
    if project_type == "cascade_hydro" and system_type == "pressurized_cascade" and station_count > 0 and control_ready:
        ready_for.extend(["pressurized_cascade_control", "mpc_scheduling"])
        if sil_ready and odd_present:
            ready_for.append("sil_odd_case_bound_testing")

    control_validation_control = (control_validation or {}).get("control") or {}
    control_validation_sil = (control_validation or {}).get("sil") or {}
    control_validation_strict = (control_validation or {}).get("strict_revalidation") or {}
    strict_revalidation_status = str(control_validation_strict.get("status") or "").strip().lower()
    traceability_checks = [
        ("missing_control_pass_rate", control_validation_control.get("pass_rate") is not None),
        ("missing_controller_backend", bool(control_validation_control.get("controller_backend"))),
        ("missing_physics_backend", bool(control_validation_control.get("physics_backend"))),
        ("missing_average_tracking_error", control_validation_control.get("average_tracking_error") is not None),
        ("missing_sil_pass_rate", control_validation_sil.get("pass_rate") is not None),
        ("missing_sil_scene_coverage", control_validation_sil.get("scene_coverage") is not None),
        (
            "missing_strict_revalidation_status",
            strict_revalidation_status not in {"", "missing", "none", "null", "unknown"},
        ),
    ]
    resolved_traceability_gaps = [gap for gap, present in traceability_checks if present]
    open_traceability_gaps = [gap for gap, present in traceability_checks if not present]
    if not ready_for:
        acceptance_signal = "insufficient_evidence"
    elif open_traceability_gaps and resolved_traceability_gaps:
        acceptance_signal = "provisional_pass_with_quantified_traceability_gaps"
    elif open_traceability_gaps:
        acceptance_signal = "provisional_pass_with_traceability_gaps"
    else:
        acceptance_signal = "provisional_pass_with_full_traceability"

    return {
        "case_id": case_id,
        "contract_type": "control_testing_readiness",
        "schema_version": "control_testing_readiness.v1",
        "generated_at": _now_iso(),
        "lane": "pressurized_cascade_control",
        "status": "ready_for_case_bound_control_testing" if ready_for else "insufficient_for_control_testing",
        "acceptance_scope": "case_bound_control_testing",
        "acceptance_signal": acceptance_signal,
        "source_contracts": {
            "config": _workspace_rel(config_path, workspace),
            "station_topology": _workspace_rel(station_topology_path, workspace) if station_topology_path.exists() else None,
            "source_import_session": _workspace_rel(source_import_session_path, workspace) if source_import_session_path.exists() else None,
            "control_optimization_report": _workspace_rel(control_report_path, workspace) if control_report_path.exists() else None,
            "control_validation_report": _workspace_rel(control_validation_path, workspace) if control_validation_path.exists() else None,
            "sil_verification_report": _workspace_rel(sil_report_path, workspace) if sil_report_path.exists() else None,
            "odd_coverage_report": _workspace_rel(odd_report_path, workspace) if odd_report_path.exists() else None,
            "outlets": _workspace_rel(outlets_path, workspace) if outlets_path.exists() else None,
        },
        "ready_for": ready_for,
        "not_ready_for": [
            "watershed_delineation",
            "authoritative_outlet_driven_data_pack",
        ],
        "waived_requirements": [
            {
                "requirement": "delineation_ready_outlets",
                "current_status": "outlets_empty" if outlet_count == 0 else "present",
                "reason": "yjdt control lane uses named cascade topology + scheme params, not outlet-grade watershed truth",
            }
        ],
        "evidence": {
            "project_type": project_type,
            "system_type": system_type,
            "station_count": station_count,
            "control_score": ((control_report or {}).get("metrics") or {}).get("control_score"),
            "scheduling_score": ((control_report or {}).get("metrics") or {}).get("scheduling_score"),
            "sil_score": ((sil_report or {}).get("metrics") or {}).get("sil_score"),
            "odd_scenarios_tested": ((odd_report or {}).get("coverage_metrics") or {}).get("total_scenarios_tested"),
            "source_mode": (source_import_session or {}).get("source_mode"),
            "control_pass_rate": control_validation_control.get("pass_rate"),
            "controller_backend": control_validation_control.get("controller_backend"),
            "physics_backend": control_validation_control.get("physics_backend"),
            "average_tracking_error": control_validation_control.get("average_tracking_error"),
            "sil_pass_rate": control_validation_sil.get("pass_rate"),
            "sil_scene_coverage": control_validation_sil.get("scene_coverage"),
            "strict_revalidation_status": control_validation_strict.get("status"),
            "strict_revalidation_control_pass_rate": control_validation_strict.get("control_pass_rate"),
        },
        "acceptance_basis": {
            "control_report_status": (control_report or {}).get("status"),
            "control_validation_status": (control_validation.get("summary") or {}).get("overall_status") if isinstance(control_validation, dict) else None,
            "sil_report_status": (sil_report or {}).get("status"),
            "odd_recovery_success_rate": ((odd_report or {}).get("coverage_metrics") or {}).get("recovery_success_rate"),
        },
        "waived_non_lane_failures": [
            {
                "failure": "outlets_empty",
                "reason": "case-bound control testing does not require authoritative outlet-driven delineation inputs",
            },
            {
                "failure": "autonomous_cascade_pipeline_partial",
                "reason": "calibration/delineation failures do not block pressurized cascade control-testing semantics",
            },
        ],
        "resolved_traceability_gaps": resolved_traceability_gaps,
        "open_traceability_gaps": open_traceability_gaps,
        "not_implied": [
            "authoritative_outlet_readiness",
            "watershed_delineation_readiness",
            "coordinate_grade_station_evidence",
        ],
        "guardrails": [
            "does_not_override_outlets_empty",
            "does_not_promote_proxy_candidates_to_outlets",
            "case_bound_control_semantics_only",
        ],
    }
