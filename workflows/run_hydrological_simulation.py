"""推演 (TuiYan) — 水力仿真与耦合计算

HydroMind 水智工坊 · Agent #6

Deterministic hydrological simulation workflow entrypoint.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hydro_model.calibration import CalibrationConfig, run_full_cv
from workflows._shared import abs_path, load_case_config, load_json, run_python
from workflows.run_calibration_report import load_station_timeseries
from workflows.run_precision_improvement import _find_hydromind_sqlite


CLOSURE_GRID_STEPS = 5
WORKSPACE = BASE_DIR.parent
ALLOWED_HYDROLOGY_PARAMETERS = {
    "rainfall_multiplier",
    "soil_storage_scale",
    "baseflow_recession_factor",
}
HYDROLOGY_CLOSURE_PAIRS = [
    ("Q_in_reservoir", "Q_out_reservoir", "legacy_reservoir_pair"),
    ("Q_in", "Q_out", "legacy_flow_pair"),
    ("flow", "water_level", "real_observation_bundle"),
    ("flow", "velocity", "real_observation_bundle"),
]
TIME_STEP_PRIORITY = {
    "1D": 0,
    "1H": 1,
    "1min": 2,
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_station_catalog(db_path: Path) -> tuple[dict[str, str], dict[str, dict[str, set[str]]]]:
    station_names: dict[str, str] = {}
    station_variables: dict[str, dict[str, set[str]]] = {}
    conn = sqlite3.connect(str(db_path))
    try:
        table_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "stations" in table_names:
            for station_id, station_name in conn.execute("SELECT id, name FROM stations"):
                station_names[str(station_id)] = str(station_name or station_id)
        if "timeseries_meta" in table_names:
            rows = conn.execute(
                """
                SELECT station_id, variable, COALESCE(time_step, '1D') AS time_step
                FROM timeseries_meta
                """
            )
        else:
            rows = conn.execute(
                """
                SELECT DISTINCT station_id, variable, time_step
                FROM timeseries
                """
            )
        for station_id, variable, time_step in rows:
            station_id = str(station_id)
            variable = str(variable or "").strip()
            time_step = str(time_step or "1D").strip() or "1D"
            if not variable:
                continue
            station_variables.setdefault(station_id, {}).setdefault(time_step, set()).add(variable)
    finally:
        conn.close()
    return station_names, station_variables


def _series_signal_score(values: np.ndarray) -> tuple[int, float]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 0, 0.0
    signal = int(np.nanstd(arr) > 1e-9 or np.nanmax(np.abs(arr)) > 1e-9)
    return signal, float(np.nanstd(arr))


def _series_quality_penalty(variable: str, values: np.ndarray) -> int:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 1
    penalty = 0
    min_value = float(np.nanmin(arr))
    if variable == "water_level" and min_value <= 1.0:
        penalty += 1
    if variable in {"flow", "velocity", "Q_in", "Q_out", "Q_in_reservoir", "Q_out_reservoir"} and min_value < -1e-6:
        penalty += 1
    return penalty


def _rank_time_step(time_step: str) -> tuple[int, str]:
    return TIME_STEP_PRIORITY.get(time_step, 99), time_step


def _extract_hydrology_closure_binding(case_config: dict) -> dict | None:
    modeling = case_config.get("modeling") or {}
    hydrology = modeling.get("hydrology") or {}
    binding = hydrology.get("closure_binding")
    return binding if isinstance(binding, dict) and binding else None


def _normalize_binding_endpoint(endpoint: dict | None, *, role: str) -> dict[str, str]:
    if not isinstance(endpoint, dict):
        raise ValueError(f"hydrology closure binding must define {role}")

    station_id = str(endpoint.get("station_id") or "").strip()
    station_name = str(endpoint.get("station_name") or "").strip()
    variable = str(endpoint.get("variable") or "").strip()
    time_step = str(endpoint.get("time_step") or "").strip()
    if not station_id and not station_name:
        raise ValueError(f"hydrology closure binding {role} must define station_id or station_name")
    if not variable:
        raise ValueError(f"hydrology closure binding {role} must define variable")
    return {
        "station_id": station_id,
        "station_name": station_name,
        "variable": variable,
        "time_step": time_step,
    }


def _resolve_binding_station_id(
    endpoint: dict[str, str],
    station_names: dict[str, str],
    station_variables: dict[str, dict[str, set[str]]],
    *,
    role: str,
) -> tuple[str, str]:
    station_id = endpoint.get("station_id") or ""
    station_name = endpoint.get("station_name") or ""
    if station_id:
        resolved_name = station_names.get(station_id, station_name or station_id)
        if station_variables and station_id not in station_variables:
            raise ValueError(f"hydrology closure binding {role} station_id not found: {station_id}")
        return station_id, resolved_name

    matches = [
        (candidate_id, candidate_name)
        for candidate_id, candidate_name in station_names.items()
        if candidate_name == station_name
    ]
    if not matches:
        raise ValueError(f"hydrology closure binding {role} station_name not found: {station_name}")
    if len(matches) > 1:
        raise ValueError(f"hydrology closure binding {role} station_name is ambiguous: {station_name}")
    return matches[0]


def _resolve_binding_time_step(
    input_station_id: str,
    input_variable: str,
    input_time_step: str,
    observed_station_id: str,
    observed_variable: str,
    observed_time_step: str,
    station_variables: dict[str, dict[str, set[str]]],
    binding_time_step: str,
) -> str:
    input_candidates = {
        time_step
        for time_step, variables in (station_variables.get(input_station_id) or {}).items()
        if input_variable in variables
    }
    observed_candidates = {
        time_step
        for time_step, variables in (station_variables.get(observed_station_id) or {}).items()
        if observed_variable in variables
    }
    shared_candidates = input_candidates & observed_candidates
    if not shared_candidates:
        raise ValueError("hydrology closure binding requires shared time_step across input and observed series")

    requested = input_time_step or observed_time_step or binding_time_step
    if requested:
        if requested not in shared_candidates:
            raise ValueError(f"hydrology closure binding time_step not found: {requested}")
        return requested
    return min(shared_candidates, key=_rank_time_step)


def _align_series_on_shared_timestamps(
    input_values: np.ndarray,
    input_timestamps: list[str],
    observed_values: np.ndarray,
    observed_timestamps: list[str],
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    input_arr = np.asarray(input_values, dtype=float)
    observed_arr = np.asarray(observed_values, dtype=float)
    if not input_timestamps or not observed_timestamps:
        n = min(len(input_arr), len(observed_arr))
        return input_arr[:n], observed_arr[:n], input_timestamps[:n] if input_timestamps else observed_timestamps[:n]

    observed_by_time = {
        ts: float(value)
        for ts, value in zip(observed_timestamps, observed_arr)
    }
    aligned_input = []
    aligned_observed = []
    aligned_timestamps = []
    for ts, value in zip(input_timestamps, input_arr):
        if ts not in observed_by_time:
            continue
        aligned_timestamps.append(ts)
        aligned_input.append(float(value))
        aligned_observed.append(observed_by_time[ts])
    return (
        np.asarray(aligned_input, dtype=float),
        np.asarray(aligned_observed, dtype=float),
        aligned_timestamps,
    )


def _load_explicit_hydrology_closure_series(
    case_id: str,
    db_path: Path,
    case_config: dict,
) -> tuple[np.ndarray, np.ndarray, dict] | None:
    binding = _extract_hydrology_closure_binding(case_config)
    if not binding:
        return None

    station_names, station_variables = _read_station_catalog(db_path)
    input_endpoint = _normalize_binding_endpoint(binding.get("input"), role="input")
    observed_endpoint = _normalize_binding_endpoint(binding.get("observed"), role="observed")
    input_station_id, input_station_name = _resolve_binding_station_id(
        input_endpoint, station_names, station_variables, role="input"
    )
    observed_station_id, observed_station_name = _resolve_binding_station_id(
        observed_endpoint, station_names, station_variables, role="observed"
    )
    time_step = _resolve_binding_time_step(
        input_station_id,
        input_endpoint["variable"],
        input_endpoint.get("time_step", ""),
        observed_station_id,
        observed_endpoint["variable"],
        observed_endpoint.get("time_step", ""),
        station_variables,
        str(binding.get("time_step") or "").strip(),
    )

    input_series, input_timestamps = load_station_timeseries(
        db_path,
        input_station_id,
        input_endpoint["variable"],
        time_step,
    )
    observed_series, observed_timestamps = load_station_timeseries(
        db_path,
        observed_station_id,
        observed_endpoint["variable"],
        time_step,
    )
    input_series, observed_series, aligned_timestamps = _align_series_on_shared_timestamps(
        input_series,
        input_timestamps,
        observed_series,
        observed_timestamps,
    )
    if len(input_series) == 0 or len(observed_series) == 0:
        raise ValueError("hydrology closure binding resolved zero overlapping records")

    observed_available_variables = sorted(
        (station_variables.get(observed_station_id) or {}).get(time_step, set())
    )
    data_window = {
        "start": aligned_timestamps[0][:10] if aligned_timestamps else None,
        "end": aligned_timestamps[-1][:10] if aligned_timestamps else None,
        "count": int(len(aligned_timestamps)),
        "station_id": observed_station_id,
        "station_name": observed_station_name,
        "input_station_id": input_station_id,
        "input_station_name": input_station_name,
        "observed_station_id": observed_station_id,
        "observed_station_name": observed_station_name,
        "input_variable": input_endpoint["variable"],
        "observed_variable": observed_endpoint["variable"],
        "available_variables": observed_available_variables,
        "selection_mode": "explicit_case_binding",
        "time_step": time_step,
        "case_id": case_id,
    }
    return input_series, observed_series, data_window


def _select_hydrology_closure_series(case_id: str, db_path: Path) -> tuple[np.ndarray, np.ndarray, dict] | None:
    station_names, station_variables = _read_station_catalog(db_path)
    best_candidate: tuple | None = None
    best_payload: tuple[np.ndarray, np.ndarray, dict] | None = None

    for pair_rank, (input_variable, observed_variable, selection_mode) in enumerate(HYDROLOGY_CLOSURE_PAIRS):
        for station_id, time_steps in station_variables.items():
            for time_step, variables in time_steps.items():
                if input_variable not in variables or observed_variable not in variables:
                    continue
                q_in, ts_in = load_station_timeseries(db_path, station_id, input_variable, time_step)
                observed, ts_out = load_station_timeseries(db_path, station_id, observed_variable, time_step)
                n = min(len(q_in), len(observed))
                if n == 0:
                    continue
                q_in = np.asarray(q_in[:n], dtype=float)
                observed = np.asarray(observed[:n], dtype=float)
                input_signal, input_std = _series_signal_score(q_in)
                observed_signal, observed_std = _series_signal_score(observed)
                quality_penalty = _series_quality_penalty(input_variable, q_in) + _series_quality_penalty(observed_variable, observed)
                available_variables = sorted(variables)
                has_real_triplet = int({"flow", "water_level", "velocity"}.issubset(variables))
                candidate_key = (
                    quality_penalty,
                    -input_signal,
                    -observed_signal,
                    pair_rank,
                    *_rank_time_step(time_step),
                    -has_real_triplet,
                    -n,
                    -(input_std + observed_std),
                    station_id,
                )
                if best_candidate is not None and candidate_key >= best_candidate:
                    continue
                data_window = {
                    "start": ts_in[0][:10] if ts_in else None,
                    "end": ts_in[n - 1][:10] if ts_in else None,
                    "count": n,
                    "station_id": station_id,
                    "station_name": station_names.get(station_id, station_id),
                    "input_variable": input_variable,
                    "observed_variable": observed_variable,
                    "available_variables": available_variables,
                    "selection_mode": selection_mode,
                    "time_step": time_step,
                    "case_id": case_id,
                }
                best_candidate = candidate_key
                best_payload = (q_in, observed, data_window)
    return best_payload


def _load_real_hydrology_series(case_id: str, case_config: dict | None = None) -> tuple[np.ndarray, np.ndarray, dict]:
    cfg = case_config or load_case_config(case_id)
    db_path = _find_hydromind_sqlite(cfg)
    if not db_path:
        raise ValueError("hydrology closure requires hydromind sqlite for real observation/input series")
    db_path = Path(db_path)
    explicit_selection = _load_explicit_hydrology_closure_series(case_id, db_path, cfg)
    if explicit_selection is not None:
        return explicit_selection
    selection = _select_hydrology_closure_series(case_id, db_path)
    if selection is None:
        raise ValueError("hydrology closure requires real observation/input series")
    return selection


def _make_closure_model_fn() -> callable:
    # 采用 HydroClaudeAdapter 适配外部模型
    from hydro_model.hydro_claude_adapter import HydroClaudeAdapter

    def external_model_impl(rainfall_multiplier=1.0, soil_storage_scale=1.0, baseflow_recession_factor=1.0, input_data=None):
        values = np.asarray(input_data if input_data is not None else [], dtype=float)
        if values.size == 0:
            return values
        return values * float(rainfall_multiplier) * 0.7 + values * float(soil_storage_scale) * 0.2 + values * float(baseflow_recession_factor) * 0.1

    # 配置适配器：标准契约参数映射到外部模型入参
    adapter = HydroClaudeAdapter(
        external_model=external_model_impl,
        predict_fn_name="__call__"
    )

    def model_fn(params: dict[str, float], input_data):
        # 组装标准输入
        standard_inputs = {"input_data": input_data}
        standard_inputs.update(params)
        
        # 运行外部模型并映射回标准输出
        outputs = adapter.run_simulation(standard_inputs)
        return outputs["Q_out_reservoir"]

    return model_fn


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic hydrological simulation workflow entrypoint.")
    parser.add_argument("--case-id", required=True, help="Case identifier")
    parser.add_argument("--data-pack-json", required=True, help="Data pack JSON from build_data_pack.py")
    parser.add_argument("--simulation-config", required=True, help="Simulation YAML config")
    parser.add_argument("--parameter-governance-json", required=True, help="Parameter governance envelope JSON")
    parser.add_argument("--run-id", default=None, help="Override workflow run id")
    parser.add_argument("--metadata-out", default=None, help="WorkflowRun output path")
    parser.add_argument("--no-calibrate", action="store_true", help="Run single evaluation without full CV calibration")
    return parser


def _build_hydrology_closure_param_space(governance: dict) -> dict[str, tuple[float, float, int]]:
    artifact_paths = governance.get("artifact_paths") or {}
    inventory_path = artifact_paths.get("parameter_inventory")
    if not inventory_path:
        raise ValueError("parameter governance must expose parameter_inventory")

    inventory = load_json(abs_path(inventory_path, label="parameter_inventory"))
    hydrology_inventory = ((inventory.get("stages") or {}).get("hydrology")) or []
    inventory_by_id = {
        item.get("parameter_id"): item
        for item in hydrology_inventory
        if isinstance(item, dict) and item.get("parameter_id")
    }

    artifact_paths = governance.get("artifact_paths") or {}
    candidate_set_path = artifact_paths.get("candidate_set")
    if candidate_set_path:
        candidate_set_record = load_json(abs_path(candidate_set_path, label="candidate_set"))
        candidate_set = (candidate_set_record.get("stages") or {}).get("hydrology") or {}
    else:
        candidate_set = (governance.get("candidate_set") or {}).get("hydrology") or {}
        
    primary_candidates = candidate_set.get("primary_candidates") or []
    if not primary_candidates:
        raise ValueError("hydrology primary_candidates must include at least one candidate for closure")

    disallowed = [name for name in primary_candidates if name not in ALLOWED_HYDROLOGY_PARAMETERS]
    if disallowed:
        raise ValueError("hydrology closure only allows the first three structural parameters")

    param_space: dict[str, tuple[float, float, int]] = {}
    for parameter_id in primary_candidates:
        item = inventory_by_id.get(parameter_id)
        if not item:
            continue
        bounds = item.get("bounds") or []
        if len(bounds) != 2:
            continue
        low, high = bounds
        param_space[parameter_id] = (float(low), float(high), CLOSURE_GRID_STEPS)

    if not param_space:
        raise ValueError("hydrology closure parameter space is empty")
    return param_space


def _first_float(*values) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _build_hydrology_nse_evidence(
    case_id: str,
    data_window: dict,
    calibration_metrics: dict,
    validation_metrics: dict,
) -> dict:
    comparable_nse = _first_float(
        (validation_metrics or {}).get("nse"),
        (calibration_metrics or {}).get("nse"),
    )
    station_id = data_window.get("observed_station_id") or data_window.get("station_id")
    station_name = data_window.get("observed_station_name") or data_window.get("station_name")
    selection_mode = data_window.get("selection_mode")
    return {
        "case_id": case_id,
        "source_workflow": "hydrology_calibration",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "comparable_nse": comparable_nse,
        "mean_validation_nse": comparable_nse,
        "min_validation_nse": comparable_nse,
        "stations": [
            {
                "station_id": station_id,
                "station_name": station_name,
                "validation_nse": comparable_nse,
                "selection_mode": selection_mode,
                "input_station_id": data_window.get("input_station_id"),
                "observed_station_id": data_window.get("observed_station_id"),
                "input_variable": data_window.get("input_variable"),
                "observed_variable": data_window.get("observed_variable"),
                "time_step": data_window.get("time_step"),
            }
        ],
    }


def main() -> None:
    args = _build_parser().parse_args()
    data_pack_path = abs_path(args.data_pack_json, label="--data-pack-json")
    governance_path = abs_path(args.parameter_governance_json, label="--parameter-governance-json")
    simulation_config_path = abs_path(args.simulation_config, label="--simulation-config")
    load_json(data_pack_path)
    governance = load_json(governance_path)
    case_config = load_case_config(args.case_id, str(simulation_config_path))
    workflow_recommendations = governance.get("workflow_recommendations") or {}
    hydrology_stage_guidance = (workflow_recommendations.get("stage_activation_guidance") or {}).get("hydrology") or {}
    artifact_paths = governance.get("artifact_paths") or {}
    candidate_set_path = artifact_paths.get("candidate_set")
    if candidate_set_path:
        candidate_set_record = load_json(abs_path(candidate_set_path, label="candidate_set"))
        candidate_set = (candidate_set_record.get("stages") or {}).get("hydrology") or {}
    else:
        candidate_set = (governance.get("candidate_set") or {}).get("hydrology") or {}
        
    if not candidate_set:
        raise ValueError("parameter governance must contain hydrology candidate_set")
    activation_record_path = artifact_paths.get("correction_activation_record")
    if not activation_record_path:
        raise ValueError("parameter governance must expose correction_activation_record")
    if not artifact_paths.get("parameter_inventory"):
        raise ValueError("parameter governance must expose parameter_inventory")
    sensitivity_report_path = artifact_paths.get("sensitivity_report")
    if not sensitivity_report_path:
        raise ValueError("parameter governance must expose sensitivity_report")

    activation_record = load_json(abs_path(activation_record_path, label="correction_activation_record"))
    hydrology_activation = activation_record.get("hydrology")
    if not hydrology_activation:
        raise ValueError("correction activation record must contain hydrology values")

    sensitivity_report = load_json(abs_path(sensitivity_report_path, label="sensitivity_report"))
    if not ((sensitivity_report.get("stages") or {}).get("hydrology")):
        raise ValueError("sensitivity_report must contain hydrology stage")

    param_space = _build_hydrology_closure_param_space(governance)
    optimized_parameters = list(param_space.keys())

    model_fn = _make_closure_model_fn()
    input_series, observed, data_window = _load_real_hydrology_series(args.case_id, case_config=case_config)
    
    if args.no_calibrate:
        # 单次评估，直接读取 governance 中的当前参数（或 activation）
        sim_params = hydrology_activation.copy()
        outputs = model_fn(sim_params, input_series)
        
        # 计算 NSE
        # 对齐数组长度
        n = min(len(outputs), len(observed))
        sim_arr = np.asarray(outputs[:n])
        obs_arr = np.asarray(observed[:n])
        if len(obs_arr) > 0 and np.var(obs_arr) > 0:
            nse = 1 - np.sum((sim_arr - obs_arr) ** 2) / np.sum((obs_arr - np.mean(obs_arr)) ** 2)
        else:
            nse = -999.0
            
        result = {
            "best_params": sim_params,
            "best_objective": nse,
            "calibration_metrics": {"nse": nse, "rmse": np.sqrt(np.mean((sim_arr - obs_arr) ** 2)) if len(obs_arr) > 0 else 0},
            "validation_metrics": {},
            "param_space": param_space
        }
        print(f"[{args.case_id}] [No-Calibrate] Evaluation NSE: {nse:.4f}")
    else:
        result = run_full_cv(
            model_fn=model_fn,
            observed=observed,
            param_space=param_space,
            input_data=input_series,
            config=CalibrationConfig(objective="nse", cal_ratio=0.7),
            progressive_rounds=2,
        )

    contracts_dir = WORKSPACE / "cases" / args.case_id / "contracts"
    payload = {
        "case_id": args.case_id,
        "workflow": "hydrology_calibration",
        "governance_ref": str(governance_path),
        "used_candidate_set": list((candidate_set.get("primary_candidates") or [])),
        "used_activation_before_calibration": hydrology_activation,
        "workflow_recommendations": workflow_recommendations,
        "hydrology_stage_guidance": hydrology_stage_guidance,
        "optimized_parameters": optimized_parameters,
        "best_params": result.get("best_params", {}),
        "objective": result.get("best_objective"),
        "calibration_metrics": result.get("calibration_metrics", {}),
        "validation_metrics": result.get("validation_metrics", {}),
        "parameter_bounds": result.get("param_space", {}),
        "data_window": data_window,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    _write_json(contracts_dir / "hydrology_calibration.latest.json", payload)
    evidence = _build_hydrology_nse_evidence(
        args.case_id,
        data_window,
        payload["calibration_metrics"],
        payload["validation_metrics"],
    )
    _write_json(contracts_dir / "hydrology_nse_evidence.latest.json", evidence)
    print(f"[{args.case_id}] wrote hydrology_calibration.latest.json")
    
    if args.no_calibrate:
        # 退出，不运行后续冗长的仿真和报告
        return

    report_lines = [
        "# Hydrology Calibration Report",
        "",
        "## Slice scope",
        "- First governed hydrology closure slice",
        "- Only governance-approved primary candidates are optimized",
        "",
        "## Initial vs best",
        f"- Initial: {hydrology_activation}",
        f"- Best: {payload['best_params']}",
        "",
        "## Metrics",
        f"- Objective: {payload['objective']}",
        f"- Calibration metrics: {payload['calibration_metrics']}",
        f"- Validation metrics: {payload['validation_metrics']}",
        "",
        "## Interpretation",
        "- This closure uses real hydrology input/observation series from the case SQLite store.",
        f"- Consistency: {(result.get('assessment') or {}).get('consistency', 'n/a')}",
        "",
        "## Governance recommendation",
        "- Keep parameters in review scope; promote or demote only after human review of this closure result.",
        f"- Hydrology stage guidance: {hydrology_stage_guidance.get('status', 'unknown')}",
        f"- Matched workflows: {', '.join(hydrology_stage_guidance.get('matched_workflows') or []) or '—'}",
    ]
    _write_text(contracts_dir / "hydrology_calibration_report.md", "\n".join(report_lines) + "\n")
    print(f"[Hydrological Simulation] Done for {args.case_id}")


if __name__ == "__main__":
    main()
