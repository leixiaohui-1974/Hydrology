"""Transformer 水文时序预测模型。

轻量级 encoder-only Transformer，适用于多变量多步预测。
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

from .base import HydroTSModel

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class _PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 2048):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x):
        return x + self.pe[:, :x.size(1)]


class _TSTransformerNet(nn.Module):
    def __init__(self, input_dim: int, d_model: int, nhead: int,
                 num_layers: int, output_dim: int, dropout: float = 0.1):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_enc = _PositionalEncoding(d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=d_model * 4,
            dropout=dropout, batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.head = nn.Linear(d_model, output_dim)

    def forward(self, x):
        x = self.input_proj(x)
        x = self.pos_enc(x)
        x = self.encoder(x)
        return self.head(x[:, -1, :])


class TransformerModel(HydroTSModel):
    """产品化 Transformer 时序模型。"""

    name = "transformer"

    def __init__(
        self,
        input_dim: int = 2,
        d_model: int = 64,
        nhead: int = 4,
        num_layers: int = 2,
        dropout: float = 0.1,
        lr: float = 1e-3,
        epochs: int = 100,
        batch_size: int = 64,
        patience: int = 10,
        device: str = "cpu",
        horizon: int = 24,
    ):
        if not HAS_TORCH:
            raise ImportError("PyTorch required: pip install torch")

        self.input_dim = input_dim
        self.d_model = d_model
        self.nhead = nhead
        self.num_layers = num_layers
        self.dropout = dropout
        self.lr = lr
        self.epochs = epochs
        self.batch_size = batch_size
        self.patience = patience
        self.device = device
        self.horizon = horizon
        self._net: _TSTransformerNet | None = None

    def _build(self) -> _TSTransformerNet:
        return _TSTransformerNet(
            self.input_dim, self.d_model, self.nhead,
            self.num_layers, self.horizon, self.dropout,
        ).to(self.device)

    def fit(self, train_inputs: np.ndarray, train_targets: np.ndarray,
            val_inputs: np.ndarray | None = None, val_targets: np.ndarray | None = None,
            **kwargs: Any) -> dict[str, Any]:
        from torch.utils.data import TensorDataset, DataLoader

        self._net = self._build()
        optimizer = torch.optim.AdamW(self._net.parameters(), lr=self.lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.epochs)
        criterion = nn.MSELoss()

        X = torch.from_numpy(train_inputs).float().to(self.device)
        Y = torch.from_numpy(train_targets).float().to(self.device)
        dl = DataLoader(TensorDataset(X, Y), batch_size=self.batch_size, shuffle=True)

        has_val = val_inputs is not None and val_targets is not None
        if has_val:
            Xv = torch.from_numpy(val_inputs).float().to(self.device)
            Yv = torch.from_numpy(val_targets).float().to(self.device)

        best_val = float("inf")
        wait = 0
        best_state = None

        for ep in range(self.epochs):
            self._net.train()
            total = 0.0
            for xb, yb in dl:
                optimizer.zero_grad()
                loss = criterion(self._net(xb), yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._net.parameters(), 1.0)
                optimizer.step()
                total += loss.item() * len(xb)
            scheduler.step()

            if has_val:
                self._net.eval()
                with torch.no_grad():
                    vl = criterion(self._net(Xv), Yv).item()
                if vl < best_val:
                    best_val = vl
                    best_state = {k: v.cpu().clone() for k, v in self._net.state_dict().items()}
                    wait = 0
                else:
                    wait += 1
                    if wait >= self.patience:
                        self._net.load_state_dict(best_state)
                        break

        return {"epochs_trained": ep + 1, "best_val_loss": best_val}

    def predict(self, inputs: np.ndarray, horizon: int = 24, **kwargs: Any) -> np.ndarray:
        if self._net is None:
            raise RuntimeError("Model not trained")
        self._net.eval()
        if inputs.ndim == 2:
            inputs = inputs[np.newaxis, :, :]
        with torch.no_grad():
            x = torch.from_numpy(inputs).float().to(self.device)
            pred = self._net(x)
        return pred.cpu().numpy().squeeze()[:horizon]

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        if self._net is not None:
            torch.save(self._net.state_dict(), p / "model.pt")
        config = {
            "name": self.name, "input_dim": self.input_dim,
            "d_model": self.d_model, "nhead": self.nhead,
            "num_layers": self.num_layers, "horizon": self.horizon,
        }
        (p / "config.json").write_text(json.dumps(config, indent=2))

    def load(self, path: str | Path) -> None:
        p = Path(path)
        config = json.loads((p / "config.json").read_text())
        for k, v in config.items():
            if k != "name" and hasattr(self, k):
                setattr(self, k, v)
        self._net = self._build()
        self._net.load_state_dict(torch.load(p / "model.pt", map_location=self.device))
        self._net.eval()
