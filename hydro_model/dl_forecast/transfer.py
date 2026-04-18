"""迁移学习模块 — 跨流域/跨站点知识迁移。

三种迁移模式：
  1. multi_station_pretrain: 多站联合预训练（学通用水文规律）
  2. finetune: 冻结底层 → 微调顶层（新流域少样本适配）
  3. zero_shot: TimesFM 基础模型直接推理（零训练）

设计意图：
  - 大渡河6站联合训练 → 生成通用预训练权重
  - 新流域（引绰济辽/中线/徐洪河）加载预训练权重 → 只微调最后几层
  - 减少 90% 训练时间，保持 95%+ 精度
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from hydro_model.dl_forecast.base import BaseForecastModel
from hydro_model.dl_forecast.config import ForecastConfig
from hydro_model.dl_forecast.dataset import TimeSeriesDataset


def multi_station_pretrain(
    station_datasets: dict[str, tuple[TimeSeriesDataset, TimeSeriesDataset]],
    cfg: ForecastConfig,
    save_path: str | Path | None = None,
) -> tuple[BaseForecastModel, dict[str, Any]]:
    """多站联合预训练：混合所有站点数据训练一个通用模型。

    Parameters
    ----------
    station_datasets : {station_id: (train_ds, val_ds)}
    cfg : ForecastConfig
    save_path : 预训练权重保存路径

    Returns
    -------
    (model, summary_dict)
    """
    from hydro_model.dl_forecast import build_model
    from torch.utils.data import ConcatDataset

    train_parts, val_parts = [], []
    for sid, (train_ds, val_ds) in station_datasets.items():
        train_parts.append(train_ds)
        val_parts.append(val_ds)

    combined_train = ConcatDataset(train_parts)
    combined_val = ConcatDataset(val_parts)

    model = build_model(cfg)
    summary = model.fit(combined_train, combined_val)

    if save_path:
        model.save(save_path)
        summary["pretrain_path"] = str(save_path)

    summary["n_stations"] = len(station_datasets)
    summary["n_train_windows"] = len(combined_train)
    summary["n_val_windows"] = len(combined_val)
    return model, summary


def finetune(
    model: BaseForecastModel,
    train_ds: TimeSeriesDataset,
    val_ds: TimeSeriesDataset | None = None,
    freeze_ratio: float = 0.7,
    finetune_epochs: int = 10,
    finetune_lr: float = 1e-4,
) -> dict[str, Any]:
    """微调预训练模型：冻结底层参数，只调顶层。

    Parameters
    ----------
    model : 已预训练的模型
    freeze_ratio : 冻结前 N% 的参数层
    finetune_epochs : 微调轮次（通常远少于预训练）
    finetune_lr : 微调学习率（通常比预训练小 10x）
    """
    if not hasattr(model, 'net') or model.net is None:
        raise ValueError("Model has no neural network to finetune")

    net = model.net
    all_params = list(net.parameters())
    n_freeze = int(len(all_params) * freeze_ratio)

    for i, param in enumerate(all_params):
        param.requires_grad = i >= n_freeze

    trainable = sum(p.numel() for p in net.parameters() if p.requires_grad)
    total = sum(p.numel() for p in net.parameters())

    original_epochs = model.cfg.epochs
    original_lr = model.cfg.lr
    model.cfg.epochs = finetune_epochs
    model.cfg.lr = finetune_lr

    summary = model.fit(train_ds, val_ds)

    model.cfg.epochs = original_epochs
    model.cfg.lr = original_lr

    for param in net.parameters():
        param.requires_grad = True

    summary["finetune_mode"] = True
    summary["frozen_params"] = total - trainable
    summary["trainable_params"] = trainable
    summary["freeze_ratio"] = freeze_ratio
    return summary


def load_pretrained_and_finetune(
    pretrain_path: str | Path,
    train_ds: TimeSeriesDataset,
    val_ds: TimeSeriesDataset | None = None,
    cfg: ForecastConfig | None = None,
    **finetune_kwargs: Any,
) -> tuple[BaseForecastModel, dict[str, Any]]:
    """加载预训练权重 → 微调 → 返回模型。

    标准迁移学习流程：
    1. 加载大渡河预训练权重
    2. 冻结 LSTM/Transformer 底层
    3. 用新流域少量数据微调顶层
    """
    from hydro_model.dl_forecast import build_model

    if cfg is None:
        cfg = ForecastConfig()

    model = build_model(cfg)
    model.load(pretrain_path)

    summary = finetune(model, train_ds, val_ds, **finetune_kwargs)
    summary["pretrain_source"] = str(pretrain_path)
    return model, summary


