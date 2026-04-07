#!/usr/bin/env python3
"""推演 (TuiYan) — 水力仿真与耦合计算

HydroMind 水智工坊 · Agent #7

D2 水力学数据同化：EnKF + 水库水量平衡模型。

使用 EnsembleKalmanFilter 对水位状态进行逐步同化：
  - 状态向量: [H] (水位标量)
  - model_forward: ReservoirBalanceModel 单步积分
  - 观测: H_obs (实测水位)
  - 输出: 同化水位 vs 开环水位 vs 实测水位精度对比

为何用 enkf.py 而非 data_assimilation/：
  enkf.py 有清晰的 model_forward(state, **kwargs) -> (new_state, obs_pred) 协议，
  与 reservoir_balance 单步积分直接对接。Phase 4 联合同化再用 data_assimilation/。

Usage:
    python3 run_hydraulic_assimilation.py --case-id zhongxian
    python3 run_hydraulic_assimilation.py --case-id zhongxian --n-ensemble 50
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from hydro_model.enkf import EnsembleKalmanFilter
from hydro_model.reservoir_balance import ReservoirBalanceModel, compute_metrics
from workflows._shared import (
    load_case_config, write_json, WORKSPACE, build_station_meta,
)
from workflows.run_calibration_report import load_station_timeseries


# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _find_db(cfg: dict[str, Any]) -> str | None:
    for p in cfg.get("sqlite_paths", []):
        if "hydromind" in str(p).lower() and Path(p).exists():
            return str(p)
    for scan_dir in cfg.get("scan_dirs", []):
        for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
            return str(f)
    return None


def _load_d2_params(case_id: str) -> dict[str, dict]:
    """从 D2 率定合约加载每站最优参数。"""
    cal_path = WORKSPACE / "cases" / case_id / "contracts" / "hydraulic_calibration.latest.json"
    if not cal_path.exists():
        return {}
    cal = json.loads(cal_path.read_text(encoding="utf-8"))
    params: dict[str, dict] = {}
    for sid, sr in cal.get("station_results", {}).items():
        if isinstance(sr, dict) and "model_params" in sr:
            params[sid] = sr["model_params"]
    return params


def _single_step_h(
    H_curr: float, qi: float, qo: float,
    A_eff: float, alpha: float, k_area: float,
    H_ref: float, beta: float, dt: float,
) -> float:
    """水库水量平衡单步积分。"""
    A_t = max(A_eff + k_area * (H_curr - H_ref), A_eff * 0.1)
    dH = alpha * (qi - qo) * dt / A_t - beta * (H_curr - H_ref) * dt / 86400.0
    dH = max(-3.0, min(3.0, dH))
    return H_curr + dH


# ── 逐站同化 ──────────────────────────────────────────────────────────────────


def assimilate_station(
    Q_in: np.ndarray, Q_out: np.ndarray, H_obs: np.ndarray,
    params: dict[str, Any],
    n_ensemble: int = 30,
    obs_error_std: float = 0.3,
    dt: float = 3600.0,
) -> dict[str, Any]:
    """对单站水位进行 EnKF 同化。

    返回 open-loop 与 assimilated 的精度对比。
    """
    n = min(len(Q_in), len(Q_out), len(H_obs))
    if n < 100:
        return {"status": "insufficient_data", "n": n}

    H0 = float(H_obs[0])
    H_ref = float(np.mean(H_obs))
    A_eff = params.get("A_eff", 1e6)
    alpha_p = params.get("alpha", 1.0)
    k_area = params.get("k_area", 0.0)
    lag = int(params.get("lag", 0))
    beta_p = params.get("beta", 0.0)

    # Open-loop simulation (no assimilation)
    model = ReservoirBalanceModel(
        A_eff=A_eff, alpha=alpha_p, k_area=k_area,
        lag=lag, beta=beta_p, H_ref=H_ref,
    )
    H_open = model.simulate(Q_in[:n], Q_out[:n], H0, dt)

    # EnKF assimilation
    enkf = EnsembleKalmanFilter(n_ensemble)
    initial_states = np.random.normal(H0, 0.5, (1, n_ensemble))
    enkf.initialize(initial_states)

    R = np.array([[obs_error_std ** 2]])
    H_assim = np.zeros(n)
    H_assim[0] = H0

    def model_forward(state: np.ndarray, *, qi_t: float, qo_t: float) -> tuple[np.ndarray, np.ndarray]:
        H_curr = state[0]
        new_H = _single_step_h(
            H_curr, qi_t, qo_t, A_eff, alpha_p, k_area, H_ref, beta_p, dt,
        )
        return np.array([new_H]), np.array([new_H])

    for t in range(n - 1):
        qi_idx = max(0, t - lag)
        qi_t = float(Q_in[qi_idx])
        qo_t = float(Q_out[t])

        forecast_obs = enkf.forecast(model_forward, qi_t=qi_t, qo_t=qo_t)
        enkf.analysis(
            observation=np.array([float(H_obs[t + 1])]),
            forecast_observations=forecast_obs,
            R=R,
        )
        H_assim[t + 1] = float(enkf.states.mean(axis=1)[0])

    m_open = compute_metrics(H_obs[:n], H_open)
    m_assim = compute_metrics(H_obs[:n], H_assim)

    return {
        "status": "completed",
        "n": n,
        "open_loop_metrics": m_open,
        "assimilated_metrics": m_assim,
        "delta_nse": m_assim["nse"] - m_open["nse"],
        "delta_rmse": m_open["rmse"] - m_assim["rmse"],
    }


# ── 主入口 ────────────────────────────────────────────────────────────────────


def run_hydraulic_assimilation(
    case_id: str,
    config_path: str | None = None,
    n_ensemble: int = 30,
    obs_error_std: float = 0.3,
    time_step: str = "1H",
) -> dict[str, Any]:
    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "No hydromind SQLite found"}

    d2_params = _load_d2_params(case_id)
    if not d2_params:
        return {"error": "No D2 calibration params. Run hyd_cal first."}

    station_meta = build_station_meta(cfg)
    dt = {"1D": 86400.0, "1H": 3600.0, "15min": 900.0}.get(time_step, 3600.0)

    print(f"=== D2 水力学 EnKF 同化 (ensemble={n_ensemble}, σ_obs={obs_error_std}m) ===")
    station_results: dict[str, dict] = {}

    for sid, meta in station_meta.items():
        if sid not in d2_params:
            continue
        v = meta.get("vars", ["H_up", "Q_in", "Q_out"])
        h_var = v[0] if len(v) > 0 else "H_up"
        q_in_var = v[1] if len(v) > 1 else "Q_in"
        q_out_var = v[2] if len(v) > 2 else "Q_out"

        h, _ = load_station_timeseries(db_path, sid, h_var, time_step)
        qi, _ = load_station_timeseries(db_path, sid, q_in_var, time_step)
        qo, _ = load_station_timeseries(db_path, sid, q_out_var, time_step)
        n = min(len(h), len(qi), len(qo))
        if n < 100:
            print(f"  {sid}: 数据不足 ({n})")
            continue

        result = assimilate_station(
            qi[:n], qo[:n], h[:n], d2_params[sid],
            n_ensemble=n_ensemble, obs_error_std=obs_error_std, dt=dt,
        )

        if result["status"] != "completed":
            print(f"  {sid}: {result['status']}")
            continue

        ol = result["open_loop_metrics"]
        da = result["assimilated_metrics"]
        print(f"  {sid} ({meta['name']}): open-loop NSE={ol['nse']:.4f} → "
              f"assimilated NSE={da['nse']:.4f} (Δ={result['delta_nse']:+.4f})")
        station_results[sid] = {
            "name": meta["name"],
            **result,
        }

    nse_deltas = [sr["delta_nse"] for sr in station_results.values()]
    ol_nses = [sr["open_loop_metrics"]["nse"] for sr in station_results.values()]
    da_nses = [sr["assimilated_metrics"]["nse"] for sr in station_results.values()]

    contract = {
        "case_id": case_id,
        "workflow": "hydraulic_assimilation",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "config": {
            "n_ensemble": n_ensemble,
            "obs_error_std": obs_error_std,
            "time_step": time_step,
        },
        "station_results": station_results,
        "summary": {
            "n_stations": len(station_results),
            "avg_open_loop_nse": float(np.mean(ol_nses)) if ol_nses else None,
            "avg_assimilated_nse": float(np.mean(da_nses)) if da_nses else None,
            "avg_delta_nse": float(np.mean(nse_deltas)) if nse_deltas else None,
        },
        "_auto_generated": True,
    }
    out_path = WORKSPACE / "cases" / case_id / "contracts" / "hydraulic_assimilation.latest.json"
    write_json(out_path, contract)
    print(f"\n合约: {out_path}")
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description="D2 水力学 EnKF 同化工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--n-ensemble", type=int, default=30)
    parser.add_argument("--obs-error", type=float, default=0.3, help="观测误差标准差 (m)")
    parser.add_argument("--time-step", default="1H", choices=["1D", "1H", "15min"])
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    contract = run_hydraulic_assimilation(
        case_id=args.case_id,
        config_path=args.config,
        n_ensemble=args.n_ensemble,
        obs_error_std=args.obs_error,
        time_step=args.time_step,
    )
    print(json.dumps(contract, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
