"""水电站特征曲线率定模块 — 从 Java Station.java 算法提取，产品化。

支持曲线类型：
  1. Z-V 库容曲线（水位→库容）
  2. Z-Q 泄流曲线（水位×开度→流量）
  3. NHQ 出力曲线（水头×出力→流量）
  4. Q-Z 尾水曲线（流量→尾水位）

率定方式：
  - 设计曲线作为初始值
  - 用实测数据迭代修正（分期修正思路，确定性）
  - 多项式/分段线性拟合 + 最小二乘优化
  - 评价指标：R², RMSE, 最大偏差

所有逻辑确定性，无随机性。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


# ── 曲线数据结构 ────────────────────────────────────────────────────────────

@dataclass
class Curve:
    """通用曲线：一组 (x, y) 点。"""
    name: str
    curve_type: str    # zv, zq, nhq, qz
    station: str
    x: np.ndarray      # 自变量（水位/水头/流量）
    y: np.ndarray      # 因变量（库容/流量/出力/尾水位）
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "curve_type": self.curve_type,
            "station": self.station,
            "x": self.x.tolist(), "y": self.y.tolist(),
            "metadata": self.metadata,
        }


@dataclass
class Curve2D:
    """二维曲面：Q = f(H, opening) 或 Q = f(H, P)。"""
    name: str
    curve_type: str
    station: str
    x1: np.ndarray     # 第一自变量（水位/水头）
    x2: np.ndarray     # 第二自变量（开度/出力）
    z: np.ndarray      # 因变量矩阵 [len(x1) × len(x2)]
    metadata: dict[str, Any] = field(default_factory=dict)


# ── 曲线读取（从 Excel）─────────────────────────────────────────────────────

def load_curve_from_xlsx(
    path: str | Path,
    sheet: str | int = 0,
    x_col: int | str = 0,
    y_col: int | str = 1,
    station: str = "",
    curve_type: str = "generic",
    name: str = "",
) -> Curve:
    """从 Excel 读取一维曲线。确定性。"""
    import pandas as pd
    df = pd.read_excel(path, sheet_name=sheet)
    x_data = df.iloc[:, x_col] if isinstance(x_col, int) else df[x_col]
    y_data = df.iloc[:, y_col] if isinstance(y_col, int) else df[y_col]
    mask = x_data.notna() & y_data.notna()
    return Curve(
        name=name or Path(path).stem,
        curve_type=curve_type,
        station=station,
        x=x_data[mask].values.astype(float),
        y=y_data[mask].values.astype(float),
        metadata={"source": str(path), "sheet": str(sheet)},
    )


# ── 插值函数（从 Java Station.java 提取）────────────────────────────────────

def interp1d_linear(x_table: np.ndarray, y_table: np.ndarray, x: float) -> float:
    """分段线性插值，超界线性外推。等价于 Java Station.java 的插值逻辑。确定性。"""
    if len(x_table) == 0:
        return 0.0
    if x <= x_table[0]:
        if len(x_table) >= 2:
            slope = (y_table[1] - y_table[0]) / (x_table[1] - x_table[0]) if x_table[1] != x_table[0] else 0
            return float(y_table[0] + slope * (x - x_table[0]))
        return float(y_table[0])
    if x >= x_table[-1]:
        if len(x_table) >= 2:
            slope = (y_table[-1] - y_table[-2]) / (x_table[-1] - x_table[-2]) if x_table[-1] != x_table[-2] else 0
            return float(y_table[-1] + slope * (x - x_table[-1]))
        return float(y_table[-1])
    idx = int(np.searchsorted(x_table, x, side="right") - 1)
    idx = max(0, min(idx, len(x_table) - 2))
    dx = x_table[idx + 1] - x_table[idx]
    if dx == 0:
        return float(y_table[idx])
    t = (x - x_table[idx]) / dx
    return float(y_table[idx] + t * (y_table[idx + 1] - y_table[idx]))


def interp2d_bilinear(
    x1_table: np.ndarray, x2_table: np.ndarray, z_table: np.ndarray,
    x1: float, x2: float,
) -> float:
    """双线性插值二维曲面。等价于 Java 的 Z-Q(水位,开度) 和 NHQ(水头,出力) 插值。确定性。"""
    # 找 x1 的区间
    i = int(np.clip(np.searchsorted(x1_table, x1, side="right") - 1, 0, len(x1_table) - 2))
    j = int(np.clip(np.searchsorted(x2_table, x2, side="right") - 1, 0, len(x2_table) - 2))

    x1a, x1b = x1_table[i], x1_table[min(i + 1, len(x1_table) - 1)]
    x2a, x2b = x2_table[j], x2_table[min(j + 1, len(x2_table) - 1)]

    t1 = (x1 - x1a) / (x1b - x1a) if x1b != x1a else 0
    t2 = (x2 - x2a) / (x2b - x2a) if x2b != x2a else 0
    t1 = np.clip(t1, 0, 1)
    t2 = np.clip(t2, 0, 1)

    i2 = min(i + 1, z_table.shape[0] - 1)
    j2 = min(j + 1, z_table.shape[1] - 1)

    z00 = z_table[i, j]
    z10 = z_table[i2, j]
    z01 = z_table[i, j2]
    z11 = z_table[i2, j2]

    return float((1 - t1) * (1 - t2) * z00 + t1 * (1 - t2) * z10 +
                 (1 - t1) * t2 * z01 + t1 * t2 * z11)


# ── 水库核心计算（从 Java 提取）──────────────────────────────────────────────

def storage_from_level(z: float, zv_curve: Curve) -> float:
    """Z→V：从水位查库容。"""
    return interp1d_linear(zv_curve.x, zv_curve.y, z)


def level_from_storage(v: float, zv_curve: Curve) -> float:
    """V→Z：从库容反查水位（反函数插值）。"""
    return interp1d_linear(zv_curve.y, zv_curve.x, v)


def calc_net_head(z_up: float, z_down: float, head_loss: float = 0.0) -> float:
    """净水头 = 坝前水位 - 坝后水位 - 水头损失。"""
    return max(0.0, z_up - z_down - head_loss)


def outlet_flow_with_gate(
    z_up: float, gate_opening: float,
    zq_x1: np.ndarray, zq_x2: np.ndarray, zq_z: np.ndarray,
    threshold: float = 0.0,
) -> float:
    """闸门泄流：Q = f(水位, 开度)。开度低于阈值则不泄流。"""
    if gate_opening <= threshold:
        return 0.0
    return interp2d_bilinear(zq_x1, zq_x2, zq_z, z_up, gate_opening)


def turbine_flow_from_nhq(
    net_head: float, power: float,
    nhq_h: np.ndarray, nhq_p: np.ndarray, nhq_q: np.ndarray,
) -> float:
    """水轮机流量：Q = f(水头, 出力)。从 NHQ 曲面插值。"""
    return interp2d_bilinear(nhq_h, nhq_p, nhq_q, net_head, power)


def tailwater_level(q_total: float, qz_curve: Curve) -> float:
    """尾水位：Z_down = f(总下泄流量)。"""
    return interp1d_linear(qz_curve.x, qz_curve.y, q_total)


def inflow_from_balance(v_start: float, v_end: float, outflow: float, dt: float) -> float:
    """水量平衡反推入流：I = (V2-V1)/dt + O。确定性。"""
    inflow = (v_end - v_start) / dt + outflow
    return max(0.0, inflow)


# ── 曲线拟合 ────────────────────────────────────────────────────────────────

def fit_polynomial(x: np.ndarray, y: np.ndarray, degree: int = 3) -> np.ndarray:
    """多项式拟合，返回系数。确定性最小二乘。"""
    return np.polyfit(x, y, degree)


def fit_piecewise_linear(x: np.ndarray, y: np.ndarray, n_segments: int = 5) -> dict[str, Any]:
    """分段线性拟合。确定性：等间距分段。"""
    breakpoints = np.linspace(x.min(), x.max(), n_segments + 1)
    slopes = []
    intercepts = []
    for i in range(n_segments):
        mask = (x >= breakpoints[i]) & (x <= breakpoints[i + 1])
        if mask.sum() < 2:
            slopes.append(0.0)
            intercepts.append(float(y[mask].mean()) if mask.sum() > 0 else 0.0)
            continue
        coeffs = np.polyfit(x[mask], y[mask], 1)
        slopes.append(float(coeffs[0]))
        intercepts.append(float(coeffs[1]))
    return {"breakpoints": breakpoints.tolist(), "slopes": slopes, "intercepts": intercepts}


# ── 曲线率定（迭代修正）────────────────────────────────────────────────────

@dataclass
class CurveCalibrationResult:
    """曲线率定结果。"""
    station: str
    curve_type: str
    original_rmse: float
    calibrated_rmse: float
    original_r2: float
    calibrated_r2: float
    correction_coeffs: list[float]
    iterations: int
    improvement_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _evaluate_fit(obs_y: np.ndarray, pred_y: np.ndarray) -> dict[str, float]:
    """评价拟合质量。"""
    residuals = obs_y - pred_y
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((obs_y - np.mean(obs_y)) ** 2))
    return {
        "rmse": float(np.sqrt(np.mean(residuals ** 2))),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0,
        "max_error": float(np.max(np.abs(residuals))),
        "mean_bias": float(np.mean(residuals)),
    }


def calibrate_curve_iterative(
    design_curve: Curve,
    obs_x: np.ndarray,
    obs_y: np.ndarray,
    max_iterations: int = 5,
    target_rmse: float = 0.01,
) -> CurveCalibrationResult:
    """迭代修正曲线（模拟分期修正流程）。确定性。

    每轮：
    1. 用当前曲线预测 obs_x 对应的 y
    2. 计算残差 = obs_y - pred_y
    3. 用多项式拟合残差 = f(x)
    4. 修正曲线：y_new = y_old + correction(x)
    5. 评价精度，达标则停止
    """
    current_x = design_curve.x.copy()
    current_y = design_curve.y.copy()

    # 初始精度
    pred_0 = np.array([interp1d_linear(current_x, current_y, xi) for xi in obs_x])
    orig_metrics = _evaluate_fit(obs_y, pred_0)

    for iteration in range(max_iterations):
        # 预测
        pred = np.array([interp1d_linear(current_x, current_y, xi) for xi in obs_x])
        residuals = obs_y - pred

        # 拟合残差修正
        if len(obs_x) >= 3:
            degree = min(3, len(obs_x) - 1)
            correction_coeffs = np.polyfit(obs_x, residuals, degree)
            correction = np.polyval(correction_coeffs, current_x)
        else:
            correction_coeffs = [float(np.mean(residuals))]
            correction = np.full_like(current_y, np.mean(residuals))

        # 应用修正
        current_y = current_y + correction

        # 评价
        pred_new = np.array([interp1d_linear(current_x, current_y, xi) for xi in obs_x])
        metrics = _evaluate_fit(obs_y, pred_new)

        if metrics["rmse"] <= target_rmse:
            break

    improvement = (1.0 - metrics["rmse"] / orig_metrics["rmse"]) * 100 if orig_metrics["rmse"] > 0 else 0

    return CurveCalibrationResult(
        station=design_curve.station,
        curve_type=design_curve.curve_type,
        original_rmse=orig_metrics["rmse"],
        calibrated_rmse=metrics["rmse"],
        original_r2=orig_metrics["r2"],
        calibrated_r2=metrics["r2"],
        correction_coeffs=[float(c) for c in correction_coeffs],
        iterations=iteration + 1,
        improvement_pct=round(improvement, 1),
    )
