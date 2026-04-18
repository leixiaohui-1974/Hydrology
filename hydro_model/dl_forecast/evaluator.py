"""预测评价器 — 标准指标集。"""
from __future__ import annotations

import numpy as np


class ForecastEvaluator:
    """时序预测精度评价。"""

    @staticmethod
    def nse(obs: np.ndarray, sim: np.ndarray) -> float:
        ss_res = np.sum((obs - sim) ** 2)
        ss_tot = np.sum((obs - np.mean(obs)) ** 2)
        return float(1 - ss_res / ss_tot) if ss_tot > 1e-10 else float("-inf")

    @staticmethod
    def rmse(obs: np.ndarray, sim: np.ndarray) -> float:
        return float(np.sqrt(np.mean((obs - sim) ** 2)))

    @staticmethod
    def mae(obs: np.ndarray, sim: np.ndarray) -> float:
        return float(np.mean(np.abs(obs - sim)))

    @staticmethod
    def mape(obs: np.ndarray, sim: np.ndarray) -> float:
        mask = np.abs(obs) > 1e-6
        if not mask.any():
            return float("inf")
        return float(np.mean(np.abs((obs[mask] - sim[mask]) / obs[mask])) * 100)

    @staticmethod
    def r2(obs: np.ndarray, sim: np.ndarray) -> float:
        ss_res = np.sum((obs - sim) ** 2)
        ss_tot = np.sum((obs - np.mean(obs)) ** 2)
        return float(1 - ss_res / ss_tot) if ss_tot > 1e-10 else 0.0

    @staticmethod
    def compute_all(
        targets: np.ndarray, preds: np.ndarray,
    ) -> dict[str, float]:
        """计算全部指标。targets/preds shape: (n, horizon) or (n,)。"""
        o = targets.ravel()
        s = preds.ravel()
        n = min(len(o), len(s))
        o, s = o[:n], s[:n]
        mask = np.isfinite(o) & np.isfinite(s)
        o, s = o[mask], s[mask]
        if len(o) < 10:
            return {"nse": float("-inf"), "rmse": float("inf"),
                    "mae": float("inf"), "mape": float("inf"), "r2": 0.0, "n": 0}
        return {
            "nse": ForecastEvaluator.nse(o, s),
            "rmse": ForecastEvaluator.rmse(o, s),
            "mae": ForecastEvaluator.mae(o, s),
            "mape": ForecastEvaluator.mape(o, s),
            "r2": ForecastEvaluator.r2(o, s),
            "n": int(len(o)),
        }

    @staticmethod
    def compute_per_horizon(
        targets: np.ndarray, preds: np.ndarray,
    ) -> list[dict[str, float]]:
        """逐预见期评价。targets/preds shape: (n, horizon)。"""
        if targets.ndim == 1 or preds.ndim == 1:
            return [ForecastEvaluator.compute_all(targets, preds)]
        horizon = min(targets.shape[1], preds.shape[1])
        results = []
        for h in range(horizon):
            m = ForecastEvaluator.compute_all(targets[:, h], preds[:, h])
            m["lead_time"] = h + 1
            results.append(m)
        return results
