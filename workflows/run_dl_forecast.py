#!/usr/bin/env python3
"""预见 (Yujian) — 智能预报与预警

HydroMind 水智工坊 · Agent #7

深度学习时序预测工作流 — 产品化入口。

配置驱动，支持多模型自动比选：LSTM / Transformer / TimesFM。
自动从数据库加载数据、训练、评价、保存最优模型。

Usage:
    python3 workflows/run_dl_forecast.py --case-id zhongxian
    python3 workflows/run_dl_forecast.py --case-id zhongxian --models lstm,transformer
    python3 workflows/run_dl_forecast.py --case-id zhongxian --models timesfm --station s1
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

from workflows._shared import load_case_config, write_json, WORKSPACE


def _find_db(cfg: dict) -> str | None:
    for p in cfg.get("sqlite_paths", []):
        if "hydromind" in str(p).lower() and Path(p).exists():
            return str(p)
    for scan_dir in cfg.get("scan_dirs", []):
        for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
            return str(f)
    return None


def _load_station_data(
    db_path: str, station_id: str,
    target_var: str, feature_vars: list[str],
) -> dict[str, np.ndarray]:
    conn = sqlite3.connect(db_path)
    result = {}
    all_vars = list(set([target_var] + feature_vars))
    for var in all_vars:
        df = pd.read_sql_query(
            "SELECT time, value FROM timeseries WHERE station_id=? AND variable=? ORDER BY time",
            conn, params=[station_id, var],
        )
        if not df.empty:
            result[var] = df["value"].values.astype(float)
    conn.close()
    return result


def run_dl_forecast(
    case_id: str,
    model_types: list[str] | None = None,
    station_ids: list[str] | None = None,
    config_path: str | None = None,
    forecast_config_path: str | None = None,
    epochs: int | None = None,
    seq_len: int | None = None,
    horizon: int | None = None,
) -> dict[str, Any]:
    """深度学习预测主入口。"""
    from hydro_model.dl_forecast import build_model, ForecastConfig, MODEL_REGISTRY
    from hydro_model.dl_forecast.dataset import TimeSeriesDataset
    from hydro_model.dl_forecast.evaluator import ForecastEvaluator

    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "No hydromind SQLite found"}

    # Build forecast config
    if forecast_config_path and Path(forecast_config_path).exists():
        fcfg = ForecastConfig.from_yaml(forecast_config_path)
    else:
        fcfg = ForecastConfig()

    if epochs is not None:
        fcfg.epochs = epochs
    if seq_len is not None:
        fcfg.seq_len = seq_len
    if horizon is not None:
        fcfg.horizon = horizon

    if model_types is None:
        model_types = ["lstm", "transformer"]
    if station_ids is None:
        station_ids = fcfg.station_ids

    available_models = [m for m in model_types if m in MODEL_REGISTRY]
    if not available_models:
        return {"error": f"No available models. Registry: {list(MODEL_REGISTRY.keys())}"}

    print(f"=== 深度学习时序预测 ===")
    print(f"  Case: {case_id}")
    print(f"  Models: {available_models}")
    print(f"  Stations: {station_ids}")
    print(f"  Seq: {fcfg.seq_len}h → Horizon: {fcfg.horizon}h")
    print(f"  Device: {fcfg.resolve_device()}")

    all_results: dict[str, dict] = {}

    for sid in station_ids:
        print(f"\n{'='*60}")
        print(f"站点 {sid}")
        print(f"{'='*60}")

        data = _load_station_data(
            db_path, sid, fcfg.target_var, fcfg.feature_vars,
        )
        if fcfg.target_var not in data:
            print(f"  跳过：{fcfg.target_var} 数据不存在")
            continue

        n = min(len(v) for v in data.values())
        print(f"  数据量: {n} 步")
        if n < fcfg.seq_len + fcfg.horizon + 200:
            print(f"  跳过：数据不足")
            continue

        # Split: train / val / test
        n_test = int(n * fcfg.test_ratio)
        n_val = int(n * fcfg.val_ratio)
        n_train = n - n_val - n_test

        data_train = {k: v[:n_train] for k, v in data.items()}
        data_val = {k: v[n_train:n_train + n_val] for k, v in data.items()}
        data_test = {k: v[n_train + n_val:] for k, v in data.items()}

        train_ds = TimeSeriesDataset.from_arrays(
            data_train, fcfg.target_var,
            seq_len=fcfg.seq_len, horizon=fcfg.horizon,
            station_id=sid,
        )
        val_ds = TimeSeriesDataset.from_arrays(
            data_val, fcfg.target_var,
            seq_len=fcfg.seq_len, horizon=fcfg.horizon,
            station_id=sid,
        )
        test_ds = TimeSeriesDataset.from_arrays(
            data_test, fcfg.target_var,
            seq_len=fcfg.seq_len, horizon=fcfg.horizon,
            station_id=sid,
        )

        print(f"  Train: {len(train_ds)} windows | Val: {len(val_ds)} | Test: {len(test_ds)}")

        station_results: dict[str, dict] = {}

        for model_type in available_models:
            print(f"\n  --- {model_type.upper()} ---")
            fcfg.model_type = model_type
            model = build_model(fcfg)

            try:
                train_summary = model.fit(train_ds, val_ds)
                print(f"    训练: {train_summary.get('epochs_run', 0)} epochs, "
                      f"best_val_loss={train_summary.get('best_val_loss', 'N/A')}")

                test_metrics = model.evaluate(test_ds)
                print(f"    测试: NSE={test_metrics['nse']:.4f} "
                      f"RMSE={test_metrics['rmse']:.4f} "
                      f"MAE={test_metrics['mae']:.4f}")

                per_horizon = ForecastEvaluator.compute_per_horizon(
                    test_ds.get_targets(),
                    model.predict(test_ds),
                )
                print(f"    逐步NSE: " + " | ".join(
                    f"t+{m['lead_time']}={m['nse']:.3f}"
                    for m in per_horizon[::max(1, fcfg.horizon // 6)]
                ))

                # Save model
                model_dir = WORKSPACE / "cases" / case_id / "models" / "dl_forecast"
                model_path = model_dir / f"{sid}_{model_type}.pt"
                model.save(model_path)
                print(f"    模型: {model_path}")

                station_results[model_type] = {
                    "test_metrics": test_metrics,
                    "train_summary": train_summary,
                    "per_horizon": per_horizon,
                    "model_path": str(model_path),
                }
            except Exception as e:
                print(f"    失败: {e}")
                station_results[model_type] = {"error": str(e)}

        # Pick best model
        best_model = None
        best_nse = float("-inf")
        for mt, res in station_results.items():
            if "test_metrics" in res and res["test_metrics"]["nse"] > best_nse:
                best_nse = res["test_metrics"]["nse"]
                best_model = mt

        print(f"\n  ★ 最优: {best_model} (NSE={best_nse:.4f})" if best_model else "  ★ 无有效模型")

        all_results[sid] = {
            "models": station_results,
            "best_model": best_model,
            "best_nse": best_nse,
            "n_data": n,
        }

    # Summary
    print(f"\n{'='*60}")
    print(f"=== 总结 ===")
    for sid, sr in all_results.items():
        bm = sr.get("best_model", "N/A")
        bn = sr.get("best_nse", float("-inf"))
        print(f"  {sid}: best={bm} NSE={bn:.4f}" if bn > float("-inf") else f"  {sid}: 无有效结果")

    # Write contract
    contract = {
        "case_id": case_id,
        "workflow": "dl_forecast",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "config": fcfg.to_dict(),
        "station_results": all_results,
        "_auto_generated": True,
    }
    out_path = WORKSPACE / "cases" / case_id / "contracts" / "dl_forecast.latest.json"
    write_json(out_path, contract)
    print(f"\n报告: {out_path}")
    return contract


def main():
    parser = argparse.ArgumentParser(description="深度学习时序预测工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--models", default="lstm,transformer",
                        help="逗号分隔的模型列表: lstm,transformer,timesfm")
    parser.add_argument("--station", default=None, help="单站预测")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--seq-len", type=int, default=None)
    parser.add_argument("--horizon", type=int, default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--forecast-config", default=None)
    args = parser.parse_args()

    model_types = [m.strip() for m in args.models.split(",")]
    station_ids = [args.station] if args.station else None

    run_dl_forecast(
        case_id=args.case_id,
        model_types=model_types,
        station_ids=station_ids,
        config_path=args.config,
        forecast_config_path=args.forecast_config,
        epochs=args.epochs,
        seq_len=args.seq_len,
        horizon=args.horizon,
    )


if __name__ == "__main__":
    main()
