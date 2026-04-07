#!/usr/bin/env python3
"""率定 (LuDing) — 参数校准与自学习

HydroMind 水智工坊 · Agent #5

迁移学习工作流 — 产品化入口。

三种模式：
  1. pretrain: 多站联合预训练（生成通用权重）
  2. finetune: 加载预训练权重 → 新流域微调
  3. zero_shot: TimesFM 零样本推理

Usage:
    # 多站预训练（由 --case-id 指定案例池）
    python3 workflows/run_dl_transfer.py --case-id zhongxian --mode pretrain

    # 迁移到新流域
    python3 workflows/run_dl_transfer.py --case-id yinchuojiliao --mode finetune \
        --pretrain-from cases/<pretrain_case>/models/dl_forecast/pretrained_lstm.pt

    # 零样本
    python3 workflows/run_dl_transfer.py --case-id yinchuojiliao --mode zero_shot
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


def run_dl_transfer(
    case_id: str,
    mode: str = "pretrain",
    model_type: str = "lstm",
    station_ids: list[str] | None = None,
    pretrain_from: str | None = None,
    config_path: str | None = None,
    freeze_ratio: float = 0.7,
    finetune_epochs: int = 10,
    finetune_lr: float = 1e-4,
    epochs: int | None = None,
) -> dict[str, Any]:
    """迁移学习主入口。"""
    from hydro_model.dl_forecast import ForecastConfig
    from hydro_model.dl_forecast.dataset import TimeSeriesDataset
    from hydro_model.dl_forecast.transfer import (
        multi_station_pretrain,
        load_pretrained_and_finetune,
    )
    from hydro_model.dl_forecast import build_model

    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "No hydromind SQLite found"}

    fcfg = ForecastConfig(model_type=model_type)
    if epochs:
        fcfg.epochs = epochs

    if station_ids is None:
        station_ids = fcfg.station_ids

    print(f"=== 迁移学习: {mode} ===")
    print(f"  Case: {case_id}, Model: {model_type}")
    print(f"  Stations: {station_ids}")

    conn = sqlite3.connect(db_path)

    if mode == "pretrain":
        station_datasets = {}
        for sid in station_ids:
            data = _load_vars(conn, sid, fcfg)
            if fcfg.target_var not in data:
                continue
            n = min(len(v) for v in data.values())
            if n < fcfg.seq_len + fcfg.horizon + 200:
                continue
            n_val = int(n * fcfg.val_ratio)
            n_train = n - n_val
            train_ds = TimeSeriesDataset.from_arrays(
                {k: v[:n_train] for k, v in data.items()}, fcfg.target_var,
                seq_len=fcfg.seq_len, horizon=fcfg.horizon, station_id=sid,
            )
            val_ds = TimeSeriesDataset.from_arrays(
                {k: v[n_train:] for k, v in data.items()}, fcfg.target_var,
                seq_len=fcfg.seq_len, horizon=fcfg.horizon, station_id=sid,
            )
            station_datasets[sid] = (train_ds, val_ds)
            print(f"  {sid}: train={len(train_ds)} val={len(val_ds)}")

        save_path = (
            WORKSPACE / "cases" / case_id / "models" / "dl_forecast"
            / f"pretrained_{model_type}.pt"
        )
        model, summary = multi_station_pretrain(station_datasets, fcfg, save_path)
        print(f"\n  预训练完成: {summary['n_stations']}站, {summary['n_train_windows']}窗口")
        print(f"  权重: {save_path}")

        contract = {
            "case_id": case_id, "workflow": "dl_transfer", "mode": "pretrain",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "model_type": model_type, "pretrain_path": str(save_path),
            "summary": summary, "_auto_generated": True,
        }

    elif mode == "finetune":
        if not pretrain_from:
            return {"error": "finetune requires --pretrain-from"}

        results = {}
        for sid in station_ids:
            data = _load_vars(conn, sid, fcfg)
            if fcfg.target_var not in data:
                continue
            n = min(len(v) for v in data.values())
            n_val = int(n * fcfg.val_ratio)
            n_test = int(n * fcfg.test_ratio)
            n_train = n - n_val - n_test

            train_ds = TimeSeriesDataset.from_arrays(
                {k: v[:n_train] for k, v in data.items()}, fcfg.target_var,
                seq_len=fcfg.seq_len, horizon=fcfg.horizon, station_id=sid,
            )
            val_ds = TimeSeriesDataset.from_arrays(
                {k: v[n_train:n_train + n_val] for k, v in data.items()}, fcfg.target_var,
                seq_len=fcfg.seq_len, horizon=fcfg.horizon, station_id=sid,
            )
            test_ds = TimeSeriesDataset.from_arrays(
                {k: v[n_train + n_val:] for k, v in data.items()}, fcfg.target_var,
                seq_len=fcfg.seq_len, horizon=fcfg.horizon, station_id=sid,
            )

            model, ft_summary = load_pretrained_and_finetune(
                pretrain_from, train_ds, val_ds, fcfg,
                freeze_ratio=freeze_ratio,
                finetune_epochs=finetune_epochs,
                finetune_lr=finetune_lr,
            )
            test_metrics = model.evaluate(test_ds)
            print(f"  {sid}: NSE={test_metrics['nse']:.4f} "
                  f"(frozen={ft_summary['frozen_params']}, trainable={ft_summary['trainable_params']})")

            save_dir = WORKSPACE / "cases" / case_id / "models" / "dl_forecast"
            model.save(save_dir / f"{sid}_{model_type}_finetuned.pt")
            results[sid] = {"test_metrics": test_metrics, "finetune_summary": ft_summary}

        contract = {
            "case_id": case_id, "workflow": "dl_transfer", "mode": "finetune",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "pretrain_source": pretrain_from, "results": results,
            "_auto_generated": True,
        }

    elif mode == "zero_shot":
        results = {}
        fcfg.model_type = "timesfm"
        for sid in station_ids:
            data = _load_vars(conn, sid, fcfg)
            if fcfg.target_var not in data:
                continue
            n = min(len(v) for v in data.values())
            n_test = int(n * fcfg.test_ratio)
            test_ds = TimeSeriesDataset.from_arrays(
                {k: v[-n_test:] for k, v in data.items()}, fcfg.target_var,
                seq_len=fcfg.seq_len, horizon=fcfg.horizon, station_id=sid,
            )
            try:
                model = build_model(fcfg)
                model.fit(test_ds)
                test_metrics = model.evaluate(test_ds)
                print(f"  {sid} (zero-shot): NSE={test_metrics['nse']:.4f}")
                results[sid] = test_metrics
            except Exception as e:
                print(f"  {sid}: FAILED ({e})")
                results[sid] = {"error": str(e)}

        contract = {
            "case_id": case_id, "workflow": "dl_transfer", "mode": "zero_shot",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "results": results, "_auto_generated": True,
        }
    else:
        conn.close()
        return {"error": f"Unknown mode: {mode}"}

    conn.close()
    out_path = WORKSPACE / "cases" / case_id / "contracts" / f"dl_transfer_{mode}.latest.json"
    write_json(out_path, contract)
    print(f"\n报告: {out_path}")
    return contract


def _load_vars(conn, sid, fcfg):
    data = {}
    for var in set([fcfg.target_var] + fcfg.feature_vars):
        df = pd.read_sql_query(
            "SELECT value FROM timeseries WHERE station_id=? AND variable=? ORDER BY time",
            conn, params=[sid, var],
        )
        if not df.empty:
            data[var] = df["value"].values.astype(float)
    return data


def main():
    parser = argparse.ArgumentParser(description="迁移学习工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--mode", default="pretrain", choices=["pretrain", "finetune", "zero_shot"])
    parser.add_argument("--model-type", default="lstm")
    parser.add_argument("--station", default=None)
    parser.add_argument("--pretrain-from", default=None)
    parser.add_argument("--freeze-ratio", type=float, default=0.7)
    parser.add_argument("--finetune-epochs", type=int, default=10)
    parser.add_argument("--finetune-lr", type=float, default=1e-4)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    station_ids = [args.station] if args.station else None
    run_dl_transfer(
        case_id=args.case_id, mode=args.mode, model_type=args.model_type,
        station_ids=station_ids, pretrain_from=args.pretrain_from,
        config_path=args.config, freeze_ratio=args.freeze_ratio,
        finetune_epochs=args.finetune_epochs, finetune_lr=args.finetune_lr,
        epochs=args.epochs,
    )


if __name__ == "__main__":
    main()
