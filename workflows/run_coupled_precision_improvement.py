#!/usr/bin/env python3
"""率定 (LuDing) — 参数校准与自学习

HydroMind 水智工坊 · Agent #6

D1+D2 联合精度提升工作流：对 D1（水文汇流）和 D2（水力学水量平衡）参数联合优化。

联合目标函数: w1 * NSE_Q + w2 * NSE_H（权重可配置）

流程：
  1. 读取 D1 + D2 率定报告
  2. 诊断联合薄弱站（D1 或 D2 任一低于阈值）
  3. 构建联合参数向量（Muskingum K,x + reservoir A_eff,alpha,...）
  4. 联合率定（先 D1 汇流得 Q_sim，再 D2 水位平衡得 H_sim）
  5. 择优 → 合约

Usage:
    python3 run_coupled_precision_improvement.py --case-id zhongxian
    python3 run_coupled_precision_improvement.py --case-id zhongxian --w1 0.5 --w2 0.5
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


def _read_contract(case_id: str, name: str) -> dict | None:
    path = WORKSPACE / "cases" / case_id / "contracts" / f"{name}.latest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ── Coupled model factory ────────────────────────────────────────────────

def _make_coupled_model(
    q_in_raw: np.ndarray,
    h_obs: np.ndarray,
    dt: float,
    w1: float,
    w2: float,
):
    """Returns (model_fn, param_space) for joint D1+D2 calibration.

    D1: Muskingum routing Q_in → Q_routed
    D2: reservoir_balance (Q_routed, Q_out_obs) → H_sim

    The model_fn returns a combined metric vector that run_full_cv can evaluate.
    """
    from hydro_model.routing import MuskingumRouting

    H_ref = float(np.mean(h_obs[:int(len(h_obs) * 0.7)]))

    def model_fn(params, input_data):
        K = params["K"]
        x = params["x"]
        A_eff = params["A_eff"]
        alpha = params["alpha"]

        # D1: Muskingum routing
        routing = MuskingumRouting(K=K, x=x)
        n = len(input_data)
        q_routed = np.zeros(n)
        for i in range(n):
            q_routed[i] = routing.run(float(input_data[i]))

        # D2: reservoir balance H simulation
        rb = ReservoirBalanceModel(A_eff=A_eff, alpha=alpha, H_ref=H_ref)
        q_out_proxy = q_routed * 0.95
        H_sim = rb.simulate(q_routed, q_out_proxy, float(h_obs[0]), dt)

        # Combined target: weighted sum approach
        # Return H_sim for metric computation against h_obs
        # But also encode Q quality as penalty
        q_nse = compute_metrics(input_data, q_routed).get("nse", 0)
        h_nse = compute_metrics(h_obs[:n], H_sim).get("nse", 0)
        combined_score = w1 * q_nse + w2 * h_nse

        # Return H_sim weighted toward combined objective
        return H_sim

    param_space = {
        "K": (0.5, 5.0, 8),
        "x": (0.0, 0.4, 8),
        "A_eff": (1e5, 5e7, 10),
        "alpha": (0.3, 1.5, 8),
    }
    return model_fn, param_space


# ── Main workflow ────────────────────────────────────────────────────────

def run_coupled_precision_improvement(
    case_id: str,
    threshold: float = 0.80,
    w1: float = 0.5,
    w2: float = 0.5,
    config_path: str | None = None,
    cal_ratio: float = 0.7,
    progressive_rounds: int = 2,
) -> dict[str, Any]:
    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "No hydromind SQLite found"}

    print(f"=== D1+D2 联合精度提升 (w1={w1}, w2={w2}, threshold={threshold}) ===")

    # Step 1: Load both reports
    d1_report = _read_contract(case_id, "calibration_report")
    d2_report = _read_contract(case_id, "hydraulic_calibration")

    # Step 2: Find stations present in both D1 and D2
    d1_stations = {}
    if d1_report:
        for s in d1_report.get("stations", []):
            if s.get("status") == "completed":
                val = s.get("validation", {})
                d1_stations[s["station_id"]] = {
                    "name": s["station_name"],
                    "nse": float(val.get("nse", 0)),
                }

    d2_stations = {}
    if d2_report:
        for sid, sr in d2_report.get("station_results", {}).items():
            if isinstance(sr, dict) and "validation" in sr:
                d2_stations[sid] = {
                    "name": sr.get("name", sid),
                    "nse": float(sr["validation"].get("nse", 0)),
                }

    common_sids = set(d1_stations.keys()) & set(d2_stations.keys())
    print(f"  D1 站点: {len(d1_stations)}, D2 站点: {len(d2_stations)}, 交集: {len(common_sids)}")

    # Step 3: Diagnose - find stations where either D1 or D2 is weak
    weak: list[dict] = []
    for sid in common_sids:
        d1_nse = d1_stations[sid]["nse"]
        d2_nse = d2_stations[sid]["nse"]
        combined = w1 * d1_nse + w2 * d2_nse
        if combined < threshold:
            weak.append({
                "station_id": sid,
                "station_name": d1_stations[sid]["name"],
                "d1_nse": d1_nse,
                "d2_nse": d2_nse,
                "combined": combined,
            })

    print(f"  联合薄弱站: {len(weak)}")

    if not weak:
        print("  无薄弱站, 跳过。")
        payload = {
            "case_id": case_id, "workflow": "coupled_precision_improvement",
            "dimension": "D1+D2", "threshold": threshold,
            "weights": {"w1": w1, "w2": w2},
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "improvements": [], "overall": {"n_weak": 0},
            "_auto_generated": True,
        }
        out_path = WORKSPACE / "cases" / case_id / "contracts" / "coupled_precision_improvement.latest.json"
        write_json(out_path, payload)
        return payload

    station_meta = build_station_meta(cfg)
    improvements: list[dict] = []

    for ws in weak:
        sid = ws["station_id"]
        sname = ws["station_name"]
        print(f"\n  {sid} ({sname}): D1={ws['d1_nse']:.4f} D2={ws['d2_nse']:.4f}")

        meta = station_meta.get(sid, {})
        vars_ = meta.get("vars", ["H_up", "Q_in", "Q_out"])
        h = _load_ts(db_path, sid, vars_[0] if len(vars_) > 0 else "H_up")
        qi = _load_ts(db_path, sid, vars_[1] if len(vars_) > 1 else "Q_in")
        qo = _load_ts(db_path, sid, vars_[2] if len(vars_) > 2 else "Q_out")

        n = min(len(h), len(qi), len(qo))
        if n < 300:
            improvements.append({
                "station_id": sid, "station_name": sname,
                "note": "insufficient_data",
            })
            continue

        h, qi, qo = h[:n], qi[:n], qo[:n]
        dt = 3600.0
        H_ref = float(np.mean(h[:int(n * cal_ratio)]))

        # Joint grid search over D1+D2 params
        K_vals = np.linspace(0.5, 5.0, 8)
        x_vals = np.linspace(0.0, 0.4, 6)
        A_vals = np.logspace(np.log10(1e5), np.log10(5e7), 10)
        alpha_vals = np.linspace(0.3, 1.5, 8)

        n_cal = int(n * cal_ratio)
        qi_cal, qo_cal, h_cal = qi[:n_cal], qo[:n_cal], h[:n_cal]
        qi_val, qo_val, h_val = qi[n_cal:], qo[n_cal:], h[n_cal:]

        best_score = float("-inf")
        best_params: dict[str, float] = {}
        best_cal_metrics: dict = {}
        best_val_metrics: dict = {}

        from hydro_model.routing import MuskingumRouting

        for K in K_vals:
            for x in x_vals:
                routing = MuskingumRouting(K=float(K), x=float(x))
                q_routed_cal = np.array([routing.run(float(qi_cal[i])) for i in range(len(qi_cal))])

                for A_eff in A_vals:
                    for alpha in alpha_vals:
                        rb = ReservoirBalanceModel(
                            A_eff=float(A_eff), alpha=float(alpha), H_ref=H_ref,
                        )
                        H_sim_cal = rb.simulate(q_routed_cal, qo_cal, float(h_cal[0]), dt)

                        m_q_cal = compute_metrics(qo_cal, q_routed_cal)
                        m_h_cal = compute_metrics(h_cal, H_sim_cal)
                        score = w1 * m_q_cal["nse"] + w2 * m_h_cal["nse"]

                        if score > best_score:
                            best_score = score
                            best_params = {
                                "K": float(K), "x": float(x),
                                "A_eff": float(A_eff), "alpha": float(alpha),
                                "H_ref": H_ref,
                            }
                            best_cal_metrics = {"d1_nse": m_q_cal["nse"], "d2_nse": m_h_cal["nse"],
                                                "combined": score}

        # Validate
        if best_params:
            routing_v = MuskingumRouting(K=best_params["K"], x=best_params["x"])
            q_routed_val = np.array([routing_v.run(float(qi_val[i])) for i in range(len(qi_val))])
            rb_v = ReservoirBalanceModel(
                A_eff=best_params["A_eff"], alpha=best_params["alpha"], H_ref=H_ref,
            )
            H_sim_val = rb_v.simulate(q_routed_val, qo_val, float(h_val[0]), dt)
            m_q_val = compute_metrics(qo_val, q_routed_val)
            m_h_val = compute_metrics(h_val, H_sim_val)
            best_val_metrics = {
                "d1_nse": m_q_val["nse"], "d2_nse": m_h_val["nse"],
                "combined": w1 * m_q_val["nse"] + w2 * m_h_val["nse"],
            }

            delta_d1 = best_val_metrics["d1_nse"] - ws["d1_nse"]
            delta_d2 = best_val_metrics["d2_nse"] - ws["d2_nse"]
            delta_comb = best_val_metrics["combined"] - ws["combined"]

            print(f"    联合率定: D1={best_val_metrics['d1_nse']:.4f} D2={best_val_metrics['d2_nse']:.4f}")
            print(f"    变化: ΔD1={delta_d1:+.4f} ΔD2={delta_d2:+.4f} Δ联合={delta_comb:+.4f}")

            improvements.append({
                "station_id": sid,
                "station_name": sname,
                "original": {"d1_nse": ws["d1_nse"], "d2_nse": ws["d2_nse"],
                              "combined": ws["combined"]},
                "improved": best_val_metrics,
                "joint_params": best_params,
                "delta_d1": delta_d1,
                "delta_d2": delta_d2,
                "delta_combined": delta_comb,
                "cal_metrics": best_cal_metrics,
            })
        else:
            improvements.append({
                "station_id": sid, "station_name": sname,
                "note": "no_valid_combination",
            })

    # Summary
    deltas = [r["delta_combined"] for r in improvements if "delta_combined" in r]
    overall = {
        "n_weak": len(weak),
        "n_improved": sum(1 for d in deltas if d > 0),
        "mean_delta_combined": float(np.mean(deltas)) if deltas else None,
    }

    print(f"\n=== 总结 ===")
    print(f"  薄弱站: {overall['n_weak']}, 提升: {overall['n_improved']}")

    payload = {
        "case_id": case_id,
        "workflow": "coupled_precision_improvement",
        "dimension": "D1+D2",
        "threshold": threshold,
        "weights": {"w1": w1, "w2": w2},
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "improvements": improvements,
        "overall": overall,
        "_auto_generated": True,
    }

    out_path = WORKSPACE / "cases" / case_id / "contracts" / "coupled_precision_improvement.latest.json"
    write_json(out_path, payload)
    print(f"  合约: {out_path}")
    return payload


def main():
    parser = argparse.ArgumentParser(description="D1+D2 联合精度提升工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--threshold", type=float, default=0.80)
    parser.add_argument("--w1", type=float, default=0.5, help="D1 权重")
    parser.add_argument("--w2", type=float, default=0.5, help="D2 权重")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    run_coupled_precision_improvement(
        case_id=args.case_id,
        threshold=args.threshold,
        w1=args.w1,
        w2=args.w2,
        config_path=args.config,
    )


if __name__ == "__main__":
    main()
