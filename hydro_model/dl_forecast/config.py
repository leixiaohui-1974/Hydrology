"""预测配置 — 全部参数集中管理。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ForecastConfig:
    """深度学习时序预测配置。"""

    # ── Model selection ──
    model_type: str = "lstm"  # lstm | transformer | timesfm

    # ── Data ──
    target_var: str = "H_up"
    target_vars: list[str] = field(default_factory=lambda: ["H_up"])
    feature_vars: list[str] = field(default_factory=lambda: ["Q_in", "Q_out"])
    station_ids: list[str] = field(default_factory=lambda: ["s1", "s2", "s3", "s4", "s5", "s6"])

    # ── Transfer Learning ──
    pretrain_path: str = ""
    freeze_ratio: float = 0.7
    finetune_epochs: int = 10
    finetune_lr: float = 1e-4

    # ── Sequence ──
    seq_len: int = 168       # 7 days × 24h lookback
    horizon: int = 24        # 24h forecast horizon
    stride: int = 1

    # ── Training ──
    batch_size: int = 64
    epochs: int = 50
    lr: float = 1e-3
    weight_decay: float = 1e-5
    patience: int = 10       # early stopping
    val_ratio: float = 0.15
    test_ratio: float = 0.15

    # ── LSTM specific ──
    lstm_hidden: int = 128
    lstm_layers: int = 2
    lstm_dropout: float = 0.2

    # ── Transformer specific ──
    d_model: int = 64
    nhead: int = 4
    num_encoder_layers: int = 3
    dim_feedforward: int = 256
    transformer_dropout: float = 0.1

    # ── TimesFM specific ──
    timesfm_model_id: str = "google/timesfm-2.5-200m-pytorch"
    timesfm_backend: str = "pytorch"  # pytorch | transformers

    # ── Output ──
    output_dir: str = ""
    save_best: bool = True

    # ── Misc ──
    device: str = "auto"     # auto | cpu | cuda | mps
    seed: int = 42
    num_workers: int = 0

    def resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ForecastConfig":
        with open(path, encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)
