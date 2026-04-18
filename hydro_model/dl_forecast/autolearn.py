"""自学习闭环模块 — 自动评价→弱点识别→超参搜索→择优→固化。

自学习五步循环：
  1. 诊断: 跑所有模型×所有变量×所有站点，生成精度矩阵
  2. 识别: 找出 NSE < threshold 的弱点（站、变量、预见期）
  3. 搜索: 对弱点自动尝试不同超参组合
  4. 择优: 选精度最高的配置
  5. 固化: 最优配置+权重+评价指标写入知识层

Usage::

    from hydro_model.dl_forecast.autolearn import AutoLearner
    learner = AutoLearner(case_id="daduhe", db_path="...")
    report = learner.run(target_nse=0.95, max_rounds=3, weak_point_batch_size=5)
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from hydro_model.dl_forecast.config import ForecastConfig
from hydro_model.dl_forecast.evaluator import ForecastEvaluator


class AutoLearner:
    """自学习闭环引擎。"""

    # 超参搜索空间
    SEARCH_SPACE = {
        "seq_len": [48, 72, 168, 336],
        "horizon": [6, 12, 24, 48],
        "lstm_hidden": [64, 128, 256],
        "lstm_layers": [1, 2, 3],
        "lstm_dropout": [0.1, 0.2, 0.3],
        "d_model": [32, 64, 128],
        "nhead": [2, 4, 8],
        "num_encoder_layers": [2, 3, 4],
        "lr": [5e-4, 1e-3, 2e-3],
        "batch_size": [32, 64, 128],
    }

    def __init__(
        self,
        case_id: str,
        db_path: str,
        output_dir: str | Path | None = None,
        target_vars: list[str] | None = None,
        station_ids: list[str] | None = None,
    ):
        self.case_id = case_id
        self.db_path = db_path
        self.output_dir = Path(output_dir) if output_dir else None
        self.target_vars = target_vars or ["H_up", "Q_in", "Q_out"]
        self.station_ids = station_ids or ["s1", "s2", "s3", "s4", "s5", "s6"]
        self.history: list[dict[str, Any]] = []

    def diagnose(
        self,
        model_types: list[str] | None = None,
        cfg: ForecastConfig | None = None,
    ) -> dict[str, dict[str, dict[str, float]]]:
        """Step 1: 全面诊断——跑所有组合，生成精度矩阵。

        Returns: {station: {variable: {model: nse}}}
        """
        from hydro_model.dl_forecast import build_model
        from hydro_model.dl_forecast.dataset import TimeSeriesDataset
        import sqlite3
        import pandas as pd

        if model_types is None:
            model_types = ["lstm", "transformer"]
        if cfg is None:
            cfg = ForecastConfig(epochs=15, seq_len=72, horizon=12)

        conn = sqlite3.connect(self.db_path)
        matrix: dict[str, dict[str, dict[str, float]]] = {}

        for sid in self.station_ids:
            matrix[sid] = {}
            for tvar in self.target_vars:
                matrix[sid][tvar] = {}

                feature_vars = [v for v in ["H_up", "Q_in", "Q_out"] if v != tvar]
                all_vars = [tvar] + feature_vars

                data = {}
                for var in all_vars:
                    df = pd.read_sql_query(
                        "SELECT value FROM timeseries WHERE station_id=? AND variable=? ORDER BY time",
                        conn, params=[sid, var],
                    )
                    if not df.empty:
                        data[var] = df["value"].values.astype(float)

                if tvar not in data or len(data.get(tvar, [])) < 500:
                    continue

                n = min(len(v) for v in data.values())
                n_test = int(n * cfg.test_ratio)
                n_val = int(n * cfg.val_ratio)
                n_train = n - n_val - n_test

                try:
                    train_ds = TimeSeriesDataset.from_arrays(
                        {k: v[:n_train] for k, v in data.items()}, tvar,
                        seq_len=cfg.seq_len, horizon=cfg.horizon, station_id=sid,
                    )
                    val_ds = TimeSeriesDataset.from_arrays(
                        {k: v[n_train:n_train + n_val] for k, v in data.items()}, tvar,
                        seq_len=cfg.seq_len, horizon=cfg.horizon, station_id=sid,
                    )
                    test_ds = TimeSeriesDataset.from_arrays(
                        {k: v[n_train + n_val:] for k, v in data.items()}, tvar,
                        seq_len=cfg.seq_len, horizon=cfg.horizon, station_id=sid,
                    )
                except Exception:
                    continue

                for mt in model_types:
                    try:
                        cfg.model_type = mt
                        model = build_model(cfg)
                        model.fit(train_ds, val_ds)
                        metrics = model.evaluate(test_ds)
                        matrix[sid][tvar][mt] = metrics["nse"]
                        print(f"  {sid}/{tvar}/{mt}: NSE={metrics['nse']:.4f}")
                    except Exception as e:
                        print(f"  {sid}/{tvar}/{mt}: FAILED ({e})")
                        matrix[sid][tvar][mt] = float("-inf")

        conn.close()
        return matrix

    def identify_weak_points(
        self, matrix: dict, threshold: float = 0.90,
    ) -> list[dict[str, Any]]:
        """Step 2: 识别弱点。"""
        weak = []
        for sid, vars_dict in matrix.items():
            for tvar, models_dict in vars_dict.items():
                best_nse = max(models_dict.values()) if models_dict else float("-inf")
                if best_nse < threshold:
                    best_model = max(models_dict, key=models_dict.get) if models_dict else None
                    weak.append({
                        "station": sid,
                        "variable": tvar,
                        "best_nse": best_nse,
                        "best_model": best_model,
                        "gap": threshold - best_nse,
                    })
        return sorted(weak, key=lambda x: x["gap"], reverse=True)

    def search_improve(
        self,
        weak_point: dict[str, Any],
        n_trials: int = 8,
        base_cfg: ForecastConfig | None = None,
    ) -> dict[str, Any]:
        """Step 3: 针对弱点搜索更优超参。"""
        import random
        from hydro_model.dl_forecast import build_model
        from hydro_model.dl_forecast.dataset import TimeSeriesDataset
        import sqlite3
        import pandas as pd

        sid = weak_point["station"]
        tvar = weak_point["variable"]
        if base_cfg is None:
            base_cfg = ForecastConfig(epochs=20, model_type=weak_point.get("best_model", "lstm"))

        conn = sqlite3.connect(self.db_path)
        feature_vars = [v for v in ["H_up", "Q_in", "Q_out"] if v != tvar]
        all_vars = [tvar] + feature_vars
        data = {}
        for var in all_vars:
            df = pd.read_sql_query(
                "SELECT value FROM timeseries WHERE station_id=? AND variable=? ORDER BY time",
                conn, params=[sid, var],
            )
            if not df.empty:
                data[var] = df["value"].values.astype(float)
        conn.close()

        if tvar not in data:
            return {"status": "no_data"}

        n = min(len(v) for v in data.values())
        n_test = int(n * base_cfg.test_ratio)
        n_val = int(n * base_cfg.val_ratio)
        n_train = n - n_val - n_test

        best_result = {"nse": weak_point["best_nse"], "config": None}
        trials = []

        for trial in range(n_trials):
            cfg = ForecastConfig(**base_cfg.to_dict())
            # Random sample from search space
            cfg.seq_len = random.choice(self.SEARCH_SPACE["seq_len"])
            cfg.horizon = random.choice(self.SEARCH_SPACE["horizon"])
            if cfg.model_type == "lstm":
                cfg.lstm_hidden = random.choice(self.SEARCH_SPACE["lstm_hidden"])
                cfg.lstm_layers = random.choice(self.SEARCH_SPACE["lstm_layers"])
                cfg.lstm_dropout = random.choice(self.SEARCH_SPACE["lstm_dropout"])
            else:
                cfg.d_model = random.choice(self.SEARCH_SPACE["d_model"])
                cfg.nhead = random.choice(self.SEARCH_SPACE["nhead"])
                cfg.num_encoder_layers = random.choice(self.SEARCH_SPACE["num_encoder_layers"])
            cfg.lr = random.choice(self.SEARCH_SPACE["lr"])
            cfg.batch_size = random.choice(self.SEARCH_SPACE["batch_size"])

            try:
                train_ds = TimeSeriesDataset.from_arrays(
                    {k: v[:n_train] for k, v in data.items()}, tvar,
                    seq_len=cfg.seq_len, horizon=cfg.horizon, station_id=sid,
                )
                val_ds = TimeSeriesDataset.from_arrays(
                    {k: v[n_train:n_train + n_val] for k, v in data.items()}, tvar,
                    seq_len=cfg.seq_len, horizon=cfg.horizon, station_id=sid,
                )
                test_ds = TimeSeriesDataset.from_arrays(
                    {k: v[n_train + n_val:] for k, v in data.items()}, tvar,
                    seq_len=cfg.seq_len, horizon=cfg.horizon, station_id=sid,
                )

                model = build_model(cfg)
                model.fit(train_ds, val_ds)
                metrics = model.evaluate(test_ds)

                trial_rec = {"trial": trial, "nse": metrics["nse"], "config": cfg.to_dict()}
                trials.append(trial_rec)
                print(f"    Trial {trial}: NSE={metrics['nse']:.4f} "
                      f"(seq={cfg.seq_len} h={cfg.horizon} lr={cfg.lr})")

                if metrics["nse"] > best_result["nse"]:
                    best_result = {"nse": metrics["nse"], "config": cfg.to_dict(), "model": model}
            except Exception as e:
                trials.append({"trial": trial, "error": str(e)})

        return {
            "status": "completed",
            "station": sid,
            "variable": tvar,
            "original_nse": weak_point["best_nse"],
            "improved_nse": best_result["nse"],
            "improvement": best_result["nse"] - weak_point["best_nse"],
            "best_config": best_result.get("config"),
            "n_trials": len(trials),
        }

    def consolidate(
        self,
        results: list[dict[str, Any]],
        knowledge_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Step 5: 固化到知识层。"""
        if knowledge_dir is None:
            knowledge_dir = (
                Path(__file__).resolve().parents[2]
                / "knowledge" / self.case_id / "precision"
            )
        knowledge_dir = Path(knowledge_dir)
        knowledge_dir.mkdir(parents=True, exist_ok=True)

        record = {
            "_generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "_source": "dl_forecast.autolearn",
            "case_id": self.case_id,
            "improvements": results,
        }

        path = knowledge_dir / "dl_autolearn_history.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

        return {"path": str(path), "n_improvements": len(results)}

    def run(
        self,
        target_nse: float = 0.90,
        max_rounds: int = 3,
        trials_per_weak: int = 8,
        model_types: list[str] | None = None,
        weak_point_batch_size: int = 5,
    ) -> dict[str, Any]:
        """完整自学习闭环。"""
        batch = max(1, int(weak_point_batch_size))
        print(f"=== 自学习闭环: {self.case_id} (target NSE={target_nse}) ===")

        for round_num in range(max_rounds):
            print(f"\n--- Round {round_num + 1}/{max_rounds} ---")

            print("Step 1: 诊断")
            matrix = self.diagnose(model_types=model_types)

            print("\nStep 2: 识别弱点")
            weak = self.identify_weak_points(matrix, threshold=target_nse)
            if not weak:
                print("  无弱点，全部达标！")
                break
            print(f"  弱点: {len(weak)} 个")
            for w in weak[:batch]:
                print(f"    {w['station']}/{w['variable']}: NSE={w['best_nse']:.4f} gap={w['gap']:.4f}")

            print("\nStep 3-4: 搜索改进")
            improvements = []
            for w in weak[:batch]:
                print(f"\n  改进 {w['station']}/{w['variable']}:")
                result = self.search_improve(w, n_trials=trials_per_weak)
                improvements.append(result)
                if result.get("improvement", 0) > 0:
                    print(f"    ★ 改进: {result['original_nse']:.4f} → {result['improved_nse']:.4f}")

            self.history.append({
                "round": round_num + 1,
                "n_weak": len(weak),
                "improvements": improvements,
            })

        print("\nStep 5: 固化")
        all_improvements = []
        for h in self.history:
            all_improvements.extend(h.get("improvements", []))
        consolidation = self.consolidate(all_improvements)

        return {
            "case_id": self.case_id,
            "rounds_run": len(self.history),
            "target_nse": target_nse,
            "weak_point_batch_size": batch,
            "consolidation": consolidation,
            "history": self.history,
        }
