#!/usr/bin/env python3
"""基于现有 case-bound 证据导出 P1 三件套合同。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
_BASE = _SCRIPTS_DIR.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids
from workflows._shared import load_case_config  # noqa: E402


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
CONTROL_CASE_DIR = WORKSPACE / "pipedream-hydrology-integration-lab" / "hydromind_control_server" / "configs" / "cases"
CONTROL_CASE_ALIASES = {
    "yinchuojiliao": "yinchuo",
    "jiaodongtiaoshui": "jiaodong",
}
CONTRACT_FILENAMES = {
    "wnal_level_report": "wnal_level_report.json",
    "control_optimization_report": "control_optimization_report.json",
    "sil_verification_report": "sil_verification_report.json",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _workspace_rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE))
    except ValueError:
        return str(path.resolve())


def _case_contract_path(case_id: str, filename: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / filename


def _load_contract_json(case_id: str, filename: str) -> tuple[dict[str, Any], str | None]:
    path = _case_contract_path(case_id, filename)
    if not path.is_file():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, None
    if not isinstance(payload, dict):
        return {}, None
    return payload, _workspace_rel_or_abs(path)


def _write_contract_json(case_id: str, filename: str, payload: dict[str, Any]) -> str:
    path = _case_contract_path(case_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _workspace_rel_or_abs(path)


def _score_status(score: Any, ready_threshold: float, review_threshold: float = 0.01) -> str:
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return "blocked"
    if numeric >= ready_threshold:
        return "ready"
    if numeric >= review_threshold:
        return "review"
    return "blocked"


def _first_number(*values: Any) -> float | int | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _status_rank(status: str) -> int:
    order = {"ready": 0, "review": 1, "blocked": 2}
    return order.get(str(status or "").strip().lower(), 2)


def _merge_status(*statuses: Any) -> str:
    normalized = [
        str(status).strip().lower()
        for status in statuses
        if isinstance(status, str) and str(status).strip()
    ]
    if not normalized:
        return "blocked"
    return max(normalized, key=_status_rank)


def _level_from_score(score: Any) -> str:
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return "L0"
    if numeric >= 0.90:
        return "L5"
    if numeric >= 0.80:
        return "L4"
    if numeric >= 0.70:
        return "L3"
    if numeric >= 0.50:
        return "L2"
    if numeric > 0:
        return "L1"
    return "L0"


def _score_from_level(level: Any) -> float | None:
    normalized = str(level or "").strip().upper()
    if not normalized:
        return None
    mapping = {
        "L0": 0.0,
        "L1": 0.01,
        "L2": 0.50,
        "L3": 0.70,
        "L4": 0.80,
        "L5": 0.90,
    }
    return mapping.get(normalized)


def _control_case_slug(case_id: str) -> str:
    return CONTROL_CASE_ALIASES.get(case_id, case_id)


def _load_control_case_yaml(case_id: str) -> tuple[dict[str, Any], str | None]:
    path = CONTROL_CASE_DIR / f"{_control_case_slug(case_id)}.yaml"
    if not path.is_file():
        return {}, None
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}, None
    try:
        rel = str(path.resolve().relative_to(WORKSPACE))
    except ValueError:
        rel = str(path.resolve())
    return payload, rel


def _build_wnal_level_report(case_id: str) -> dict[str, Any]:
    try:
        case_cfg = load_case_config(case_id)
    except Exception:
        case_cfg = {"case_id": case_id}
    project_type = str(case_cfg.get("project_type") or "").strip().lower()
    d1d4_precision, d1d4_path = _load_contract_json(case_id, "d1d4_precision_report.latest.json")
    autonomy_assessment, autonomy_path = _load_contract_json(case_id, "autonomy_assessment.latest.json")
    control_case_cfg, control_case_path = _load_control_case_yaml(case_id)
    control_wnal = control_case_cfg.get("wnal") or {}

    autonomy_scores = autonomy_assessment.get("scores") or {}
    control_wnal_score = _first_number(control_wnal.get("current_score"))
    if isinstance(control_wnal_score, (int, float)) and float(control_wnal_score) > 1.0:
        control_wnal_score = float(control_wnal_score) / 5.0
    control_wnal_level = str(control_wnal.get("current_level") or "").strip().upper()
    if not isinstance(control_wnal_score, (int, float)):
        control_wnal_score = _score_from_level(control_wnal_level)

    if "canal" in project_type:
        wnal_score = _first_number(control_wnal_score, d1d4_precision.get("wnal_score"), autonomy_scores.get("wnal"))
        wnal_level = str(control_wnal_level or d1d4_precision.get("wnal_level") or _level_from_score(wnal_score))
        source_contracts = [path for path in [control_case_path, d1d4_path, autonomy_path] if path]
        fallback_used = not bool(control_case_path)
        primary_source = control_case_path or d1d4_path or autonomy_path
    else:
        wnal_score = _first_number(d1d4_precision.get("wnal_score"), autonomy_scores.get("wnal"))
        wnal_level = str(d1d4_precision.get("wnal_level") or _level_from_score(wnal_score))
        source_contracts = [path for path in [d1d4_path, autonomy_path] if path]
        fallback_used = not bool(d1d4_path)
        primary_source = d1d4_path or autonomy_path

    status = _score_status(wnal_score, ready_threshold=0.70, review_threshold=0.01)

    return {
        "case_id": case_id,
        "contract_type": "wnal_level_report",
        "schema_version": "0.1.0",
        "generated_at": _utc_now_iso(),
        "status": status,
        "summary": (
            f"WNAL {wnal_level} ({float(wnal_score):.2f})"
            if isinstance(wnal_score, (int, float))
            else "missing WNAL score"
        ),
        "source_contracts": source_contracts,
        "metrics": {
            "wnal_score": wnal_score,
            "wnal_level": wnal_level,
            "capability_score": d1d4_precision.get("capability_score"),
            "target_nse": d1d4_precision.get("target_nse"),
            "autonomy_wnal_score": autonomy_scores.get("wnal"),
            "d1_mean_val_nse": ((d1d4_precision.get("dimensions") or {}).get("d1") or {}).get("mean_val_nse"),
            "d1_station_count": ((d1d4_precision.get("dimensions") or {}).get("d1") or {}).get("stations_total"),
            "control_yaml_wnal_score": control_wnal_score,
            "control_yaml_wnal_level": control_wnal_level,
            "project_type": project_type,
        },
        "evidence": {
            "primary_source_contract": primary_source,
            "fallback_used": fallback_used,
            "overall_problems": d1d4_precision.get("overall_problems") or [],
            "overall_recommendations": d1d4_precision.get("overall_recommendations") or [],
        },
    }


def _build_control_optimization_report(case_id: str) -> dict[str, Any]:
    autonomy_assessment, autonomy_path = _load_contract_json(case_id, "autonomy_assessment.latest.json")
    odd_coverage, odd_path = _load_contract_json(case_id, "odd_coverage_report.json")
    control_validation, control_validation_path = _load_contract_json(case_id, "control_validation.latest.json")

    autonomy_scores = autonomy_assessment.get("scores") or {}
    control_score = _first_number(autonomy_scores.get("control"))
    scheduling_score = _first_number(autonomy_scores.get("scheduling"))
    control_pass_rate = _first_number(((control_validation.get("control") or {}).get("pass_rate")))
    recovery_success_rate = _first_number(((odd_coverage.get("coverage_metrics") or {}).get("recovery_success_rate")))
    scenarios_tested = int(_first_number(((odd_coverage.get("coverage_metrics") or {}).get("total_scenarios_tested")), 0) or 0)

    autonomy_status = _merge_status(
        _score_status(control_score, ready_threshold=0.65, review_threshold=0.01),
        _score_status(scheduling_score, ready_threshold=0.65, review_threshold=0.01),
    )
    evidence_status = "review" if isinstance(control_pass_rate, (int, float)) and float(control_pass_rate) < 1.0 else "ready"
    odd_status = "review" if isinstance(recovery_success_rate, (int, float)) and float(recovery_success_rate) < 1.0 else "ready"
    status = _merge_status(autonomy_status, evidence_status, odd_status)
    source_contracts = [path for path in [autonomy_path, control_validation_path, odd_path] if path]

    return {
        "case_id": case_id,
        "contract_type": "control_optimization_report",
        "schema_version": "0.1.0",
        "generated_at": _utc_now_iso(),
        "status": status,
        "summary": (
            f"control {float(control_score or 0):.2f} · scheduling {float(scheduling_score or 0):.2f}"
            if isinstance(control_score, (int, float)) or isinstance(scheduling_score, (int, float))
            else "missing control optimization evidence"
        ),
        "source_contracts": source_contracts,
        "metrics": {
            "control_score": control_score,
            "scheduling_score": scheduling_score,
            "control_pass_rate": control_pass_rate,
            "controller_backend": (control_validation.get("control") or {}).get("controller_backend"),
            "physics_backend": (control_validation.get("control") or {}).get("physics_backend"),
            "average_tracking_error": (control_validation.get("control") or {}).get("average_tracking_error"),
            "recovery_success_rate": recovery_success_rate,
            "scenarios_tested": scenarios_tested,
            "odd_score": autonomy_scores.get("odd"),
        },
        "evidence": {
            "control_validation_present": bool(control_validation_path),
            "recommended_actions": autonomy_assessment.get("recommended_actions") or [],
            "blockers": (control_validation.get("summary") or {}).get("blockers") or [],
        },
    }


def _build_sil_verification_report(case_id: str) -> dict[str, Any]:
    autonomy_assessment, autonomy_path = _load_contract_json(case_id, "autonomy_assessment.latest.json")
    odd_coverage, odd_path = _load_contract_json(case_id, "odd_coverage_report.json")
    control_validation, control_validation_path = _load_contract_json(case_id, "control_validation.latest.json")

    autonomy_scores = autonomy_assessment.get("scores") or {}
    sil_score = _first_number(autonomy_scores.get("sil"))
    sil_pass_rate = _first_number(((control_validation.get("sil") or {}).get("pass_rate")))
    scene_coverage = _first_number(((control_validation.get("sil") or {}).get("scene_coverage")))
    scenario_count = int(
        _first_number(
            ((control_validation.get("sil") or {}).get("scenario_count")),
            ((odd_coverage.get("coverage_metrics") or {}).get("total_scenarios_tested")),
            0,
        )
        or 0
    )
    odd_recovery = _first_number(((odd_coverage.get("coverage_metrics") or {}).get("recovery_success_rate")))
    autonomy_status = _score_status(sil_score, ready_threshold=0.65, review_threshold=0.01)
    coverage_status = "review" if isinstance(sil_pass_rate, (int, float)) and float(sil_pass_rate) < 1.0 else "ready"
    odd_status = "review" if isinstance(odd_recovery, (int, float)) and float(odd_recovery) < 1.0 else "ready"
    status = _merge_status(autonomy_status, coverage_status, odd_status)
    source_contracts = [path for path in [autonomy_path, control_validation_path, odd_path] if path]

    return {
        "case_id": case_id,
        "contract_type": "sil_verification_report",
        "schema_version": "0.1.0",
        "generated_at": _utc_now_iso(),
        "status": status,
        "summary": (
            f"SIL {float(sil_score or 0):.2f} · scenarios {scenario_count}"
            if isinstance(sil_score, (int, float))
            else "missing SIL score"
        ),
        "source_contracts": source_contracts,
        "metrics": {
            "sil_score": sil_score,
            "sil_pass_rate": sil_pass_rate,
            "scene_coverage": scene_coverage,
            "scenario_count": scenario_count,
            "passed_count": (control_validation.get("sil") or {}).get("passed_count"),
            "odd_recovery_success_rate": odd_recovery,
            "odd_score": autonomy_scores.get("odd"),
        },
        "evidence": {
            "control_validation_present": bool(control_validation_path),
            "strict_revalidation_status": (control_validation.get("strict_revalidation") or {}).get("status"),
            "recommended_actions": autonomy_assessment.get("recommended_actions") or [],
        },
    }


def export_case_contracts(case_id: str) -> dict[str, str]:
    payloads = {
        "wnal_level_report": _build_wnal_level_report(case_id),
        "control_optimization_report": _build_control_optimization_report(case_id),
        "sil_verification_report": _build_sil_verification_report(case_id),
    }
    written: dict[str, str] = {"case_id": case_id}
    for contract_key, filename in CONTRACT_FILENAMES.items():
        written[contract_key] = _write_contract_json(case_id, filename, payloads[contract_key])
    return written


def _resolve_cases(args: argparse.Namespace) -> list[str]:
    if args.cases:
        return list(args.cases)
    cfg_path = args.config if args.config.is_absolute() else WORKSPACE / args.config
    cfg = load_loop_yaml(WORKSPACE, cfg_path.resolve())
    return resolve_case_ids(cfg, WORKSPACE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export P1 contract triplet from existing case-bound evidence.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Loop config used to resolve default six cases.")
    parser.add_argument("--cases", nargs="+", help="Override case ids.")
    parser.add_argument("--stdout", action="store_true", help="Print JSON payload instead of only written paths.")
    args = parser.parse_args()

    results = [export_case_contracts(case_id) for case_id in _resolve_cases(args)]
    if args.stdout:
        print(json.dumps({"ok": True, "cases": results}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
