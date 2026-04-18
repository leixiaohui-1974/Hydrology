"""LSTM 水文时序预测模型。

配置驱动，支持多变量输入、多步预测、自动早停。
"""
from __future__ import annotations

import json
import logging
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


class _LSTMNet(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, num_layers: int,
                 output_dim: int, dropout: float = 0.1):
        super().__init__()
        self.lstm = nn.LSTM(
            input_dim, hidden_dim, num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc = nn.Linear(hidden_dim, output_dim)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


class LSTMModel(HydroTSModel):
    """产品化 LSTM 模型。"""

    name = "lstm"

    def __init__(
        self,
        input_dim: int = 2,
        hidden_dim: int = 64,
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
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.dropout = dropout
        self.lr = lr
        self.epochs = epochs
        self.batch_size = batch_size
        self.patience = patience
        self.device = device
        self.horizon = horizon
        self._net: _LSTMNet | None = None

    def _build(self) -> _LSTMNet:
        net = _LSTMNet(
            self.input_dim, self.hidden_dim, self.num_layers,
            self.horizon, self.dropout,
        ).to(self.device)
        return net

    def fit(
        self,
        train_inputs: np.ndarray,
        train_targets: np.ndarray,
        val_inputs: np.ndarray | None = None,
        val_targets: np.ndarray | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from torch.utils.data import TensorDataset, DataLoader

        self._net = self._build()
        optimizer = torch.optim.Adam(self._net.parameters(), lr=self.lr)
        criterion = nn.MSELoss()

        X_train = torch.from_numpy(train_inputs).float().to(self.device)
        Y_train = torch.from_numpy(train_targets).float().to(self.device)
        train_ds = TensorDataset(X_train, Y_train)
        train_dl = DataLoader(train_ds, batch_size=self.batch_size, shuffle=True)

        has_val = val_inputs is not None and val_targets is not None
        if has_val:
            X_val = torch.from_numpy(val_inputs).float().to(self.device)
            Y_val = torch.from_numpy(val_targets).float().to(self.device)

        best_val_loss = float("inf")
        wait = 0
        history = {"train_loss": [], "val_loss": []}

        for epoch in range(self.epochs):
            self._net.train()
            epoch_loss = 0.0
            for xb, yb in train_dl:
                optimizer.zero_grad()
                pred = self._net(xb)
                loss = criterion(pred, yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._net.parameters(), 1.0)
                optimizer.step()
                epoch_loss += loss.item() * len(xb)
            epoch_loss /= len(train_ds)
            history["train_loss"].append(epoch_loss)

            if has_val:
                self._net.eval()
                with torch.no_grad():
                    val_pred = self._net(X_val)
                    val_loss = criterion(val_pred, Y_val).item()
                history["val_loss"].append(val_loss)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    best_state = {k: v.cpu().clone() for k, v in self._net.state_dict().items()}
                    wait = 0
                else:
                    wait += 1
                    if wait >= self.patience:
                        logger.info("Early stop at epoch %d", epoch + 1)
                        self._net.load_state_dict(best_state)
                        break

            if (epoch + 1) % 20 == 0 or epoch == 0:
                vl = f" val={history['val_loss'][-1]:.6f}" if has_val else ""
                logger.info("Epoch %d/%d train=%.6f%s", epoch + 1, self.epochs, epoch_loss, vl)

        return {"epochs_trained": epoch + 1, "best_val_loss": best_val_loss, "history": history}

    def predict(self, inputs: np.ndarray, horizon: int = 24, **kwargs: Any) -> np.ndarray:
        if self._net is None:
            raise RuntimeError("Model not trained. Call fit() first.")

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
            "hidden_dim": self.hidden_dim, "num_layers": self.num_layers,
            "dropout": self.dropout, "horizon": self.horizon,
        }
        (p / "config.json").write_text(json.dumps(config, indent=2))

    def load(self, path: str | Path) -> None:
        p = Path(path)
        config = json.loads((p / "config.json").read_text())
        self.input_dim = config["input_dim"]
        self.hidden_dim = config["hidden_dim"]
        self.num_layers = config["num_layers"]
        self.dropout = config["dropout"]
        self.horizon = config["horizon"]
        self._net = self._build()
        self._net.load_state_dict(torch.load(p / "model.pt", map_location=self.device))
        self._net.eval()
