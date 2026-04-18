"""通用模型精度评价模块 — 适用于流域划分、水文、水动力等所有模型。

统一评价框架：只要有"模拟值"和"观测值/期望值"就能评价。

支持的评价类型：
  1. 流域划分精度 — 划分面积 vs 期望面积（控制面积闭合率）
  2. 水文模拟精度 — 模拟流量 vs 观测流量（NSE/RMSE/KGE）
  3. 水动力精度   — 模拟水位 vs 观测水位（NSE/RMSE/MAE）
  4. 曲线拟合精度 — 拟合曲线 vs 实测曲线（R²/RMSE）

所有逻辑确定性。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from hydro_model.calibration import compute_all_metrics


# ── 流域划分精度评价 ────────────────────────────────────────────────────────

@dataclass
class DelineationAccuracy:
    """流域划分精度评价结果。"""
    stations: list[dict[str, Any]]
    total_simulated_km2: float
    total_expected_km2: float
    closure_ratio: float         # 总面积闭合率
    max_relative_error: float    # 最大相对误差
    grade: str                   # 优秀/良好/合格/不合格


def evaluate_delineation(
    basins: list[dict[str, Any]],
    expected_areas: dict[str, float],
) -> DelineationAccuracy:
    """评价流域划分精度。确定性。

    basins: [{"name": "xxx", "area_km2": 123.4}, ...]
    expected_areas: {"station_name": expected_cumulative_km2, ...}
    """
    # 计算累积面积（按面积从大到小排序）
    sorted_basins = sorted(basins, key=lambda b: -b["area_km2"])
    cumulative = 0.0
    results = []

    for b in sorted_basins:
        cumulative += b["area_km2"]
        exp = expected_areas.get(b["name"])
        if exp and exp > 0:
            rel_error = abs(cumulative - exp) / exp
            results.append({
                "name": b["name"],
                "interval_km2": round(b["area_km2"], 1),
                "cumulative_km2": round(cumulative, 1),
                "expected_km2": exp,
                "relative_error": round(rel_error, 4),
                "match_pct": round(cumulative / exp * 100, 1),
            })
        else:
            results.append({
                "name": b["name"],
                "interval_km2": round(b["area_km2"], 1),
                "cumulative_km2": round(cumulative, 1),
                "expected_km2": None,
                "relative_error": None,
                "match_pct": None,
            })

    total_sim = cumulative
    total_exp = max(expected_areas.values()) if expected_areas else 0
    closure = total_sim / total_exp if total_exp > 0 else 0

    errors = [r["relative_error"] for r in results if r["relative_error"] is not None]
    max_err = max(errors) if errors else 0

    if max_err < 0.05:
        grade = "优秀"
    elif max_err < 0.10:
        grade = "良好"
    elif max_err < 0.20:
        grade = "合格"
    else:
        grade = "不合格"

    return DelineationAccuracy(
        stations=results,
        total_simulated_km2=round(total_sim, 1),
        total_expected_km2=total_exp,
        closure_ratio=round(closure, 4),
        max_relative_error=round(max_err, 4),
        grade=grade,
    )


# ── 时序模拟精度评价（水文/水动力通用）────────────────────────────────────

@dataclass
class TimeseriesAccuracy:
    """时序模拟精度评价结果。"""
    variable: str               # 评价变量名（如 Q_out, H_dam_up）
    station: str                # 站点名
    period: str                 # calibration / validation / full
    n_points: int
    metrics: dict[str, float]   # nse, rmse, mae, r2, pbias, kge
    grade: str
    peak_error: dict[str, float] | None  # 峰值误差


def evaluate_timeseries(
    observed: np.ndarray,
    simulated: np.ndarray,
    variable: str = "Q",
    station: str = "",
    period: str = "full",
) -> TimeseriesAccuracy:
    """评价时序模拟精度。确定性。"""
    min_len = min(len(observed), len(simulated))
    obs = observed[:min_len]
    sim = simulated[:min_len]

    metrics = compute_all_metrics(obs, sim)

    # 峰值误差
    peak_error = None
    if min_len > 0:
        obs_peak_idx = int(np.argmax(obs))
        sim_peak_idx = int(np.argmax(sim))
        peak_error = {
            "obs_peak": float(obs[obs_peak_idx]),
            "sim_peak": float(sim[sim_peak_idx]),
            "peak_error_pct": round(abs(float(sim[sim_peak_idx]) - float(obs[obs_peak_idx]))
                                    / max(float(obs[obs_peak_idx]), 1e-6) * 100, 2),
            "peak_time_error": abs(sim_peak_idx - obs_peak_idx),
        }

    nse_val = metrics.get("nse", float("-inf"))
    if nse_val >= 0.75:
        grade = "优秀"
    elif nse_val >= 0.65:
        grade = "良好"
    elif nse_val >= 0.50:
        grade = "合格"
    else:
        grade = "不合格"

    return TimeseriesAccuracy(
        variable=variable, station=station, period=period,
        n_points=min_len, metrics=metrics, grade=grade,
        peak_error=peak_error,
    )


# ── 综合精度报告 ────────────────────────────────────────────────────────────

@dataclass
class PrecisionReport:
    """多模型综合精度报告。"""
    case_id: str
    delineation: DelineationAccuracy | None = None
    hydrology: list[TimeseriesAccuracy] = field(default_factory=list)
    hydraulics: list[TimeseriesAccuracy] = field(default_factory=list)
    coupled: list[TimeseriesAccuracy] = field(default_factory=list)
    overall_grade: str = ""

    def compute_overall(self) -> str:
        """综合评定。确定性规则。"""
        grades = []
        if self.delineation:
            grades.append(self.delineation.grade)
        for ts in self.hydrology + self.hydraulics + self.coupled:
            grades.append(ts.grade)

        if not grades:
            self.overall_grade = "无数据"
            return self.overall_grade

        grade_scores = {"优秀": 4, "良好": 3, "合格": 2, "不合格": 1}
        avg = sum(grade_scores.get(g, 0) for g in grades) / len(grades)

        if avg >= 3.5:
            self.overall_grade = "优秀"
        elif avg >= 2.5:
            self.overall_grade = "良好"
        elif avg >= 1.5:
            self.overall_grade = "合格"
        else:
            self.overall_grade = "不合格"
        return self.overall_grade

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        d = asdict(self)
        d["overall_grade"] = self.compute_overall()
        return d
