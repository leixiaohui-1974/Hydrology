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
from typing import Any

import numpy as np
import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))

from hydro_model.calibration import CalibrationConfig, run_full_cv
from hydro_model.precision_evaluation import (
    PrecisionReport, evaluate_delineation, evaluate_timeseries,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def load_station_timeseries(
    db_path: str | Path,
    station_id: str,
    variable: str,
    time_step: str = "1D",
) -> tuple[np.ndarray, list[str]]:
    """从 SQLite 加载站点时序数据。返回 (values, timestamps)。"""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT time, value FROM timeseries WHERE station_id=? AND variable=? AND time_step=? ORDER BY time",
        (station_id, variable, time_step),
    ).fetchall()
    conn.close()
    if not rows:
        return np.array([]), []
    return np.array([r[1] for r in rows], dtype=float), [r[0] for r in rows]


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
) -> dict[str, Any]:
    """对单站进行率定验证。确定性。"""
    q_in, ts_in = load_station_timeseries(db_path, station_id, "Q_in_reservoir", "1D")
    q_out, ts_out = load_station_timeseries(db_path, station_id, "Q_out_reservoir", "1D")

    if len(q_in) < 100 or len(q_out) < 100:
        return {
            "station_id": station_id, "station_name": station_name,
            "status": "insufficient_data",
            "data_count": min(len(q_in), len(q_out)),
        }

    min_len = min(len(q_in), len(q_out))
    q_in, q_out = q_in[:min_len], q_out[:min_len]
    period = f"{ts_in[0][:10]}~{ts_in[min_len-1][:10]}"

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
    db_paths = cfg.get("sqlite_paths", [])
    hydromind_db = None
    for p in db_paths:
        if "hydromind" in str(p) and Path(p).exists():
            hydromind_db = p
            break
    if not hydromind_db:
        # 搜索
        for scan_dir in cfg.get("scan_dirs", []):
            for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
                hydromind_db = str(f)
                break

    if not hydromind_db:
        return {"error": "No hydromind database found"}

    # 站点映射
    conn = sqlite3.connect(hydromind_db)
    stations = conn.execute(
        "SELECT id, name, basin_area_km2, metadata_json FROM stations WHERE station_type='hydropower_station'"
    ).fetchall()
    conn.close()

    # 逐站率定
    station_reports = []
    print(f"{'站点':8s} {'数据':>6s} {'时段':14s} {'率定NSE':>8s} {'验证NSE':>8s} {'率定级':>6s} {'验证级':>6s} {'一致性'}")
    print("-" * 80)

    # 搜索库容曲线文件
    zv_curves = _find_zv_curves(cfg.get("scan_dirs", []))

    for sid, name, area, meta_json in stations:
        clean_name = name.replace("一级", "").replace("二级", "").strip()
        # 自动选模型：有库容曲线→reservoir，否则→muskingum
        has_zv = clean_name in zv_curves or name in zv_curves
        if model_type == "auto":
            use_model = "reservoir" if has_zv else "muskingum"
        else:
            use_model = model_type

        zv = zv_curves.get(clean_name) or zv_curves.get(name)
        result = calibrate_station(
            db_path=hydromind_db,
            station_id=sid,
            station_name=clean_name,
            model_type=use_model,
            zv_curve=zv,
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
        for sid, name, area, _ in stations:
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
