"""Google TimesFM 基础模型适配器。

支持两种后端：
  1. transformers (HuggingFace): `google/timesfm-2.5-200m-transformers`
  2. timesfm 原生包: `pip install timesfm`

Zero-shot 预测（无需训练）+ 可选 fine-tune。

Usage::

    model = TimesFMModel(backend="transformers")
    preds = model.predict(context_series, horizon=24)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from .base import HydroTSModel

logger = logging.getLogger(__name__)

_DEFAULT_HF_MODEL = "google/timesfm-2.5-200m-transformers"
_DEFAULT_NATIVE_CKPT = "google/timesfm-2.5-200m-pytorch"


class TimesFMModel(HydroTSModel):
    """Google TimesFM 时序基础模型。"""

    name = "timesfm"

    def __init__(
        self,
        backend: str = "transformers",
        model_id: str = "",
        context_length: int = 512,
        horizon: int = 24,
        freq: str = "H",
        device: str = "cpu",
    ):
        self.backend = backend
        self.model_id = model_id or (
            _DEFAULT_HF_MODEL if backend == "transformers" else _DEFAULT_NATIVE_CKPT
        )
        self.context_length = context_length
        self.horizon = horizon
        self.freq = freq
        self.device = device
        self._model = None
        self._processor = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return

        if self.backend == "transformers":
            self._load_transformers()
        else:
            self._load_native()

    def _load_transformers(self) -> None:
        try:
            from transformers import (
                TimesFm2_5ModelForPrediction,
                TimesFmConfig,
            )
        except ImportError:
            raise ImportError(
                "transformers>=4.48 required. "
                "Install: pip install transformers torch"
            )

        logger.info("Loading TimesFM from transformers: %s", self.model_id)
        self._model = TimesFm2_5ModelForPrediction.from_pretrained(
            self.model_id,
        )
        self._model.eval()
        if self.device != "cpu":
            self._model = self._model.to(self.device)

    def _load_native(self) -> None:
        try:
            import timesfm
        except ImportError:
            raise ImportError(
                "timesfm package required. "
                "Install: pip install timesfm (Python 3.10-3.11)"
            )

        logger.info("Loading TimesFM native: %s", self.model_id)
        self._model = timesfm.TimesFm(
            hparams=timesfm.TimesFmHparams(
                per_core_batch_size=32,
                horizon_len=self.horizon,
                context_len=self.context_length,
            ),
            checkpoint=timesfm.TimesFmCheckpoint(
                huggingface_repo_id=self.model_id,
            ),
        )

    def fit(
        self,
        train_inputs: np.ndarray,
        train_targets: np.ndarray,
        val_inputs: np.ndarray | None = None,
        val_targets: np.ndarray | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """TimesFM 是 zero-shot 模型，fit 仅记录统计量。"""
        self._ensure_loaded()
        self._train_mean = float(np.mean(train_targets))
        self._train_std = float(np.std(train_targets) + 1e-8)
        return {
            "status": "zero-shot (no training needed)",
            "train_samples": len(train_targets),
            "train_mean": self._train_mean,
            "train_std": self._train_std,
        }

    def predict(
        self,
        inputs: np.ndarray,
        horizon: int = 24,
        **kwargs: Any,
    ) -> np.ndarray:
        """预测未来 horizon 步。

        inputs: 1D context series (length >= context_length) 或
                2D array [n_samples, context_length]
        """
        self._ensure_loaded()

        if inputs.ndim == 1:
            inputs = inputs.reshape(1, -1)

        ctx_len = min(inputs.shape[1], self.context_length)
        context = inputs[:, -ctx_len:].astype(np.float32)

        if self.backend == "transformers":
            return self._predict_transformers(context, horizon)
        else:
            return self._predict_native(context, horizon)

    def _predict_transformers(self, context: np.ndarray, horizon: int) -> np.ndarray:
        import torch

        device = next(self._model.parameters()).device
        input_ids = torch.from_numpy(context).to(device)

        freq_map = {"H": 0, "D": 1, "W": 2, "M": 3, "Q": 4, "Y": 5, "T": 6}
        freq_token = freq_map.get(self.freq, 0)
        freq_input = torch.full(
            (context.shape[0],), freq_token, dtype=torch.long, device=device,
        )

        with torch.no_grad():
            outputs = self._model(
                input_ids=input_ids,
                freq_input=freq_input,
            )

        point_forecast = outputs.mean_predictions
        if point_forecast is not None:
            result = point_forecast[:, :horizon].cpu().numpy()
        else:
            result = outputs.last_hidden_state[:, :horizon, 0].cpu().numpy()

        return result.squeeze()

    def _predict_native(self, context: np.ndarray, horizon: int) -> np.ndarray:
        forecasts, _ = self._model.forecast(
            context.tolist(),
            freq=[self.freq] * len(context),
        )
        return np.array(forecasts)[:, :horizon].squeeze()

    def predict_rolling(
        self,
        series: np.ndarray,
        horizon: int = 24,
        step: int = 24,
    ) -> tuple[np.ndarray, np.ndarray]:
        """滚动预测：每 step 步重新预测 horizon 步。

        Returns: (predictions, actuals) 对齐的数组。
        """
        self._ensure_loaded()
        preds_all = []
        actual_all = []
        ctx_len = min(len(series), self.context_length)

        t = ctx_len
        while t + horizon <= len(series):
            ctx = series[t - ctx_len:t]
            pred = self.predict(ctx, horizon=horizon)
            actual = series[t:t + horizon]
            preds_all.append(pred)
            actual_all.append(actual)
            t += step

        if not preds_all:
            return np.array([]), np.array([])

        return np.concatenate(preds_all), np.concatenate(actual_all)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        config = {
            "name": self.name,
            "backend": self.backend,
            "model_id": self.model_id,
            "context_length": self.context_length,
            "horizon": self.horizon,
            "freq": self.freq,
            "device": self.device,
        }
        (p / "config.json").write_text(json.dumps(config, indent=2))

    def load(self, path: str | Path) -> None:
        p = Path(path)
        config = json.loads((p / "config.json").read_text())
        self.backend = config.get("backend", self.backend)
        self.model_id = config.get("model_id", self.model_id)
        self.context_length = config.get("context_length", self.context_length)
        self.horizon = config.get("horizon", self.horizon)
        self.freq = config.get("freq", self.freq)
        self._ensure_loaded()
