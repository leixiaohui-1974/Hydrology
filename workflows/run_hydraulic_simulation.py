#!/usr/bin/env python3
"""推演 (TuiYan) — 水力仿真与耦合计算

HydroMind 水智工坊 · Agent #6

水力学梯级联合模拟工作流。

功能：
  1. replay   — 历史回溯验证（用观测 Q_in/Q_out 驱动）
  2. cascade  — 级联验证（上游 Q_out → Muskingum → 下游 Q_in）
  3. scenario — 场景模拟（控制输入驱动）
  4. report   — 生成精度报告

Usage:
    python3 -m workflows run hyd_sim --case-id zhongxian --mode replay
    python3 -m workflows run hyd_sim --case-id zhongxian --mode cascade
    python3 workflows/run_hydraulic_simulation.py --case-id zhongxian
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from hydro_model.hydraulic_simulator import (
    CascadeSimulator, CascadeSimulatorConfig, REACH_ORDER, STATION_META,
)
from hydro_model.reservoir_balance import compute_metrics
from workflows._shared import abs_path, load_case_config, load_json, write_json, WORKSPACE, build_station_meta, get_station_ids


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


def _build_cascade_diagram(cfg: dict) -> str:
    """从配置动态生成级联示意图文字。"""
    from workflows._shared import build_sid_to_name
    sid_name = build_sid_to_name(cfg)
    ids = get_station_ids(cfg)
    if not ids:
        return "上游入流 → [stations] → 下游"
    parts = [f"上游入流 → [{ids[0]} {sid_name.get(ids[0], '')}]"]
    for s in ids[1:]:
        parts.append(f"→ Muskingum → [{s} {sid_name.get(s, '')}]")
    return " ".join(parts)


def _load_all_ts(db_path: str, cfg: dict) -> dict[str, dict[str, np.ndarray]]:
    """加载所有站的 H, Q_in, Q_out。"""
    station_meta = build_station_meta(cfg)
    data: dict[str, dict[str, np.ndarray]] = {}
    for sid, meta in station_meta.items():
        v = meta.get("vars", ["H_up", "Q_in", "Q_out"])
        H = _load_ts(db_path, sid, v[0] if v else "H_up")
        Q_in = _load_ts(db_path, sid, v[1] if len(v) > 1 else "Q_in")
        Q_out = _load_ts(db_path, sid, v[2] if len(v) > 2 else "Q_out")
        n = min(len(H), len(Q_in), len(Q_out))
        if n > 0:
            data[sid] = {"H": H[:n], "Q_in": Q_in[:n], "Q_out": Q_out[:n]}
    return data


def run_replay_verification(case_id: str) -> dict:
    """回溯验证：用历史 Q_in/Q_out 驱动，对比模拟水位与观测水位。"""
    cfg = load_case_config(case_id)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "database not found"}

    print(f"[replay] 加载数据 db={db_path}")
    data = _load_all_ts(db_path, cfg)

    sim = CascadeSimulator.from_case(case_id)

    Q_in_s = {sid: d["Q_in"] for sid, d in data.items()}
    Q_out_s = {sid: d["Q_out"] for sid, d in data.items()}
    H_obs = {sid: d["H"] for sid, d in data.items()}

    print(f"[replay] 运行回溯模拟，站点={list(data.keys())}")
    result = sim.run_replay(Q_in_s, Q_out_s, H_obs)

    print("\n" + "=" * 60)
    print("  回溯验证结果 (Replay Mode)")
    print("=" * 60)

    summary = {}
    for sid in REACH_ORDER:
        if sid not in result:
            continue
        r = result[sid]
        m = r.get("metrics", {})
        name = STATION_META.get(sid, {}).get("name", sid)
        nse = m.get("nse", float("-inf"))
        rmse = m.get("rmse", float("inf"))
        print(f"  {sid} {name:6s}  NSE={nse:.4f}  RMSE={rmse:.3f}m  n={r['n']}")
        summary[sid] = {
            "name": name,
            "nse": round(nse, 4),
            "rmse": round(rmse, 4),
            "n": r["n"],
        }

    nse_values = [s["nse"] for s in summary.values() if s["nse"] > -100]
    avg_nse = np.mean(nse_values) if nse_values else 0.0
    print(f"\n  平均 NSE = {avg_nse:.4f}")
    print("=" * 60)

    return {
        "mode": "replay",
        "stations": summary,
        "avg_nse": round(avg_nse, 4),
        "timestamp": datetime.now().isoformat(),
    }


def run_cascade_verification(case_id: str) -> dict:
    """级联验证：仅第一站用观测 Q_in，后续站由上游传播。"""
    cfg = load_case_config(case_id)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "database not found"}

    print(f"[cascade] 加载数据 db={db_path}")
    data = _load_all_ts(db_path, cfg)

    station_ids = get_station_ids(cfg)
    first_station = station_ids[0] if station_ids else sorted(data.keys())[0]
    if first_station not in data:
        return {"error": f"{first_station} data missing"}

    sim = CascadeSimulator.from_case(case_id)

    upstream_Q = data[first_station]["Q_in"]
    Q_out_s = {sid: d["Q_out"] for sid, d in data.items()}
    H_obs = {sid: d["H"] for sid, d in data.items()}

    print(f"[cascade] 运行级联模拟，上游入流 n={len(upstream_Q)}")
    result = sim.run_cascade(upstream_Q, Q_out_s, H_obs=H_obs)

    print("\n" + "=" * 60)
    print("  级联验证结果 (Cascade Mode)")
    print("=" * 60)

    summary = {}
    for sid in REACH_ORDER:
        if sid not in result:
            continue
        r = result[sid]
        m = r.get("metrics", {})
        name = STATION_META.get(sid, {}).get("name", sid)
        nse = m.get("nse", float("-inf"))
        rmse = m.get("rmse", float("inf"))
        print(f"  {sid} {name:6s}  NSE={nse:.4f}  RMSE={rmse:.3f}m  n={r['n']}")
        summary[sid] = {
            "name": name,
            "nse": round(nse, 4),
            "rmse": round(rmse, 4),
            "n": r["n"],
        }

    nse_values = [s["nse"] for s in summary.values() if s["nse"] > -100]
    avg_nse = np.mean(nse_values) if nse_values else 0.0
    print(f"\n  平均 NSE = {avg_nse:.4f}")
    print("=" * 60)

    return {
        "mode": "cascade",
        "stations": summary,
        "avg_nse": round(avg_nse, 4),
        "timestamp": datetime.now().isoformat(),
    }


def generate_report(case_id: str, replay_res: dict, cascade_res: dict) -> str:
    """生成水力学模拟精度报告。"""
    out_dir = WORKSPACE / "cases" / case_id / "contracts"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_case_config(case_id)

    lines = [
        "# 水力学梯级联合模拟精度报告",
        "",
        f"**案例**: {case_id}",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**模型**: 水库水量平衡 + Muskingum 河道演算",
        "",
        "## 1. 回溯验证 (Replay Mode)",
        "",
        "用历史观测 Q_in / Q_out 驱动各站独立水量平衡模型。",
        "",
        "| 站点 | 名称 | NSE | RMSE (m) | 数据量 |",
        "|------|------|-----|----------|--------|",
    ]

    for sid in REACH_ORDER:
        s = replay_res.get("stations", {}).get(sid, {})
        if s:
            lines.append(f"| {sid} | {s['name']} | {s['nse']:.4f} | {s['rmse']:.3f} | {s['n']} |")

    lines.extend([
        "",
        f"**平均 NSE**: {replay_res.get('avg_nse', 'N/A')}",
        "",
        "## 2. 级联验证 (Cascade Mode)",
        "",
        "仅第一站用观测入流，后续站由上游出流经 Muskingum 演算传播。",
        "",
        "| 站点 | 名称 | NSE | RMSE (m) | 数据量 |",
        "|------|------|-----|----------|--------|",
    ])

    for sid in REACH_ORDER:
        s = cascade_res.get("stations", {}).get(sid, {})
        if s:
            lines.append(f"| {sid} | {s['name']} | {s['nse']:.4f} | {s['rmse']:.3f} | {s['n']} |")

    lines.extend([
        "",
        f"**平均 NSE**: {cascade_res.get('avg_nse', 'N/A')}",
        "",
        "## 3. 模型架构",
        "",
        "```",
        _build_cascade_diagram(cfg),
        "```",
        "",
        "### 关键创新",
        "",
        "1. **真实断面驱动**: A(H) 从实测断面计算",
        "2. **率定参数复用**: D2 水力学率定的 (A_eff, alpha, beta, lag) 直接加载",
        "3. **三种运行模式**: replay / cascade / scenario",
        "4. **逐步接口**: 支持 SIL 软件在环测试",
        "",
        "## 4. 下一步",
        "",
        "- [ ] 场景模式验证（闸门/机组控制 → 水位预测）",
        "- [ ] ODD 评价框架（多场景组合覆盖度）",
        "- [ ] SIL 接口对接",
        "",
        f"_auto_generated: {datetime.now().isoformat()}_",
    ])

    report_path = out_dir / "hydraulic_cascade_simulation_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[report] 已生成 → {report_path}")

    # 同时保存 JSON 合约
    contract = {
        "_auto_generated": datetime.now().isoformat(),
        "replay": replay_res,
        "cascade": cascade_res,
    }
    json_path = out_dir / "hydraulic_cascade_simulation.json"
    write_json(json_path, contract)
    print(f"[report] JSON合约 → {json_path}")

    return str(report_path)


def run_simulation(case_id: str, mode: str = "all", hydraulics_activation: dict | None = None) -> dict:
    """主入口。"""
    replay_res = {}
    cascade_res = {}

    if mode in ("all", "replay"):
        replay_res = run_replay_verification(case_id)

    if mode in ("all", "cascade"):
        cascade_res = run_cascade_verification(case_id)

    if mode != "scenario":
        report_path = generate_report(case_id, replay_res, cascade_res)

    return {
        "status": "completed",
        "replay": replay_res,
        "cascade": cascade_res,
    }


def main():
    parser = argparse.ArgumentParser(description="水力学梯级联合模拟")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--mode", choices=["all", "replay", "cascade", "scenario"],
                        default="all")
    parser.add_argument("--parameter-governance-json", required=True, help="Parameter governance envelope JSON")
    args = parser.parse_args()

    governance = load_json(abs_path(args.parameter_governance_json, label="--parameter-governance-json"))
    hydraulics_candidates = (governance.get("candidate_set") or {}).get("hydraulics")
    if not hydraulics_candidates:
        raise ValueError("parameter governance must contain hydraulics candidate_set")
    activation_record_path = (governance.get("artifact_paths") or {}).get("correction_activation_record")
    if not activation_record_path:
        raise ValueError("parameter governance must expose correction_activation_record")
    activation_record = load_json(abs_path(activation_record_path, label="correction_activation_record"))
    hydraulics_activation = activation_record.get("hydraulics")
    if not hydraulics_activation:
        raise ValueError("correction activation record must contain hydraulics values")

    result = run_simulation(args.case_id, args.mode, hydraulics_activation=hydraulics_activation)
    print(f"\n完成: avg_nse(replay)={result.get('replay', {}).get('avg_nse', 'N/A')}"
          f"  avg_nse(cascade)={result.get('cascade', {}).get('avg_nse', 'N/A')}")


if __name__ == "__main__":
    main()
