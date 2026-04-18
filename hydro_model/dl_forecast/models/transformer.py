"""产品化 Transformer 时序预测模型。"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from hydro_model.dl_forecast.base import BaseForecastModel
from hydro_model.dl_forecast.config import ForecastConfig
from hydro_model.dl_forecast.dataset import TimeSeriesDataset


class _PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 5000, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.dropout(x + self.pe[:, :x.size(1)])


class _TransformerNet(nn.Module):
    def __init__(self, n_features: int, d_model: int, nhead: int,
                 num_layers: int, dim_ff: int, horizon: int, dropout: float):
        super().__init__()
        self.input_proj = nn.Linear(n_features, d_model)
        self.pos_enc = _PositionalEncoding(d_model, dropout=dropout)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=dim_ff,
            dropout=dropout, batch_first=True, activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.head = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, horizon),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.input_proj(x)
        x = self.pos_enc(x)
        x = self.encoder(x)
        return self.head(x[:, -1, :])


class TransformerForecastModel(BaseForecastModel):
    """Transformer Encoder 多步预测模型。"""

    def __init__(self, cfg: ForecastConfig):
        super().__init__(cfg)
        self.device = cfg.resolve_device()
        self.net: _TransformerNet | None = None
        self._n_features: int = 0

    def _build_net(self, n_features: int) -> _TransformerNet:
        self._n_features = n_features
        return _TransformerNet(
            n_features=n_features,
            d_model=self.cfg.d_model,
            nhead=self.cfg.nhead,
            num_layers=self.cfg.num_encoder_layers,
            dim_ff=self.cfg.dim_feedforward,
            horizon=self.cfg.horizon,
            dropout=self.cfg.transformer_dropout,
        ).to(self.device)

    def fit(
        self,
        train_ds: TimeSeriesDataset,
        val_ds: TimeSeriesDataset | None = None,
    ) -> dict[str, Any]:
        torch.manual_seed(self.cfg.seed)
        x0, _ = train_ds[0]
        self.net = self._build_net(n_features=x0.shape[-1])

        train_loader = DataLoader(
            train_ds, batch_size=self.cfg.batch_size,
            shuffle=True, num_workers=self.cfg.num_workers,
        )
        val_loader = None
        if val_ds and len(val_ds) > 0:
            val_loader = DataLoader(
                val_ds, batch_size=self.cfg.batch_size,
                shuffle=False, num_workers=self.cfg.num_workers,
            )

        optimizer = torch.optim.AdamW(
            self.net.parameters(), lr=self.cfg.lr,
            weight_decay=self.cfg.weight_decay,
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=self.cfg.epochs,
        )
        criterion = nn.HuberLoss(delta=1.0)

        best_val_loss = float("inf")
        no_improve = 0
        best_state = None

        for epoch in range(self.cfg.epochs):
            self.net.train()
            train_loss = 0.0
            n_batch = 0
            for xb, yb in train_loader:
                xb, yb = xb.to(self.device), yb.to(self.device)
                pred = self.net(xb)
                loss = criterion(pred, yb)
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()
                n_batch += 1
            train_loss /= max(n_batch, 1)
            scheduler.step()

            val_loss = None
            if val_loader:
                self.net.eval()
                vl = 0.0
                vn = 0
                with torch.no_grad():
                    for xb, yb in val_loader:
                        xb, yb = xb.to(self.device), yb.to(self.device)
                        pred = self.net(xb)
                        vl += criterion(pred, yb).item()
                        vn += 1
                val_loss = vl / max(vn, 1)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    no_improve = 0
                    best_state = {k: v.cpu().clone() for k, v in self.net.state_dict().items()}
                else:
                    no_improve += 1

            self.train_history.append({
                "epoch": epoch + 1, "train_loss": train_loss,
                "val_loss": val_loss, "lr": optimizer.param_groups[0]["lr"],
            })

            if no_improve >= self.cfg.patience:
                break

        if best_state is not None:
            self.net.load_state_dict(best_state)

        self.is_fitted = True
        return {
            "epochs_run": len(self.train_history),
            "best_val_loss": best_val_loss if val_loader else None,
            "final_train_loss": self.train_history[-1]["train_loss"],
        }

    @torch.no_grad()
    def predict(self, ds: TimeSeriesDataset) -> np.ndarray:
        if self.net is None:
            raise RuntimeError("Model not fitted")
        self.net.eval()
        loader = DataLoader(ds, batch_size=self.cfg.batch_size, shuffle=False)
        preds = []
        for xb, _ in loader:
            xb = xb.to(self.device)
            out = self.net(xb).cpu().numpy()
            preds.append(out)
        result = np.concatenate(preds, axis=0)
        if ds.target_scaler is not None:
            result = ds.target_scaler.inverse_transform(result)
        return result

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "state_dict": self.net.state_dict() if self.net else None,
            "n_features": self._n_features,
            "config": self.cfg.to_dict(),
            "history": self.train_history,
        }, path)

    def load(self, path: str | Path) -> None:
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self.net = self._build_net(ckpt["n_features"])
        self.net.load_state_dict(ckpt["state_dict"])
        self.train_history = ckpt.get("history", [])
        self.is_fitted = True
