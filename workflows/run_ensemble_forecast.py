#!/usr/bin/env python3
"""预见 (Yujian) — 智能预报与预警

HydroMind 水智工坊 · Agent #7

嵌套集合预报工作流 — 流域管理级产品。

长中短嵌套预报：
  短期 (0-24h): LSTM + Transformer + 水库水量平衡
  中期 (1-7d):  Transformer + TimesFM + 水文模型
  长期 (7-30d): TimesFM + 气候统计

集合方法：
  - 多模型加权平均（RMSE 反比 / BMA）
  - 不确定性量化（模型间方差 + MC-Dropout）
  - 置信区间（50%/80%/95%）
  - 可靠性评价（PIT/CRPS/覆盖率/锐度）

Usage:
    python3 workflows/run_ensemble_forecast.py --case-id zhongxian
    python3 workflows/run_ensemble_forecast.py --case-id zhongxian --horizons short,medium
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

from workflows._shared import load_case_config, write_json, WORKSPACE, get_station_ids


def _find_db(cfg: dict) -> str | None:
    for p in cfg.get("sqlite_paths", []):
        if "hydromind" in str(p).lower() and Path(p).exists():
            return str(p)
    for scan_dir in cfg.get("scan_dirs", []):
        for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
            return str(f)
    return None


def _load_ts(db_path: str, sid: str, var: str) -> np.ndarray:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT value FROM timeseries WHERE station_id=? AND variable=? ORDER BY time",
        conn, params=[sid, var],
    )
    conn.close()
    return df["value"].values.astype(float) if not df.empty else np.array([])


def _run_reservoir_balance(
    q_in: np.ndarray, q_out: np.ndarray, h_obs: np.ndarray,
    cal_ratio: float = 0.7,
) -> dict[str, Any]:
    """水库水量平衡预测（物理模型成员）。"""
    try:
        from hydro_model.reservoir_balance import calibrate_station
        result = calibrate_station(q_in, q_out, h_obs, cal_ratio=cal_ratio)
        if result["status"] == "completed":
            model = result["model"]
            n = len(h_obs)
            n_cal = int(n * cal_ratio)
            h_sim = model.simulate(q_in[n_cal:], q_out[n_cal:], float(h_obs[n_cal]))
            return {"predictions": h_sim, "metrics": result["val_metrics"],
                    "status": "ok", "model_type": "reservoir_balance"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    return {"status": "failed"}


def _run_climatology(h_obs: np.ndarray, horizon: int) -> dict[str, Any]:
    """气候统计学预测（基线成员）。"""
    h_mean = float(np.mean(h_obs))
    h_std = float(np.std(h_obs))
    preds = np.full(horizon, h_mean)
    return {
        "predictions": preds,
        "metrics": {"rmse": h_std, "nse": 0.0},
        "status": "ok",
        "model_type": "climatology",
        "h_mean": h_mean,
        "h_std": h_std,
    }


def _run_dl_model(
    data: dict[str, np.ndarray],
    target_var: str,
    model_type: str,
    seq_len: int,
    horizon: int,
    epochs: int = 20,
) -> dict[str, Any]:
    """DL 模型预测成员。"""
    try:
        from hydro_model.dl_forecast import build_model, ForecastConfig
        from hydro_model.dl_forecast.dataset import TimeSeriesDataset
        from hydro_model.dl_forecast.evaluator import ForecastEvaluator

        n = min(len(v) for v in data.values())
        n_test = int(n * 0.15)
        n_val = int(n * 0.15)
        n_train = n - n_val - n_test

        data_train = {k: v[:n_train] for k, v in data.items()}
        data_val = {k: v[n_train:n_train + n_val] for k, v in data.items()}
        data_test = {k: v[n_train + n_val:] for k, v in data.items()}

        train_ds = TimeSeriesDataset.from_arrays(
            data_train, target_var, seq_len=seq_len, horizon=horizon)
        val_ds = TimeSeriesDataset.from_arrays(
            data_val, target_var, seq_len=seq_len, horizon=horizon)
        test_ds = TimeSeriesDataset.from_arrays(
            data_test, target_var, seq_len=seq_len, horizon=horizon)

        cfg = ForecastConfig(
            model_type=model_type, seq_len=seq_len, horizon=horizon,
            epochs=epochs, patience=8,
        )
        model = build_model(cfg)
        model.fit(train_ds, val_ds)

        preds = model.predict(test_ds)
        targets = test_ds.get_targets()
        metrics = ForecastEvaluator.compute_all(targets, preds)

        return {
            "predictions": preds,
            "metrics": metrics,
            "status": "ok",
            "model_type": model_type,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_ensemble_forecast(
    case_id: str,
    station_ids: list[str] | None = None,
    horizons: list[str] | None = None,
    config_path: str | None = None,
    epochs: int = 20,
) -> dict[str, Any]:
    """集合预报主入口。"""
    from hydro_model.dl_forecast.ensemble import (
        HORIZON_PRESETS, EnsembleForecaster, ReliabilityEvaluator,
    )

    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "No database found"}

    if horizons is None:
        horizons = ["short", "medium"]
    if station_ids is None:
        station_ids = get_station_ids(cfg)

    print(f"=== 嵌套集合预报 ===")
    print(f"  Case: {case_id}")
    print(f"  Horizons: {horizons}")
    print(f"  Stations: {station_ids}")

    all_results = {}

    for sid in station_ids:
        print(f"\n{'='*60}")
        print(f"站点 {sid}")

        h = _load_ts(db_path, sid, "H_up")
        q_in = _load_ts(db_path, sid, "Q_in")
        q_out = _load_ts(db_path, sid, "Q_out")

        if len(h) < 500:
            print(f"  跳过：数据不足 ({len(h)})")
            continue

        data = {"H_up": h, "Q_in": q_in[:len(h)], "Q_out": q_out[:len(h)]}
        station_result = {}

        for hz_name in horizons:
            hz = HORIZON_PRESETS.get(hz_name)
            if hz is None:
                continue

            print(f"\n  --- {hz.label} ---")
            ensemble = EnsembleForecaster(
                horizons=[hz_name],
                quantiles=[0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975],
            )

            for mt in hz.model_types:
                print(f"    [{mt}] ", end="", flush=True)

                if mt == "reservoir_balance":
                    r = _run_reservoir_balance(q_in[:len(h)], q_out[:len(h)], h)
                elif mt == "climatology":
                    r = _run_climatology(h, hz.horizon_hours)
                elif mt in ("lstm", "transformer", "timesfm"):
                    r = _run_dl_model(
                        data, "H_up", mt,
                        seq_len=hz.seq_len, horizon=hz.horizon_hours,
                        epochs=epochs,
                    )
                elif mt == "hydrology":
                    r = _run_climatology(h, hz.horizon_hours)
                    r["model_type"] = "hydrology_placeholder"
                else:
                    r = {"status": "unknown_model"}

                if r.get("status") == "ok":
                    metrics = r.get("metrics", {})
                    nse = metrics.get("nse", float("-inf"))
                    rmse = metrics.get("rmse", float("inf"))
                    print(f"NSE={nse:.4f} RMSE={rmse:.3f}")
                    preds = np.asarray(r["predictions"], dtype=float).reshape(-1)

                    ensemble.add_member(
                        name=f"{sid}_{hz_name}_{mt}",
                        model_type=mt,
                        horizon=hz_name,
                        predictions=preds,
                        metrics=metrics,
                    )
                else:
                    print(f"失败: {r.get('error', r.get('status'))}")

            if len(ensemble.members) >= 2:
                # 不同基模型可能给出不同长度预测，先对齐到最短长度再做集合。
                min_pred_len = min(len(m.predictions) for m in ensemble.members)
                for m in ensemble.members:
                    if len(m.predictions) != min_pred_len:
                        m.predictions = m.predictions[:min_pred_len]
                weights = ensemble.compute_weights("inverse_rmse")
                ens_result = ensemble.ensemble_forecast(weights)

                n_test = int(len(h) * 0.15)
                h_test = h[-n_test:]
                obs_for_eval = h_test[:len(ens_result["point_forecast"])]

                reliability = ReliabilityEvaluator.evaluate_all(obs_for_eval, ens_result)

                print(f"\n    ★ 集合预报:")
                det = reliability.get("deterministic", {})
                print(f"      确定性: NSE={det.get('nse', 'N/A'):.4f} RMSE={det.get('rmse', 'N/A'):.3f}")
                for ci_level in [50, 80, 95]:
                    cov_key = f"coverage_{ci_level}"
                    sharp_key = f"sharpness_{ci_level}"
                    if cov_key in reliability:
                        print(f"      {ci_level}%区间: 覆盖率={reliability[cov_key]:.1%} "
                              f"宽度={reliability[sharp_key]:.3f}m")

                station_result[hz_name] = {
                    "n_members": len(ensemble.members),
                    "weights": weights,
                    "reliability": reliability,
                    "members": [
                        {"name": m.name, "model_type": m.model_type,
                         "nse": m.metrics.get("nse"), "rmse": m.metrics.get("rmse")}
                        for m in ensemble.members
                    ],
                }
            else:
                print(f"\n    集合成员不足 ({len(ensemble.members)})")

        all_results[sid] = station_result

    # Write contract
    contract = {
        "case_id": case_id,
        "workflow": "ensemble_forecast",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "horizons": horizons,
        "station_results": all_results,
        "_auto_generated": True,
    }
    out_path = WORKSPACE / "cases" / case_id / "contracts" / "ensemble_forecast.latest.json"
    write_json(out_path, contract)
    print(f"\n报告: {out_path}")
    return contract


def main():
    parser = argparse.ArgumentParser(description="嵌套集合预报工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--horizons", default="short,medium",
                        help="预见期: short,medium,long")
    parser.add_argument("--station", default=None)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    horizons = [h.strip() for h in args.horizons.split(",")]
    stations = [args.station] if args.station else None

    run_ensemble_forecast(
        case_id=args.case_id,
        station_ids=stations,
        horizons=horizons,
        config_path=args.config,
        epochs=args.epochs,
    )


if __name__ == "__main__":
    main()
