"""MC-Dropout 不确定性量化。

原理：推理阶段保持 Dropout 激活，多次前向传播生成预测分布。
用途：为单个 DL 模型提供预测的不确定性估计，补充集合模型间方差。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import torch


def enable_mc_dropout(model: "torch.nn.Module") -> None:
    """将所有 Dropout 层切换到训练模式（保持其他层 eval）。"""
    for m in model.modules():
        if isinstance(m, (
            __import__("torch").nn.Dropout,
            __import__("torch").nn.Dropout1d,
            __import__("torch").nn.Dropout2d,
        )):
            m.train()


def mc_predict(
    model: "torch.nn.Module",
    x: "torch.Tensor",
    n_samples: int = 50,
) -> dict[str, np.ndarray]:
    """MC-Dropout 推理。

    Returns:
        mean:  点预测 shape (batch, horizon)
        std:   标准差 shape (batch, horizon)
        samples: 原始样本 shape (n_samples, batch, horizon)
    """
    import torch

    model.eval()
    enable_mc_dropout(model)

    samples = []
    with torch.no_grad():
        for _ in range(n_samples):
            out = model(x)
            samples.append(out.cpu().numpy())

    samples_arr = np.array(samples)  # (n_samples, batch, horizon)
    mean = samples_arr.mean(axis=0)
    std = samples_arr.std(axis=0)

    return {
        "mean": mean,
        "std": std,
        "samples": samples_arr,
    }


def mc_quantiles(
    samples: np.ndarray,
    quantiles: list[float] | None = None,
) -> dict[str, np.ndarray]:
    """从 MC 样本计算分位数预测。

    Args:
        samples: shape (n_samples, batch, horizon)
        quantiles: 分位数列表，默认 [0.025, 0.1, 0.5, 0.9, 0.975]

    Returns:
        {f"q{q:.3f}": array} — 每个分位数的预测
    """
    if quantiles is None:
        quantiles = [0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975]

    result = {}
    for q in quantiles:
        result[f"q{q:.3f}"] = np.quantile(samples, q, axis=0)
    return result
