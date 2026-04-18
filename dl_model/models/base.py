"""DL 时序模型统一基类。

所有模型（LSTM / Transformer / TimesFM / TiDE）必须实现此接口。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np


class HydroTSModel(ABC):
    """水文时序预测模型统一接口。"""

    name: str = "base"

    @abstractmethod
    def fit(
        self,
        train_inputs: np.ndarray,
        train_targets: np.ndarray,
        val_inputs: np.ndarray | None = None,
        val_targets: np.ndarray | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """训练模型。返回训练指标。"""

    @abstractmethod
    def predict(
        self,
        inputs: np.ndarray,
        horizon: int = 24,
        **kwargs: Any,
    ) -> np.ndarray:
        """给定输入序列，预测未来 horizon 步。"""

    @abstractmethod
    def save(self, path: str | Path) -> None:
        """保存模型到磁盘。"""

    @abstractmethod
    def load(self, path: str | Path) -> None:
        """从磁盘加载模型。"""

    def evaluate(
        self,
        inputs: np.ndarray,
        targets: np.ndarray,
        horizon: int = 24,
    ) -> dict[str, float]:
        """评估模型精度。"""
        preds = self.predict(inputs, horizon=horizon)
        n = min(len(targets), len(preds))
        if n < 5:
            return {"nse": float("-inf"), "rmse": float("inf"), "n": 0}

        o, s = targets[:n], preds[:n]
        mask = np.isfinite(o) & np.isfinite(s)
        o, s = o[mask], s[mask]
        if len(o) < 5:
            return {"nse": float("-inf"), "rmse": float("inf"), "n": 0}

        rmse = float(np.sqrt(np.mean((o - s) ** 2)))
        ss_res = float(np.sum((o - s) ** 2))
        ss_tot = float(np.sum((o - np.mean(o)) ** 2))
        nse = 1.0 - ss_res / ss_tot if ss_tot > 1e-10 else float("-inf")
        mae = float(np.mean(np.abs(o - s)))

        return {"nse": nse, "rmse": rmse, "mae": mae, "n": int(len(o))}
