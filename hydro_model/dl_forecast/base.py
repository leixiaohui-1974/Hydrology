"""预测模型基类 — 统一接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

from hydro_model.dl_forecast.config import ForecastConfig
from hydro_model.dl_forecast.dataset import TimeSeriesDataset


class BaseForecastModel(ABC):
    """所有预测模型的统一接口。"""

    def __init__(self, cfg: ForecastConfig):
        self.cfg = cfg
        self.is_fitted = False
        self.train_history: list[dict[str, float]] = []

    @abstractmethod
    def fit(
        self,
        train_ds: TimeSeriesDataset,
        val_ds: TimeSeriesDataset | None = None,
    ) -> dict[str, Any]:
        """训练模型。返回训练摘要。"""

    @abstractmethod
    def predict(self, ds: TimeSeriesDataset) -> np.ndarray:
        """生成预测。返回 shape (n_samples, horizon)。"""

    @abstractmethod
    def save(self, path: str | Path) -> None:
        """保存模型到磁盘。"""

    @abstractmethod
    def load(self, path: str | Path) -> None:
        """从磁盘加载模型。"""

    def evaluate(self, ds: TimeSeriesDataset) -> dict[str, float]:
        """在数据集上评价模型。"""
        from hydro_model.dl_forecast.evaluator import ForecastEvaluator
        preds = self.predict(ds)
        targets = ds.get_targets()
        return ForecastEvaluator.compute_all(targets, preds)

    @property
    def model_name(self) -> str:
        return self.__class__.__name__
