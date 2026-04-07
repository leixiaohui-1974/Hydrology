#!/usr/bin/env python3
"""推演 (TuiYan) — 水力仿真与耦合计算

HydroMind 水智工坊 · Agent #7

D1+D2 联合状态同化工作流：同时更新水文状态和水力学状态。

状态向量: [q_state, H, A_eff_pert, alpha_pert]
观测算子: H_obs (水位站) + Q_obs (流量站)

使用 LocalizedEnKF（data_assimilation 包）或 EnsembleKalmanFilter（enkf.py）。

Usage:
    python3 run_coupled_assimilation.py --case-id zhongxian
    python3 run_coupled_assimilation.py --case-id zhongxian --n-ensemble 40
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from hydro_model.enkf import EnsembleKalmanFilter
from hydro_model.reservoir_balance import ReservoirBalanceModel, compute_metrics
from workflows._shared import load_case_config, write_json, WORKSPACE, build_station_meta


def _find_db(cfg: dict) -> str | None:
    for p in cfg.get("sqlite_paths", []):
        if "hydromind" in str(p).lower() and Path(p).exists():
            return str(p)
    for scan_dir in cfg.get("scan_dirs", []):
        for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
            return str(f)
    return None


def _load_ts(db_path: str, station_id: str, variable: str) -> np.ndarray:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT time, value FROM timeseries WHERE station_id=? AND variable=? ORDER BY time",
        conn, params=[station_id, variable],
    )
    conn.close()
    return df["value"].values.astype(float) if not df.empty else np.array([])


def _load_cal_params(case_id: str, station_id: str) -> dict[str, Any] | None:
    path = WORKSPACE / "cases" / case_id / "contracts" / "hydraulic_calibration.latest.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    sr = data.get("station_results", {}).get(station_id, {})
    return sr.get("model_params") or sr.get("calibration", {}).get("best")


# ── Coupled state-space model ────────────────────────────────────────────
#
# State vector: [q_state, H, A_eff, alpha]
#   q_state : Muskingum-like routing state (D1 surrogate)
#   H       : reservoir water level (D2)
#   A_eff   : effective area parameter (random walk)
#   alpha   : scaling parameter (random walk)
#
# Observations: [H_obs, Q_obs] or just [H_obs]

def _make_coupled_forward(
    base_model: ReservoirBalanceModel,
    q_in_t: float,
    q_out_t: float,
    dt: float,
    has_q_obs: bool = False,
    process_noise: dict[str, float] | None = None,
):
    pn = process_noise or {
        "q": 5.0,
        "H": 0.02,
        "A_eff": 5e3,
        "alpha": 0.005,
    }

    def model_forward(state, **kwargs):
        q_state = float(state[0])
        H = float(state[1])
        A_eff = float(state[2])
        alpha_val = float(state[3])

        # D1: simple routing state update
        musk_x = 0.2
        q_routed = musk_x * q_in_t + (1 - musk_x) * q_state
        q_state_next = q_routed + np.random.normal(0, pn["q"])

        # D2: reservoir balance with current parameter estimates
        m = ReservoirBalanceModel(
            A_eff=max(1e4, A_eff), alpha=max(0.1, min(2.0, alpha_val)),
            k_area=base_model.k_area, lag=base_model.lag,
            beta=base_model.beta, H_ref=base_model.H_ref,
            ah_curve=base_model.ah_curve,
        )
        A_t = m._area_at(H)
        dH = (m.alpha * (q_in_t - q_out_t) * dt / A_t
              - m.beta * (H - m.H_ref) * dt / 86400.0)
        dH = max(-3.0, min(3.0, dH))
        H_next = H + dH + np.random.normal(0, pn["H"])

        # Parameter random walk
        A_eff_next = A_eff + np.random.normal(0, pn["A_eff"])
        alpha_next = alpha_val + np.random.normal(0, pn["alpha"])

        new_state = np.array([
            q_state_next,
            H_next,
            max(1e4, A_eff_next),
            max(0.1, min(2.0, alpha_next)),
        ])

        if has_q_obs:
            obs_pred = np.array([H_next, q_routed])
        else:
            obs_pred = np.array([H_next])

        return new_state, obs_pred

    return model_forward


def run_station_coupled_assimilation(
    station_id: str,
    station_name: str,
    h_obs: np.ndarray,
    q_in: np.ndarray,
    q_out: np.ndarray,
    q_obs: np.ndarray | None,
    model_params: dict[str, Any],
    dt: float = 3600.0,
    n_ensemble: int = 30,
    obs_noise_h: float = 0.2,
    obs_noise_q: float = 10.0,
) -> dict[str, Any]:
    n = min(len(h_obs), len(q_in), len(q_out))
    if q_obs is not None:
        n = min(n, len(q_obs))
    h_obs, q_in, q_out = h_obs[:n], q_in[:n], q_out[:n]
    has_q_obs = q_obs is not None and len(q_obs) >= n
    if has_q_obs:
        q_obs = q_obs[:n]

    H0 = float(h_obs[0])
    H_ref = model_params.get("H_ref", float(np.mean(h_obs)))
    A_eff_0 = model_params.get("A_eff", 1e6)
    alpha_0 = model_params.get("alpha", 1.0)

    base_model = ReservoirBalanceModel(
        A_eff=A_eff_0, alpha=alpha_0,
        k_area=model_params.get("k_area", 0.0),
        lag=model_params.get("lag", 0),
        beta=model_params.get("beta", 0.0),
        H_ref=H_ref,
    )

    # Open-loop
    H_openloop = base_model.simulate(q_in, q_out, H0, dt)

    # EnKF
    state_dim = 4
    obs_dim = 2 if has_q_obs else 1

    enkf = EnsembleKalmanFilter(n_ensemble)
    initial = np.zeros((state_dim, n_ensemble))
    initial[0, :] = float(q_in[0]) + np.random.normal(0, 5, n_ensemble)
    initial[1, :] = H0 + np.random.normal(0, 0.3, n_ensemble)
    initial[2, :] = A_eff_0 + np.random.normal(0, A_eff_0 * 0.05, n_ensemble)
    initial[3, :] = alpha_0 + np.random.normal(0, 0.02, n_ensemble)
    enkf.initialize(initial)

    if has_q_obs:
        R = np.diag([obs_noise_h ** 2, obs_noise_q ** 2])
    else:
        R = np.array([[obs_noise_h ** 2]])

    H_assim = np.zeros(n)
    Q_assim = np.zeros(n)
    H_assim[0] = H0
    Q_assim[0] = float(q_in[0])

    param_trace: list[dict] = []
    lag = base_model.lag

    for t in range(n - 1):
        qi_t = float(q_in[max(0, t - lag)])
        qo_t = float(q_out[t])

        fwd = _make_coupled_forward(base_model, qi_t, qo_t, dt, has_q_obs=has_q_obs)
        forecast_obs = enkf.forecast(fwd)

        if has_q_obs:
            obs_val = np.array([float(h_obs[t + 1]), float(q_obs[t + 1])])
        else:
            obs_val = np.array([float(h_obs[t + 1])])

        enkf.analysis(obs_val, forecast_obs, R)

        Q_assim[t + 1] = float(np.mean(enkf.states[0, :]))
        H_assim[t + 1] = float(np.mean(enkf.states[1, :]))

        if t % max(1, (n // 20)) == 0:
            param_trace.append({
                "t": t + 1,
                "A_eff": float(np.mean(enkf.states[2, :])),
                "alpha": float(np.mean(enkf.states[3, :])),
            })

    m_h_open = compute_metrics(h_obs, H_openloop)
    m_h_assim = compute_metrics(h_obs, H_assim)

    result: dict[str, Any] = {
        "station_id": station_id,
        "station_name": station_name,
        "n_ensemble": n_ensemble,
        "n_timesteps": n,
        "has_q_obs": has_q_obs,
        "openloop_h_metrics": m_h_open,
        "assimilated_h_metrics": m_h_assim,
        "delta_h_nse": m_h_assim["nse"] - m_h_open["nse"],
        "delta_h_rmse": m_h_open["rmse"] - m_h_assim["rmse"],
        "param_evolution": param_trace,
    }

    if has_q_obs:
        m_q_assim = compute_metrics(q_obs, Q_assim)
        result["assimilated_q_metrics"] = m_q_assim

    if param_trace:
        result["final_params"] = param_trace[-1]

    return result


def run_coupled_assimilation(
    case_id: str,
    config_path: str | None = None,
    n_ensemble: int = 30,
    obs_noise_h: float = 0.2,
    obs_noise_q: float = 10.0,
) -> dict[str, Any]:
    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "No hydromind SQLite found"}

    station_meta = build_station_meta(cfg)
    print(f"=== D1+D2 联合状态同化 (n={n_ensemble}) ===")

    station_results: list[dict[str, Any]] = []
    for sid, meta in station_meta.items():
        sname = meta.get("name", sid)
        params = _load_cal_params(case_id, sid)
        if not params:
            continue

        vars_ = meta.get("vars", ["H_up", "Q_in", "Q_out"])
        h = _load_ts(db_path, sid, vars_[0] if len(vars_) > 0 else "H_up")
        qi = _load_ts(db_path, sid, vars_[1] if len(vars_) > 1 else "Q_in")
        qo = _load_ts(db_path, sid, vars_[2] if len(vars_) > 2 else "Q_out")

        # Try to load Q observation for dual-obs mode
        q_obs = _load_ts(db_path, sid, "Q_obs")
        if len(q_obs) < 200:
            q_obs = None

        if len(h) < 200:
            continue

        print(f"\n  {sid} ({sname}): {len(h)} pts, Q_obs={'yes' if q_obs is not None else 'no'}")
        result = run_station_coupled_assimilation(
            station_id=sid, station_name=sname,
            h_obs=h, q_in=qi, q_out=qo, q_obs=q_obs,
            model_params=params, dt=3600.0,
            n_ensemble=n_ensemble,
            obs_noise_h=obs_noise_h,
            obs_noise_q=obs_noise_q,
        )
        station_results.append(result)

        oh = result["openloop_h_metrics"]
        ah = result["assimilated_h_metrics"]
        print(f"    开环H: NSE={oh['nse']:.4f}")
        print(f"    同化H: NSE={ah['nse']:.4f} (Δ={result['delta_h_nse']:+.4f})")

    deltas = [r["delta_h_nse"] for r in station_results]
    summary = {
        "n_stations": len(station_results),
        "mean_delta_h_nse": float(np.mean(deltas)) if deltas else None,
        "improved_count": sum(1 for d in deltas if d > 0),
    }

    print(f"\n=== 总结 ===")
    print(f"  站点: {summary['n_stations']}, 提升: {summary['improved_count']}")

    payload = {
        "case_id": case_id,
        "workflow": "coupled_assimilation",
        "dimension": "D1+D2",
        "n_ensemble": n_ensemble,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "station_results": station_results,
        "summary": summary,
        "_auto_generated": True,
    }

    out_path = WORKSPACE / "cases" / case_id / "contracts" / "coupled_assimilation.latest.json"
    write_json(out_path, payload)
    print(f"  合约: {out_path}")
    return payload


def main():
    parser = argparse.ArgumentParser(description="D1+D2 联合状态同化工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--n-ensemble", type=int, default=30)
    parser.add_argument("--obs-noise-h", type=float, default=0.2)
    parser.add_argument("--obs-noise-q", type=float, default=10.0)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    run_coupled_assimilation(
        case_id=args.case_id,
        config_path=args.config,
        n_ensemble=args.n_ensemble,
        obs_noise_h=args.obs_noise_h,
        obs_noise_q=args.obs_noise_q,
    )


if __name__ == "__main__":
    main()
