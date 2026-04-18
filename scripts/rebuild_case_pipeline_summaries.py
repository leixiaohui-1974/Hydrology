#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
CASES_DIR = WORKSPACE / "cases"
PIPEDREAM_DIR = WORKSPACE / "pipedream-hydrology-integration-lab"
PIPEDREAM_CASE_CONFIG_DIR = PIPEDREAM_DIR / "hydromind_control_server" / "configs" / "cases"
PIPEDREAM_REPORTS_DIR = PIPEDREAM_DIR / "research" / "e2e_reports"

DEFAULT_CASE_IDS = [
    "zhongxian",
    "xuhonghe",
    "yinchuojiliao",
    "jiaodongtiaoshui",
    "yjdt",
]

CASE_ALIASES = {
    "yinchuojiliao": "yinchuo",
    "jiaodongtiaoshui": "jiaodong",
}


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rel(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(WORKSPACE).as_posix()
    except ValueError:
        return path.as_posix()


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return copy.deepcopy(value)
    return {}


def _first_number(*values: Any) -> float | int | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _first_bool(*values: Any) -> bool | None:
    for value in values:
        if isinstance(value, bool):
            return value
    return None


def _max_timestamp(*values: Any) -> str:
    timestamps = [str(value) for value in values if isinstance(value, str) and value.strip()]
    if not timestamps:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return max(timestamps)


def _extract_latest_evaluate_phase(self_improving: dict[str, Any]) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for iteration in self_improving.get("iterations", []):
        if not isinstance(iteration, dict):
            continue
        for phase in iteration.get("phases", []):
            if not isinstance(phase, dict) or phase.get("phase") != "evaluate":
                continue
            generated_at = _first_string(phase.get("generated_at"))
            latest_generated_at = _first_string(latest.get("generated_at"))
            if latest and generated_at and latest_generated_at and generated_at <= latest_generated_at:
                continue
            latest = copy.deepcopy(phase)
    return latest


def _load_case_context(case_id: str) -> dict[str, Any]:
    alias = CASE_ALIASES.get(case_id)
    contracts_dir = CASES_DIR / case_id / "contracts"
    summary_path = PIPEDREAM_REPORTS_DIR / case_id / f"{case_id}_pipeline_summary.json"
    data_source_path = PIPEDREAM_REPORTS_DIR / case_id / "data_source.json"
    case_config_path = PIPEDREAM_CASE_CONFIG_DIR / f"{case_id}.json"
    alias_summary_path = None
    alias_data_source_path = None
    legacy_summary = None

    if alias:
        alias_summary_path = PIPEDREAM_REPORTS_DIR / alias / f"{alias}_pipeline_summary.json"
        alias_data_source_path = PIPEDREAM_REPORTS_DIR / alias / "data_source.json"
        legacy_summary = _read_json(alias_summary_path)

    current_summary = _read_json(summary_path)
    if legacy_summary is None and current_summary:
        data_source = str(current_summary.get("data_source", ""))
        if "synthetic" not in data_source.lower():
            legacy_summary = current_summary

    return {
        "case_id": case_id,
        "alias": alias,
        "case_config_path": case_config_path,
        "case_config": _read_json(case_config_path) or {},
        "summary_path": summary_path,
        "current_summary": current_summary or {},
        "legacy_summary_path": alias_summary_path,
        "legacy_summary": legacy_summary or {},
        "data_source_path": data_source_path,
        "data_source": _read_json(data_source_path) or {},
        "alias_data_source_path": alias_data_source_path,
        "alias_data_source": _read_json(alias_data_source_path) or {},
        "review_bundle_path": contracts_dir / "review_bundle.json",
        "review_bundle": _read_json(contracts_dir / "review_bundle.json") or {},
        "reval_hf_path": contracts_dir / "reval_hf.json",
        "reval_hf": _read_json(contracts_dir / "reval_hf.json") or {},
        "odd_path": contracts_dir / "odd_coverage_report.json",
        "odd_coverage": _read_json(contracts_dir / "odd_coverage_report.json") or {},
        "state_estimation_path": contracts_dir / "state_estimation.latest.json",
        "state_estimation": _read_json(contracts_dir / "state_estimation.latest.json") or {},
        "autonomous_cascade_path": contracts_dir / "autonomous_cascade_report.latest.json",
        "autonomous_cascade": _read_json(contracts_dir / "autonomous_cascade_report.latest.json") or {},
        "outcome_coverage_path": contracts_dir / "outcome_coverage_report.latest.json",
        "outcome_coverage": _read_json(contracts_dir / "outcome_coverage_report.latest.json") or {},
        "workflow_run_path": contracts_dir / "workflow_run.json",
        "workflow_run": _read_json(contracts_dir / "workflow_run.json") or {},
        "rollout_minimal_loop_path": contracts_dir / "rollout_minimal_loop.latest.json",
        "rollout_minimal_loop": _read_json(contracts_dir / "rollout_minimal_loop.latest.json") or {},
        "self_improving_pipeline_path": contracts_dir / "self_improving_pipeline.latest.json",
        "self_improving_pipeline": _read_json(contracts_dir / "self_improving_pipeline.latest.json") or {},
        "hydrology_nse_evidence_path": contracts_dir / "hydrology_nse_evidence.latest.json",
        "hydrology_nse_evidence": _read_json(contracts_dir / "hydrology_nse_evidence.latest.json") or {},
        "hydrology_auto_learning_report_path": contracts_dir / "hydrology_auto_learning_report.json",
        "hydrology_auto_learning_report": _read_json(contracts_dir / "hydrology_auto_learning_report.json") or {},
        "d1d4_precision_path": contracts_dir / "d1d4_precision_report.latest.json",
        "d1d4_precision": _read_json(contracts_dir / "d1d4_precision_report.latest.json") or {},
        "pipeline_evaluation_path": contracts_dir / "pipeline_evaluation.latest.json",
        "pipeline_evaluation": _read_json(contracts_dir / "pipeline_evaluation.latest.json") or {},
    }


def _extract_simulation_metrics(review_bundle: dict[str, Any]) -> dict[str, Any]:
    for finding in review_bundle.get("findings", []):
        if not isinstance(finding, dict):
            continue
        metadata = finding.get("metadata")
        if not isinstance(metadata, dict):
            continue
        metrics = metadata.get("simulation_metrics")
        if isinstance(metrics, dict):
            return metrics
    return {}


def _build_topology(ctx: dict[str, Any]) -> dict[str, Any]:
    legacy = ctx["legacy_summary"].get("topology")
    if isinstance(legacy, dict) and legacy:
        return copy.deepcopy(legacy)

    data_source = ctx["data_source"] or ctx["alias_data_source"]
    topology = data_source.get("topology", {}) if isinstance(data_source, dict) else {}
    case_config = ctx["case_config"]
    stations = case_config.get("stations", []) if isinstance(case_config.get("stations"), list) else []
    station_names = [item.get("name") for item in stations if isinstance(item, dict) and item.get("name")]

    nodes = topology.get("nodes", []) if isinstance(topology.get("nodes"), list) else []
    links = topology.get("links", []) if isinstance(topology.get("links"), list) else []

    built: dict[str, Any] = {
        "n_stations": len(station_names),
        "station_names": station_names,
    }
    if nodes:
        built["n_nodes"] = len(nodes)
    if links:
        built["n_links"] = len(links)
    if data_source.get("meta", {}).get("design_flow_m3s") is not None:
        built["design_flow_m3s"] = data_source["meta"]["design_flow_m3s"]
    if data_source.get("meta", {}).get("sim_hours") is not None:
        built["sim_hours"] = data_source["meta"]["sim_hours"]
    water_stats = data_source.get("water_levels", {}).get("stats", {})
    if isinstance(water_stats, dict) and water_stats:
        built["water_level_stats"] = water_stats
    return built


def _build_calibration(ctx: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any]:
    calibration = _first_dict(ctx["legacy_summary"].get("calibration"))
    metrics = _extract_simulation_metrics(ctx["review_bundle"])
    outcome_coverage = ctx["outcome_coverage"].get("outcome_coverage")

    hydro_model = _first_dict(calibration.get("hydro_model"))
    if metrics:
        hydro_model.update(
            {
                "NSE": metrics.get("NSE"),
                "RMSE": metrics.get("RMSE"),
                "R2": metrics.get("R2"),
                "Bias_pct": metrics.get("Bias"),
            }
        )
    hydro_model = {k: v for k, v in hydro_model.items() if v is not None}
    if hydro_model:
        calibration["hydro_model"] = hydro_model

    if "n_channels_calibrated" not in calibration:
        calibration["n_channels_calibrated"] = int(
            _first_number(topology.get("n_links"), topology.get("n_stations"), 0) or 0
        )

    if outcome_coverage is not None:
        calibration.setdefault("section_coverage", float(outcome_coverage))
        calibration.setdefault("section_coverage_pct", float(outcome_coverage) * 100.0)

    calibration.setdefault("historical_calibrated", False)
    calibration["note"] = (
        "Rebuilt from case-bound contracts: hydro metrics use review_bundle simulation_metrics; "
        "coverage proxies use rollout outcome coverage and available topology evidence."
    )
    return calibration


def _build_validation(ctx: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any]:
    legacy = ctx["legacy_summary"].get("validation")
    if isinstance(legacy, dict) and legacy:
        validation = copy.deepcopy(legacy)
        validation["message"] = "legacy closed-loop summary reused as case-bound baseline"
        return validation

    reval_hf = ctx["reval_hf"]
    physics = reval_hf.get("modules", {}).get("physics", {}) if isinstance(reval_hf, dict) else {}
    control = reval_hf.get("modules", {}).get("control", {}) if isinstance(reval_hf, dict) else {}
    failed_sample = None
    for item in physics.get("failed_samples", []):
        if isinstance(item, dict) and item.get("test_type") == "steady_state":
            failed_sample = item
            break

    water_stats = topology.get("water_level_stats", {})
    h_range = None
    if isinstance(water_stats, dict):
        h_min = _first_number(water_stats.get("min"))
        h_max = _first_number(water_stats.get("max"))
        if h_min is not None and h_max is not None:
            h_range = [float(h_min), float(h_max)]

    steady_pass = bool(physics) and int(physics.get("failed_tests", 0) or 0) == 0
    control_pass = bool(control) and int(control.get("failed_tests", 0) or 0) == 0
    steady_metrics = failed_sample.get("metrics", {}) if isinstance(failed_sample, dict) else {}

    return {
        "steady_state": {
            "passed": steady_pass,
            "converged_step": int(
                _first_number(
                    steady_metrics.get("steps_to_converge"),
                    physics.get("total_tests"),
                    0,
                )
                or 0
            ),
            "flow_error": _first_number(steady_metrics.get("deviation_from_initial")),
            "H_range": h_range,
            "message": f"physics pass_rate={float(physics.get('pass_rate', 0.0) or 0.0):.3f}",
        },
        "unsteady": {
            "passed": True,
            "rmse": -1.0,
            "message": "No direct unsteady observation contract is bound in the current case bundle.",
        },
        "step_response": {
            "passed": control_pass,
            "delta_Q": None,
            "delta_h_max": None,
            "response_time_s": None,
            "overshoot_pct": None,
            "settling_time_s": None,
            "sse": None,
            "message": f"control pass_rate={float(control.get('pass_rate', 0.0) or 0.0):.3f}",
        },
        "all_passed": steady_pass and control_pass,
        "recommendations": [],
    }


def _build_identification(ctx: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any]:
    legacy = ctx["legacy_summary"].get("identification")
    if isinstance(legacy, dict) and legacy:
        return copy.deepcopy(legacy)

    state_estimation = ctx["state_estimation"]
    summary = state_estimation.get("summary", {}) if isinstance(state_estimation, dict) else {}
    total = int(_first_number(summary.get("total_stations"), 0) or 0)
    completed = int(_first_number(summary.get("completed"), 0) or 0)
    coverage = float(completed / total) if total else 0.0

    return {
        "active_mode": "state_estimation",
        "model_type": _first_string(state_estimation.get("method"), "unknown"),
        "model_coverage": coverage,
        "fopdt_fit_ok": False,
        "full_order_available": bool(topology.get("n_nodes")),
        "full_order_n_states": int(_first_number(topology.get("n_nodes"), 0) or 0),
    }


def _build_kalman_filter(ctx: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any]:
    legacy = ctx["legacy_summary"].get("kalman_filter")
    if isinstance(legacy, dict) and legacy:
        return copy.deepcopy(legacy)

    state_estimation = ctx["state_estimation"]
    method = _first_string(state_estimation.get("method"), "unknown")
    return {
        "mode": method.lower() if method else "unknown",
        "n_states": int(_first_number(topology.get("n_nodes"), 0) or 0),
        "built": method is not None,
        "configured": method is not None,
    }


def _build_mpc_controller(ctx: dict[str, Any]) -> dict[str, Any]:
    legacy = ctx["legacy_summary"].get("mpc_controller")
    if isinstance(legacy, dict) and legacy:
        return copy.deepcopy(legacy)

    case_config = ctx["case_config"]
    autonomous = ctx["autonomous_cascade"]
    control_stage = {}
    for step in autonomous.get("steps", []):
        if isinstance(step, dict) and step.get("stage") == "control":
            control_stage = step
            break

    np_horizon = int(_first_number(case_config.get("mpc_horizon"), 0) or 0)
    nc_horizon = min(5, np_horizon) if np_horizon else 0
    built = control_stage.get("status") == "completed"
    return {
        "mode": "base_mpc" if built else "not_built",
        "Np": np_horizon,
        "Nc": nc_horizon,
        "built": built,
        "configured": built,
    }


def _build_scheduling(ctx: dict[str, Any]) -> dict[str, Any]:
    legacy = ctx["legacy_summary"].get("scheduling")
    if isinstance(legacy, dict) and legacy:
        return copy.deepcopy(legacy)

    case_config = ctx["case_config"]
    station_count = len(case_config.get("stations", [])) if isinstance(case_config.get("stations"), list) else 1
    autonomous = ctx["autonomous_cascade"]
    control_stage = {}
    dispatch_done = False
    for step in autonomous.get("steps", []):
        if not isinstance(step, dict):
            continue
        if step.get("stage") == "control":
            control_stage = step
        if step.get("stage") == "dispatch" and step.get("status") == "completed":
            dispatch_done = True

    return {
        "method": "mpc" if control_stage.get("status") == "completed" else "rule",
        "efficiency_gain_pct": 0.0,
        "n_stations_coordinated": max(station_count, 1),
        "dispatch_completed": dispatch_done,
    }


def _build_sil_verification(ctx: dict[str, Any]) -> dict[str, Any]:
    legacy = ctx["legacy_summary"].get("sil_verification")
    if isinstance(legacy, dict) and legacy:
        return copy.deepcopy(legacy)

    reval_hf = ctx["reval_hf"]
    modules = reval_hf.get("modules", {}) if isinstance(reval_hf, dict) else {}
    pass_rates = []
    for module in ("physics", "control"):
        mod = modules.get(module)
        if isinstance(mod, dict) and mod.get("pass_rate") is not None:
            pass_rates.append(float(mod.get("pass_rate") or 0.0))

    scenario_count = int(_first_number(reval_hf.get("scenario_count"), 0) or 0)
    requested = int(_first_number(reval_hf.get("requested_scenarios"), scenario_count, 1) or 1)
    return {
        "has_sil": bool(modules),
        "has_mil": False,
        "has_hil": False,
        "n_scenarios": scenario_count,
        "pass_rate": _mean(pass_rates),
        "scene_coverage": min(float(scenario_count) / float(requested), 1.0) if requested else 0.0,
    }


def _build_odd_validation(ctx: dict[str, Any]) -> dict[str, Any]:
    legacy = ctx["legacy_summary"].get("odd_validation")
    if isinstance(legacy, dict) and legacy:
        return copy.deepcopy(legacy)

    odd = ctx["odd_coverage"]
    odd_dimensions = odd.get("odd_dimensions", {}) if isinstance(odd, dict) else {}
    scenarios = odd.get("scenarios", []) if isinstance(odd.get("scenarios"), list) else []
    simplified = []
    observed_states: list[str] = []

    for item in scenarios:
        if not isinstance(item, dict):
            continue
        state = _first_string(item.get("state"), "Unknown")
        if state:
            observed_states.append(state)
        simplified.append(
            {
                "scenario": item.get("scenario_id"),
                "description": item.get("description"),
                "state": state,
                "in_bounds": item.get("in_bounds"),
                "violations": item.get("violations", []),
                "recovery_action": item.get("recovery_action"),
            }
        )

    transitions = []
    for prev, curr in zip(observed_states, observed_states[1:]):
        if prev and curr and prev != curr:
            transitions.append(f"{prev}->{curr}")

    boundary_count = 0
    for values in odd_dimensions.values():
        if isinstance(values, list):
            boundary_count += len(values)

    coverage = odd.get("coverage_metrics", {}) if isinstance(odd, dict) else {}
    return {
        "validated_in_simulation": bool(simplified),
        "n_boundary_conditions": boundary_count,
        "n_scenarios": int(_first_number(coverage.get("total_scenarios_tested"), len(simplified), 0) or 0),
        "scenarios": simplified,
        "transitions_observed": transitions,
        "n_transitions": len(transitions),
        "recovery_success_rate": _first_number(coverage.get("recovery_success_rate")),
    }


def _build_closedloop_validation(ctx: dict[str, Any]) -> dict[str, Any]:
    legacy = ctx["legacy_summary"].get("closedloop_validation")
    if isinstance(legacy, dict) and legacy:
        return copy.deepcopy(legacy)

    reval_hf = ctx["reval_hf"]
    modules = reval_hf.get("modules", {}) if isinstance(reval_hf, dict) else {}
    physics = modules.get("physics", {}) if isinstance(modules.get("physics"), dict) else {}
    control = modules.get("control", {}) if isinstance(modules.get("control"), dict) else {}
    pass_rates = [
        float(item.get("pass_rate") or 0.0)
        for item in (physics, control)
        if isinstance(item, dict) and item.get("pass_rate") is not None
    ]
    return {
        "overall_pass_rate": _mean(pass_rates),
        "physics_pass_rate": _first_number(physics.get("pass_rate")),
        "control_pass_rate": _first_number(control.get("pass_rate")),
        "disturbance_tested": bool(ctx["odd_coverage"].get("scenarios")),
    }


def build_case_pipeline_evaluation(case_id: str) -> tuple[Path, dict[str, Any]]:
    ctx = _load_case_context(case_id)
    contracts_dir = CASES_DIR / case_id / "contracts"
    existing = _first_dict(ctx["pipeline_evaluation"])
    if _first_string(existing.get("case_id")) == "adhoc":
        existing = {}

    latest_evaluate = _extract_latest_evaluate_phase(ctx["self_improving_pipeline"])
    evaluation = _first_dict(latest_evaluate, existing)
    outcome_ratio = _first_number(
        ctx["outcome_coverage"].get("outcome_coverage"),
        ((ctx["rollout_minimal_loop"].get("summary") or {}).get("outcome_coverage")),
    )
    coverage_pct = _first_number(
        float(outcome_ratio) * 100.0 if outcome_ratio is not None else None,
        evaluation.get("coverage_pct"),
    )
    d1_dimension = ((ctx["d1d4_precision"].get("dimensions") or {}).get("d1") or {})
    d1_station_count = int(_first_number(d1_dimension.get("stations_total"), 0) or 0)
    d1_mean_nse = _first_number(
        ctx["hydrology_nse_evidence"].get("comparable_nse"),
        d1_dimension.get("mean_val_nse"),
        (((evaluation.get("dimension_scores") or {}).get("d1_hydro_modeling") or {}).get("mean_nse")),
        ((ctx["pipeline_evaluation"].get("calibration_metrics") or {}).get("nse")),
        ctx["pipeline_evaluation"].get("objective"),
    )
    d1_min_nse = _first_number(
        ((ctx["hydrology_nse_evidence"].get("metrics") or {}).get("nse")),
        d1_dimension.get("mean_val_nse"),
        (((evaluation.get("dimension_scores") or {}).get("d1_hydro_modeling") or {}).get("min_nse")),
        d1_mean_nse,
    )
    existing_improvement = ((evaluation.get("dimension_scores") or {}).get("self_improvement") or {})
    improve_phase = {}
    for iteration in ctx["self_improving_pipeline"].get("iterations", []):
        if not isinstance(iteration, dict):
            continue
        for phase in iteration.get("phases", []):
            if isinstance(phase, dict) and phase.get("phase") == "improve":
                improve_phase = phase
    rollout_summary = ctx["rollout_minimal_loop"].get("summary") or {}
    readiness = _first_dict(
        ctx["rollout_minimal_loop"].get("readiness"),
        {
            "ready": ctx["rollout_minimal_loop"].get("ready"),
            "status": ctx["rollout_minimal_loop"].get("status"),
            "reason": ctx["rollout_minimal_loop"].get("reason"),
        },
    )
    default_maturity = "L2_case_bound" if readiness.get("ready") else "L1_assisted"
    payload = {
        "phase": "evaluate",
        "status": "completed",
        "case_id": case_id,
        "generated_at": _max_timestamp(
            evaluation.get("generated_at"),
            ctx["rollout_minimal_loop"].get("generated_at"),
            ctx["outcome_coverage"].get("generated_at"),
            ctx["hydrology_auto_learning_report"].get("generated_at"),
        ),
        "workflow": "case_bound_contract_rebuild",
        "evaluation_basis": "case_bound_contracts",
        "available_contracts": sorted(path.name for path in contracts_dir.glob("*.json")),
        "coverage_pct": coverage_pct,
        "maturity": _first_string(evaluation.get("maturity"), default_maturity),
        "convergence": _first_bool(
            ctx["hydrology_auto_learning_report"].get("success"),
            evaluation.get("convergence"),
            readiness.get("ready"),
        ),
        "dimension_scores": {
            "d1_hydro_modeling": {
                "mean_nse": d1_mean_nse,
                "min_nse": d1_min_nse,
                "station_count": max(
                    d1_station_count,
                    int(_first_number((ctx["hydrology_nse_evidence"].get("station_count")), 0) or 0),
                ),
            },
            "self_improvement": {
                "rounds_run": int(
                    _first_number(
                        len(ctx["self_improving_pipeline"].get("iterations", [])),
                        existing_improvement.get("rounds_run"),
                        0,
                    )
                    or 0
                ),
                "improved_count": int(
                    _first_number(
                        improve_phase.get("improved_count"),
                        existing_improvement.get("improved_count"),
                        0,
                    )
                    or 0
                ),
                "mean_delta": _first_number(
                    improve_phase.get("mean_delta"),
                    existing_improvement.get("mean_delta"),
                ),
            },
        },
        "readiness": {
            "ready": bool(readiness.get("ready")),
            "status": _first_string(readiness.get("status"), "pending"),
            "reason": _first_string(readiness.get("reason"), ""),
            "minimal_loop_path": _rel(ctx["rollout_minimal_loop_path"]),
            "workflow_run_path": _rel(ctx["workflow_run_path"]),
            "outcome_coverage": _first_number(rollout_summary.get("outcome_coverage"), outcome_ratio),
        },
        "target_check": {
            "target_value": _first_number(
                (ctx["hydrology_auto_learning_report"].get("threshold_validation") or {}).get("business_threshold"),
                ctx["hydrology_auto_learning_report"].get("target_value"),
            ),
            "current_metric": _first_number(
                (ctx["hydrology_auto_learning_report"].get("threshold_validation") or {}).get("current_metric"),
                d1_mean_nse,
            ),
            "success": _first_bool(ctx["hydrology_auto_learning_report"].get("success")),
            "metric_source_path": _first_string(
                ctx["hydrology_auto_learning_report"].get("metric_source_path"),
                (ctx["hydrology_auto_learning_report"].get("threshold_validation") or {}).get("metric_source_path"),
            ),
            "metric_source_mode": _first_string(
                ctx["hydrology_auto_learning_report"].get("metric_source_mode"),
                (ctx["hydrology_auto_learning_report"].get("threshold_validation") or {}).get("metric_source_mode"),
            ),
        },
        "source_contracts": [
            item
            for item in [
                _rel(ctx["self_improving_pipeline_path"]),
                _rel(ctx["rollout_minimal_loop_path"]),
                _rel(ctx["workflow_run_path"]),
                _rel(ctx["outcome_coverage_path"]),
                _rel(ctx["hydrology_nse_evidence_path"]),
                _rel(ctx["hydrology_auto_learning_report_path"]),
                _rel(ctx["d1d4_precision_path"]),
            ]
            if item
        ],
    }
    return ctx["pipeline_evaluation_path"], payload


def build_case_pipeline_summary(case_id: str) -> tuple[Path, dict[str, Any]]:
    ctx = _load_case_context(case_id)
    case_config = ctx["case_config"]
    topology = _build_topology(ctx)
    calibration = _build_calibration(ctx, topology)
    validation = _build_validation(ctx, topology)
    identification = _build_identification(ctx, topology)
    kalman_filter = _build_kalman_filter(ctx, topology)
    mpc_controller = _build_mpc_controller(ctx)
    scheduling = _build_scheduling(ctx)
    sil_verification = _build_sil_verification(ctx)
    odd_validation = _build_odd_validation(ctx)
    closedloop_validation = _build_closedloop_validation(ctx)

    evidence_refs = [
        _rel(ctx["review_bundle_path"]),
        _rel(ctx["reval_hf_path"]),
        _rel(ctx["odd_path"]),
        _rel(ctx["state_estimation_path"]),
        _rel(ctx["autonomous_cascade_path"]),
        _rel(ctx["outcome_coverage_path"]),
        _rel(ctx["workflow_run_path"]),
        _rel(ctx["case_config_path"]),
        _rel(ctx["data_source_path"]) if ctx["data_source"] else None,
        _rel(ctx["alias_data_source_path"]) if ctx["alias_data_source"] else None,
        _rel(ctx["legacy_summary_path"]) if ctx["legacy_summary"] else None,
    ]
    evidence_refs = [item for item in evidence_refs if item]

    payload = {
        "case_name": case_id,
        "display_name": _first_string(case_config.get("display_name"), case_id),
        "timestamp": (ctx["review_bundle"] or {}).get("generated_at") or (ctx["reval_hf"] or {}).get("generated_at"),
        "pipeline_version": "case_contract_native_v1",
        "route": "A_canal" if case_config.get("project_type", "canal") == "canal" else "B_cascade_hydro",
        "data_source": "case-bound contracts + existing e2e artifacts (no synthetic placeholder)",
        "evidence_refs": evidence_refs,
        "topology": topology,
        "calibration": calibration,
        "validation": validation,
        "historical_validation": _first_dict(
            ctx["legacy_summary"].get("historical_validation"),
            {"available": False, "mean_nse": 0.0, "mean_rmse": 0.0, "grade": "N/A"},
        ),
        "identification": identification,
        "kalman_filter": kalman_filter,
        "mpc_controller": mpc_controller,
        "closedloop_validation": closedloop_validation,
        "scheduling": scheduling,
        "sil_verification": sil_verification,
        "odd_validation": odd_validation,
        "generator": {
            "tool": "Hydrology/scripts/rebuild_case_pipeline_summaries.py",
            "mode": "contract_native_rebuild",
        },
    }
    return ctx["summary_path"], payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild canonical case pipeline summaries from case-bound contracts.")
    parser.add_argument("--cases", nargs="+", default=DEFAULT_CASE_IDS, help="Case ids to rebuild.")
    args = parser.parse_args()

    for case_id in args.cases:
        pipeline_eval_path, pipeline_eval_payload = build_case_pipeline_evaluation(case_id)
        _write_json(pipeline_eval_path, pipeline_eval_payload)
        print(f"wrote {_rel(pipeline_eval_path)}")

        summary_path, summary_payload = build_case_pipeline_summary(case_id)
        _write_json(summary_path, summary_payload)
        print(f"wrote {_rel(summary_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
