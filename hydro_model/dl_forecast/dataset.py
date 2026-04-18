"""时序数据集 — 滑窗构造 + 标准化。"""
from __future__ import annotations

from typing import Any

import numpy as np

try:
    import torch
    from torch.utils.data import Dataset as TorchDataset
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    TorchDataset = object


class TimeSeriesDataset(TorchDataset):
    """滑窗时序数据集，支持多变量输入 + 单/多步输出。

    Parameters
    ----------
    features : np.ndarray, shape (T, n_features)
    targets : np.ndarray, shape (T,) or (T, n_targets)
    seq_len : int
    horizon : int
    stride : int
    scaler : optional fitted scaler with transform/inverse_transform
    """

    def __init__(
        self,
        features: np.ndarray,
        targets: np.ndarray,
        seq_len: int = 168,
        horizon: int = 24,
        stride: int = 1,
        scaler: Any = None,
        target_scaler: Any = None,
        station_id: str = "",
    ):
        self.raw_features = features
        self.raw_targets = targets
        self.seq_len = seq_len
        self.horizon = horizon
        self.stride = stride
        self.scaler = scaler
        self.target_scaler = target_scaler
        self.station_id = station_id

        if scaler is not None:
            self.features = scaler.transform(features)
        else:
            self.features = features.copy()

        if target_scaler is not None:
            t = targets.reshape(-1, 1) if targets.ndim == 1 else targets
            self.targets = target_scaler.transform(t).ravel()
        else:
            self.targets = targets.copy()

        self._indices = list(range(0, len(self.features) - seq_len - horizon + 1, stride))

    def __len__(self) -> int:
        return len(self._indices)

    def __getitem__(self, idx: int):
        i = self._indices[idx]
        x = self.features[i: i + self.seq_len]
        y = self.targets[i + self.seq_len: i + self.seq_len + self.horizon]
        if HAS_TORCH:
            return torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)
        return x.astype(np.float32), y.astype(np.float32)

    def get_targets(self) -> np.ndarray:
        """返回所有窗口的目标值 (n_windows, horizon)，原始尺度。"""
        all_y = []
        for idx in range(len(self)):
            i = self._indices[idx]
            y = self.raw_targets[i + self.seq_len: i + self.seq_len + self.horizon]
            all_y.append(y)
        return np.array(all_y)

    def get_full_target_series(self) -> np.ndarray:
        """返回原始目标时序（未标准化）。"""
        return self.raw_targets

    @staticmethod
    def from_arrays(
        feature_dict: dict[str, np.ndarray],
        target_key: str,
        seq_len: int = 168,
        horizon: int = 24,
        stride: int = 1,
        normalize: bool = True,
        station_id: str = "",
    ) -> "TimeSeriesDataset":
        """从变量字典构造数据集。"""
        from sklearn.preprocessing import StandardScaler

        keys = sorted(feature_dict.keys())
        if target_key not in keys:
            raise ValueError(f"Target '{target_key}' not in feature_dict keys: {keys}")

        n = min(len(v) for v in feature_dict.values())
        feat_matrix = np.column_stack([feature_dict[k][:n] for k in keys])
        target_arr = feature_dict[target_key][:n]

        scaler = None
        target_scaler = None
        if normalize:
            scaler = StandardScaler().fit(feat_matrix)
            target_scaler = StandardScaler().fit(target_arr.reshape(-1, 1))

        return TimeSeriesDataset(
            features=feat_matrix, targets=target_arr,
            seq_len=seq_len, horizon=horizon, stride=stride,
            scaler=scaler, target_scaler=target_scaler,
            station_id=station_id,
        )
