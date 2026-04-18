"""水库水量平衡模型 — 通用产品模块。

逐时段水库水量平衡：
    H(t+1) = H(t) + alpha * (Q_in(t-lag) - Q_out(t)) * dt / A(H) - beta * (H - H_ref)

支持特性：
  - 非线性面积 A(H) = A_eff + k_area * (H - H_ref)
  - 入流时滞 lag（整时段）
  - 回归项 beta（消除漂移）
  - 网格搜索率定
  - 精细化 + 高级搜索自提升
  - cal/val 自动分段

使用方式::

    from hydro_model.reservoir_balance import ReservoirBalanceModel, calibrate_station
    model = ReservoirBalanceModel(A_eff=1e7, alpha=0.8, beta=0.01)
    H_sim = model.simulate(Q_in, Q_out, H0=500.0, dt=3600.0)
    result = calibrate_station(Q_in, Q_out, H_obs, cal_ratio=0.7)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class ReservoirBalanceModel:
    """水库水量平衡单站模型。

    支持两种面积模式：
      1. 线性近似: A(H) = A_eff + k_area * (H - H_ref)
      2. 查表法: A(H) 从实测断面 ah_curve 插值（优先）
    """
    A_eff: float = 1e6
    alpha: float = 1.0
    k_area: float = 0.0
    H_ref: float = 0.0
    lag: int = 0
    beta: float = 0.0
    ah_curve: list[tuple[float, float]] = field(default_factory=list)

    def _area_at(self, H: float) -> float:
        """根据水位返回水面面积。优先用 ah_curve 查表插值。"""
        if self.ah_curve:
            if H <= self.ah_curve[0][0]:
                return max(self.ah_curve[0][1], self.A_eff * 0.1)
            if H >= self.ah_curve[-1][0]:
                return self.ah_curve[-1][1]
            for i in range(len(self.ah_curve) - 1):
                h0, a0 = self.ah_curve[i]
                h1, a1 = self.ah_curve[i + 1]
                if h0 <= H <= h1:
                    frac = (H - h0) / (h1 - h0) if h1 > h0 else 0.5
                    return a0 + frac * (a1 - a0)
        return max(self.A_eff + self.k_area * (H - self.H_ref), self.A_eff * 0.1)

    def simulate(
        self, Q_in: np.ndarray, Q_out: np.ndarray,
        H0: float, dt: float = 3600.0,
        max_dH: float = 3.0,
    ) -> np.ndarray:
        """模拟水位过程。"""
        n = min(len(Q_in), len(Q_out))
        H = np.zeros(n)
        H[0] = H0
        for t in range(n - 1):
            qi = float(Q_in[max(0, t - self.lag)])
            qo = float(Q_out[t])
            A_t = self._area_at(H[t])
            dH = (self.alpha * (qi - qo) * dt / A_t
                  - self.beta * (H[t] - self.H_ref) * dt / 86400.0)
            dH = max(-max_dH, min(max_dH, dH))
            H[t + 1] = H[t] + dH
        return H

    def to_dict(self) -> dict[str, Any]:
        d = {
            "A_eff": self.A_eff, "alpha": self.alpha,
            "k_area": self.k_area, "H_ref": self.H_ref,
            "lag": self.lag, "beta": self.beta,
        }
        if self.ah_curve:
            d["ah_curve_n"] = len(self.ah_curve)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReservoirBalanceModel":
        fields = {k for k in cls.__dataclass_fields__}
        return cls(**{k: d[k] for k in fields if k in d})


def compute_metrics(obs: np.ndarray, sim: np.ndarray, min_pts: int = 10) -> dict[str, float]:
    """计算精度指标：NSE, KGE, RMSE, MAE, R², PBIAS。"""
    n = min(len(obs), len(sim))
    _empty = {"nse": float("-inf"), "kge": float("-inf"), "rmse": float("inf"),
              "mae": float("inf"), "r2": 0.0, "pbias": 0.0, "n": 0}
    if n < min_pts:
        return _empty
    o, s = obs[:n].copy(), sim[:n].copy()
    mask = np.isfinite(o) & np.isfinite(s)
    o, s = o[mask], s[mask]
    if len(o) < min_pts:
        return _empty

    rmse = float(np.sqrt(np.mean((o - s) ** 2)))
    mae = float(np.mean(np.abs(o - s)))
    ss_res = float(np.sum((o - s) ** 2))
    ss_tot = float(np.sum((o - np.mean(o)) ** 2))
    nse = 1.0 - ss_res / ss_tot if ss_tot > 1e-10 else float("-inf")
    pbias = float(np.sum(s - o) / np.sum(o) * 100) if abs(np.sum(o)) > 1e-10 else 0.0

    std_o = float(np.std(o))
    std_s = float(np.std(s))
    cov = float(np.mean((o - np.mean(o)) * (s - np.mean(s))))
    r = cov / (std_o * std_s) if std_o > 1e-10 and std_s > 1e-10 else 0.0
    r2 = r ** 2

    # KGE (Kling-Gupta Efficiency)
    mean_o, mean_s = float(np.mean(o)), float(np.mean(s))
    beta_kge = mean_s / mean_o if abs(mean_o) > 1e-10 else 1.0
    gamma_kge = (std_s / mean_s) / (std_o / mean_o) if abs(mean_o * std_o) > 1e-10 and abs(mean_s) > 1e-10 else 1.0
    kge = 1.0 - float(np.sqrt((r - 1) ** 2 + (beta_kge - 1) ** 2 + (gamma_kge - 1) ** 2))

    return {"nse": nse, "kge": kge, "rmse": rmse, "mae": mae, "r2": r2, "pbias": pbias, "n": int(len(o))}


def _score_by_objective(metrics: dict[str, float], objective: str) -> float:
    """从指标字典中提取优化得分（越大越好）。"""
    if objective == "nse":
        return metrics.get("nse", float("-inf"))
    if objective == "kge":
        return metrics.get("kge", float("-inf"))
    if objective == "rmse":
        return -metrics.get("rmse", float("inf"))
    return metrics.get("nse", float("-inf"))


def calibrate_station(
    Q_in: np.ndarray, Q_out: np.ndarray, H_obs: np.ndarray,
    cal_ratio: float = 0.7,
    dt: float = 3600.0,
    A_range: tuple[float, float] = (1e5, 5e7),
    A_grid: int = 20,
    alpha_range: tuple[float, float] = (0.3, 1.5),
    alpha_grid: int = 12,
    auto_improve: bool = True,
    target_nse: float = 0.85,
    objective: str = "nse",
    ah_curve: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """逐站率定水库参数：基础 → 精细 → 高级（按需）。

    Parameters
    ----------
    objective : 优化目标 ("nse", "kge", "rmse")
    ah_curve : 可选的面积-水位关系 [(H, A), ...], 替代常数 A_eff 搜索

    返回包含 cal_metrics, val_metrics, model_params, model 的字典。
    """
    n = min(len(Q_in), len(Q_out), len(H_obs))
    if n < 200:
        return {"status": "insufficient_data", "n": n}

    n_cal = int(n * cal_ratio)
    qi, qo, ho = Q_in[:n], Q_out[:n], H_obs[:n]
    H0 = float(ho[0])
    H_ref = float(np.mean(ho[:n_cal]))

    # Phase 1: basic grid search
    best_params, best_score = _grid_search(
        qi[:n_cal], qo[:n_cal], ho[:n_cal], H0, H_ref, dt,
        A_range, A_grid, alpha_range, alpha_grid,
        objective=objective, ah_curve=ah_curve,
    )

    # Phase 2: fine grid around best
    if auto_improve:
        A_lo = max(1e4, best_params["A_eff"] / 5)
        A_hi = best_params["A_eff"] * 5
        a_lo = max(0.1, best_params["alpha"] - 0.3)
        a_hi = min(2.0, best_params["alpha"] + 0.3)
        fine_params, fine_score = _grid_search(
            qi[:n_cal], qo[:n_cal], ho[:n_cal], H0, H_ref, dt,
            (A_lo, A_hi), 30, (a_lo, a_hi), 20,
            objective=objective, ah_curve=ah_curve,
        )
        if fine_score > best_score:
            best_params, best_score = fine_params, fine_score

    # Phase 3: advanced model (non-linear area, lag, regression)
    # Use NSE to decide whether to trigger advanced search, regardless of objective
    best_nse_check = best_score if objective == "nse" else _eval_nse(
        qi[:n_cal], qo[:n_cal], ho[:n_cal], H0, H_ref, dt, best_params, ah_curve)
    if auto_improve and best_nse_check < target_nse:
        A_lo = max(1e4, best_params["A_eff"] / 5)
        A_hi = best_params["A_eff"] * 5
        a_lo = max(0.1, best_params["alpha"] - 0.3)
        a_hi = min(2.0, best_params["alpha"] + 0.3)
        adv_params, adv_score = _advanced_search(
            qi[:n_cal], qo[:n_cal], ho[:n_cal], H0, H_ref, dt,
            (A_lo, A_hi), 15, (a_lo, a_hi), 8,
            objective=objective, ah_curve=ah_curve,
        )
        if adv_score > best_score:
            model_adv = ReservoirBalanceModel(**adv_params, H_ref=H_ref,
                                              ah_curve=ah_curve or [])
            val_sim_adv = model_adv.simulate(qi[n_cal:n], qo[n_cal:n], float(ho[n_cal]), dt)
            val_adv = compute_metrics(ho[n_cal:n], val_sim_adv)
            model_basic = ReservoirBalanceModel(**best_params, H_ref=H_ref,
                                                ah_curve=ah_curve or [])
            val_sim_basic = model_basic.simulate(qi[n_cal:n], qo[n_cal:n], float(ho[n_cal]), dt)
            val_basic = compute_metrics(ho[n_cal:n], val_sim_basic)
            if _score_by_objective(val_adv, objective) > _score_by_objective(val_basic, objective):
                best_params, best_score = adv_params, adv_score

    model = ReservoirBalanceModel(**best_params, H_ref=H_ref,
                                  ah_curve=ah_curve or [])

    cal_sim = model.simulate(qi[:n_cal], qo[:n_cal], H0, dt)
    cal_m = compute_metrics(ho[:n_cal], cal_sim)

    val_sim = model.simulate(qi[n_cal:n], qo[n_cal:n], float(ho[n_cal]), dt)
    val_m = compute_metrics(ho[n_cal:n], val_sim)

    return {
        "status": "completed",
        "model": model,
        "model_params": model.to_dict(),
        "cal_metrics": cal_m,
        "val_metrics": val_m,
        "n_cal": n_cal,
        "n_val": n - n_cal,
        "objective": objective,
        "phases_used": "basic+fine" + ("+advanced" if best_params.get("beta", 0) > 0 else ""),
    }


def _eval_nse(
    qi: np.ndarray, qo: np.ndarray, ho: np.ndarray,
    H0: float, H_ref: float, dt: float,
    params: dict, ah_curve: list | None,
) -> float:
    m = ReservoirBalanceModel(**params, H_ref=H_ref, ah_curve=ah_curve or [])
    return compute_metrics(ho, m.simulate(qi, qo, H0, dt))["nse"]


def _grid_search(
    qi: np.ndarray, qo: np.ndarray, ho: np.ndarray,
    H0: float, H_ref: float, dt: float,
    A_range: tuple[float, float], A_grid: int,
    alpha_range: tuple[float, float], alpha_grid: int,
    objective: str = "nse",
    ah_curve: list[tuple[float, float]] | None = None,
) -> tuple[dict[str, Any], float]:
    A_vals = np.logspace(np.log10(A_range[0]), np.log10(A_range[1]), A_grid)
    alpha_vals = np.linspace(alpha_range[0], alpha_range[1], alpha_grid)
    best_p: dict[str, Any] = {"A_eff": 1e6, "alpha": 1.0}
    best_score = float("-inf")

    for A_eff in A_vals:
        for alpha in alpha_vals:
            m = ReservoirBalanceModel(A_eff=float(A_eff), alpha=float(alpha),
                                      H_ref=H_ref, ah_curve=ah_curve or [])
            H_sim = m.simulate(qi, qo, H0, dt)
            score = _score_by_objective(compute_metrics(ho, H_sim), objective)
            if score > best_score:
                best_score = score
                best_p = {"A_eff": float(A_eff), "alpha": float(alpha)}

    return best_p, best_score


def _advanced_search(
    qi: np.ndarray, qo: np.ndarray, ho: np.ndarray,
    H0: float, H_ref: float, dt: float,
    A_range: tuple[float, float], A_grid: int,
    alpha_range: tuple[float, float], alpha_grid: int,
    objective: str = "nse",
    ah_curve: list[tuple[float, float]] | None = None,
) -> tuple[dict[str, Any], float]:
    A_vals = np.logspace(np.log10(A_range[0]), np.log10(A_range[1]), A_grid)
    alpha_vals = np.linspace(alpha_range[0], alpha_range[1], alpha_grid)
    k_area_options = [0.0, 5000.0, 20000.0, 100000.0]
    lag_options = [0, 1, 2, 3, 6]
    beta_options = [0.0, 0.001, 0.005, 0.01]

    best_p: dict[str, Any] = {"A_eff": 1e6, "alpha": 1.0, "k_area": 0.0, "lag": 0, "beta": 0.0}
    best_score = float("-inf")

    for A_eff in A_vals:
        for alpha in alpha_vals:
            for k_area in k_area_options:
                for lag in lag_options:
                    for beta in beta_options:
                        m = ReservoirBalanceModel(
                            A_eff=float(A_eff), alpha=float(alpha),
                            k_area=k_area, lag=lag, beta=beta, H_ref=H_ref,
                            ah_curve=ah_curve or [],
                        )
                        H_sim = m.simulate(qi, qo, H0, dt)
                        score = _score_by_objective(compute_metrics(ho, H_sim), objective)
                        if score > best_score:
                            best_score = score
                            best_p = {"A_eff": float(A_eff), "alpha": float(alpha),
                                      "k_area": k_area, "lag": lag, "beta": beta}

    return best_p, best_score
