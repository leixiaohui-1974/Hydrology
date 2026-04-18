"""通用模型率定与验证框架 — 适用于水文、水动力、耦合等任意模型。

设计原则：
  - 通用：任何模型只要实现 ModelInterface 就能率定
  - 确定性：网格搜索 + 逐步优化，无随机性
  - 灵活：率定期/验证期按日期或比例分割
  - 多指标：NSE, RMSE, MAE, R², PBIAS, KGE

使用方式：
    from hydro_model.calibration import (
        CalibrationConfig, split_data, calibrate, validate, run_full_cv
    )

    # 定义模型接口
    def my_model(params, input_series):
        ...
        return simulated_series

    # 率定
    result = calibrate(
        model_fn=my_model,
        observed=obs_series,
        input_data=rain_series,
        param_space={"manning_n": (0.01, 0.06, 10), "K": (1.0, 5.0, 5)},
        config=CalibrationConfig(objective="nse"),
    )
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np


# ── 评估指标 ────────────────────────────────────────────────────────────────

def rmse(obs: np.ndarray, sim: np.ndarray) -> float:
    """均方根误差 (m 或 m³/s)"""
    return float(np.sqrt(np.mean((obs - sim) ** 2)))


def mae(obs: np.ndarray, sim: np.ndarray) -> float:
    """平均绝对误差"""
    return float(np.mean(np.abs(obs - sim)))


def nse(obs: np.ndarray, sim: np.ndarray) -> float:
    """Nash-Sutcliffe 效率系数 (1.0=完美, <0=不如均值)"""
    ss_res = np.sum((obs - sim) ** 2)
    ss_tot = np.sum((obs - np.mean(obs)) ** 2)
    return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("-inf")


def r_squared(obs: np.ndarray, sim: np.ndarray) -> float:
    """决定系数 R²"""
    corr = np.corrcoef(obs, sim)[0, 1] if len(obs) > 1 else 0.0
    return float(corr ** 2)


def pbias(obs: np.ndarray, sim: np.ndarray) -> float:
    """百分比偏差 (%, 正=高估, 负=低估)"""
    s = np.sum(obs)
    return float(100.0 * np.sum(sim - obs) / s) if s != 0 else 0.0


def kge(obs: np.ndarray, sim: np.ndarray) -> float:
    """Kling-Gupta 效率系数"""
    r = np.corrcoef(obs, sim)[0, 1] if len(obs) > 1 else 0.0
    alpha = np.std(sim) / np.std(obs) if np.std(obs) > 0 else 1.0
    beta = np.mean(sim) / np.mean(obs) if np.mean(obs) != 0 else 1.0
    return float(1.0 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))


METRICS = {
    "nse": nse,
    "rmse": rmse,
    "mae": mae,
    "r2": r_squared,
    "pbias": pbias,
    "kge": kge,
}


def compute_all_metrics(obs: np.ndarray, sim: np.ndarray) -> dict[str, float]:
    """计算所有评估指标。确定性。"""
    return {name: func(obs, sim) for name, func in METRICS.items()}


# ── 数据分割 ────────────────────────────────────────────────────────────────

@dataclass
class DataSplit:
    """率定期/验证期数据分割结果。"""
    cal_obs: np.ndarray
    cal_input: np.ndarray | None
    val_obs: np.ndarray
    val_input: np.ndarray | None
    cal_indices: tuple[int, int]  # (start, end)
    val_indices: tuple[int, int]


def split_by_ratio(
    observed: np.ndarray,
    input_data: np.ndarray | None = None,
    cal_ratio: float = 0.7,
) -> DataSplit:
    """按比例分割率定期和验证期。确定性。"""
    n = len(observed)
    split_idx = int(n * cal_ratio)
    return DataSplit(
        cal_obs=observed[:split_idx],
        cal_input=input_data[:split_idx] if input_data is not None else None,
        val_obs=observed[split_idx:],
        val_input=input_data[split_idx:] if input_data is not None else None,
        cal_indices=(0, split_idx),
        val_indices=(split_idx, n),
    )


def split_by_date(
    observed: np.ndarray,
    timestamps: np.ndarray,
    cal_end: str,
    val_start: str | None = None,
    input_data: np.ndarray | None = None,
) -> DataSplit:
    """按日期分割率定期和验证期。确定性。"""
    cal_mask = timestamps <= np.datetime64(cal_end)
    val_start_dt = np.datetime64(val_start) if val_start else np.datetime64(cal_end)
    val_mask = timestamps > val_start_dt

    cal_idx = np.where(cal_mask)[0]
    val_idx = np.where(val_mask)[0]

    return DataSplit(
        cal_obs=observed[cal_mask],
        cal_input=input_data[cal_mask] if input_data is not None else None,
        val_obs=observed[val_mask],
        val_input=input_data[val_mask] if input_data is not None else None,
        cal_indices=(int(cal_idx[0]), int(cal_idx[-1] + 1)) if len(cal_idx) > 0 else (0, 0),
        val_indices=(int(val_idx[0]), int(val_idx[-1] + 1)) if len(val_idx) > 0 else (0, 0),
    )


# ── 率定配置 ────────────────────────────────────────────────────────────────

@dataclass
class CalibrationConfig:
    """率定配置。"""
    objective: str = "nse"          # 优化目标指标
    maximize: bool = True           # NSE/KGE 越大越好; RMSE/MAE 越小越好
    cal_ratio: float = 0.7          # 率定期比例（按比例分割时用）
    cal_end_date: str | None = None # 率定截止日期（按日期分割时用）
    val_start_date: str | None = None


@dataclass
class CalibrationResult:
    """率定结果。"""
    best_params: dict[str, float]
    best_objective: float
    cal_metrics: dict[str, float]
    val_metrics: dict[str, float]
    search_history: list[dict[str, Any]]
    param_space: dict[str, tuple]
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── 网格搜索率定 ────────────────────────────────────────────────────────────

from typing import Optional
ModelFn = Callable[[dict[str, float], Optional[np.ndarray]], np.ndarray]


def _build_param_grid(param_space: dict[str, tuple]) -> list[dict[str, float]]:
    """构建参数网格。确定性：固定步长等分。

    param_space: {"param_name": (min, max, n_steps)}
    """
    import itertools

    names = list(param_space.keys())
    ranges = []
    for name in names:
        low, high, steps = param_space[name]
        ranges.append(np.linspace(low, high, int(steps)).tolist())

    grid = []
    for combo in itertools.product(*ranges):
        grid.append({names[i]: combo[i] for i in range(len(names))})
    return grid


def calibrate(
    model_fn: ModelFn,
    observed: np.ndarray,
    param_space: dict[str, tuple],
    input_data: np.ndarray | None = None,
    config: CalibrationConfig | None = None,
    timestamps: np.ndarray | None = None,
) -> CalibrationResult:
    """通用网格搜索率定。确定性。

    model_fn: 模型函数，签名 (params_dict, input_data) -> simulated_array
    observed: 观测序列
    param_space: {"param_name": (min, max, n_steps)}
    """
    cfg = config or CalibrationConfig()

    # 数据分割
    if cfg.cal_end_date and timestamps is not None:
        split = split_by_date(observed, timestamps, cfg.cal_end_date, cfg.val_start_date, input_data)
    else:
        split = split_by_ratio(observed, input_data, cfg.cal_ratio)

    objective_fn = METRICS.get(cfg.objective, nse)
    grid = _build_param_grid(param_space)

    best_params = {}
    best_obj = float("-inf") if cfg.maximize else float("inf")
    search_history = []

    for params in grid:
        try:
            sim = model_fn(params, split.cal_input)
            min_len = min(len(split.cal_obs), len(sim))
            if min_len == 0:
                continue
            obj = objective_fn(split.cal_obs[:min_len], sim[:min_len])
        except Exception:
            continue

        improved = (obj > best_obj) if cfg.maximize else (obj < best_obj)
        if improved:
            best_obj = obj
            best_params = dict(params)

        search_history.append({**params, cfg.objective: obj})

    # 用最优参数评估率定期和验证期
    try:
        cal_sim = model_fn(best_params, split.cal_input)
        min_cal = min(len(split.cal_obs), len(cal_sim))
        cal_metrics = compute_all_metrics(split.cal_obs[:min_cal], cal_sim[:min_cal])
    except Exception:
        cal_metrics = {}

    try:
        val_sim = model_fn(best_params, split.val_input)
        min_val = min(len(split.val_obs), len(val_sim))
        val_metrics = compute_all_metrics(split.val_obs[:min_val], val_sim[:min_val])
    except Exception:
        val_metrics = {}

    return CalibrationResult(
        best_params=best_params,
        best_objective=best_obj,
        cal_metrics=cal_metrics,
        val_metrics=val_metrics,
        search_history=search_history,
        param_space={k: list(v) for k, v in param_space.items()},
        config=asdict(cfg),
    )


# ── 逐步优化（确定性缩小搜索范围）──────────────────────────────────────────

def calibrate_progressive(
    model_fn: ModelFn,
    observed: np.ndarray,
    param_space: dict[str, tuple],
    input_data: np.ndarray | None = None,
    config: CalibrationConfig | None = None,
    timestamps: np.ndarray | None = None,
    rounds: int = 3,
    shrink_factor: float = 0.3,
) -> CalibrationResult:
    """逐步缩小范围的率定。确定性：每轮网格搜索后缩小到最优点附近。"""
    current_space = dict(param_space)

    for round_idx in range(rounds):
        result = calibrate(
            model_fn=model_fn, observed=observed,
            param_space=current_space, input_data=input_data,
            config=config, timestamps=timestamps,
        )
        # 缩小搜索范围到最优点附近
        for name, (low, high, steps) in current_space.items():
            best_val = result.best_params.get(name, (low + high) / 2)
            span = (high - low) * shrink_factor
            new_low = max(low, best_val - span / 2)
            new_high = min(high, best_val + span / 2)
            current_space[name] = (new_low, new_high, steps)

    return result


# ── 验证 ────────────────────────────────────────────────────────────────────

def validate(
    model_fn: ModelFn,
    params: dict[str, float],
    observed: np.ndarray,
    input_data: np.ndarray | None = None,
) -> dict[str, float]:
    """用给定参数在独立数据上验证模型。确定性。"""
    sim = model_fn(params, input_data)
    min_len = min(len(observed), len(sim))
    return compute_all_metrics(observed[:min_len], sim[:min_len])


# ── 完整率定-验证流程 ────────────────────────────────────────────────────────

def run_full_cv(
    model_fn: ModelFn,
    observed: np.ndarray,
    param_space: dict[str, tuple],
    input_data: np.ndarray | None = None,
    config: CalibrationConfig | None = None,
    timestamps: np.ndarray | None = None,
    progressive_rounds: int = 3,
) -> dict[str, Any]:
    """完整的率定+验证流程。确定性。

    返回包含率定期指标、验证期指标、最优参数的完整报告。
    """
    result = calibrate_progressive(
        model_fn=model_fn, observed=observed,
        param_space=param_space, input_data=input_data,
        config=config, timestamps=timestamps,
        rounds=progressive_rounds,
    )

    report = {
        "best_params": result.best_params,
        "best_objective": result.best_objective,
        "calibration_metrics": result.cal_metrics,
        "validation_metrics": result.val_metrics,
        "param_space": result.param_space,
        "progressive_rounds": progressive_rounds,
        "assessment": _assess_quality(result.cal_metrics, result.val_metrics),
    }
    return report


def _assess_quality(cal: dict, val: dict) -> dict[str, str]:
    """评估模型质量等级。确定性规则。"""
    assessment = {}
    # NSE 评级
    for period, metrics in [("calibration", cal), ("validation", val)]:
        nse_val = metrics.get("nse", float("-inf"))
        if nse_val >= 0.75:
            grade = "优秀"
        elif nse_val >= 0.65:
            grade = "良好"
        elif nse_val >= 0.50:
            grade = "合格"
        else:
            grade = "不合格"
        assessment[f"{period}_grade"] = grade
        assessment[f"{period}_nse"] = nse_val

    # 率定/验证一致性
    cal_nse = cal.get("nse", 0)
    val_nse = val.get("nse", 0)
    if abs(cal_nse - val_nse) < 0.1:
        assessment["consistency"] = "稳定（率定验证差<0.1）"
    elif abs(cal_nse - val_nse) < 0.2:
        assessment["consistency"] = "可接受（率定验证差<0.2）"
    else:
        assessment["consistency"] = "过拟合风险（率定验证差≥0.2）"

    return assessment


# ── 工具：保存/加载结果 ──────────────────────────────────────────────────────

def save_result(result: CalibrationResult | dict, path: str | Path) -> None:
    """保存率定结果到 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def load_result(path: str | Path) -> dict[str, Any]:
    """加载率定结果。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))
