"""TimesFM 2.5 基础模型封装 — 零训练推理 + 可选微调。

支持两种后端：
  1. transformers: HuggingFace Transformers 原生
  2. pytorch: Google timesfm 原生包

TimesFM 是 Google Research 发布的时序基础模型（200M 参数），
预训练于大规模时间序列数据，支持零样本预测。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from hydro_model.dl_forecast.base import BaseForecastModel
from hydro_model.dl_forecast.config import ForecastConfig
from hydro_model.dl_forecast.dataset import TimeSeriesDataset


class TimesFMForecastModel(BaseForecastModel):
    """TimesFM 2.5 预测模型 — 零样本 / 少样本微调。"""

    def __init__(self, cfg: ForecastConfig):
        super().__init__(cfg)
        self.model = None
        self.backend = cfg.timesfm_backend
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        if self.backend == "transformers":
            self._load_transformers()
        else:
            self._load_native()
        self._loaded = True

    def _load_transformers(self) -> None:
        """通过 HuggingFace Transformers 加载 TimesFM。"""
        import torch
        try:
            from transformers import TimesFm2_5ModelForPrediction
        except ImportError:
            from transformers import AutoModelForCausalLM
            print("Warning: TimesFm2_5ModelForPrediction not available, "
                  "trying AutoModel fallback")
            self.model = AutoModelForCausalLM.from_pretrained(
                self.cfg.timesfm_model_id.replace("pytorch", "transformers"),
                trust_remote_code=True,
            )
            return

        model_id = self.cfg.timesfm_model_id
        if "transformers" not in model_id:
            model_id = model_id.replace("pytorch", "transformers")

        self.model = TimesFm2_5ModelForPrediction.from_pretrained(model_id)
        device = self.cfg.resolve_device()
        if device != "cpu":
            self.model = self.model.to(device)
        self.model.eval()

    def _load_native(self) -> None:
        """通过 Google timesfm 包加载。"""
        try:
            import timesfm
            self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                self.cfg.timesfm_model_id, torch_compile=False,
            )
        except ImportError:
            raise ImportError(
                "timesfm package not installed. "
                "Install with: pip install timesfm  OR  use backend='transformers'"
            )

    def fit(
        self,
        train_ds: TimeSeriesDataset,
        val_ds: TimeSeriesDataset | None = None,
    ) -> dict[str, Any]:
        """TimesFM 是基础模型，fit 仅加载权重（零训练）。"""
        self._ensure_loaded()
        self.is_fitted = True
        return {
            "epochs_run": 0,
            "note": "TimesFM foundation model — zero-shot, no training needed",
            "model_id": self.cfg.timesfm_model_id,
            "backend": self.backend,
        }

    def predict(self, ds: TimeSeriesDataset) -> np.ndarray:
        self._ensure_loaded()

        if self.backend == "transformers":
            return self._predict_transformers(ds)
        return self._predict_native(ds)

    def _predict_transformers(self, ds: TimeSeriesDataset) -> np.ndarray:
        """Transformers 后端推理。"""
        import torch

        preds = []
        for idx in range(len(ds)):
            x, _ = ds[idx]
            target_col = 0
            context = x[:, target_col] if x.ndim > 1 else x
            input_tensor = torch.tensor(
                context.numpy() if hasattr(context, 'numpy') else context,
                dtype=torch.float32,
            ).unsqueeze(0)

            device = self.cfg.resolve_device()
            if device != "cpu":
                input_tensor = input_tensor.to(device)

            with torch.no_grad():
                outputs = self.model(past_values=input_tensor, return_dict=True)

            point_forecast = outputs.last_hidden_state
            if hasattr(outputs, "prediction_outputs"):
                point_forecast = outputs.prediction_outputs

            forecast = point_forecast[0, :self.cfg.horizon].cpu().numpy()
            preds.append(forecast)

        result = np.array(preds)
        if ds.target_scaler is not None:
            result = ds.target_scaler.inverse_transform(result)
        return result

    def _predict_native(self, ds: TimeSeriesDataset) -> np.ndarray:
        """Google timesfm 原生推理。"""
        import timesfm

        self.model.compile(timesfm.ForecastConfig(
            num_jobs=1,
            context_length=self.cfg.seq_len,
            horizon=self.cfg.horizon,
        ))

        inputs = []
        for idx in range(len(ds)):
            x, _ = ds[idx]
            target_col = 0
            context = x[:, target_col] if x.ndim > 1 else x
            if hasattr(context, 'numpy'):
                context = context.numpy()
            inputs.append(context.astype(float).tolist())

        point_forecast, _ = self.model.forecast(
            horizon=self.cfg.horizon, inputs=inputs,
        )
        result = np.array(point_forecast)
        if ds.target_scaler is not None:
            result = ds.target_scaler.inverse_transform(result)
        return result

    def save(self, path: str | Path) -> None:
        """TimesFM 无需保存权重，仅记录配置。"""
        import json
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "model_type": "timesfm",
                "model_id": self.cfg.timesfm_model_id,
                "backend": self.backend,
                "config": self.cfg.to_dict(),
            }, f, indent=2)

    def load(self, path: str | Path) -> None:
        """加载配置并初始化模型。"""
        import json
        with open(path) as f:
            d = json.load(f)
        self.backend = d.get("backend", "transformers")
        self._ensure_loaded()
        self.is_fitted = True
