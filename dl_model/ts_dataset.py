"""通用水文时序数据集 — 配置驱动，支持多变量多站点。

从 SQLite / CSV / numpy 加载，自动构建滑动窗口，
适配 PyTorch DataLoader 和 TimesFM 推理格式。

Usage::

    ds = HydroTimeSeriesDataset.from_sqlite(
        db_path, station_id="s1",
        input_vars=["Q_in", "Q_out"], target_var="H_up",
        lookback=168, horizon=24,
    )
    train_ds, val_ds = ds.split(ratio=0.7)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

try:
    import torch
    from torch.utils.data import Dataset as TorchDataset
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    TorchDataset = object


@dataclass
class TSConfig:
    """时序数据集配置。"""
    station_id: str = ""
    input_vars: list[str] = field(default_factory=lambda: ["Q_in", "Q_out"])
    target_var: str = "H_up"
    lookback: int = 168
    horizon: int = 24
    stride: int = 1
    normalize: bool = True
    cal_ratio: float = 0.7


class HydroTimeSeriesDataset(TorchDataset):
    """通用水文时序数据集。"""

    def __init__(
        self,
        inputs: np.ndarray,
        targets: np.ndarray,
        cfg: TSConfig,
        scaler: dict[str, Any] | None = None,
    ):
        self.inputs = inputs.astype(np.float32)
        self.targets = targets.astype(np.float32)
        self.cfg = cfg
        self.scaler = scaler or {}

        n = len(self.targets) - cfg.lookback - cfg.horizon + 1
        self._n_samples = max(0, n // cfg.stride)

    def __len__(self) -> int:
        return self._n_samples

    def __getitem__(self, idx: int):
        start = idx * self.cfg.stride
        end_in = start + self.cfg.lookback
        end_out = end_in + self.cfg.horizon

        x = self.inputs[start:end_in]
        y = self.targets[end_in:end_out]

        if HAS_TORCH:
            return torch.from_numpy(x), torch.from_numpy(y)
        return x, y

    def split(self, ratio: float | None = None) -> tuple["HydroTimeSeriesDataset", "HydroTimeSeriesDataset"]:
        r = ratio or self.cfg.cal_ratio
        n = len(self.targets)
        n_cal = int(n * r)

        train = HydroTimeSeriesDataset(
            self.inputs[:n_cal], self.targets[:n_cal], self.cfg, self.scaler,
        )
        val = HydroTimeSeriesDataset(
            self.inputs[n_cal:], self.targets[n_cal:], self.cfg, self.scaler,
        )
        return train, val

    def get_flat_series(self) -> np.ndarray:
        """返回目标变量的完整一维序列（供 TimesFM 等基础模型使用）。"""
        return self.targets.copy()

    def get_context_window(self, idx: int) -> np.ndarray:
        """返回第 idx 个样本的目标变量上下文窗口。"""
        start = idx * self.cfg.stride
        end = start + self.cfg.lookback
        return self.targets[start:end].copy()

    @classmethod
    def from_sqlite(
        cls,
        db_path: str,
        station_id: str,
        input_vars: Sequence[str] = ("Q_in", "Q_out"),
        target_var: str = "H_up",
        lookback: int = 168,
        horizon: int = 24,
        normalize: bool = True,
        **kwargs: Any,
    ) -> "HydroTimeSeriesDataset":
        import sqlite3
        import pandas as pd

        cfg = TSConfig(
            station_id=station_id,
            input_vars=list(input_vars),
            target_var=target_var,
            lookback=lookback,
            horizon=horizon,
            **kwargs,
        )

        conn = sqlite3.connect(db_path)
        all_vars = list(input_vars) + [target_var]
        frames = {}
        for var in all_vars:
            df = pd.read_sql_query(
                "SELECT time, value FROM timeseries WHERE station_id=? AND variable=? ORDER BY time",
                conn, params=[station_id, var],
            )
            if not df.empty:
                df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time")
                frames[var] = df["value"]
        conn.close()

        if not frames:
            raise ValueError(f"No data for {station_id}")

        merged = pd.DataFrame(frames).dropna()
        if len(merged) < lookback + horizon + 10:
            raise ValueError(f"Insufficient data: {len(merged)} rows for {station_id}")

        input_cols = [c for c in input_vars if c in merged.columns]
        inputs = merged[input_cols].values
        targets = merged[target_var].values

        scaler = {}
        if normalize:
            for i, col in enumerate(input_cols):
                mu, std = float(inputs[:, i].mean()), float(inputs[:, i].std() + 1e-8)
                inputs[:, i] = (inputs[:, i] - mu) / std
                scaler[f"input_{col}_mean"] = mu
                scaler[f"input_{col}_std"] = std

            mu_t, std_t = float(targets.mean()), float(targets.std() + 1e-8)
            targets_norm = (targets - mu_t) / std_t
            scaler["target_mean"] = mu_t
            scaler["target_std"] = std_t
        else:
            targets_norm = targets

        return cls(inputs, targets_norm, cfg, scaler)

    @classmethod
    def from_arrays(
        cls,
        inputs: np.ndarray,
        targets: np.ndarray,
        lookback: int = 168,
        horizon: int = 24,
        **kwargs: Any,
    ) -> "HydroTimeSeriesDataset":
        cfg = TSConfig(lookback=lookback, horizon=horizon, **kwargs)
        return cls(inputs, targets, cfg)

    def inverse_transform(self, y: np.ndarray) -> np.ndarray:
        """反标准化目标变量。"""
        mu = self.scaler.get("target_mean", 0.0)
        std = self.scaler.get("target_std", 1.0)
        return y * std + mu
