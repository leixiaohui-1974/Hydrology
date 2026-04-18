#!/usr/bin/env python3
"""批量导出六案例 readiness / release 聚合视图（单 JSON 快照，供 CI / HydroDesk 对比）。"""
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

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402
from workflows._shared import load_case_config  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
DEFAULT_GOVERNANCE_CONFIG = WORKSPACE / "Hydrology" / "configs" / "release_readiness_governance.yaml"
DEFAULT_OUT = WORKSPACE / "cases" / "rollout_readiness_baseline.latest.json"
READINESS_RELEASE_SCHEMA_VERSION = "six_case_readiness_release.v1"
REQUIRED_PARAMETER_STAGES = (
    "watershed_delineation",
    "hydrology",
    "hydraulics",
    "coupling",
    "assimilation",
    "identification",
    "scheduling_control",
    "sil_odd",
)
DIMENSION_CATALOG = [
    {
        "key": "data_preparedness",
        "label": "数据准备度",
        "description": "是否存在可消费的 source import session 证据。",
        "source_contracts": ["source_import_session.latest.json"],
    },
    {
        "key": "modeling_readiness",
        "label": "建模准备度",
        "description": "优先基于 case-bound pipeline_evaluation，缺失时回退 autonomy assessment。",
        "source_contracts": [
            "pipeline_evaluation.latest.json",
            "rollout_minimal_loop.latest.json",
            "autonomy_assessment.latest.json",
        ],
    },
    {
        "key": "parameter_governance",
        "label": "参数治理完整度",
        "description": "八阶段 parameter governance 是否齐备。",
        "source_contracts": ["parameter_governance.latest.json"],
    },
    {
        "key": "assimilation_readiness",
        "label": "同化可用性",
        "description": "parameter governance 中是否存在可用 assimilation stage。",
        "source_contracts": ["parameter_governance.latest.json"],
    },
    {
        "key": "control_sil_odd",
        "label": "控制 / SIL / ODD",
        "description": "优先消费 control / SIL 新合同，缺失时回退 autonomy 与 odd 覆盖报告。",
        "source_contracts": [
            "control_optimization_report.json",
            "sil_verification_report.json",
            "autonomy_assessment.latest.json",
            "odd_coverage_report.json",
        ],
    },
    {
        "key": "wnal",
        "label": "WNAL 等级",
        "description": "优先消费 wnal_level_report，缺失时回退 d1d4 precision report 与 autonomy assessment。",
        "source_contracts": [
            "wnal_level_report.json",
            "d1d4_precision_report.latest.json",
            "autonomy_assessment.latest.json",
        ],
    },
    {
        "key": "e2e_gate",
        "label": "E2E Gate",
        "description": "综合 outcome coverage gate 与 zero hardcoding gate。",
        "source_contracts": ["outcome_coverage_report.latest.json", "e2e_outcome_verification_report.json"],
    },
    {
        "key": "autonomy_quality",
        "label": "自主性总评",
        "description": "采用最新 autonomy contract（assessment / autorun）的总体 verdict 作为主判据。",
        "source_contracts": ["autonomy_assessment.latest.json", "autonomy_autorun.latest.json"],
    },
]
ACTION_HINTS = {
    "data_preparedness": "补跑 source import / source bundle 导入，确保 source_import_session.latest.json 具备有效记录。",
    "modeling_readiness": "优先提升 simulation 维度表现，再重新评估 readiness / release gate。",
    "parameter_governance": "重新生成 parameter_governance.latest.json，补齐 8-stage stage_catalog 与参数清单。",
    "assimilation_readiness": "补齐 assimilation stage 参数治理定义，确保同化阶段可被产品统一读取。",
    "control_sil_odd": "补充控制 / SIL / ODD 证据并提升相关分值后，再重新跑 release 聚合。",
    "wnal": "补齐 D1-D4 与 WNAL 相关能力证据，先把 WNAL 从 0 提升到可评估状态。",
    "e2e_gate": "修复 E2E gate 风险并重跑 outcome verification，优先清理 hardcoding / lint 类问题。",
    "autonomy_quality": "按 autonomy_assessment 的 weak_dimensions 优先整改，再重新生成 autonomy contract。",
}


def _workspace_rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE))
    except ValueError:
        return str(path.resolve())


def _load_contract_json(case_id: str, filename: str) -> tuple[dict[str, Any], str | None]:
    path = WORKSPACE / "cases" / case_id / "contracts" / filename
    if not path.is_file():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, None
    if not isinstance(payload, dict):
        return {}, None
    return payload, _workspace_rel_or_abs(path)


def _json_pointer(payload: dict[str, Any], pointer: str) -> Any:
    current: Any = payload
    for token in [part for part in pointer.strip("/").split("/") if part]:
        if not isinstance(current, dict):
            return None
        current = current.get(token)
    return current


def _unique_strings(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _merge_statuses(*statuses: str) -> str:
    order = {"ready": 0, "review": 1, "blocked": 2}
    normalized = [str(status).strip().lower() for status in statuses if str(status).strip()]
    if not normalized:
        return "blocked"
    return max(normalized, key=lambda item: order.get(item, 2))


def _build_dimension(
    *,
    key: str,
    label: str,
    status: str,
    summary: str,
    source_contracts: list[str],
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "summary": summary,
        "source_contracts": source_contracts,
        "metrics": metrics or {},
    }


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


def _wnal_status_merge_contract_vs_score(
    *,
    wnal_level_report: dict[str, Any],
    wnal_score: Any,
    ready_threshold: float,
    review_threshold: float,
) -> str:
    """WNAL 合同里的 status 不能单独宣称 ready：须与分数推导的 score_status 一致，否则采用较差侧。"""
    score_status = _score_status(wnal_score, ready_threshold, review_threshold)
    file_status = str(wnal_level_report.get("status") or "").strip().lower()
    if not file_status:
        return score_status
    if file_status == "ready":
        return score_status
    return _merge_statuses(file_status, score_status)


def _wnal_summary_merge_contract_vs_score(
    *,
    wnal_level_report: dict[str, Any],
    wnal_score: Any,
    resolved_status: str,
) -> str:
    contract_summary = str(wnal_level_report.get("summary") or "").strip()
    if isinstance(wnal_score, (int, float)) and float(wnal_score) <= 0:
        return f"WNAL score {float(wnal_score):.2f} — governance evidence not satisfied"
    if contract_summary and resolved_status == str(wnal_level_report.get("status") or "").strip().lower():
        return contract_summary
    if isinstance(wnal_score, (int, float)):
        return f"WNAL score {float(wnal_score):.2f}"
    if contract_summary:
        return contract_summary
    return "missing WNAL score"


def load_release_readiness_governance(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"release readiness governance config not found: {resolved}")
    data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("release_readiness_governance root must be a mapping")
    return data


_GOVERNANCE_CACHE: dict[str, Any] | None = None
_GOVERNANCE_CACHE_KEY: str | None = None


def _cached_governance(path: Path) -> dict[str, Any]:
    global _GOVERNANCE_CACHE, _GOVERNANCE_CACHE_KEY
    key = str(path.resolve())
    if _GOVERNANCE_CACHE is not None and _GOVERNANCE_CACHE_KEY == key:
        return _GOVERNANCE_CACHE
    _GOVERNANCE_CACHE = load_release_readiness_governance(path)
    _GOVERNANCE_CACHE_KEY = key
    return _GOVERNANCE_CACHE


def _greenfield_cascade_lane_gates_met(
    project_type: str,
    *,
    rollout_ready: bool,
    pipeline_case_id: str,
    case_id: str,
    normalized_coverage: float | None,
    station_count: int | None,
    mean_nse: float | None,
    lane_cfg: dict[str, Any],
) -> bool:
    if not lane_cfg or not lane_cfg.get("enabled", True):
        return False
    types = {str(t).strip().lower() for t in (lane_cfg.get("project_types") or []) if str(t).strip()}
    if not types or project_type not in types:
        return False
    if lane_cfg.get("require_rollout_ready", True) and not rollout_ready:
        return False
    if lane_cfg.get("require_pipeline_case_id_match", True) and pipeline_case_id != case_id:
        return False
    min_cov = float(lane_cfg["min_pipeline_coverage_ratio"])
    if not isinstance(normalized_coverage, (int, float)):
        return False
    if float(normalized_coverage) < min_cov:
        return False
    if lane_cfg.get("require_station_count_zero", True):
        if station_count is None or int(station_count) != 0:
            return False
    max_nse = lane_cfg.get("max_mean_nse")
    if max_nse is not None:
        if not isinstance(mean_nse, (int, float)):
            return False
        if float(mean_nse) > float(max_nse):
            return False
    return True


def _canal_lane_gates_met(
    project_type: str,
    *,
    rollout_ready: bool,
    pipeline_case_id: str,
    case_id: str,
    normalized_coverage: float | None,
    lane_cfg: dict[str, Any],
) -> bool:
    if not lane_cfg.get("promote_modeling_to_ready_when_gates_pass"):
        return False
    markers = [str(m).strip().lower() for m in (lane_cfg.get("project_type_substrings") or []) if str(m).strip()]
    if not markers or not any(m in project_type for m in markers):
        return False
    if lane_cfg.get("require_rollout_ready", True) and not rollout_ready:
        return False
    if lane_cfg.get("require_pipeline_case_id_match", True) and pipeline_case_id != case_id:
        return False
    min_cov = float(lane_cfg["min_pipeline_coverage_ratio"])
    if not isinstance(normalized_coverage, (int, float)):
        return False
    return float(normalized_coverage) >= min_cov


def _stage_catalog_stats(parameter_governance: dict[str, Any]) -> tuple[int, int, int]:
    stage_catalog = parameter_governance.get("stage_catalog") or {}
    ready_stages = 0
    total_parameters = 0
    for stage_key in REQUIRED_PARAMETER_STAGES:
        stage_payload = stage_catalog.get(stage_key) or {}
        parameter_count = int(stage_payload.get("parameter_count") or 0)
        total_parameters += parameter_count
        if parameter_count > 0:
            ready_stages += 1
    return ready_stages, len(REQUIRED_PARAMETER_STAGES), total_parameters


def _contract_generated_at(payload: dict[str, Any]) -> str:
    value = payload.get("generated_at")
    return str(value).strip() if isinstance(value, str) else ""


def _prefer_newer_contract(
    primary_payload: dict[str, Any],
    primary_path: str | None,
    fallback_payload: dict[str, Any],
    fallback_path: str | None,
) -> tuple[dict[str, Any], str | None]:
    if not primary_payload:
        return fallback_payload, fallback_path
    if not fallback_payload:
        return primary_payload, primary_path
    if _contract_generated_at(primary_payload) >= _contract_generated_at(fallback_payload):
        return primary_payload, primary_path
    return fallback_payload, fallback_path


def _import_chain_rollup(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_case: list[dict] = []
    imported_count = 0
    latest_imported_at: str | None = None

    for row in case_rows:
        metrics = ((row.get("dimensions") or {}).get("data_preparedness") or {}).get("metrics") or {}
        present = bool(metrics.get("present"))
        imported_at = metrics.get("imported_at")
        if present:
            imported_count += 1
            if imported_at and (latest_imported_at is None or str(imported_at) > str(latest_imported_at)):
                latest_imported_at = str(imported_at)
        per_case.append(
            {
                "case_id": row.get("case_id"),
                "present": present,
                "source": metrics.get("source_contracts", [None])[0],
                "mode": metrics.get("source_mode"),
                "imported_at": imported_at,
                "path": metrics.get("path"),
            }
        )

    total = len(case_rows)
    missing_case_ids = [str(item["case_id"]) for item in per_case if not item["present"]]
    ready_case_ids = [str(item["case_id"]) for item in per_case if item["present"]]
    ready = imported_count == total and total > 0
    status = "ready" if ready else "pending"
    reason = "all_cases_imported" if ready else f"missing_import_session:{','.join(missing_case_ids)}"
    return {
        "case_count": total,
        "imported_case_count": imported_count,
        "missing_case_count": total - imported_count,
        "coverage_ratio": (imported_count / total) if total else 0.0,
        "ready": ready,
        "status": status,
        "reason": reason,
        "ready_case_ids": ready_case_ids,
        "missing_case_ids": missing_case_ids,
        "latest_imported_at": latest_imported_at,
        "per_case": per_case,
    }


def _build_case_dimensions(case_id: str, governance: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    gov = governance if governance is not None else _cached_governance(DEFAULT_GOVERNANCE_CONFIG)
    try:
        case_cfg = load_case_config(case_id)
    except Exception:
        case_cfg = {"case_id": case_id}
    project_type = str(case_cfg.get("project_type") or "").strip().lower()
    source_import_session, source_import_path = _load_contract_json(case_id, "source_import_session.latest.json")
    parameter_governance, parameter_governance_path = _load_contract_json(case_id, "parameter_governance.latest.json")
    autonomy_assessment, autonomy_assessment_path = _load_contract_json(case_id, "autonomy_assessment.latest.json")
    autonomy_autorun, autonomy_autorun_path = _load_contract_json(case_id, "autonomy_autorun.latest.json")
    outcome_coverage, outcome_coverage_path = _load_contract_json(case_id, "outcome_coverage_report.latest.json")
    e2e_report, e2e_report_path = _load_contract_json(case_id, "e2e_outcome_verification_report.json")
    odd_coverage, odd_coverage_path = _load_contract_json(case_id, "odd_coverage_report.json")
    d1d4_precision, d1d4_precision_path = _load_contract_json(case_id, "d1d4_precision_report.latest.json")
    wnal_level_report, wnal_level_report_path = _load_contract_json(case_id, "wnal_level_report.json")
    control_optimization_report, control_optimization_report_path = _load_contract_json(case_id, "control_optimization_report.json")
    sil_verification_report, sil_verification_report_path = _load_contract_json(case_id, "sil_verification_report.json")
    pipeline_evaluation, pipeline_evaluation_path = _load_contract_json(case_id, "pipeline_evaluation.latest.json")
    rollout_minimal_loop, rollout_minimal_loop_path = _load_contract_json(case_id, "rollout_minimal_loop.latest.json")
    final_report, final_report_path = _load_contract_json(case_id, "final_report.latest.json")

    import_record_count = int(source_import_session.get("record_count") or 0)
    source_import_present = bool(source_import_session) and import_record_count > 0
    data_status = "ready" if source_import_present else "blocked"
    data_summary = (
        f"imported {import_record_count} records"
        if source_import_present
        else "missing or empty source_import_session.latest.json"
    )

    pipeline_dimensions = pipeline_evaluation.get("dimension_scores") or {}
    pipeline_d1 = pipeline_dimensions.get("d1_hydro_modeling") or {}
    rollout_summary = rollout_minimal_loop.get("summary") or {}
    rollout_readiness = (
        rollout_minimal_loop.get("readiness")
        or {
            "ready": rollout_minimal_loop.get("ready"),
            "status": rollout_minimal_loop.get("status"),
            "reason": rollout_minimal_loop.get("reason"),
        }
    )
    simulation_score = (
        pipeline_d1.get("mean_nse")
        if isinstance(pipeline_d1.get("mean_nse"), (int, float))
        else (autonomy_assessment.get("scores") or {}).get("simulation")
    )
    pipeline_case_id = str(pipeline_evaluation.get("case_id") or "").strip()
    pipeline_coverage_pct = pipeline_evaluation.get("coverage_pct")
    rollout_ready = bool(rollout_readiness.get("ready"))
    normalized_pipeline_coverage_pct = (
        float(pipeline_coverage_pct) / 100.0
        if isinstance(pipeline_coverage_pct, (int, float)) and float(pipeline_coverage_pct) > 1.0
        else float(pipeline_coverage_pct)
        if isinstance(pipeline_coverage_pct, (int, float))
        else None
    )
    mr_gov = gov.get("modeling_readiness") or {}
    sim_gov = mr_gov.get("simulation_score") or {}
    lane_cfg = mr_gov.get("canal_lane") or {}
    gf_lane_cfg = mr_gov.get("greenfield_cascade_lane") or {}
    modeling_thr_ready = float(sim_gov["ready_threshold"])
    modeling_thr_review = float(sim_gov["review_threshold"])
    canal_case_ready_for_review = _canal_lane_gates_met(
        project_type,
        rollout_ready=rollout_ready,
        pipeline_case_id=pipeline_case_id,
        case_id=case_id,
        normalized_coverage=normalized_pipeline_coverage_pct,
        lane_cfg=lane_cfg,
    )
    sc_raw = pipeline_d1.get("station_count")
    station_count_int: int | None
    if isinstance(sc_raw, (int, float)) and not isinstance(sc_raw, bool):
        station_count_int = int(sc_raw)
    else:
        station_count_int = None
    mean_nse_for_lane: float | None
    if isinstance(simulation_score, (int, float)):
        mean_nse_for_lane = float(simulation_score)
    else:
        mean_nse_for_lane = None
    greenfield_cascade_lane_gates_met = _greenfield_cascade_lane_gates_met(
        project_type,
        rollout_ready=rollout_ready,
        pipeline_case_id=pipeline_case_id,
        case_id=case_id,
        normalized_coverage=normalized_pipeline_coverage_pct,
        station_count=station_count_int,
        mean_nse=mean_nse_for_lane,
        lane_cfg=gf_lane_cfg,
    )
    modeling_status = _score_status(
        simulation_score,
        ready_threshold=modeling_thr_ready,
        review_threshold=modeling_thr_review,
    )
    if canal_case_ready_for_review and modeling_status == "blocked":
        modeling_status = "review"
    elif (
        not isinstance(simulation_score, (int, float))
        and rollout_readiness.get("ready")
    ):
        modeling_status = "review"
    if canal_case_ready_for_review:
        modeling_status = "ready"
        modeling_summary = str(lane_cfg.get("summary_template") or "").format(
            coverage_ratio=float(normalized_pipeline_coverage_pct),
        )
    elif isinstance(simulation_score, (int, float)) and pipeline_evaluation_path:
        modeling_summary = f"pipeline mean_nse {float(simulation_score):.4f}"
    elif isinstance(simulation_score, (int, float)):
        modeling_summary = f"simulation score {float(simulation_score):.4f}"
    elif rollout_readiness.get("ready"):
        modeling_summary = "case-bound minimal loop ready, numeric NSE pending"
    else:
        modeling_summary = "missing simulation score"

    if greenfield_cascade_lane_gates_met:
        if modeling_status == "blocked":
            modeling_status = "review"
        modeling_summary = str(gf_lane_cfg.get("summary_template") or "").format(
            coverage_ratio=float(normalized_pipeline_coverage_pct or 0),
        )

    ready_stages, total_stages, total_parameters = _stage_catalog_stats(parameter_governance)
    parameter_status = "ready" if ready_stages == total_stages and total_stages > 0 else "blocked"
    parameter_summary = f"{ready_stages}/{total_stages} stages ready · {total_parameters} parameters"

    assimilation_stage = ((parameter_governance.get("stage_catalog") or {}).get("assimilation") or {})
    assimilation_parameter_count = int(assimilation_stage.get("parameter_count") or 0)
    assimilation_status = "ready" if assimilation_parameter_count > 0 else "blocked"
    assimilation_summary = (
        f"assimilation parameters {assimilation_parameter_count}"
        if assimilation_parameter_count > 0
        else "assimilation stage missing"
    )

    autonomy_scores = autonomy_assessment.get("scores") or {}
    control_optimization_metrics = control_optimization_report.get("metrics") or {}
    sil_verification_metrics = sil_verification_report.get("metrics") or {}
    control_score = control_optimization_metrics.get("control_score")
    scheduling_score = control_optimization_metrics.get("scheduling_score")
    sil_score = (
        sil_verification_metrics.get("sil_score")
        if isinstance(sil_verification_metrics.get("sil_score"), (int, float))
        else autonomy_scores.get("sil")
    )
    odd_score = autonomy_scores.get("odd")
    recovery_success_rate = ((odd_coverage.get("coverage_metrics") or {}).get("recovery_success_rate"))
    scenarios_tested = int(((odd_coverage.get("coverage_metrics") or {}).get("total_scenarios_tested")) or 0)
    cso_gov = gov.get("control_sil_odd") or {}
    cso_ready_thr = float(cso_gov["score_ready_threshold"])
    cso_review_thr = float(cso_gov["score_review_threshold"])
    recovery_ready = float(cso_gov["recovery_success_rate_ready"])
    control_sil_odd_status = "blocked"
    if odd_coverage:
        control_sil_odd_status = "ready"
        if control_optimization_report_path:
            control_sil_odd_status = _merge_statuses(
                control_sil_odd_status,
                str(control_optimization_report.get("status") or ""),
            )
        elif _score_status(control_score, ready_threshold=cso_ready_thr, review_threshold=cso_review_thr) != "ready":
            control_sil_odd_status = "review"
        if sil_verification_report_path:
            control_sil_odd_status = _merge_statuses(
                control_sil_odd_status,
                str(sil_verification_report.get("status") or ""),
            )
        elif _score_status(sil_score, ready_threshold=cso_ready_thr, review_threshold=cso_review_thr) != "ready":
            control_sil_odd_status = "review"
        if _score_status(odd_score, ready_threshold=cso_ready_thr, review_threshold=cso_review_thr) != "ready":
            control_sil_odd_status = "review"
        if isinstance(recovery_success_rate, (int, float)) and float(recovery_success_rate) < recovery_ready:
            control_sil_odd_status = "review"
    control_sil_odd_summary = (
        f"control {float(control_score or 0):.2f} · SIL {float(sil_score or 0):.2f} · ODD {float(odd_score or 0):.2f} · scenarios {scenarios_tested}"
        if odd_coverage
        else "missing odd_coverage_report.json"
    )

    wnal_metrics = wnal_level_report.get("metrics") or {}
    d1d4_wnal_score = d1d4_precision.get("wnal_score")
    wnal_score = (
        wnal_metrics.get("wnal_score")
        if isinstance(wnal_metrics.get("wnal_score"), (int, float))
        else (d1d4_wnal_score if isinstance(d1d4_wnal_score, (int, float)) else autonomy_scores.get("wnal"))
    )
    wn_gov = gov.get("wnal") or {}
    wnal_status = _wnal_status_merge_contract_vs_score(
        wnal_level_report=wnal_level_report,
        wnal_score=wnal_score,
        ready_threshold=float(wn_gov["ready_threshold"]),
        review_threshold=float(wn_gov["review_threshold"]),
    )
    wnal_summary = _wnal_summary_merge_contract_vs_score(
        wnal_level_report=wnal_level_report,
        wnal_score=wnal_score,
        resolved_status=wnal_status,
    )

    outcome_gate_status = outcome_coverage.get("gate_status")
    outcome_coverage_ratio = outcome_coverage.get("outcome_coverage")
    zero_hardcoding_gate = (
        e2e_report.get("zero_hardcoding_gate")
        or ((e2e_report.get("stage3_outcome_quality") or {}).get("zero_hardcoding_gate"))
    )
    e2e_status = "blocked"
    if outcome_gate_status == "passed":
        e2e_status = "ready" if zero_hardcoding_gate != "failed" else "review"
    elif outcome_gate_status == "failed_by_hardcoding_linter":
        e2e_status = "review"
    e2e_summary = (
        f"coverage gate {outcome_gate_status or 'missing'} · hardcoding {zero_hardcoding_gate or 'unknown'}"
    )

    latest_autonomy_payload, latest_autonomy_path = _prefer_newer_contract(
        autonomy_assessment,
        autonomy_assessment_path,
        autonomy_autorun,
        autonomy_autorun_path,
    )
    latest_autonomy_judge = (latest_autonomy_payload.get("judge") or {}) if latest_autonomy_payload is autonomy_assessment else {}
    latest_autonomy_final = (latest_autonomy_payload.get("final") or {}) if latest_autonomy_payload is autonomy_autorun else {}
    autonomy_weak_dimensions = [
        item.get("dimension")
        for item in (
            (latest_autonomy_judge.get("weak_dimensions"))
            or (latest_autonomy_final.get("weak_dimensions"))
            or []
        )
        if isinstance(item, dict) and item.get("dimension")
    ]
    au_gov = gov.get("autonomy") or {}
    vmap = {str(k).upper(): str(v) for k, v in (au_gov.get("verdict_to_dimension_status") or {}).items()}
    default_verdict = str(au_gov.get("default_verdict") or "BLOCK").upper()
    autonomy_verdict = str(
        latest_autonomy_judge.get("verdict")
        or latest_autonomy_final.get("verdict")
        or default_verdict
    ).upper()
    autonomy_overall_score = (
        latest_autonomy_judge.get("overall_score")
        if isinstance(latest_autonomy_judge.get("overall_score"), (int, float))
        else latest_autonomy_final.get("overall_score")
    )
    autonomy_status = vmap.get(autonomy_verdict, "blocked")
    waiver_cfg = au_gov.get("simulation_only_waiver") or {}
    waiver_applied = False
    if waiver_cfg.get("enabled"):
        req_verdict = str(waiver_cfg.get("requires_source_verdict") or "WARN").upper()
        pre_waiver_status = vmap.get(req_verdict, "blocked")
        waiver_types = {str(p).strip().lower() for p in (waiver_cfg.get("project_types") or [])}
        need_model = str(waiver_cfg.get("requires_modeling_dimension_status") or "")
        weak_exact = list(waiver_cfg.get("weak_dimensions_exact_set") or [])
        if (
            project_type in waiver_types
            and autonomy_verdict == req_verdict
            and autonomy_status == pre_waiver_status
            and modeling_status == need_model
            and autonomy_weak_dimensions
            and set(autonomy_weak_dimensions) == set(weak_exact)
        ):
            autonomy_status = str(waiver_cfg.get("target_dimension_status") or "ready")
            waiver_applied = True
    autonomy_summary = (
        f"{autonomy_verdict} · overall {float(autonomy_overall_score):.4f}"
        if isinstance(autonomy_overall_score, (int, float))
        else autonomy_verdict
    )
    if waiver_applied:
        suffix = str(waiver_cfg.get("append_summary_suffix") or "")
        if suffix:
            autonomy_summary = f"{autonomy_summary}{suffix}"

    dimensions = {
        "data_preparedness": _build_dimension(
            key="data_preparedness",
            label="数据准备度",
            status=data_status,
            summary=data_summary,
            source_contracts=[path for path in [source_import_path] if path],
            metrics={
                "present": source_import_present,
                "record_count": import_record_count,
                "imported_at": source_import_session.get("imported_at"),
                "source_mode": source_import_session.get("source_mode"),
                "path": source_import_path,
                "source_contracts": [path for path in [source_import_path] if path],
            },
        ),
        "modeling_readiness": _build_dimension(
            key="modeling_readiness",
            label="建模准备度",
            status=modeling_status,
            summary=modeling_summary,
            source_contracts=[path for path in [pipeline_evaluation_path, autonomy_assessment_path, rollout_minimal_loop_path] if path],
            metrics={
                "simulation_score": simulation_score,
                "pipeline_case_id": pipeline_case_id,
                "pipeline_coverage_pct": pipeline_coverage_pct,
                "rollout_ready": rollout_ready,
                "rollout_status": rollout_readiness.get("status"),
                "project_type": project_type,
                "canal_case_ready_for_review": canal_case_ready_for_review,
                "greenfield_cascade_lane_gates_met": greenfield_cascade_lane_gates_met,
                "station_count": station_count_int,
                "modeling_readiness_suggested_action_override": (
                    str(gf_lane_cfg.get("review_suggested_action") or "").strip()
                    if greenfield_cascade_lane_gates_met
                    else None
                ),
            },
        ),
        "parameter_governance": _build_dimension(
            key="parameter_governance",
            label="参数治理完整度",
            status=parameter_status,
            summary=parameter_summary,
            source_contracts=[path for path in [parameter_governance_path] if path],
            metrics={
                "ready_stages": ready_stages,
                "total_stages": total_stages,
                "total_parameters": total_parameters,
            },
        ),
        "assimilation_readiness": _build_dimension(
            key="assimilation_readiness",
            label="同化可用性",
            status=assimilation_status,
            summary=assimilation_summary,
            source_contracts=[path for path in [parameter_governance_path] if path],
            metrics={"assimilation_parameter_count": assimilation_parameter_count},
        ),
        "control_sil_odd": _build_dimension(
            key="control_sil_odd",
            label="控制 / SIL / ODD",
            status=control_sil_odd_status,
            summary=control_sil_odd_summary,
            source_contracts=_unique_strings(
                [control_optimization_report_path, sil_verification_report_path]
                + list(control_optimization_report.get("source_contracts") or [])
                + list(sil_verification_report.get("source_contracts") or [])
                + [autonomy_assessment_path, odd_coverage_path]
            ),
            metrics={
                "control_score": control_score,
                "scheduling_score": scheduling_score,
                "sil_score": sil_score,
                "odd_score": odd_score,
                "recovery_success_rate": recovery_success_rate,
                "scenarios_tested": scenarios_tested,
                "control_contract_status": control_optimization_report.get("status"),
                "sil_contract_status": sil_verification_report.get("status"),
            },
        ),
        "wnal": _build_dimension(
            key="wnal",
            label="WNAL 等级",
            status=wnal_status,
            summary=wnal_summary,
            source_contracts=_unique_strings(
                [wnal_level_report_path]
                + list(wnal_level_report.get("source_contracts") or [])
                + [d1d4_precision_path, autonomy_assessment_path]
            ),
            metrics={
                "wnal_score": wnal_score,
                "wnal_level": wnal_metrics.get("wnal_level") or d1d4_precision.get("wnal_level"),
                "capability_score": wnal_metrics.get("capability_score") or d1d4_precision.get("capability_score"),
            },
        ),
        "e2e_gate": _build_dimension(
            key="e2e_gate",
            label="E2E Gate",
            status=e2e_status,
            summary=e2e_summary,
            source_contracts=[path for path in [outcome_coverage_path, e2e_report_path] if path],
            metrics={
                "gate_status": outcome_gate_status,
                "outcome_coverage": outcome_coverage_ratio,
                "zero_hardcoding_gate": zero_hardcoding_gate,
                "failed_workflow_count": int(
                    (((e2e_report.get("stage2_execution_integrity") or {}).get("summary") or {}).get("failed"))
                    or 0
                ),
            },
        ),
        "autonomy_quality": _build_dimension(
            key="autonomy_quality",
            label="自主性总评",
            status=autonomy_status,
            summary=autonomy_summary,
            source_contracts=[path for path in [latest_autonomy_path] if path],
            metrics={
                "overall_score": autonomy_overall_score,
                "verdict": autonomy_verdict,
                "generated_at": _contract_generated_at(latest_autonomy_payload),
                "weak_dimensions": autonomy_weak_dimensions,
            },
        ),
    }
    contracts = {
        "source_import_session": source_import_path,
        "parameter_governance": parameter_governance_path,
        "autonomy_assessment": autonomy_assessment_path,
        "autonomy_autorun": autonomy_autorun_path,
        "outcome_coverage": outcome_coverage_path,
        "e2e_outcome_verification": e2e_report_path,
        "odd_coverage": odd_coverage_path,
        "d1d4_precision": d1d4_precision_path,
        "wnal_level_report": wnal_level_report_path,
        "control_optimization_report": control_optimization_report_path,
        "sil_verification_report": sil_verification_report_path,
        "pipeline_evaluation": pipeline_evaluation_path,
        "rollout_minimal_loop": rollout_minimal_loop_path,
        "final_report": final_report_path,
    }
    raw_contracts = {
        "source_import_session": source_import_session,
        "parameter_governance": parameter_governance,
        "autonomy_assessment": autonomy_assessment,
        "autonomy_autorun": autonomy_autorun,
        "outcome_coverage": outcome_coverage,
        "e2e_outcome_verification": e2e_report,
        "odd_coverage": odd_coverage,
        "d1d4_precision": d1d4_precision,
        "wnal_level_report": wnal_level_report,
        "control_optimization_report": control_optimization_report,
        "sil_verification_report": sil_verification_report,
        "pipeline_evaluation": pipeline_evaluation,
        "rollout_minimal_loop": rollout_minimal_loop,
        "final_report": final_report,
    }
    return dimensions, contracts, raw_contracts


def _build_issue(case_id: str, dimension: dict[str, Any], severity: str) -> dict[str, Any]:
    dimension_key = str(dimension.get("key") or "")
    metrics = dimension.get("metrics") or {}
    weak_dimensions = metrics.get("weak_dimensions") or []
    summary = str(dimension.get("summary") or "")
    if weak_dimensions:
        summary = f"{summary} · weak: {', '.join(weak_dimensions[:3])}"
    override = metrics.get("modeling_readiness_suggested_action_override")
    suggested = ACTION_HINTS.get(dimension_key, "根据该维度对应 contract 修复后重跑聚合。")
    if dimension_key == "modeling_readiness" and override:
        suggested = str(override).strip() or suggested
    return {
        "case_id": case_id,
        "dimension": dimension_key,
        "label": dimension.get("label"),
        "severity": severity,
        "summary": summary,
        "source_contracts": dimension.get("source_contracts") or [],
        "suggested_action": suggested,
    }


def _build_release_gate(case_id: str, dimensions: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        _build_issue(case_id, payload, "blocker")
        for payload in dimensions.values()
        if payload.get("status") == "blocked"
    ]
    review_items = [
        _build_issue(case_id, payload, "review")
        for payload in dimensions.values()
        if payload.get("status") == "review"
    ]
    if blockers:
        gate_status = "blocked"
        summary = blockers[0]["summary"]
    elif review_items:
        gate_status = "needs-review"
        summary = review_items[0]["summary"]
    else:
        gate_status = "release-ready"
        summary = "all readiness dimensions passed"
    next_actions = [
        {
            "priority": "high" if item["severity"] == "blocker" else "medium",
            "dimension": item["dimension"],
            "summary": item["suggested_action"],
            "source_contracts": item["source_contracts"],
        }
        for item in [*blockers, *review_items]
    ]
    return {
        "status": gate_status,
        "summary": summary,
        "blockers": blockers,
        "review_items": review_items,
        "next_actions": next_actions,
    }


def _build_case_release_record(case_id: str, governance: dict[str, Any]) -> dict[str, Any]:
    dimensions, contracts, raw_contracts = _build_case_dimensions(case_id, governance)
    release_gate = _build_release_gate(case_id, dimensions)
    final_report = raw_contracts.get("final_report") or {}
    final_report_present = bool(contracts.get("final_report"))
    final_report_status = str(final_report.get("overall_status") or "")
    final_report_release_board_status = str(
        _json_pointer(final_report, "/readiness/release_board/status") or ""
    )
    final_report_promotion_status = final_report_release_board_status
    final_report_review_verdict = str(_json_pointer(final_report, "/review/verdict") or "")
    final_report_release_status = str(_json_pointer(final_report, "/release/status") or "")
    final_report_assertion_total = int(
        _json_pointer(final_report, "/assertion_summary/total")
        or len(final_report.get("assertions") or [])
        or 0
    )
    final_report_assertion_passed = int(_json_pointer(final_report, "/assertion_summary/passed") or 0)
    final_report_acceptance_source = ""
    for item in final_report.get("assertions") or []:
        if (
            isinstance(item, dict)
            and item.get("key") == "release_gate_not_blocked"
            and isinstance(item.get("source"), str)
        ):
            final_report_acceptance_source = str(item["source"])
            break
    raw_accept_scope = str(final_report.get("acceptance_scope") or "").strip()
    if final_report_present:
        # 旧合同无字段时视为单案交付面（与历史 rollup 一致）
        final_report_acceptance_scope = raw_accept_scope or "case"
    else:
        final_report_acceptance_scope = ""
    return {
        "case_id": case_id,
        "dimensions": dimensions,
        "release_gate": release_gate,
        "contract_paths": contracts,
        "final_report_present": final_report_present,
        "final_report_path": contracts.get("final_report") or "",
        "final_report_generated_at": str(final_report.get("generated_at") or ""),
        "final_report_status": final_report_status,
        "final_report_release_board_status": final_report_release_board_status,
        "final_report_promotion_status": final_report_promotion_status,
        "final_report_review_verdict": final_report_review_verdict,
        "final_report_release_status": final_report_release_status,
        "final_report_assertion_total": final_report_assertion_total,
        "final_report_assertion_passed": final_report_assertion_passed,
        "final_report_acceptance_scope": final_report_acceptance_scope,
        "final_report_acceptance_source": final_report_acceptance_source,
    }


def _build_release_board(case_ids: list[str], governance: dict[str, Any]) -> dict[str, Any]:
    cases = [_build_case_release_record(case_id, governance) for case_id in case_ids]
    by_status = {
        "release-ready": [row["case_id"] for row in cases if (row.get("release_gate") or {}).get("status") == "release-ready"],
        "needs-review": [row["case_id"] for row in cases if (row.get("release_gate") or {}).get("status") == "needs-review"],
        "blocked": [row["case_id"] for row in cases if (row.get("release_gate") or {}).get("status") == "blocked"],
    }
    return {
        "schema_version": READINESS_RELEASE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "contract_only_dependencies": True,
        "dimension_catalog": DIMENSION_CATALOG,
        "gate_rules": {
            "release-ready": "所有 readiness 维度均为 ready。",
            "needs-review": "无 blocker，但至少一个维度为 review。",
            "blocked": "至少一个关键维度为 blocked。",
        },
        "rollup": {
            "total_cases": len(case_ids),
            "release_ready_count": len(by_status["release-ready"]),
            "needs_review_count": len(by_status["needs-review"]),
            "blocked_count": len(by_status["blocked"]),
            "non_blocked_count": len(by_status["release-ready"]) + len(by_status["needs-review"]),
            "release_ready_case_ids": by_status["release-ready"],
            "needs_review_case_ids": by_status["needs-review"],
            "blocked_case_ids": by_status["blocked"],
        },
        "cases": cases,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Export rollout readiness / release board (multi-case JSON)")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument(
        "--governance-config",
        type=Path,
        default=Path("Hydrology/configs/release_readiness_governance.yaml"),
        help="YAML: thresholds / canal_lane / greenfield_cascade_lane / autonomy waiver (productization single source)",
    )
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--stdout", action="store_true", help="Print JSON bundle to stdout instead of only writing the output path")
    args = p.parse_args()
    cfg_path = args.config if args.config.is_absolute() else WORKSPACE / args.config
    if not cfg_path.is_file():
        print(json.dumps({"ok": False, "error": f"config not found: {cfg_path}"}, ensure_ascii=False))
        return 2
    gov_path = args.governance_config if args.governance_config.is_absolute() else WORKSPACE / args.governance_config
    try:
        governance = load_release_readiness_governance(gov_path)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    cfg = load_loop_yaml(WORKSPACE, cfg_path.resolve())
    case_ids = resolve_case_ids(cfg, WORKSPACE)
    release_board = _build_release_board(case_ids, governance)
    out_path = args.output if args.output.is_absolute() else WORKSPACE / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "ok": True,
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "loop_config_path": str(cfg_path.relative_to(WORKSPACE)),
        "release_readiness_governance_path": str(gov_path.relative_to(WORKSPACE)),
        "release_readiness_governance_schema": governance.get("schema_version"),
        "case_ids": case_ids,
        "import_chain_rollup": _import_chain_rollup(release_board.get("cases") or []),
        "readiness_release_board": release_board,
    }
    out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.stdout:
        print(json.dumps(bundle, ensure_ascii=False))
    else:
        print(_workspace_rel_or_abs(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
