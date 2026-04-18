#!/usr/bin/env python3
"""推演 (TuiYan) — 水力仿真与耦合计算

HydroMind 水智工坊 · Agent #6

D4 状态估计工作流 — 基于扩展卡尔曼滤波 (EKF) 的水库水位估计。

物理模型：
  dZ/dt = (Q_in - Q_out) / A(Z)
  其中 A(Z) 由水位-面积关系或常数面积近似

测量模型：
  Z_obs = Z_true + v,  v ~ N(0, R)

EKF 步骤：
  1. 预测: Z_pred = Z + dt * (Q_in - Q_out) / A(Z)
  2. 更新: K = P_pred / (P_pred + R);  Z_est = Z_pred + K * (Z_obs - Z_pred)

评价指标：
  - RMSE(Z_est - Z_obs)
  - Nash-Sutcliffe of estimated vs observed
  - 收敛稳定性

设计原则：
  - 零硬编码：所有参数从 case YAML knowledge 层读取
  - 通用：适用于任何有水位观测的案例
  - 产品化：输出标准合约 JSON

Usage:
    python3 run_state_estimation.py --case-id zhongxian
    python3 run_state_estimation.py --case-id zhongxian --process-noise 0.1 --meas-noise 0.5
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

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import load_case_config, WORKSPACE, coerce_path_str
from hydro_model.control.mock_sensors import MockSensor
from hydro_model.object_report_generator import ObjectReportGenerator


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _nse(sim: np.ndarray, obs: np.ndarray) -> float:
    """Nash-Sutcliffe Efficiency."""
    if len(obs) < 2:
        return float("nan")
    mean_obs = np.mean(obs)
    ss_res = np.sum((obs - sim) ** 2)
    ss_tot = np.sum((obs - mean_obs) ** 2)
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else float("-inf")
    return float(1.0 - ss_res / ss_tot)


# ── 数据准备 ──────────────────────────────────────────────────────────────────

def _load_timeseries_from_sqlite(
    sqlite_paths: list[str],
    station_name: str,
    variable: str = "Z",
) -> tuple[np.ndarray, np.ndarray]:
    """从 SQLite 加载时序数据。返回 (timestamps, values)。"""
    import sqlite3

    for sp in sqlite_paths:
        full_path = WORKSPACE / sp if not Path(sp).is_absolute() else Path(sp)
        if not full_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(full_path))
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]

            for table in tables:
                cols = [c[1] for c in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]
                time_col = next((c for c in cols if c.lower() in ("time", "datetime", "timestamp", "date")), None)
                val_col = next((c for c in cols if c.lower() == variable.lower()), None)
                if not time_col or not val_col:
                    continue

                rows = conn.execute(f"SELECT {time_col}, {val_col} FROM {table} WHERE name=? OR station=?", (station_name, station_name)).fetchall()
                if rows:
                    t = np.array([r[0] for r in rows])
                    v = np.array([r[1] for r in rows])
                    return t, v
        except Exception:
            continue

    return np.array([]), np.array([])


def _load_hydraulic_levels(contracts_dir: Path) -> dict[str, np.ndarray]:
    """从水动力合约中加载各节点水位时序。"""
    levels = {}

    unsteady = _load_json(contracts_dir / "hydraulics_unsteady.latest.json")
    for name, info in unsteady.get("node_results", {}).items():
        if isinstance(info, dict) and "water_levels" in info:
            wl = info["water_levels"]
            if isinstance(wl, list) and wl:
                levels[name] = np.array(wl)

    if not levels:
        for name, info in unsteady.get("node_results", {}).items():
            if isinstance(info, dict):
                final_level = info.get("final_level") or info.get("water_level")
                zb = info.get("zb", 0)
                if final_level is not None:
                    levels[name] = np.array([float(final_level)])

    return levels


def _load_inflows(contracts_dir: Path) -> dict[str, float]:
    """从水动力合约中加载各节点流量。"""
    inflows = {}
    steady = _load_json(contracts_dir / "hydraulics_steady.latest.json")
    for name, info in steady.get("node_results", {}).items():
        if isinstance(info, dict):
            q = info.get("inflow_m3s", info.get("Q", 0.0))
            inflows[name] = float(q) if q else 0.0
    return inflows


# ── EKF 核心 ──────────────────────────────────────────────────────────────────

def ekf_reservoir(
    z_obs: np.ndarray,
    q_in: float,
    q_out: float,
    area: float,
    dt: float = 3600.0,
    process_noise: float = 0.01,
    meas_noise: float = 0.5,
    robust_threshold: float = 3.0,  # 新增抗差阈值 (默认 3-sigma)
    sensor_count: int = 1,
) -> dict[str, Any]:
    """对单个水库运行 EKF 状态估计。动态构建观测矩阵 H 和误差协方差矩阵 R。

    Args:
        z_obs: 观测水位序列
        q_in: 入流 (m³/s)
        q_out: 出流 (m³/s)
        area: 水面面积近似 (m²)
        dt: 时间步长 (s)
        process_noise: 过程噪声方差 Q
        meas_noise: 测量噪声方差 R
        robust_threshold: 抗差拦截的 sigma 阈值
        sensor_count: 传感器数量（用于动态构建 H 和 R 矩阵）
    """
    n = len(z_obs)
    if n < 2:
        return {"status": "insufficient_data", "n_obs": n}

    valid_mask = ~np.isnan(z_obs)
    if np.sum(valid_mask) == 0:
        return {"status": "insufficient_data", "n_obs": n}
        
    z_est = np.zeros(n)
    z_pred = np.zeros(n)
    P = np.zeros(n)
    K_gain = np.zeros(n)
    innovations = np.zeros(n)

    # 动态构建观测矩阵 H 和 观测误差协方差矩阵 R
    # 这里为了通用化，假设有 sensor_count 个传感器观测同一个水位
    # 状态向量维度为 1，观测向量维度为 sensor_count
    H = np.ones((sensor_count, 1))
    R_mat = np.eye(sensor_count) * meas_noise
    Q_mat = np.array([[process_noise]])

    # Find first valid observation for initialization
    first_valid_idx = np.argmax(valid_mask)
    z_est[0] = z_obs[first_valid_idx] if first_valid_idx == 0 else z_obs[first_valid_idx] # Approximation for missing initial
    P[0] = meas_noise

    dz_per_step = (q_in - q_out) * dt / max(area, 1.0)

    for k in range(1, n):
        z_pred[k] = z_est[k - 1] + dz_per_step
        P_pred = P[k - 1] + Q_mat[0, 0]

        if np.isnan(z_obs[k]):
            # Packet loss (Predict-only / Hold)
            z_est[k] = z_pred[k]
            P[k] = P_pred
            innovations[k] = 0.0
            K_gain[k] = 0.0
        else:
            # 扩展为多传感器观测 (此处简化为将同一个观测值复制 sensor_count 份以适配矩阵维度)
            y_k = np.full((sensor_count, 1), z_obs[k])
            
            # 预测观测值
            y_pred = H @ np.array([[z_pred[k]]])
            innovation_vec = y_k - y_pred
            
            # 创新协方差 S = H * P_pred * H^T + R
            S = H @ np.array([[P_pred]]) @ H.T + R_mat
            
            # 计算卡尔曼增益 K = P_pred * H^T * S^-1
            # 对于标量状态和对角R，可以简化，但这里保留矩阵运算结构以体现泛化
            K_mat = np.array([[P_pred]]) @ H.T @ np.linalg.inv(S)
            
            innovation = innovation_vec[0, 0]
            innovation_std = np.sqrt(S[0, 0])
            
            # 抗差拦截 (Robust interception): 极端离群点拦截，按丢包处理 (Predict-only)
            if abs(innovation) > robust_threshold * innovation_std:
                z_est[k] = z_pred[k]
                P[k] = P_pred
                innovations[k] = innovation  # 记录实际 innovation，但增益为 0
                K_gain[k] = 0.0
            else:
                innovations[k] = innovation
                K_gain[k] = K_mat[0, 0]
                
                # 状态更新
                z_est_vec = np.array([[z_pred[k]]]) + K_mat @ innovation_vec
                z_est[k] = z_est_vec[0, 0]
                
                # 协方差更新
                P_mat = (np.eye(1) - K_mat @ H) @ np.array([[P_pred]])
                P[k] = P_mat[0, 0]

    # Compute metrics only on valid observations
    valid_mask = ~np.isnan(z_obs)
    if np.sum(valid_mask) > 0:
        residuals = z_est[valid_mask] - z_obs[valid_mask]
        rmse = float(np.sqrt(np.mean(residuals ** 2)))
        nse = _nse(z_est[valid_mask], z_obs[valid_mask])
    else:
        rmse = float('inf')
        nse = float('-inf')

    max_innov = float(np.max(np.abs(innovations[1:]))) if n > 1 else 0.0
    mean_gain = float(np.mean(K_gain[1:])) if n > 1 else 0.0

    converged = rmse < 2.0 and nse > 0.5

    # Convert to list and replace NaN with None for JSON serialization
    z_obs_list = [val if not np.isnan(val) else None for val in z_obs[:5].tolist()]
    
    return {
        "status": "completed",
        "n_obs": n,
        "rmse_m": round(rmse, 4),
        "nse": round(nse, 4),
        "max_innovation_m": round(max_innov, 4),
        "mean_kalman_gain": round(mean_gain, 4),
        "converged": converged,
        "z_est_first5": z_est[:5].tolist(),
        "z_obs_first5": z_obs_list,
        "process_noise": process_noise,
        "meas_noise": meas_noise,
    }


# ── 多站点状态估计 ─────────────────────────────────────────────────────────────

def run_state_estimation(
    case_id: str,
    *,
    config_path: str | None = None,
    process_noise: float = 0.01,
    meas_noise: float = 0.5,
    dt_seconds: float = 3600.0,
    use_mock_sensor: bool = False,
    mock_packet_loss: float = 0.05,
    mock_noise_std: float = 0.01,
    mock_drift_std: float = 0.001,
) -> dict[str, Any]:
    """对案例的所有水库/节点运行 EKF 状态估计。"""
    cfg = load_case_config(case_id, config_path)
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"

    knowledge = cfg.get("knowledge", {})
    reservoirs = knowledge.get("reservoirs", {})
    topology_nodes = knowledge.get("topology", {}).get("nodes", {})

    sqlite_paths: list[str] = []
    for raw in cfg.get("sqlite_paths", []) or []:
        p = coerce_path_str(raw)
        if p:
            sqlite_paths.append(p)
    for raw in knowledge.get("scada_timeseries", {}).get("files", []) or []:
        p = coerce_path_str(raw)
        if p:
            sqlite_paths.append(p)
    sqlite_paths.sort(key=lambda x: (0 if "hydromind" in x.lower() else 1, x))
        
    hydraulic_levels = _load_hydraulic_levels(contracts_dir)
    inflows = _load_inflows(contracts_dir)

    station_results: dict[str, Any] = {}
    total_rmse = 0.0
    total_nse = 0.0
    n_completed = 0
    primary_total_rmse = 0.0
    primary_total_nse = 0.0
    primary_completed = 0

    print(f"\n[D4 状态估计] 案例: {case_id}")
    print(f"  水库数: {len(reservoirs)}, 节点数: {len(topology_nodes)}")
    print(f"  水动力水位序列: {len(hydraulic_levels)} 个节点")
    print(f"  参数: Q={process_noise}, R={meas_noise}, dt={dt_seconds}s")

    targets = list(reservoirs.items())
    if not targets:
        targets = [(name, {"name": name, "Amin": info.get("Amin", 22500)})
                    for name, info in topology_nodes.items()]

    for sid, rinfo in targets:
        name = rinfo.get("name", sid)
        area = rinfo.get("basin_area_km2", 0)
        area_m2 = area * 1e6 if area and area > 0 else rinfo.get("Amin", 22500.0)

        z_obs = None
        source = "none"

        for node_name, levels in hydraulic_levels.items():
            if name in node_name or node_name in name:
                if len(levels) > 1:
                    z_obs = levels
                    source = "hydraulics_unsteady"
                    break

        if z_obs is None and sqlite_paths:
            _, values = _load_timeseries_from_sqlite(sqlite_paths, name, "Z")
            if len(values) > 1:
                # 引入数据质量控制 (QC)：过滤物理异常极值
                qc_cfg = knowledge.get("qc", {})
                valid_min = qc_cfg.get("z_min", -10.0)
                valid_max = qc_cfg.get("z_max", 50.0)
                
                valid_mask = (values >= valid_min) & (values <= valid_max)
                if np.sum(valid_mask) > 1:
                    z_obs = values[valid_mask]
                    source = "sqlite"

        if z_obs is None:
            node_info = topology_nodes.get(f"{name}前", topology_nodes.get(f"{name}后", {}))
            zb = node_info.get("zb", rinfo.get("elevation_m", 0))
            normal_pool = rinfo.get("normal_pool_m")
            if normal_pool is None and zb is not None:
                normal_pool = zb + 2.0  # Fallback for synthetic data
            if zb is not None and normal_pool is not None:
                z_obs = np.linspace(normal_pool - 2, normal_pool + 2, 100) + np.random.normal(0, 0.3, 100)
                source = "synthetic_from_params"

        if z_obs is None or len(z_obs) < 2:
            station_results[sid] = {
                "name": name,
                "status": "no_data",
                "source": "none",
            }
            print(f"  ✗ {name}: 无观测数据")
            continue

        q_in = inflows.get(f"{name}前", inflows.get(name, 100.0))
        q_out_candidates = [
            inflows.get(f"{name}后", 0),
        ]
        q_out = max(q_out_candidates) if any(q_out_candidates) else q_in * 0.95

        # 注入 Mock Sensor 数据
        if use_mock_sensor and z_obs is not None:
            sensor = MockSensor(
                noise_std=mock_noise_std,
                drift_std=mock_drift_std,
                packet_loss_rate=mock_packet_loss
            )
            z_obs = sensor.generate_series(z_obs)
            source = f"{source}_mocked"

        result = ekf_reservoir(
            z_obs=z_obs,
            q_in=q_in,
            q_out=q_out,
            area=area_m2,
            dt=dt_seconds,
            process_noise=process_noise,
            meas_noise=meas_noise,
        )
        result["name"] = name
        result["source"] = source
        result["area_m2"] = area_m2
        station_results[sid] = result

        if result["status"] == "completed":
            total_rmse += result["rmse_m"]
            total_nse += result["nse"]
            n_completed += 1
            if not str(source).startswith("synthetic_from_params"):
                primary_total_rmse += result["rmse_m"]
                primary_total_nse += result["nse"]
                primary_completed += 1
            status_icon = "✓" if result["converged"] else "△"
            print(f"  {status_icon} {name}: RMSE={result['rmse_m']:.4f}m, "
                  f"NSE={result['nse']:.4f}, K_gain={result['mean_kalman_gain']:.3f} [{source}]")

    avg_rmse = total_rmse / max(n_completed, 1)
    avg_nse = total_nse / max(n_completed, 1)
    primary_avg_rmse = primary_total_rmse / max(primary_completed, 1)
    primary_avg_nse = primary_total_nse / max(primary_completed, 1)
    n_converged = sum(1 for r in station_results.values()
                      if isinstance(r, dict) and r.get("converged"))
    primary_converged = sum(
        1
        for r in station_results.values()
        if isinstance(r, dict)
        and r.get("status") == "completed"
        and r.get("converged")
        and not str(r.get("source", "")).startswith("synthetic_from_params")
    )
    synthetic_count = sum(
        1
        for r in station_results.values()
        if isinstance(r, dict) and str(r.get("source", "")).startswith("synthetic_from_params")
    )
    no_data_count = sum(
        1
        for r in station_results.values()
        if isinstance(r, dict) and r.get("status") == "no_data"
    )
    unconverged_count = max(n_completed - n_converged, 0)

    d4_score = _compute_d4_score(primary_completed or n_completed, primary_converged or n_converged, primary_avg_rmse if primary_completed else avg_rmse, primary_avg_nse if primary_completed else avg_nse)

    outcome_status = "completed"
    quality_gate_passed = True
    quality_reasons: list[str] = []
    if n_completed == 0:
        outcome_status = "no_data"
        quality_gate_passed = False
        quality_reasons.append("没有可用于状态估计的有效观测序列")
    elif primary_completed == 0:
        outcome_status = "degraded"
        quality_gate_passed = False
        quality_reasons.append("缺少真实观测站点，当前结果仅基于 synthetic_from_params 回退")
    elif primary_avg_nse < 0 or primary_converged == 0:
        outcome_status = "quality_failed"
        quality_gate_passed = False
        quality_reasons.append(f"状态估计整体质量未达标（primary_avg_nse={primary_avg_nse:.4f}, converged={primary_converged}/{primary_completed}）")
    elif synthetic_count > 0 or unconverged_count > 0:
        outcome_status = "degraded"
        quality_gate_passed = False
        if synthetic_count > 0:
            quality_reasons.append(f"{synthetic_count} 个站点使用 synthetic_from_params 回退")
        if unconverged_count > 0:
            quality_reasons.append(f"{unconverged_count} 个站点未收敛")

    report = {
        "case_id": case_id,
        "generated_at": datetime.now().isoformat(),
        "method": "EKF",
        "outcome_status": outcome_status,
        "quality_gate_passed": quality_gate_passed,
        "quality_reason": "；".join(quality_reasons) or None,
        "params": {
            "process_noise": process_noise,
            "meas_noise": meas_noise,
            "dt_seconds": dt_seconds,
        },
        "stations": station_results,
        "summary": {
            "total_stations": len(station_results),
            "completed": n_completed,
            "converged": n_converged,
            "primary_completed": primary_completed,
            "primary_converged": primary_converged,
            "unconverged": unconverged_count,
            "synthetic_fallback": synthetic_count,
            "no_data": no_data_count,
            "avg_rmse_m": round(avg_rmse, 4),
            "avg_nse": round(avg_nse, 4),
            "primary_avg_rmse_m": round(primary_avg_rmse, 4) if primary_completed else None,
            "primary_avg_nse": round(primary_avg_nse, 4) if primary_completed else None,
            "d4_score": d4_score,
        },
    }

    _write_json(contracts_dir / "state_estimation.latest.json", report)
    
    # ── 生成对象标准报告 ──
    try:
        report_dir = contracts_dir / "object_reports"
        generator = ObjectReportGenerator(case_id, report_dir)
        
        for sid, rinfo in station_results.items():
            if not isinstance(rinfo, dict) or rinfo.get("status") != "completed":
                continue
                
            metrics = {
                "RMSE_m": rinfo.get("rmse_m"),
                "NSE": rinfo.get("nse"),
                "Converged": rinfo.get("converged"),
                "Max_Innovation_m": rinfo.get("max_innovation_m"),
                "Mean_Kalman_Gain": rinfo.get("mean_kalman_gain"),
            }
            details = {
                "method": "扩展卡尔曼滤波 (Robust EKF)",
                "source_data": rinfo.get("source"),
                "process_noise": process_noise,
                "meas_noise": meas_noise,
            }
            # The node type is assumed to be Reservoir for D4 unless otherwise specified
            generator.generate_report(
                object_type="Reservoir",
                object_id=sid,
                display_name=rinfo.get("name", sid),
                metrics=metrics,
                details=details,
                rules={"rmse_threshold": 0.2}
            )
        generator.save_index()
        print(f"  [报告] 生成了 {len(generator.generated_reports)} 份标准对象报告")
    except Exception as e:
        print(f"  [警告] 生成标准对象报告失败: {e}")

    print(f"\n  [汇总] 完成: {n_completed}/{len(station_results)}, "
          f"收敛: {n_converged}, avg_RMSE={avg_rmse:.4f}m, avg_NSE={avg_nse:.4f}")
    print(f"  [D4 评分] {d4_score:.1f}/5.0")

    return report


def _compute_d4_score(
    n_completed: int,
    n_converged: int,
    avg_rmse: float,
    avg_nse: float,
) -> float:
    """计算 D4 评分 (0-5)。"""
    if n_completed == 0:
        return 0.0

    coverage = n_converged / max(n_completed, 1)
    rmse_score = max(0, min(1, 1 - avg_rmse / 2.0))
    nse_score = max(0, min(1, avg_nse))

    raw = coverage * 2.0 + rmse_score * 1.5 + nse_score * 1.5
    return round(min(5.0, raw), 1)


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="D4 状态估计 (EKF)")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", help="YAML 配置路径")
    parser.add_argument("--process-noise", type=float, default=0.01)
    parser.add_argument("--meas-noise", type=float, default=0.5)
    parser.add_argument("--dt", type=float, default=3600.0, help="时间步长 (秒)")
    
    # Mock Sensor 参数
    parser.add_argument("--use-mock-sensor", action="store_true", help="使用 Mock Sensor 生成伪监测数据")
    parser.add_argument("--mock-packet-loss", type=float, default=0.05, help="Mock Sensor 丢包率 (0.0-1.0)")
    parser.add_argument("--mock-noise-std", type=float, default=0.01, help="Mock Sensor 高斯噪声标准差")
    parser.add_argument("--mock-drift-std", type=float, default=0.001, help="Mock Sensor 零均值漂移标准差")

    args = parser.parse_args()

    run_state_estimation(
        args.case_id,
        config_path=args.config,
        process_noise=args.process_noise,
        meas_noise=args.meas_noise,
        dt_seconds=args.dt,
        use_mock_sensor=args.use_mock_sensor,
        mock_packet_loss=args.mock_packet_loss,
        mock_noise_std=args.mock_noise_std,
        mock_drift_std=args.mock_drift_std,
    )


if __name__ == "__main__":
    main()
