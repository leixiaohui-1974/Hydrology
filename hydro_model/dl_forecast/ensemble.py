"""嵌套集合预报引擎。

流域预报产品架构：
  短期 (0-24h)  → LSTM / Transformer / 水库水量平衡
  中期 (1-7d)   → TimesFM / Transformer / 水文模型
  长期 (7-30d)  → TimesFM / 气候统计 / 水文模型

集合策略：
  - 多模型集合：数据驱动 × 物理模型 × 基础模型
  - 不确定性量化：分位数回归 / MC-Dropout / 模型间方差
  - 置信区间：50%/80%/95% 概率带
  - 可靠性评价：PIT / CRPS / Brier Score

配置驱动，零硬编码。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from hydro_model.dl_forecast.config import ForecastConfig
from hydro_model.dl_forecast.evaluator import ForecastEvaluator


# ── Forecast horizons ──

@dataclass
class HorizonSpec:
    """预见期定义。"""
    name: str              # short | medium | long
    label: str             # 短期 | 中期 | 长期
    horizon_hours: int     # 预见期长度
    seq_len: int           # 回溯窗口
    step_hours: int        # 输出时间步长
    model_types: list[str] = field(default_factory=list)
    weight: float = 1.0    # 集合权重（初始等权）


HORIZON_PRESETS: dict[str, HorizonSpec] = {
    "short": HorizonSpec(
        name="short", label="短期(0-24h)",
        horizon_hours=24, seq_len=72, step_hours=1,
        model_types=["lstm", "transformer", "reservoir_balance"],
    ),
    "medium": HorizonSpec(
        name="medium", label="中期(1-7d)",
        horizon_hours=168, seq_len=336, step_hours=1,
        model_types=["transformer", "timesfm", "hydrology"],
    ),
    "long": HorizonSpec(
        name="long", label="长期(7-30d)",
        horizon_hours=720, seq_len=720, step_hours=6,
        model_types=["timesfm", "climatology", "hydrology"],
    ),
}


# ── Ensemble methods ──

@dataclass
class EnsembleMember:
    """集合成员。"""
    name: str
    model_type: str
    horizon: str
    predictions: np.ndarray | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    weight: float = 1.0


class EnsembleForecaster:
    """多模型集合预报器 + 不确定性量化。"""

    def __init__(
        self,
        horizons: list[str] | None = None,
        quantiles: list[float] | None = None,
        n_mc_samples: int = 50,
    ):
        self.horizons = horizons or ["short", "medium"]
        self.quantiles = quantiles or [0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975]
        self.n_mc_samples = n_mc_samples
        self.members: list[EnsembleMember] = []
        self._performance_weights: dict[str, float] = {}

    def add_member(
        self, name: str, model_type: str, horizon: str,
        predictions: np.ndarray, metrics: dict[str, float],
    ) -> None:
        self.members.append(EnsembleMember(
            name=name, model_type=model_type, horizon=horizon,
            predictions=predictions, metrics=metrics,
        ))

    def compute_weights(self, method: str = "inverse_rmse") -> dict[str, float]:
        """基于历史精度计算成员权重。"""
        if method == "equal":
            n = len(self.members)
            return {m.name: 1.0 / n for m in self.members}

        if method == "inverse_rmse":
            rmses = {}
            for m in self.members:
                r = m.metrics.get("rmse", float("inf"))
                if r > 0 and np.isfinite(r):
                    rmses[m.name] = 1.0 / r
                else:
                    rmses[m.name] = 0.01
            total = sum(rmses.values())
            return {k: v / total for k, v in rmses.items()}

        if method == "bma":
            return self._bayesian_model_averaging()

        return {m.name: 1.0 / len(self.members) for m in self.members}

    def _bayesian_model_averaging(self) -> dict[str, float]:
        """贝叶斯模型平均 (BMA) 权重。"""
        log_likelihoods = {}
        for m in self.members:
            rmse = m.metrics.get("rmse", 1.0)
            n = m.metrics.get("n", 100)
            ll = -n / 2 * np.log(2 * np.pi * rmse ** 2) - n / 2
            log_likelihoods[m.name] = ll

        max_ll = max(log_likelihoods.values())
        exp_lls = {k: np.exp(v - max_ll) for k, v in log_likelihoods.items()}
        total = sum(exp_lls.values())
        return {k: v / total for k, v in exp_lls.items()}

    def ensemble_forecast(
        self,
        weights: dict[str, float] | None = None,
    ) -> dict[str, np.ndarray]:
        """生成加权集合预测 + 不确定性。"""
        if weights is None:
            weights = self.compute_weights("inverse_rmse")

        active = [m for m in self.members if m.predictions is not None]
        if not active:
            return {}

        # Align prediction lengths
        min_len = min(m.predictions.shape[-1] for m in active)
        preds_list = []
        w_list = []
        for m in active:
            p = m.predictions
            if p.ndim == 1:
                p = p[:min_len]
            else:
                p = p[:, :min_len]
            preds_list.append(p)
            w_list.append(weights.get(m.name, 1.0 / len(active)))

        preds_array = np.array(preds_list)
        w_array = np.array(w_list)
        w_array = w_array / w_array.sum()

        # Weighted mean
        if preds_array.ndim == 3:
            point = np.average(preds_array, axis=0, weights=w_array)
        else:
            point = np.average(preds_array, axis=0, weights=w_array)

        # Model spread → uncertainty
        model_std = np.std(preds_array, axis=0)

        quantile_forecasts = {}
        for q in self.quantiles:
            z = self._norm_ppf(q)
            quantile_forecasts[f"q{q:.3f}"] = point + z * model_std

        return {
            "point_forecast": point,
            "ensemble_mean": point,
            "ensemble_std": model_std,
            "quantile_forecasts": quantile_forecasts,
            "weights": weights,
            "n_members": len(active),
            "confidence_50": (quantile_forecasts["q0.250"], quantile_forecasts["q0.750"]),
            "confidence_80": (quantile_forecasts["q0.100"], quantile_forecasts["q0.900"]),
            "confidence_95": (quantile_forecasts["q0.025"], quantile_forecasts["q0.975"]),
        }

    @staticmethod
    def _norm_ppf(q: float) -> float:
        """标准正态分位数函数（简化近似）。"""
        from math import sqrt, log, pi
        if q <= 0 or q >= 1:
            return 0.0
        if q == 0.5:
            return 0.0
        t = sqrt(-2 * log(min(q, 1 - q)))
        c0, c1, c2 = 2.515517, 0.802853, 0.010328
        d1, d2, d3 = 1.432788, 0.189269, 0.001308
        result = t - (c0 + c1 * t + c2 * t ** 2) / (1 + d1 * t + d2 * t ** 2 + d3 * t ** 3)
        return result if q > 0.5 else -result


# ── Reliability evaluation ──

class ReliabilityEvaluator:
    """预报可靠性评价。"""

    @staticmethod
    def pit_histogram(obs: np.ndarray, quantile_preds: dict[str, np.ndarray],
                      n_bins: int = 10) -> dict[str, Any]:
        """PIT (Probability Integral Transform) 直方图。

        理想预报：PIT 均匀分布 → 直方图平坦。
        """
        q_levels = sorted([float(k.replace("q", "")) for k in quantile_preds.keys()])
        pit_values = []
        for i, o in enumerate(obs.ravel()):
            for j, q in enumerate(q_levels):
                qk = f"q{q:.3f}"
                if qk in quantile_preds:
                    qv = quantile_preds[qk]
                    val = qv.ravel()[i] if i < len(qv.ravel()) else qv.ravel()[-1]
                    if o <= val:
                        pit_values.append(q)
                        break
            else:
                pit_values.append(1.0)

        hist, bin_edges = np.histogram(pit_values, bins=n_bins, range=(0, 1))
        expected = len(pit_values) / n_bins
        chi2 = float(np.sum((hist - expected) ** 2 / expected)) if expected > 0 else 0

        return {
            "histogram": hist.tolist(),
            "bin_edges": bin_edges.tolist(),
            "chi2": chi2,
            "is_reliable": chi2 < 2 * n_bins,
            "n_obs": len(pit_values),
        }

    @staticmethod
    def crps(obs: np.ndarray, ensemble_preds: np.ndarray) -> float:
        """CRPS (Continuous Ranked Probability Score)。

        ensemble_preds: shape (n_members, n_time)
        越低越好，0 为完美。
        """
        n_members = ensemble_preds.shape[0]
        n = obs.shape[0]
        score = 0.0
        for t in range(min(n, ensemble_preds.shape[1] if ensemble_preds.ndim > 1 else n)):
            o = obs[t]
            ens = np.sort(ensemble_preds[:, t] if ensemble_preds.ndim > 1 else ensemble_preds)
            for k in range(n_members):
                score += abs(ens[k] - o)
            for k in range(n_members):
                for j in range(n_members):
                    score -= abs(ens[k] - ens[j]) / (2 * n_members)
            score /= n_members
        return float(score / max(n, 1))

    @staticmethod
    def coverage_rate(
        obs: np.ndarray, lower: np.ndarray, upper: np.ndarray,
    ) -> float:
        """置信区间覆盖率。"""
        n = min(len(obs), len(lower), len(upper))
        o = obs[:n].ravel()
        lo = lower[:n].ravel()[:len(o)]
        up = upper[:n].ravel()[:len(o)]
        covered = np.sum((o >= lo) & (o <= up))
        return float(covered / len(o)) if len(o) > 0 else 0.0

    @staticmethod
    def sharpness(lower: np.ndarray, upper: np.ndarray) -> float:
        """置信区间平均宽度（越窄越好）。"""
        n = min(len(lower), len(upper))
        return float(np.mean(upper[:n].ravel() - lower[:n].ravel()))

    @staticmethod
    def evaluate_all(
        obs: np.ndarray,
        ensemble_result: dict[str, Any],
    ) -> dict[str, Any]:
        """全面评价集合预报质量。"""
        point = ensemble_result.get("point_forecast", np.array([]))
        det_metrics = ForecastEvaluator.compute_all(obs, point)

        ci50 = ensemble_result.get("confidence_50", (None, None))
        ci80 = ensemble_result.get("confidence_80", (None, None))
        ci95 = ensemble_result.get("confidence_95", (None, None))

        reliability = {"deterministic": det_metrics}

        if ci50[0] is not None:
            reliability["coverage_50"] = ReliabilityEvaluator.coverage_rate(obs, ci50[0], ci50[1])
            reliability["sharpness_50"] = ReliabilityEvaluator.sharpness(ci50[0], ci50[1])
        if ci80[0] is not None:
            reliability["coverage_80"] = ReliabilityEvaluator.coverage_rate(obs, ci80[0], ci80[1])
            reliability["sharpness_80"] = ReliabilityEvaluator.sharpness(ci80[0], ci80[1])
        if ci95[0] is not None:
            reliability["coverage_95"] = ReliabilityEvaluator.coverage_rate(obs, ci95[0], ci95[1])
            reliability["sharpness_95"] = ReliabilityEvaluator.sharpness(ci95[0], ci95[1])

        qf = ensemble_result.get("quantile_forecasts", {})
        if qf:
            pit = ReliabilityEvaluator.pit_histogram(obs, qf)
            reliability["pit"] = pit

        return reliability
