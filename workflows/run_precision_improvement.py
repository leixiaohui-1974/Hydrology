#!/usr/bin/env python3
"""率定 (LuDing) — 参数校准与自学习

HydroMind 水智工坊 · Agent #5

精度自提升工作流：基于既有率定报告，对薄弱站点尝试更高分辨率与多模型率定。

步骤:
  1. load_report   — 读取 calibration_report.latest.json
  2. diagnose      — NSE < threshold 的验证期薄弱站
  3. mine_data     — 检索 1H 时序是否可用
  4. multi_calibrate — 模型×分辨率组合率定
  5. select_best   — 验证期 NSE 最优
  6. report        — 写入 precision_improvement.latest.json

Usage:
    python3 run_precision_improvement.py --case-id zhongxian
    python3 run_precision_improvement.py --case-id zhongxian --threshold 0.80
    python3 run_precision_improvement.py --case-id zhongxian --max-rounds 3
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from hydro_model.calibration import CalibrationConfig, run_full_cv
from hydro_model.curve_calibration import interp1d_linear
from workflows._shared import load_case_config, write_json, WORKSPACE
from workflows.run_calibration_report import _find_zv_curves, load_station_timeseries

# ── 常量 ──────────────────────────────────────────────────────────────────────

UNIT_VOL = 1e8
DT_DAY = 86400.0
DT_HOUR = 3600.0
MIN_POINTS_DAILY = 100
MIN_POINTS_HOURLY = 500
LAG_DAYS_OPTIONS = (0, 1, 2, 3, 5, 8)


# ── 数据库 ──────────────────────────────────────────────────────────────────


def _find_hydromind_sqlite(cfg: dict[str, Any]) -> str | None:
    for p in cfg.get("sqlite_paths", []):
        if "hydromind" in str(p).lower() and Path(p).exists():
            return str(p)
    for scan_dir in cfg.get("scan_dirs", []):
        for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
            return str(f)
    return None


# ── 模型工厂 ─────────────────────────────────────────────────────────────────


def _make_muskingum_model() -> tuple[Callable, dict[str, tuple]]:
    from hydro_model.routing import MuskingumRouting

    def model_fn(params, input_data):
        routing = MuskingumRouting(K=params["K"], x=params["x"])
        result = np.zeros(len(input_data))
        for i in range(len(input_data)):
            result[i] = routing.run(float(input_data[i]))
        return result

    param_space = {"K": (0.5, 5.0, 12), "x": (0.0, 0.4, 12)}
    return model_fn, param_space


def _make_reservoir_basic_model(
    zv_x: np.ndarray, zv_y: np.ndarray, dt_sec: float
) -> tuple[Callable, dict[str, tuple]]:
    z_mid = zv_x[len(zv_x) // 2]
    z_min, z_max = float(zv_x[0]), float(zv_x[-1])
    v_min = interp1d_linear(zv_x, zv_y, z_min)
    v_max = interp1d_linear(zv_x, zv_y, z_max)

    def model_fn(params, input_data):
        alpha = params["alpha"]
        beta = params["beta"]
        z_target = params["z_target"]
        n = len(input_data)
        outflow = np.zeros(n)
        z = z_mid
        v = interp1d_linear(zv_x, zv_y, z)

        for t in range(n):
            inflow = float(input_data[t])
            z_bias = z - z_target
            o_target = max(0.0, alpha * inflow + beta * z_bias * UNIT_VOL / dt_sec)
            dv = (inflow - o_target) * dt_sec / UNIT_VOL
            v_new = v + dv
            if v_new < v_min:
                o_target = max(0.0, inflow - (v_min - v) * UNIT_VOL / dt_sec)
                v_new = v_min
            elif v_new > v_max:
                o_target = inflow + (v_new - v_max) * UNIT_VOL / dt_sec
                v_new = v_max
            outflow[t] = o_target
            v = v_new
            z = interp1d_linear(zv_y, zv_x, v)
        return outflow

    param_space = {
        "alpha": (0.85, 1.05, 12),
        "beta": (0.1, 5.0, 12),
        "z_target": (float(z_mid) - 15.0, float(z_mid) + 15.0, 12),
    }
    return model_fn, param_space


def _lag_steps_for_resolution(lag_days: int, dt_sec: float) -> int:
    if dt_sec >= DT_DAY * 0.5:
        return int(lag_days)
    steps_per_day = int(round(DT_DAY / dt_sec))
    return int(lag_days * steps_per_day)


def _make_reservoir_lagged_model(
    zv_x: np.ndarray, zv_y: np.ndarray, dt_sec: float, lag_days: int
) -> Callable:
    z_mid = zv_x[len(zv_x) // 2]
    z_min, z_max = float(zv_x[0]), float(zv_x[-1])
    v_min = interp1d_linear(zv_x, zv_y, z_min)
    v_max = interp1d_linear(zv_x, zv_y, z_max)
    lag = _lag_steps_for_resolution(lag_days, dt_sec)

    def model_fn(params, input_data):
        alpha = params["alpha"]
        beta = params["beta"]
        z_target = params["z_target"]
        n = len(input_data)
        outflow = np.zeros(n)
        z = z_mid
        v = interp1d_linear(zv_x, zv_y, z)

        for t in range(n):
            inflow_idx = max(0, t - lag)
            inflow_lagged = float(input_data[inflow_idx])
            z_bias = z - z_target
            o_target = max(
                0.0, alpha * inflow_lagged + beta * z_bias * UNIT_VOL / dt_sec
            )
            cur_in = float(input_data[t])
            dv = (cur_in - o_target) * dt_sec / UNIT_VOL
            v_new = v + dv
            if v_new < v_min:
                o_target = max(0.0, cur_in - (v_min - v) * UNIT_VOL / dt_sec)
                v_new = v_min
            elif v_new > v_max:
                o_target = cur_in + (v_new - v_max) * UNIT_VOL / dt_sec
                v_new = v_max
            outflow[t] = o_target
            v = v_new
            z = interp1d_linear(zv_y, zv_x, v)
        return outflow

    return model_fn


def _reservoir_lagged_param_space(zv_x: np.ndarray) -> dict[str, tuple]:
    z_mid = float(zv_x[len(zv_x) // 2])
    return {
        "alpha": (0.85, 1.05, 12),
        "beta": (0.1, 5.0, 12),
        "z_target": (z_mid - 15.0, z_mid + 15.0, 12),
    }


# ── 工作流步骤 ────────────────────────────────────────────────────────────────


def step_load_report(case_id: str) -> dict[str, Any]:
    path = WORKSPACE / "cases" / case_id / "contracts" / "calibration_report.latest.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing calibration report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def step_diagnose(report: dict[str, Any], threshold: float) -> list[dict[str, Any]]:
    weak: list[dict[str, Any]] = []
    for st in report.get("stations", []):
        if st.get("status") != "completed":
            continue
        val = st.get("validation") or {}
        nse = float(val.get("nse", float("nan")))
        if np.isnan(nse) or nse >= threshold:
            continue
        weak.append(st)
    return weak


def step_mine_data(
    db_path: str,
    station_id: str,
) -> list[str]:
    """返回该站可用的 time_step 列表（满足最小长度），始终包含 1D 若可用。"""
    available: list[str] = []
    q_in_d, _ = load_station_timeseries(db_path, station_id, "Q_in_reservoir", "1D")
    q_out_d, _ = load_station_timeseries(db_path, station_id, "Q_out_reservoir", "1D")
    if len(q_in_d) >= MIN_POINTS_DAILY and len(q_out_d) >= MIN_POINTS_DAILY:
        available.append("1D")

    for qin_var, qout_var in [("Q_in_reservoir", "Q_out_reservoir"), ("Q_in", "Q_out")]:
        q_in_h, _ = load_station_timeseries(db_path, station_id, qin_var, "1H")
        q_out_h, _ = load_station_timeseries(db_path, station_id, qout_var, "1H")
        if len(q_in_h) >= MIN_POINTS_HOURLY and len(q_out_h) >= MIN_POINTS_HOURLY:
            available.append("1H")
            break

    return available


def _align_series(
    db_path: str, station_id: str, time_step: str
) -> tuple[np.ndarray, np.ndarray] | None:
    q_in, q_out = np.array([]), np.array([])
    for qin_var, qout_var in [("Q_in_reservoir", "Q_out_reservoir"), ("Q_in", "Q_out")]:
        q_in, _ = load_station_timeseries(db_path, station_id, qin_var, time_step)
        q_out, _ = load_station_timeseries(db_path, station_id, qout_var, time_step)
        if len(q_in) > 0 and len(q_out) > 0:
            break
    n = min(len(q_in), len(q_out))
    if n < (MIN_POINTS_DAILY if time_step == "1D" else MIN_POINTS_HOURLY):
        return None
    return q_in[:n].astype(float), q_out[:n].astype(float)


def _run_one_calibration(
    model_fn: Callable,
    param_space: dict[str, tuple],
    q_in: np.ndarray,
    q_out: np.ndarray,
    cal_ratio: float,
    progressive_rounds: int,
) -> dict[str, Any] | None:
    try:
        return run_full_cv(
            model_fn=model_fn,
            observed=q_out,
            param_space=param_space,
            input_data=q_in,
            config=CalibrationConfig(objective="nse", cal_ratio=cal_ratio),
            progressive_rounds=progressive_rounds,
        )
    except Exception:
        return None


def step_multi_calibrate(
    db_path: str,
    station_entry: dict[str, Any],
    resolutions: list[str],
    zv_curve: tuple[np.ndarray, np.ndarray] | None,
    progressive_rounds: int,
    cal_ratio: float = 0.7,
) -> list[dict[str, Any]]:
    """返回所有成功组合的列表，每项含 model, resolution, nse_val, best_params, raw_report。"""
    sid = station_entry["station_id"]
    results: list[dict[str, Any]] = []

    for time_step in resolutions:
        aligned = _align_series(db_path, sid, time_step)
        if aligned is None:
            continue
        q_in, q_out = aligned
        dt_sec = DT_DAY if time_step == "1D" else DT_HOUR

        # muskingum
        m_fn, p_space = _make_muskingum_model()
        rep = _run_one_calibration(
            m_fn, p_space, q_in, q_out, cal_ratio, progressive_rounds
        )
        if rep and rep.get("validation_metrics"):
            nse = float(rep["validation_metrics"].get("nse", float("-inf")))
            results.append(
                {
                    "model": "muskingum",
                    "resolution": time_step,
                    "nse_val": nse,
                    "best_params": rep.get("best_params", {}),
                    "raw": rep,
                }
            )

        if zv_curve is None:
            continue

        zx, zy = zv_curve
        # reservoir_basic
        rb_fn, rb_space = _make_reservoir_basic_model(zx, zy, dt_sec)
        rep_b = _run_one_calibration(
            rb_fn, rb_space, q_in, q_out, cal_ratio, progressive_rounds
        )
        if rep_b and rep_b.get("validation_metrics"):
            nse_b = float(rep_b["validation_metrics"].get("nse", float("-inf")))
            results.append(
                {
                    "model": "reservoir_basic",
                    "resolution": time_step,
                    "nse_val": nse_b,
                    "best_params": rep_b.get("best_params", {}),
                    "raw": rep_b,
                }
            )

        # reservoir_lagged: 离散 lag，对每种 lag 做 progressive 率定
        lag_space = _reservoir_lagged_param_space(zx)
        for lag_d in LAG_DAYS_OPTIONS:
            rl_fn = _make_reservoir_lagged_model(zx, zy, dt_sec, lag_d)
            rep_l = _run_one_calibration(
                rl_fn, lag_space, q_in, q_out, cal_ratio, progressive_rounds
            )
            if rep_l and rep_l.get("validation_metrics"):
                nse_l = float(rep_l["validation_metrics"].get("nse", float("-inf")))
                params = dict(rep_l.get("best_params", {}))
                params["lag"] = float(lag_d)
                results.append(
                    {
                        "model": "reservoir_lagged",
                        "resolution": time_step,
                        "nse_val": nse_l,
                        "best_params": params,
                        "raw": rep_l,
                    }
                )

    return results


def step_select_best(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return max(candidates, key=lambda x: x["nse_val"])


def _clean_station_name(name: str) -> str:
    return name.replace("一级", "").replace("二级", "").strip()


def _resolve_zv(
    station_name: str, zv_curves: dict[str, tuple]
) -> tuple[np.ndarray, np.ndarray] | None:
    clean = _clean_station_name(station_name)
    zv = zv_curves.get(clean) or zv_curves.get(station_name)
    return zv


def run_precision_improvement(
    case_id: str,
    threshold: float = 0.75,
    max_rounds: int = 3,
    config_path: str | None = None,
    cal_ratio: float = 0.7,
) -> dict[str, Any]:
    try:
        from workflows.run_knowledge_registry import should_run as _should_run
        check = _should_run(case_id, "improve", dimension="D1_hydrology", target_nse=threshold)
        if not check["should_run"]:
            print(f"\n[去重保护] {check['reason']}")
            return {"case_id": case_id, "skipped": True, "reason": check["reason"]}
    except ImportError:
        pass

    report = step_load_report(case_id)
    weak_stations = step_diagnose(report, threshold)
    cfg = load_case_config(case_id, config_path)
    db_path = _find_hydromind_sqlite(cfg)
    if not db_path:
        raise RuntimeError("No hydromind SQLite database found in case config.")

    zv_curves = _find_zv_curves(cfg.get("scan_dirs", []))

    diagnosed = []
    for st in weak_stations:
        diagnosed.append(
            {
                "station_id": st["station_id"],
                "station_name": st["station_name"],
                "validation_nse": float((st.get("validation") or {}).get("nse", 0.0)),
                "model_type": st.get("model_type"),
            }
        )

    improvements: list[dict[str, Any]] = []

    for st in weak_stations:
        sid = st["station_id"]
        sname = st["station_name"]
        orig_val = st.get("validation") or {}
        original_nse = float(orig_val.get("nse", float("nan")))
        original_model = st.get("model_type", "muskingum")

        resolutions = step_mine_data(db_path, sid)
        if not resolutions:
            improvements.append(
                {
                    "station_id": sid,
                    "station_name": sname,
                    "original": {
                        "model": original_model,
                        "resolution": "1D",
                        "nse_val": original_nse,
                    },
                    "improved": None,
                    "delta_nse": None,
                    "note": "no_usable_timeseries",
                    "available_resolutions": [],
                }
            )
            continue

        zv = _resolve_zv(sname, zv_curves)
        candidates = step_multi_calibrate(
            db_path,
            st,
            resolutions,
            zv,
            progressive_rounds=max_rounds,
            cal_ratio=cal_ratio,
        )
        best = step_select_best(candidates)

        if best is None:
            improvements.append(
                {
                    "station_id": sid,
                    "station_name": sname,
                    "original": {
                        "model": original_model,
                        "resolution": "1D",
                        "nse_val": original_nse,
                    },
                    "improved": None,
                    "delta_nse": None,
                    "note": "calibration_failed_all_combos",
                    "available_resolutions": resolutions,
                }
            )
            continue

        improved_nse = best["nse_val"]
        improvements.append(
            {
                "station_id": sid,
                "station_name": sname,
                "original": {
                    "model": original_model,
                    "resolution": "1D",
                    "nse_val": original_nse,
                },
                "improved": {
                    "model": best["model"],
                    "resolution": best["resolution"],
                    "nse_val": improved_nse,
                    "best_params": best["best_params"],
                },
                "delta_nse": float(improved_nse - original_nse),
                "available_resolutions": resolutions,
                "candidates_tried": len(candidates),
            }
        )

    # overall_improvement
    deltas = [
        float(r["delta_nse"])
        for r in improvements
        if r.get("delta_nse") is not None
    ]
    nse_before_all = [float(d["validation_nse"]) for d in diagnosed]
    after = [
        float(r["improved"]["nse_val"])
        for r in improvements
        if r.get("improved") is not None
    ]
    improved_count = sum(1 for d in deltas if d > 0)

    overall_improvement: dict[str, Any] = {
        "weak_station_count": len(weak_stations),
        "with_solution_count": len(after),
        "improved_count": improved_count,
        "mean_nse_before": float(np.mean(nse_before_all)) if nse_before_all else None,
        "mean_nse_after": float(np.mean(after)) if after else None,
        "mean_delta_nse": float(np.mean(deltas)) if deltas else None,
    }

    out_payload = {
        "case_id": case_id,
        "threshold": threshold,
        "max_rounds": max_rounds,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "diagnosed_weak_stations": diagnosed,
        "improvements": improvements,
        "overall_improvement": overall_improvement,
    }

    out_path = WORKSPACE / "cases" / case_id / "contracts" / "precision_improvement.latest.json"
    write_json(out_path, out_payload)
    print(f"Wrote {out_path}")
    return out_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="精度自提升工作流")
    parser.add_argument("--case-id", required=True, help="Case 标识，对应 configs/{case_id}.yaml")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.75,
        help="验证期 NSE 低于该阈值视为薄弱站（默认 0.75）",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=3,
        help="run_full_cv 的 progressive_rounds（默认 3）",
    )
    parser.add_argument("--config", default=None, help="可选 YAML 配置路径")
    args = parser.parse_args()

    payload = run_precision_improvement(
        case_id=args.case_id,
        threshold=args.threshold,
        max_rounds=args.max_rounds,
        config_path=args.config,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
