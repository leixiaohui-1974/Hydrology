#!/usr/bin/env python3
"""率定 (LuDing) — 参数校准与自学习

HydroMind 水智工坊 · Agent #6

D2 水力学精度自提升工作流：基于水库水量平衡率定报告，
对薄弱站点尝试多分辨率×多目标×多面积模型策略矩阵率定。

六步闭环:
  1. load_report   — 读取 hydraulic_calibration.latest.json
  2. diagnose      — 验证期 NSE < threshold 的薄弱站
  3. mine_data     — 检索 1D/1H 可用性 + Z-V 曲线
  4. multi_strategy — 分辨率×目标×面积模型组合率定
  5. select_best   — 验证期 NSE 择优（防过拟合）
  6. report        — 写入 hydraulic_precision_improvement.latest.json

Usage:
    python3 run_hydraulic_precision_improvement.py --case-id zhongxian
    python3 run_hydraulic_precision_improvement.py --case-id zhongxian --threshold 0.80
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from hydro_model.reservoir_balance import calibrate_station
from workflows._shared import (
    load_case_config, write_json, WORKSPACE, build_station_meta,
)
from workflows.run_calibration_report import _find_zv_curves, load_station_timeseries

MIN_POINTS_DAILY = 100
MIN_POINTS_HOURLY = 500
DT_MAP: dict[str, float] = {"1D": 86400.0, "1H": 3600.0, "15min": 900.0}
OBJECTIVES = ("nse", "kge")
UNIT_VOL = 1e8


# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _find_db(cfg: dict[str, Any]) -> str | None:
    for p in cfg.get("sqlite_paths", []):
        if "hydromind" in str(p).lower() and Path(p).exists():
            return str(p)
    for scan_dir in cfg.get("scan_dirs", []):
        for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
            return str(f)
    return None


def _make_zv_area_curve(
    zv_x: np.ndarray, zv_y: np.ndarray,
) -> list[tuple[float, float]]:
    """从 Z-V 曲线推导 A(H) = dV/dZ (m²)。"""
    if len(zv_x) < 3:
        return []
    dz = np.diff(zv_x)
    dv = np.diff(zv_y) * UNIT_VOL
    mask = dz > 0.01
    area = np.where(mask, dv / dz, 1e4)
    area = np.maximum(area, 1e4)
    h_mid = (zv_x[:-1] + zv_x[1:]) / 2
    return list(zip(h_mid.tolist(), area.tolist()))


def _load_aligned(
    db_path: str, station_id: str,
    h_var: str, q_in_var: str, q_out_var: str,
    time_step: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    h, _ = load_station_timeseries(db_path, station_id, h_var, time_step)
    qi, _ = load_station_timeseries(db_path, station_id, q_in_var, time_step)
    qo, _ = load_station_timeseries(db_path, station_id, q_out_var, time_step)
    min_pts = MIN_POINTS_DAILY if time_step == "1D" else MIN_POINTS_HOURLY
    if len(h) < min_pts or len(qi) < min_pts or len(qo) < min_pts:
        return None
    n = min(len(h), len(qi), len(qo))
    return h[:n].astype(float), qi[:n].astype(float), qo[:n].astype(float)


def _clean_name(name: str) -> str:
    return name.replace("一级", "").replace("二级", "").strip()


def _resolve_zv(
    station_name: str, zv_curves: dict[str, tuple],
) -> tuple[np.ndarray, np.ndarray] | None:
    clean = _clean_name(station_name)
    return zv_curves.get(clean) or zv_curves.get(station_name)


# ── 六步闭环 ──────────────────────────────────────────────────────────────────


def step_load_report(case_id: str) -> dict[str, Any]:
    path = WORKSPACE / "cases" / case_id / "contracts" / "hydraulic_calibration.latest.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing hydraulic calibration report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def step_diagnose(report: dict[str, Any], threshold: float) -> list[dict[str, Any]]:
    weak: list[dict[str, Any]] = []
    for sid, sr in report.get("station_results", {}).items():
        if not isinstance(sr, dict) or "validation" not in sr:
            continue
        val = sr["validation"]
        val_nse = val.get("nse")
        if val_nse is None or float(val_nse) >= threshold:
            continue
        cal_best = sr.get("calibration", {}).get("best", {})
        param_keys = {"A_eff", "alpha", "k_area", "lag", "beta", "H_ref"}
        model_params = {k: v for k, v in cal_best.items() if k in param_keys}
        if not model_params:
            model_params = sr.get("model_params", {})
        weak.append({
            "station_id": sid,
            "station_name": sr.get("name", sid),
            "validation_nse": float(val_nse),
            "model_params": model_params,
        })
    return weak


def step_mine_data(
    db_path: str, station_id: str,
    h_var: str, q_in_var: str, q_out_var: str,
) -> list[str]:
    """返回该站可用的 time_step 列表。"""
    available: list[str] = []
    for ts, min_pts in [("1D", MIN_POINTS_DAILY), ("1H", MIN_POINTS_HOURLY)]:
        h, _ = load_station_timeseries(db_path, station_id, h_var, ts)
        qi, _ = load_station_timeseries(db_path, station_id, q_in_var, ts)
        qo, _ = load_station_timeseries(db_path, station_id, q_out_var, ts)
        if len(h) >= min_pts and len(qi) >= min_pts and len(qo) >= min_pts:
            available.append(ts)
    return available


def step_multi_strategy(
    db_path: str,
    station: dict[str, Any],
    resolutions: list[str],
    ah_curve: list[tuple[float, float]] | None,
    h_var: str, q_in_var: str, q_out_var: str,
    cal_ratio: float = 0.7,
) -> list[dict[str, Any]]:
    """策略矩阵：分辨率 × 目标 × 面积模型。"""
    sid = station["station_id"]
    results: list[dict[str, Any]] = []
    area_models = ["constant"]
    if ah_curve:
        area_models.append("zv_interp")

    for ts in resolutions:
        aligned = _load_aligned(db_path, sid, h_var, q_in_var, q_out_var, ts)
        if aligned is None:
            continue
        h, qi, qo = aligned
        dt = DT_MAP.get(ts, 3600.0)

        for obj in OBJECTIVES:
            for area_model in area_models:
                ah = ah_curve if area_model == "zv_interp" else None
                try:
                    result = calibrate_station(
                        qi, qo, h,
                        cal_ratio=cal_ratio, dt=dt,
                        auto_improve=True, target_nse=0.85,
                        objective=obj, ah_curve=ah,
                    )
                except Exception:
                    continue
                if result.get("status") != "completed":
                    continue
                results.append({
                    "resolution": ts,
                    "objective": obj,
                    "area_model": area_model,
                    "cal_nse": result["cal_metrics"]["nse"],
                    "val_nse": result["val_metrics"]["nse"],
                    "val_rmse": result["val_metrics"]["rmse"],
                    "model_params": result["model_params"],
                    "phases_used": result["phases_used"],
                })
    return results


def step_select_best(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """验证期 NSE 择优，次排序 cal-val 差值最小（防过拟合），物理约束检查。"""
    if not candidates:
        return None

    def _sort_key(c: dict[str, Any]) -> tuple[float, float, float]:
        val_nse = c["val_nse"]
        gap = abs(c["cal_nse"] - c["val_nse"])
        alpha = c["model_params"].get("alpha", 1.0)
        alpha_penalty = abs(alpha - 1.0)
        return (val_nse, -gap, -alpha_penalty)

    return max(candidates, key=_sort_key)


# ── 主入口 ────────────────────────────────────────────────────────────────────


def run_hydraulic_precision_improvement(
    case_id: str,
    threshold: float = 0.75,
    max_rounds: int = 3,
    config_path: str | None = None,
    cal_ratio: float = 0.7,
) -> dict[str, Any]:
    try:
        from workflows.run_knowledge_registry import should_run
        check = should_run(case_id, "improve", dimension="D2_hydraulics", target_nse=threshold)
        if not check["should_run"]:
            print(f"\n[去重保护] {check['reason']}")
            return {"case_id": case_id, "skipped": True, "reason": check["reason"]}
    except ImportError:
        pass

    report = step_load_report(case_id)
    weak_stations = step_diagnose(report, threshold)
    if not weak_stations:
        print(f"  D2 全站验证期 NSE >= {threshold}，无需提升")
        payload: dict[str, Any] = {
            "case_id": case_id, "threshold": threshold,
            "diagnosed_weak_stations": [], "improvements": [],
            "overall_improvement": {"weak_station_count": 0},
            "_auto_generated": True,
        }
        out_path = WORKSPACE / "cases" / case_id / "contracts" / "hydraulic_precision_improvement.latest.json"
        write_json(out_path, payload)
        return payload

    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        raise RuntimeError("No hydromind SQLite database found in case config.")

    station_meta = build_station_meta(cfg)
    zv_curves = _find_zv_curves(cfg.get("scan_dirs", []))

    improvements: list[dict[str, Any]] = []

    for ws in weak_stations:
        sid = ws["station_id"]
        sname = ws["station_name"]
        original_nse = ws["validation_nse"]
        original_params = ws["model_params"]
        print(f"\n  [{sid}] {sname} — 当前验证 NSE={original_nse:.4f}")

        meta = station_meta.get(sid, {})
        v = meta.get("vars", ["H_up", "Q_in", "Q_out"])
        h_var = v[0] if len(v) > 0 else "H_up"
        q_in_var = v[1] if len(v) > 1 else "Q_in"
        q_out_var = v[2] if len(v) > 2 else "Q_out"

        resolutions = step_mine_data(db_path, sid, h_var, q_in_var, q_out_var)
        if not resolutions:
            print(f"    无可用时序数据")
            improvements.append({
                "station_id": sid, "station_name": sname,
                "original": {"nse_val": original_nse, "model_params": original_params},
                "improved": None, "delta_nse": None,
                "note": "no_usable_timeseries",
            })
            continue
        print(f"    可用分辨率: {resolutions}")

        zv = _resolve_zv(sname, zv_curves)
        ah_curve = _make_zv_area_curve(zv[0], zv[1]) if zv else None
        if ah_curve:
            print(f"    Z-V 面积曲线: {len(ah_curve)} 点")

        candidates = step_multi_strategy(
            db_path, ws, resolutions, ah_curve,
            h_var, q_in_var, q_out_var,
            cal_ratio=cal_ratio,
        )
        print(f"    策略总数: {len(candidates)}")
        best = step_select_best(candidates)

        if best is None:
            improvements.append({
                "station_id": sid, "station_name": sname,
                "original": {"nse_val": original_nse, "model_params": original_params},
                "improved": None, "delta_nse": None,
                "note": "calibration_failed_all_combos",
            })
            continue

        delta = best["val_nse"] - original_nse
        print(f"    最优: {best['resolution']}/{best['objective']}/{best['area_model']} "
              f"NSE={best['val_nse']:.4f} (Δ={delta:+.4f})")

        improvements.append({
            "station_id": sid, "station_name": sname,
            "original": {"nse_val": original_nse, "model_params": original_params},
            "improved": {"nse_val": best["val_nse"], "model_params": best["model_params"]},
            "strategy": {
                "resolution": best["resolution"],
                "objective": best["objective"],
                "area_model": best["area_model"],
            },
            "delta_nse": delta,
            "candidates_tried": len(candidates),
        })

    deltas = [r["delta_nse"] for r in improvements if r.get("delta_nse") is not None]
    nse_before = [ws["validation_nse"] for ws in weak_stations]
    nse_after = [r["improved"]["nse_val"] for r in improvements if r.get("improved")]
    improved_count = sum(1 for d in deltas if d > 0)

    overall = {
        "weak_station_count": len(weak_stations),
        "with_solution_count": len(nse_after),
        "improved_count": improved_count,
        "mean_nse_before": float(np.mean(nse_before)) if nse_before else None,
        "mean_nse_after": float(np.mean(nse_after)) if nse_after else None,
        "mean_delta_nse": float(np.mean(deltas)) if deltas else None,
    }

    payload = {
        "case_id": case_id,
        "threshold": threshold,
        "max_rounds": max_rounds,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "diagnosed_weak_stations": [
            {"station_id": ws["station_id"], "station_name": ws["station_name"],
             "validation_nse": ws["validation_nse"]} for ws in weak_stations
        ],
        "improvements": improvements,
        "overall_improvement": overall,
        "_auto_generated": True,
    }

    out_path = WORKSPACE / "cases" / case_id / "contracts" / "hydraulic_precision_improvement.latest.json"
    write_json(out_path, payload)
    print(f"\n  合约: {out_path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="D2 水力学精度自提升工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    payload = run_hydraulic_precision_improvement(
        case_id=args.case_id,
        threshold=args.threshold,
        max_rounds=args.max_rounds,
        config_path=args.config,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
