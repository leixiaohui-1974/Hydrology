#!/usr/bin/env python3
"""率定 (LuDing) — 参数校准与自学习

HydroMind 水智工坊 · Agent #5

水力学历史率定验证 + 自提升工作流 (产品化)。

调用通用产品模块完成：
  - hydro_model.reservoir_balance: 逐站水库水量平衡率定
  - hydro_model.report_md: 自动生成 D2 精度报告 (Markdown)

配置驱动，零硬编码。新案例只需 YAML + 数据，零代码修改。

Usage:
    python3 -m workflows run hyd_cal --case-id zhongxian
    python3 workflows/run_hydraulic_calibration.py --case-id zhongxian
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
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from hydro_model.reservoir_balance import (
    ReservoirBalanceModel, calibrate_station, compute_metrics,
)
from hydro_model.report_md import ReportGenerator
from workflows._shared import load_case_config, write_json, WORKSPACE, build_station_meta


def _find_db(cfg: dict) -> str | None:
    for p in cfg.get("sqlite_paths", []):
        if "hydromind" in str(p).lower() and Path(p).exists():
            return str(p)
    for scan_dir in cfg.get("scan_dirs", []):
        for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
            return str(f)
    return None


def _load_ts(db_path: str, station_id: str, variable: str) -> np.ndarray:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT time, value FROM timeseries WHERE station_id=? AND variable=? ORDER BY time",
        conn, params=[station_id, variable],
    )
    conn.close()
    return df["value"].values.astype(float) if not df.empty else np.array([])


def _get_station_meta(cfg: dict) -> dict[str, dict]:
    """从配置获取站点元信息，全部来自 knowledge.reservoirs。"""
    meta = build_station_meta(cfg)
    result = {}
    for sid, m in meta.items():
        v = m.get("vars", ["H_up", "Q_in", "Q_out"])
        result[sid] = {
            "name": m.get("name", sid),
            "h_var": v[0] if len(v) > 0 else "H_up",
            "q_in_var": v[1] if len(v) > 1 else "Q_in",
            "q_out_var": v[2] if len(v) > 2 else "Q_out",
        }
    return result


def calibrate_and_validate(
    case_id: str,
    config_path: str | None = None,
    cal_ratio: float = 0.7,
    target_nse: float = 0.85,
    generate_report: bool = True,
) -> dict[str, Any]:
    """水力学历史率定验证主入口（产品化）。"""
    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "No hydromind SQLite found"}

    station_meta = _get_station_meta(cfg)

    # 1. Load data
    print("=== 加载历史数据 ===")
    data: dict[str, dict] = {}
    for sid, meta in station_meta.items():
        h = _load_ts(db_path, sid, meta["h_var"])
        q_in = _load_ts(db_path, sid, meta["q_in_var"])
        q_out = _load_ts(db_path, sid, meta["q_out_var"])
        if len(h) > 100:
            data[sid] = {"h": h, "q_in": q_in, "q_out": q_out, **meta}
            print(f"  {sid} ({meta['name']}): H=[{h.min():.1f},{h.max():.1f}]m "
                  f"Q_in={len(q_in)} Q_out={len(q_out)}")
        else:
            print(f"  {sid} ({meta['name']}): 数据不足")

    # 2. Per-station calibration using product module
    print("\n=== 逐站水库水量平衡率定 ===")
    station_results: dict[str, dict] = {}
    for sid, sdata in data.items():
        h, q_in, q_out = sdata["h"], sdata["q_in"], sdata["q_out"]
        print(f"\n  {sid} ({sdata['name']}):")

        result = calibrate_station(
            Q_in=q_in, Q_out=q_out, H_obs=h,
            cal_ratio=cal_ratio,
            target_nse=target_nse,
            auto_improve=True,
        )

        if result["status"] != "completed":
            print(f"    失败: {result.get('status')}")
            station_results[sid] = result
            continue

        cal_m = result["cal_metrics"]
        val_m = result["val_metrics"]
        print(f"    率定: NSE={cal_m['nse']:.4f} RMSE={cal_m['rmse']:.3f}m ({result['phases_used']})")
        print(f"    验证: NSE={val_m['nse']:.4f} RMSE={val_m['rmse']:.3f}m")
        print(f"    ★ 参数: {result['model_params']}")

        station_results[sid] = {
            "name": sdata["name"],
            "calibration": {"best": {**result["cal_metrics"], **result["model_params"]}},
            "validation": result["val_metrics"],
            "model_params": result["model_params"],
            "phases_used": result["phases_used"],
            "n_cal": result["n_cal"],
            "n_val": result["n_val"],
        }

    # 3. Steady-state summary
    print("\n=== 稳态水位统计 ===")
    steady_metrics: dict[str, dict] = {}
    for sid, sdata in data.items():
        h_mean = float(np.mean(sdata["h"]))
        q_mean = float(np.mean(np.abs(sdata["q_in"][:len(sdata["h"])])))
        steady_metrics[sid] = {
            "name": sdata["name"],
            "obs_mean_level": h_mean,
            "obs_mean_Q": q_mean,
            "obs_range": [float(sdata["h"].min()), float(sdata["h"].max())],
        }
        print(f"  {sid} ({sdata['name']}): H_mean={h_mean:.1f}m Q_mean={q_mean:.0f}m³/s")

    # 4. Build summary
    cal_nses = [sr["calibration"]["best"]["nse"]
                for sr in station_results.values()
                if isinstance(sr, dict) and "calibration" in sr]
    val_nses = [sr["validation"]["nse"]
                for sr in station_results.values()
                if isinstance(sr, dict) and "validation" in sr
                and isinstance(sr["validation"].get("nse"), (int, float))]

    summary = {
        "n_stations_calibrated": len(cal_nses),
        "avg_cal_nse": float(np.mean(cal_nses)) if cal_nses else None,
        "avg_val_nse": float(np.mean(val_nses)) if val_nses else None,
        "avg_cal_rmse": float(np.mean([
            sr["calibration"]["best"]["rmse"]
            for sr in station_results.values()
            if isinstance(sr, dict) and "calibration" in sr
        ])) if cal_nses else None,
    }

    print(f"\n=== 总结 ===")
    print(f"  站点数: {summary['n_stations_calibrated']}")
    print(f"  平均率定 NSE: {summary.get('avg_cal_nse')}")
    print(f"  平均验证 NSE: {summary.get('avg_val_nse')}")

    # 5. Write JSON contract
    contract = {
        "case_id": case_id,
        "workflow": "hydraulic_calibration_validation",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "station_results": station_results,
        "steady_metrics": steady_metrics,
        "summary": summary,
        "_auto_generated": True,
    }
    json_path = WORKSPACE / "cases" / case_id / "contracts" / "hydraulic_calibration.latest.json"
    write_json(json_path, contract)
    print(f"  合约: {json_path}")

    # 6. Generate D2 Markdown report
    if generate_report:
        gen = ReportGenerator(case_id=case_id, dimension="D2",
                              title=f"D2 水力学精度评价报告 — {case_id}")
        md_content = gen.build(
            station_results=station_results,
            steady_metrics=steady_metrics,
            summary=summary,
            methodology="",
        )
        md_path = WORKSPACE / "cases" / case_id / "contracts" / "D2_hydraulic_report.md"
        gen.write(md_path)
        print(f"  MD报告: {md_path}")

    return contract


def main():
    parser = argparse.ArgumentParser(description="水力学历史率定验证工作流 (产品化)")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--cal-ratio", type=float, default=0.7)
    parser.add_argument("--target-nse", type=float, default=0.85)
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()

    calibrate_and_validate(
        case_id=args.case_id,
        config_path=args.config,
        cal_ratio=args.cal_ratio,
        target_nse=args.target_nse,
        generate_report=not args.no_report,
    )


if __name__ == "__main__":
    main()
