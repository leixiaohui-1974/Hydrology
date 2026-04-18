#!/usr/bin/env python3
"""撰报 (ZhuanBao) — 成果报告自动生成

HydroMind 水智工坊 · Agent #9

逐站率定验证报告产品 — 通用化，按 case 配置驱动。

支持模型类型：
  - muskingum: Muskingum 汇流（河道/小库容）
  - reservoir: 水量平衡水库模型（大库容）
  - coupled: 水文水动力耦合

产出：
  - 逐站率定参数
  - 逐站率定期/验证期精度指标（NSE/RMSE/KGE/R²/PBIAS）
  - 流域划分精度
  - 综合评定报告 JSON

Usage:
    python3 run_calibration_report.py --case-id zhongxian
    python3 run_calibration_report.py --case-id zhongxian --config configs/<case>.yaml
    python3 run_calibration_report.py --case-id zhongxian --model-type reservoir
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))

from hydro_model.calibration import CalibrationConfig, run_full_cv
from hydro_model.precision_evaluation import (
    PrecisionReport, evaluate_delineation, evaluate_timeseries,
)

SERIES_PAIR_PRIORITY = [
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
OBSERVATION_VARIABLE_COLUMN = {
    "Q_in_reservoir": "Q",
    "Q_out_reservoir": "Q",
    "Q_in": "Q",
    "Q_out": "Q",
    "flow": "Q",
    "H_up": "Z",
    "H_down": "Z",
    "water_level": "Z",
    "velocity": "Q",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_hydrology_nse_evidence(case_id: str, station_reports: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_stations: list[dict[str, Any]] = []
    validation_nses: list[float] = []
    for station in station_reports:
        if station.get("status") != "completed":
            continue
        validation_nse = ((station.get("validation") or {}).get("nse"))
        if validation_nse is None:
            continue
        validation_nse = float(validation_nse)
        validation_nses.append(validation_nse)
        data_binding = station.get("data_binding") or {}
        evidence_stations.append(
            {
                "station_id": station.get("station_id"),
                "station_name": station.get("station_name"),
                "validation_nse": validation_nse,
                "selection_mode": data_binding.get("selection_mode"),
                "input_station_id": data_binding.get("input_station_id"),
                "observed_station_id": data_binding.get("observed_station_id"),
                "input_variable": data_binding.get("input_variable"),
                "observed_variable": data_binding.get("observed_variable"),
                "time_step": data_binding.get("time_step"),
            }
        )
    comparable_nse = min(validation_nses) if validation_nses else None
    mean_validation_nse = sum(validation_nses) / len(validation_nses) if validation_nses else None
    return {
        "case_id": case_id,
        "source_workflow": "calibration_report",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "comparable_nse": comparable_nse,
        "mean_validation_nse": mean_validation_nse,
        "min_validation_nse": comparable_nse,
        "stations": evidence_stations,
    }


# ── 数据加载 ────────────────────────────────────────────────────────────────

def _find_zv_curves(scan_dirs: list) -> dict[str, tuple]:
    """搜索库容曲线 xlsx 文件，返回 {站名: (z_array, v_array)}。通用，不硬编码。"""
    import glob
    curves = {}
    for scan_dir in scan_dirs:
        for fpath in sorted(Path(scan_dir).rglob("*库容曲线*.xlsx")):
            try:
                import pandas as pd
                df = pd.read_excel(fpath)
                z = pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna().values.astype(float)
                v = pd.to_numeric(df.iloc[:, 1], errors="coerce").dropna().values.astype(float)
                n = min(len(z), len(v))
                if n < 3:
                    continue
                # 从文件名提取站名
                stem = fpath.stem.replace("库容曲线", "").strip()
                # 自动判断单位：如果 V 最大值 > 100，可能是万m³，转换为亿m³
                v_arr = v[:n]
                if v_arr.max() > 100:
                    v_arr = v_arr / 10000.0
                curves[stem] = (z[:n], v_arr)
            except Exception:
                continue
    return curves


def _find_supported_db(cfg: dict[str, Any]) -> str | None:
    candidates: list[Path] = []
    for raw_path in cfg.get("sqlite_paths", []) or []:
        path = Path(str(raw_path))
        if path.exists() and path.is_file() and path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
            candidates.append(path.resolve())
    for scan_dir in cfg.get("scan_dirs", []) or []:
        base = Path(str(scan_dir))
        if not base.exists() or not base.is_dir():
            continue
        for pattern in ("*.sqlite", "*.sqlite3", "*.db"):
            for file_path in sorted(base.glob(pattern)):
                if file_path.is_file():
                    candidates.append(file_path.resolve())

    seen: set[str] = set()
    unique_candidates: list[Path] = []
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(path)

    def _priority(path: Path) -> tuple[int, str]:
        low = path.name.lower()
        if "hydromind" in low:
            return (0, str(path))
        if "observation" in low:
            return (1, str(path))
        return (2, str(path))

    unique_candidates.sort(key=_priority)
    for path in unique_candidates:
        try:
            conn = sqlite3.connect(str(path))
            try:
                tables = {
                    row[0]
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                conn.close()
        except sqlite3.Error:
            continue
        if {"timeseries", "observations"} & tables:
            return str(path)
    return None



def _load_observations_series(
    conn: sqlite3.Connection,
    station_id: str,
    variable: str,
) -> tuple[np.ndarray, list[str]]:
    column = OBSERVATION_VARIABLE_COLUMN.get(variable)
    if not column:
        return np.array([]), []
    rows = conn.execute(
        f"SELECT time, {column} FROM observations WHERE station=? AND {column} IS NOT NULL ORDER BY time",
        (station_id,),
    ).fetchall()
    if not rows:
        rows = conn.execute(
            f"SELECT time, {column} FROM observations WHERE station LIKE ? AND {column} IS NOT NULL ORDER BY time",
            (f"%{station_id}%",),
        ).fetchall()
    if not rows:
        return np.array([]), []
    return np.array([float(row[1]) for row in rows], dtype=float), [str(row[0]) for row in rows]



def load_station_timeseries(
    db_path: str | Path,
    station_id: str,
    variable: str,
    time_step: str = "1D",
) -> tuple[np.ndarray, list[str]]:
    """从 SQLite 加载站点时序数据。返回 (values, timestamps)。"""
    conn = sqlite3.connect(str(db_path))
    try:
        table_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "timeseries" in table_names:
            rows = conn.execute(
                "SELECT time, value FROM timeseries WHERE station_id=? AND variable=? AND time_step=? ORDER BY time",
                (station_id, variable, time_step),
            ).fetchall()
            if rows:
                return np.array([float(r[1]) for r in rows], dtype=float), [str(r[0]) for r in rows]
        if "observations" in table_names:
            return _load_observations_series(conn, station_id, variable)
    finally:
        conn.close()
    return np.array([]), []



def _read_station_catalog(
    db_path: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, dict[str, set[str]]]]:
    station_rows: list[dict[str, Any]] = []
    station_names: dict[str, str] = {}
    station_variables: dict[str, dict[str, set[str]]] = {}
    conn = sqlite3.connect(str(db_path))
    try:
        table_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "stations" in table_names:
            rows = conn.execute(
                """
                SELECT id, name, station_type, basin_area_km2, metadata_json
                FROM stations
                """
            )
            for station_id, station_name, station_type, basin_area_km2, metadata_json in rows:
                station_id = str(station_id)
                station_name = str(station_name or station_id)
                station_rows.append(
                    {
                        "id": station_id,
                        "name": station_name,
                        "station_type": station_type,
                        "basin_area_km2": basin_area_km2,
                        "metadata_json": metadata_json,
                    }
                )
                station_names[station_id] = station_name
        if "timeseries_meta" in table_names:
            rows = conn.execute(
                """
                SELECT station_id, variable, COALESCE(time_step, '1D') AS time_step
                FROM timeseries_meta
                """
            )
            for station_id, variable, time_step in rows:
                station_id = str(station_id)
                variable = str(variable or "").strip()
                time_step = str(time_step or "1D").strip() or "1D"
                if not variable:
                    continue
                station_variables.setdefault(station_id, {}).setdefault(time_step, set()).add(variable)
                station_names.setdefault(station_id, station_id)
        elif "timeseries" in table_names:
            rows = conn.execute(
                """
                SELECT DISTINCT station_id, variable, COALESCE(time_step, '1D') AS time_step
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
                station_names.setdefault(station_id, station_id)
        elif "observations" in table_names:
            rows = conn.execute(
                "SELECT DISTINCT station FROM observations WHERE station IS NOT NULL ORDER BY station"
            )
            for (station_id,) in rows:
                sid = str(station_id)
                station_names[sid] = sid
                station_variables.setdefault(sid, {}).setdefault("1D", set()).update({"flow", "water_level"})
    finally:
        conn.close()

    known_station_ids = {row["id"] for row in station_rows}
    for station_id in sorted(station_variables):
        if station_id in known_station_ids:
            continue
        station_rows.append(
            {
                "id": station_id,
                "name": station_names.get(station_id, station_id),
                "station_type": None,
                "basin_area_km2": None,
                "metadata_json": None,
            }
        )
    return station_rows, station_names, station_variables


def _extract_hydrology_closure_binding(cfg: dict[str, Any]) -> dict[str, Any] | None:
    modeling = cfg.get("modeling") or {}
    hydrology = modeling.get("hydrology") or {}
    binding = hydrology.get("closure_binding")
    return binding if isinstance(binding, dict) and binding else None


def _normalize_binding_endpoint(endpoint: Any, *, role: str) -> dict[str, str]:
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


def _resolve_binding_station(
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


def _rank_time_step(time_step: str) -> tuple[int, str]:
    return TIME_STEP_PRIORITY.get(time_step, 99), time_step


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
    if not input_timestamps or not observed_timestamps:
        n = min(len(input_values), len(observed_values))
        timestamps = input_timestamps[:n] if input_timestamps else observed_timestamps[:n]
        return input_values[:n], observed_values[:n], timestamps

    observed_by_time = {
        ts: float(value)
        for ts, value in zip(observed_timestamps, observed_values)
    }
    aligned_input = []
    aligned_observed = []
    aligned_timestamps = []
    for ts, value in zip(input_timestamps, input_values):
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


def _lookup_station_row(station_rows: list[dict[str, Any]], station_id: str) -> dict[str, Any] | None:
    for row in station_rows:
        if row["id"] == station_id:
            return row
    return None


def _load_explicit_binding_target(
    db_path: str | Path,
    cfg: dict[str, Any],
    station_rows: list[dict[str, Any]],
    station_names: dict[str, str],
    station_variables: dict[str, dict[str, set[str]]],
) -> dict[str, Any] | None:
    binding = _extract_hydrology_closure_binding(cfg)
    if not binding:
        return None

    input_endpoint = _normalize_binding_endpoint(binding.get("input"), role="input")
    observed_endpoint = _normalize_binding_endpoint(binding.get("observed"), role="observed")
    input_station_id, input_station_name = _resolve_binding_station(
        input_endpoint, station_names, station_variables, role="input"
    )
    observed_station_id, observed_station_name = _resolve_binding_station(
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

    q_in, ts_in = load_station_timeseries(db_path, input_station_id, input_endpoint["variable"], time_step)
    q_out, ts_out = load_station_timeseries(db_path, observed_station_id, observed_endpoint["variable"], time_step)
    q_in, q_out, timestamps = _align_series_on_shared_timestamps(q_in, ts_in, q_out, ts_out)
    station_row = _lookup_station_row(station_rows, observed_station_id) or {}
    return {
        "station_id": observed_station_id,
        "station_name": observed_station_name,
        "basin_area_km2": station_row.get("basin_area_km2"),
        "series_mode": "explicit_case_binding",
        "input_series": q_in,
        "observed_series": q_out,
        "timestamps": timestamps,
        "input_variable": input_endpoint["variable"],
        "observed_variable": observed_endpoint["variable"],
        "data_binding": {
            "selection_mode": "explicit_case_binding",
            "input_station_id": input_station_id,
            "input_station_name": input_station_name,
            "observed_station_id": observed_station_id,
            "observed_station_name": observed_station_name,
            "input_variable": input_endpoint["variable"],
            "observed_variable": observed_endpoint["variable"],
            "time_step": time_step,
        },
    }


def _discover_station_targets(
    db_path: str | Path,
    cfg: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    station_rows, station_names, station_variables = _read_station_catalog(db_path)
    explicit_target = _load_explicit_binding_target(
        db_path, cfg, station_rows, station_names, station_variables
    )
    if explicit_target is not None:
        return [explicit_target], station_rows

    targets: list[dict[str, Any]] = []
    for station in station_rows:
        station_id = station["id"]
        time_steps = station_variables.get(station_id) or {}
        best_target = None
        best_key = None
        for time_step, variables in time_steps.items():
            for pair_rank, (input_variable, observed_variable, selection_mode) in enumerate(SERIES_PAIR_PRIORITY):
                if input_variable not in variables or observed_variable not in variables:
                    continue
                q_in, ts_in = load_station_timeseries(db_path, station_id, input_variable, time_step)
                q_out, ts_out = load_station_timeseries(db_path, station_id, observed_variable, time_step)
                q_in, q_out, timestamps = _align_series_on_shared_timestamps(q_in, ts_in, q_out, ts_out)
                n = min(len(q_in), len(q_out))
                if n == 0:
                    continue
                q_in = np.asarray(q_in[:n], dtype=float)
                q_out = np.asarray(q_out[:n], dtype=float)
                candidate_key = (
                    pair_rank,
                    *_rank_time_step(time_step),
                    -n,
                )
                if best_key is not None and candidate_key >= best_key:
                    continue
                best_key = candidate_key
                best_target = {
                    "station_id": station_id,
                    "station_name": station["name"],
                    "basin_area_km2": station.get("basin_area_km2"),
                    "series_mode": selection_mode,
                    "input_series": q_in,
                    "observed_series": q_out,
                    "timestamps": timestamps[:n],
                    "input_variable": input_variable,
                    "observed_variable": observed_variable,
                    "data_binding": {
                        "selection_mode": selection_mode,
                        "input_station_id": station_id,
                        "input_station_name": station["name"],
                        "observed_station_id": station_id,
                        "observed_station_name": station["name"],
                        "input_variable": input_variable,
                        "observed_variable": observed_variable,
                        "time_step": time_step,
                    },
                }
        if best_target is not None:
            targets.append(best_target)
    return targets, station_rows


# ── 模型工厂 ────────────────────────────────────────────────────────────────

def _make_muskingum_model():
    from hydro_model.routing import MuskingumRouting

    def model_fn(params, input_data):
        routing = MuskingumRouting(K=params["K"], x=params["x"])
        result = np.zeros(len(input_data))
        for i in range(len(input_data)):
            result[i] = routing.run(float(input_data[i]))
        return result

    param_space = {"K": (0.5, 5.0, 8), "x": (0.0, 0.4, 8)}
    return model_fn, param_space


def _make_reservoir_model(zv_x, zv_y):
    """水量平衡水库模型：O = alpha*I + beta*(Z-Z_target)/dt_norm。

    率定参数：
      alpha: 出入流比例跟踪因子
      beta: 水位偏差调节系数（亿m³→m³/s 换算）
      z_target: 目标运行水位

    物理意义：水库按目标水位运行，出流跟踪入流并受水位偏差调节。
    """
    from hydro_model.curve_calibration import interp1d_linear

    z_mid = zv_x[len(zv_x) // 2]
    z_min, z_max = float(zv_x[0]), float(zv_x[-1])
    v_min = interp1d_linear(zv_x, zv_y, z_min)
    v_max = interp1d_linear(zv_x, zv_y, z_max)

    def model_fn(params, input_data):
        alpha = params["alpha"]
        beta = params["beta"]
        z_target = params["z_target"]
        dt = 86400.0
        n = len(input_data)
        outflow = np.zeros(n)
        z = z_mid
        v = interp1d_linear(zv_x, zv_y, z)

        for t in range(n):
            inflow = float(input_data[t])
            z_bias = z - z_target
            o_target = max(0.0, alpha * inflow + beta * z_bias * 1e8 / dt)
            dv = (inflow - o_target) * dt / 1e8
            v_new = v + dv
            if v_new < v_min:
                o_target = max(0, inflow - (v_min - v) * 1e8 / dt)
                v_new = v_min
            elif v_new > v_max:
                o_target = inflow + (v_new - v_max) * 1e8 / dt
                v_new = v_max
            outflow[t] = o_target
            v = v_new
            z = interp1d_linear(zv_y, zv_x, v)
        return outflow

    param_space = {
        "alpha": (0.85, 1.05, 8),
        "beta": (0.1, 5.0, 8),
        "z_target": (z_mid - 10, z_mid + 10, 8),
    }
    return model_fn, param_space


# ── 逐站率定 ────────────────────────────────────────────────────────────────

def calibrate_station(
    db_path: str | Path,
    station_id: str,
    station_name: str,
    model_type: str = "muskingum",
    cal_ratio: float = 0.7,
    zv_curve: tuple | None = None,
    input_series: np.ndarray | None = None,
    observed_series: np.ndarray | None = None,
    timestamps: list[str] | None = None,
    data_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """对单站进行率定验证。确定性。"""
    if input_series is None or observed_series is None:
        q_in, ts_in = load_station_timeseries(db_path, station_id, "Q_in_reservoir", "1D")
        q_out, ts_out = load_station_timeseries(db_path, station_id, "Q_out_reservoir", "1D")
        q_in, q_out, resolved_timestamps = _align_series_on_shared_timestamps(q_in, ts_in, q_out, ts_out)
        resolved_binding = data_binding or {
            "selection_mode": "legacy_reservoir_pair",
            "input_station_id": station_id,
            "input_station_name": station_name,
            "observed_station_id": station_id,
            "observed_station_name": station_name,
            "input_variable": "Q_in_reservoir",
            "observed_variable": "Q_out_reservoir",
            "time_step": "1D",
        }
    else:
        q_in = np.asarray(input_series, dtype=float)
        q_out = np.asarray(observed_series, dtype=float)
        resolved_timestamps = list(timestamps or [])
        resolved_binding = data_binding or {}

    if len(q_in) < 100 or len(q_out) < 100:
        return {
            "station_id": station_id, "station_name": station_name,
            "status": "insufficient_data",
            "data_count": min(len(q_in), len(q_out)),
            "data_binding": resolved_binding,
        }

    min_len = min(len(q_in), len(q_out))
    q_in, q_out = q_in[:min_len], q_out[:min_len]
    resolved_timestamps = resolved_timestamps[:min_len]
    period = None
    if resolved_timestamps:
        period = f"{resolved_timestamps[0][:10]}~{resolved_timestamps[min_len-1][:10]}"

    # 选择模型
    if model_type == "reservoir" and zv_curve:
        model_fn, param_space = _make_reservoir_model(zv_curve[0], zv_curve[1])
    else:
        model_fn, param_space = _make_muskingum_model()

    # 率定
    result = run_full_cv(
        model_fn=model_fn,
        observed=q_out,
        param_space=param_space,
        input_data=q_in,
        config=CalibrationConfig(objective="nse", cal_ratio=cal_ratio),
        progressive_rounds=2,
    )

    # 逐期精度评价
    split_idx = int(min_len * cal_ratio)
    cal_sim = model_fn(result["best_params"], q_in[:split_idx])
    val_sim = model_fn(result["best_params"], q_in[split_idx:])

    cal_eval = evaluate_timeseries(q_out[:split_idx], cal_sim, "Q_out", station_name, "calibration")
    val_eval = evaluate_timeseries(q_out[split_idx:], val_sim, "Q_out", station_name, "validation")

    return {
        "station_id": station_id,
        "station_name": station_name,
        "status": "completed",
        "model_type": model_type,
        "data_count": min_len,
        "period": period,
        "best_params": result["best_params"],
        "data_binding": resolved_binding,
        "calibration": {
            "nse": cal_eval.metrics["nse"],
            "rmse": cal_eval.metrics["rmse"],
            "kge": cal_eval.metrics["kge"],
            "r2": cal_eval.metrics["r2"],
            "pbias": cal_eval.metrics["pbias"],
            "grade": cal_eval.grade,
            "peak_error": cal_eval.peak_error,
        },
        "validation": {
            "nse": val_eval.metrics["nse"],
            "rmse": val_eval.metrics["rmse"],
            "kge": val_eval.metrics["kge"],
            "r2": val_eval.metrics["r2"],
            "pbias": val_eval.metrics["pbias"],
            "grade": val_eval.grade,
            "peak_error": val_eval.peak_error,
        },
        "assessment": result["assessment"],
    }


# ── 主流程 ──────────────────────────────────────────────────────────────────

def run_report(
    case_id: str,
    config_path: str | None = None,
    model_type: str = "auto",
) -> dict[str, Any]:
    """生成逐站率定验证报告。确定性。"""
    # 加载配置（支持相对路径 → 绝对路径自动解析）
    from workflows._shared import resolve_config_paths
    if config_path:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
    else:
        default_cfg = BASE_DIR / "configs" / f"{case_id}.yaml"
        if default_cfg.exists():
            with open(default_cfg) as f:
                cfg = yaml.safe_load(f)
        else:
            cfg = {"case_id": case_id}
    cfg = resolve_config_paths(cfg, WORKSPACE)

    # 定位数据库
    hydromind_db = _find_supported_db(cfg)
    if not hydromind_db:
        return {
            "error": "No supported hydrology database found",
            "business_status_zh": "当前案例缺少可用于率定报告的时序数据库。",
            "recommended_next_action": "请提供包含 timeseries 或 observations 表的 .sqlite/.sqlite3/.db 文件后重试。",
        }

    targets, station_rows = _discover_station_targets(hydromind_db, cfg)

    # 逐站率定
    station_reports = []
    print(f"{'站点':8s} {'数据':>6s} {'时段':14s} {'率定NSE':>8s} {'验证NSE':>8s} {'率定级':>6s} {'验证级':>6s} {'一致性'}")
    print("-" * 80)

    # 搜索库容曲线文件
    zv_curves = _find_zv_curves(cfg.get("scan_dirs", []))

    for target in targets:
        sid = target["station_id"]
        station_name = target["station_name"]
        clean_name = station_name.replace("一级", "").replace("二级", "").strip()
        # 自动选模型：有库容曲线→reservoir，否则→muskingum
        has_zv = clean_name in zv_curves or station_name in zv_curves
        if model_type == "auto":
            use_model = "reservoir" if has_zv else "muskingum"
        else:
            use_model = model_type

        zv = zv_curves.get(clean_name) or zv_curves.get(station_name)
        result = calibrate_station(
            db_path=hydromind_db,
            station_id=sid,
            station_name=clean_name,
            model_type=use_model,
            zv_curve=zv,
            input_series=target.get("input_series"),
            observed_series=target.get("observed_series"),
            timestamps=target.get("timestamps"),
            data_binding=target.get("data_binding"),
        )
        station_reports.append(result)

        if result["status"] == "completed":
            cal = result["calibration"]
            val = result["validation"]
            assess = result["assessment"]
            print(f"{result['station_name']:8s} {result['data_count']:6d} {result['period']:14s} "
                  f"{cal['nse']:8.3f} {val['nse']:8.3f} {cal['grade']:>6s} {val['grade']:>6s} "
                  f"{assess.get('consistency', '')}")
        else:
            print(f"{result['station_name']:8s} {result.get('data_count', 0):6d} {result['status']}")

    # 流域划分精度
    delin_path = WORKSPACE / "cases" / case_id / "contracts" / "delineation.latest.json"
    delin_eval = None
    if delin_path.exists():
        delin = _load_json(delin_path)
        expected_areas = {}
        for station in station_rows:
            sid = station["id"]
            name = station["name"]
            area = station.get("basin_area_km2")
            if area:
                clean = name.replace("一级", "").replace("二级", "").strip()
                expected_areas[clean] = area
        delin_eval = evaluate_delineation(delin["basins"], expected_areas)
        print(f"\n流域划分: {delin_eval.grade} (闭合{delin_eval.closure_ratio:.3f}, 最大误差{delin_eval.max_relative_error:.2%})")

    # 综合报告
    hydro_evals = []
    for r in station_reports:
        if r["status"] == "completed":
            # 构造 TimeseriesAccuracy 用于综合评定
            cal_eval = evaluate_timeseries(
                np.array([0]), np.array([0]),  # placeholder
                r["station_name"], r["station_name"], "calibration"
            )
            cal_eval.metrics = r["calibration"]
            cal_eval.grade = r["calibration"]["grade"]
            hydro_evals.append(cal_eval)

    report_obj = PrecisionReport(
        case_id=case_id, delineation=delin_eval, hydrology=hydro_evals,
    )
    overall = report_obj.compute_overall()
    print(f"\n综合评定: {overall}")

    # 保存报告
    report = {
        "case_id": case_id,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "model_type": model_type,
        "stations": station_reports,
        "delineation": {
            "grade": delin_eval.grade if delin_eval else None,
            "closure_ratio": delin_eval.closure_ratio if delin_eval else None,
            "stations": delin_eval.stations if delin_eval else [],
        } if delin_eval else None,
        "overall_grade": overall,
    }

    output_path = WORKSPACE / "cases" / case_id / "contracts" / "calibration_report.latest.json"
    _write_json(output_path, report)
    evidence_path = WORKSPACE / "cases" / case_id / "contracts" / "hydrology_nse_evidence.latest.json"
    _write_json(evidence_path, _build_hydrology_nse_evidence(case_id, station_reports))
    print(f"\nReport: {output_path}")
    return report


def main():
    parser = argparse.ArgumentParser(description="逐站率定验证报告")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--model-type", default="auto", choices=["auto", "muskingum", "reservoir"])
    args = parser.parse_args()
    report = run_report(args.case_id, args.config, args.model_type)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
