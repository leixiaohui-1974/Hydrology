"""梯级水电站水动力建模模块 — 确定性，通用化。

基于 pipedream SuperLink 求解器，构建包含水轮机、泄洪闸、溢流堰的
梯级水电站 1D 水动力模型。

产品能力：
  1. build_cascade_model  — 从知识挖掘参数自动构建 SuperLink 模型
  2. run_steady_state     — 稳态收敛（给定恒定入流+水轮机出力+闸门开度）
  3. run_unsteady         — 非稳态模拟（历史/设计入流过程）
  4. calibrate            — 用历史数据率定 Manning's n
  5. validate             — 用独立历史时段验证模型

控制输入：
  - Q_in: 上游入流过程 (m³/s)
  - u_o:  闸门开度 (0~1, 0=全关 1=全开)
  - u_p:  水轮机出力/流量 (m³/s 或归一化)
  - H_bc: 下游水位边界 (m)

所有逻辑确定性，无随机性。
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


# ── 模型构建 ────────────────────────────────────────────────────────────────

@dataclass
class CascadeModelConfig:
    """梯级模型配置，从知识挖掘参数自动生成。"""
    case_id: str
    node_names: list[str]                   # 节点名（按拓扑序）
    node_elevations: dict[str, float]       # 节点底高程 zb
    node_areas: dict[str, float]            # 节点最小面积 Amin
    channels: list[dict[str, Any]]          # 河道参数
    orifices: list[dict[str, Any]]          # 闸门参数
    pumps: list[dict[str, Any]]             # 水轮机参数（用 pump 模拟）
    weirs: list[dict[str, Any]]            # 溢流堰参数
    boundaries: dict[str, float]            # 边界条件初始值
    initial_levels: dict[str, float]        # 初始水位
    reservoir_props: dict[str, dict]        # 水库特征参数
    internal_links: int = 4
    manning_n: float = 0.015
    default_width: float = 100.0
    default_depth: float = 15.0


def build_config_from_params(
    hydraulic_params: dict[str, Any],
    case_id: str = "",
    manning_n: float = 0.015,
    default_width: float = 100.0,
    default_depth: float = 15.0,
) -> CascadeModelConfig:
    """从知识挖掘的 hydraulic_params.json 自动构建模型配置。确定性。"""
    stations = hydraulic_params.get("stations", {})
    channels = hydraulic_params.get("channels", [])
    turbines = hydraulic_params.get("turbines", {})
    gates = hydraulic_params.get("gates", {})
    boundaries = hydraulic_params.get("boundaries", {})
    initial_z = hydraulic_params.get("initial_conditions", {})
    reservoir_props = hydraulic_params.get("reservoir_properties", {})

    # 确定节点拓扑序（按河道连接关系）
    node_names = []
    for ch in channels:
        for n in [ch["node1"], ch["node2"]]:
            if n not in node_names:
                node_names.append(n)

    # 节点高程和面积
    node_elevations = {n: stations.get(n, {}).get("zb", 500.0) for n in node_names}
    node_areas = {n: stations.get(n, {}).get("Amin", 10000.0) for n in node_names}

    # 构建闸门（orifice）：每个电站的泄洪闸
    orifice_list = []
    oid = 0
    for station_name, gate_list in sorted(gates.items()):
        # 找到该站的前/后节点
        station_front = station_name + "前"
        station_back = station_name + "后"
        sj_0_idx = node_names.index(station_front) if station_front in node_names else None
        sj_1_idx = node_names.index(station_back) if station_back in node_names else None
        if sj_0_idx is None or sj_1_idx is None:
            continue
        for gate in gate_list:
            orifice_list.append({
                "id": oid,
                "name": gate["name"],
                "sj_0": sj_0_idx,
                "sj_1": sj_1_idx,
                "orientation": "bottom",
                "C": 0.65,           # 标准闸门流量系数
                "A": 50.0,           # 闸门面积 m² (需率定)
                "y_max": 10.0,       # 闸门最大开度 m
                "z_o": 0.0,          # 闸底高程偏移
                "oneway": True,
            })
            oid += 1

    # 构建水轮机（pump）：每个电站的水轮机组
    pump_list = []
    pid = 0
    for station_name, unit_list in sorted(turbines.items()):
        station_front = station_name + "前"
        station_back = station_name + "后"
        # 水轮机取水在坝前，排水在坝后
        sj_0_idx = node_names.index(station_front) if station_front in node_names else None
        sj_1_idx = node_names.index(station_back) if station_back in node_names else None
        if sj_0_idx is None or sj_1_idx is None:
            continue
        for unit in unit_list:
            # pump 椭圆参数：a_q 控制最大流量, a_h 控制最大水头
            rp = _find_reservoir_prop(reservoir_props, station_name)
            max_head = (rp.get("normal_pool", 650) - node_elevations.get(station_back, 500)) if rp else 100.0
            pump_list.append({
                "id": pid,
                "name": unit["name"],
                "sj_0": sj_0_idx,
                "sj_1": sj_1_idx,
                "z_p": 0.0,
                "a_q": 200.0,         # 单机最大流量 m³/s (需率定)
                "a_h": max_head,       # 最大水头 m
                "dH_min": 10.0,        # 最小工作水头
                "dH_max": max_head,    # 最大工作水头
            })
            pid += 1

    return CascadeModelConfig(
        case_id=case_id or hydraulic_params.get("case_id", ""),
        node_names=node_names,
        node_elevations=node_elevations,
        node_areas=node_areas,
        channels=channels,
        orifices=orifice_list,
        pumps=pump_list,
        weirs=[],  # 溢流堰暂由闸门替代
        boundaries=boundaries,
        initial_levels=initial_z,
        reservoir_props=reservoir_props,
        manning_n=manning_n,
        default_width=default_width,
        default_depth=default_depth,
    )


def _first_boundary(boundaries: dict[str, float], default: float = 334.0) -> float:
    """取边界条件字典中第一个值（上游入流）。通用，不绑站名。"""
    if not boundaries:
        return default
    return float(next(iter(boundaries.values())))


def _last_boundary_key(boundaries: dict[str, float]) -> str | None:
    """取边界条件字典中最后一个 key（下游水位）。通用，不绑站名。"""
    if not boundaries:
        return None
    return list(boundaries.keys())[-1]


def _find_reservoir_prop(props: dict, station_name: str) -> dict | None:
    """按站名模糊匹配水库特征参数。"""
    for sid, rp in props.items():
        rp_name = rp.get("name", "")
        clean = rp_name.replace("一级", "").replace("二级", "").strip()
        if station_name in clean or clean in station_name:
            return rp
    return None


def build_superlink_model(cfg: CascadeModelConfig) -> Any:
    """从配置构建 SuperLink 模型实例。确定性。"""
    import sys
    # 确保 pipedream 在路径中
    workspace = Path(__file__).resolve().parents[2]
    pipedream_path = str(next(
        (workspace / d for d in ["pipedream-hydrology-integration-lab", "pipedream"] if (workspace / d).exists()),
        workspace / "pipedream-hydrology-integration-lab",
    ))
    if pipedream_path not in sys.path:
        sys.path.append(pipedream_path)
    from pipedream_solver.superlink import SuperLink

    n_j = len(cfg.node_names)
    n_l = len(cfg.channels)

    # Superjunctions
    sj = pd.DataFrame({
        "id": list(range(n_j)),
        "name": cfg.node_names,
        "z_inv": [cfg.node_elevations.get(n, 500.0) for n in cfg.node_names],
        "h_0": [cfg.initial_levels.get(
            _channel_key_for_node(cfg.channels, n), 2.0
        ) - cfg.node_elevations.get(n, 500.0) for n in cfg.node_names],
        "bc": [False] * (n_j - 1) + [True],
        "A_sj": [cfg.node_areas.get(n, 10000.0) for n in cfg.node_names],
        "storage": ["functional"] * n_j,
        "a": [0.0] * n_j, "b": [0.0] * n_j, "c": [1.0] * n_j,
    })
    # 修正 h_0 保证非负
    sj["h_0"] = sj["h_0"].clip(lower=0.5)

    # Superlinks
    sl = pd.DataFrame({
        "id": list(range(n_l)),
        "name": [ch["name"] for ch in cfg.channels],
        "sj_0": [cfg.node_names.index(ch["node1"]) for ch in cfg.channels],
        "sj_1": [cfg.node_names.index(ch["node2"]) for ch in cfg.channels],
        "in_offset": [0.0] * n_l,
        "out_offset": [0.0] * n_l,
        "dx": [10000.0] * n_l,
        "n": [ch.get("manning_n") or cfg.manning_n for ch in cfg.channels],
        "shape": ["rect_open"] * n_l,
        "g1": [cfg.default_width] * n_l,
        "g2": [cfg.default_depth] * n_l,
        "g3": [0.0] * n_l, "g4": [0.0] * n_l,
        "Q_0": [_first_boundary(cfg.boundaries)] * n_l,
        "h_0": [2.0] * n_l,
        "A_s": [cfg.default_width * 2.0] * n_l,
        "ctrl": [False] * n_l,
        "A_c": [0.0] * n_l, "C": [0.0] * n_l,
        "C_uk": [0.0] * n_l, "C_dk": [0.0] * n_l,
    })

    # Orifices (闸门)
    orifices_df = None
    if cfg.orifices:
        orifices_df = pd.DataFrame(cfg.orifices)

    # Pumps (水轮机)
    pumps_df = None
    if cfg.pumps:
        pumps_df = pd.DataFrame(cfg.pumps)

    model = SuperLink(
        sl, sj,
        orifices=orifices_df,
        pumps=pumps_df,
        internal_links=cfg.internal_links,
    )
    return model


def _channel_key_for_node(channels: list[dict], node_name: str) -> str:
    """从河道列表中找包含该节点的河道 key（用于初始水位查找）。"""
    for ch in channels:
        if ch["node1"] == node_name or ch["node2"] == node_name:
            return ch["name"]
    return ""


# ── 稳态求解 ────────────────────────────────────────────────────────────────

@dataclass
class SteadyStateResult:
    converged: bool
    iterations: int
    final_dH: float
    levels: dict[str, float]
    config_summary: dict[str, Any] = field(default_factory=dict)


def run_steady_state(
    cfg: CascadeModelConfig,
    *,
    Q_upstream: float | None = None,
    H_downstream: float | None = None,
    gate_openings: dict[str, float] | None = None,
    turbine_flows: dict[str, float] | None = None,
    dt: float = 10.0,
    max_iter: int = 5000,
    tolerance: float = 0.01,
) -> SteadyStateResult:
    """稳态收敛：给定恒定入流 + 水轮机出力 + 闸门开度。确定性。"""
    model = build_superlink_model(cfg)

    Q_in = np.zeros(model.M)
    Q_in[0] = Q_upstream or _first_boundary(cfg.boundaries)

    # 下游水位边界
    H_bc = np.full(model.M, np.nan)
    if H_downstream is not None:
        H_bc[-1] = H_downstream
    elif _last_boundary_key(cfg.boundaries):
        H_bc[-1] = cfg.boundaries[_last_boundary_key(cfg.boundaries)]

    # 闸门开度控制 (0~1)
    u_o = None
    if hasattr(model, 'n_o') and model.n_o > 0:
        u_o = np.zeros(model.n_o)  # 初始全关
        if gate_openings and cfg.orifices:
            for i, orif in enumerate(cfg.orifices):
                opening = gate_openings.get(orif["name"], 0.0)
                if i < len(u_o):
                    u_o[i] = max(0.0, min(1.0, opening))

    # 水轮机控制
    u_p = None
    if hasattr(model, 'n_p') and model.n_p > 0:
        u_p = np.ones(model.n_p)  # 默认全开
        if turbine_flows and cfg.pumps:
            for i, pump in enumerate(cfg.pumps):
                flow = turbine_flows.get(pump["name"], 1.0)
                if i < len(u_p):
                    u_p[i] = max(0.0, min(1.0, flow))

    prev_H = model.H_j.copy()
    converged = False
    final_dH = float("inf")

    for iteration in range(max_iter):
        try:
            model.step(dt=dt, Q_in=Q_in, H_bc=H_bc, u_o=u_o, u_p=u_p)
        except Exception:
            break

        final_dH = float(np.max(np.abs(model.H_j - prev_H)))
        prev_H = model.H_j.copy()
        if final_dH < tolerance:
            converged = True
            break

    levels = {cfg.node_names[j]: float(model.H_j[j]) for j in range(model.M)}
    return SteadyStateResult(
        converged=converged,
        iterations=iteration + 1 if converged else max_iter,
        final_dH=final_dH,
        levels=levels,
        config_summary={
            "Q_upstream": float(Q_in[0]),
            "n_orifices": len(cfg.orifices),
            "n_pumps": len(cfg.pumps),
            "manning_n": cfg.manning_n,
        },
    )


# ── 非稳态模拟 ──────────────────────────────────────────────────────────────

@dataclass
class UnsteadyResult:
    n_steps: int
    dt: float
    station_levels: dict[str, dict[str, float]]  # name -> {max, min, final}
    timeseries: dict[str, list[float]]           # name -> [H at each step]


def run_unsteady(
    cfg: CascadeModelConfig,
    *,
    inflow_series: np.ndarray,
    gate_series: dict[str, np.ndarray] | None = None,
    turbine_series: dict[str, np.ndarray] | None = None,
    H_downstream: float | None = None,
    dt: float = 10.0,
    warmup_steps: int = 200,
) -> UnsteadyResult:
    """非稳态模拟：时变入流 + 闸门/水轮机控制过程。确定性。"""
    model = build_superlink_model(cfg)
    n_steps = len(inflow_series)

    # 稳态暖机
    Q_warmup = np.zeros(model.M)
    Q_warmup[0] = float(inflow_series[0])
    H_bc = np.full(model.M, np.nan)
    if H_downstream is not None:
        H_bc[-1] = H_downstream
    elif _last_boundary_key(cfg.boundaries):
        H_bc[-1] = cfg.boundaries[_last_boundary_key(cfg.boundaries)]

    for _ in range(warmup_steps):
        try:
            model.step(dt=dt, Q_in=Q_warmup, H_bc=H_bc)
        except Exception:
            break

    # 非稳态循环
    h_records = {name: [] for name in cfg.node_names}

    for t in range(n_steps):
        Q_in = np.zeros(model.M)
        Q_in[0] = float(inflow_series[t])

        u_o = None
        if hasattr(model, 'n_o') and model.n_o > 0:
            u_o = np.zeros(model.n_o)
            if gate_series:
                for i, orif in enumerate(cfg.orifices):
                    if orif["name"] in gate_series and i < len(u_o):
                        idx = min(t, len(gate_series[orif["name"]]) - 1)
                        u_o[i] = float(gate_series[orif["name"]][idx])

        u_p = None
        if hasattr(model, 'n_p') and model.n_p > 0:
            u_p = np.ones(model.n_p)
            if turbine_series:
                for i, pump in enumerate(cfg.pumps):
                    if pump["name"] in turbine_series and i < len(u_p):
                        idx = min(t, len(turbine_series[pump["name"]]) - 1)
                        u_p[i] = float(turbine_series[pump["name"]][idx])

        try:
            model.step(dt=dt, Q_in=Q_in, H_bc=H_bc, u_o=u_o, u_p=u_p)
            for j, name in enumerate(cfg.node_names):
                h_records[name].append(float(model.H_j[j]))
        except Exception:
            break

    actual_steps = len(h_records[cfg.node_names[0]])
    station_levels = {}
    for name, series in h_records.items():
        if series:
            station_levels[name] = {
                "max": float(np.max(series)),
                "min": float(np.min(series)),
                "final": float(series[-1]),
            }

    return UnsteadyResult(
        n_steps=actual_steps, dt=dt,
        station_levels=station_levels,
        timeseries=h_records,
    )


# ── 率定 ────────────────────────────────────────────────────────────────────

def load_historical_data(
    db_path: str | Path,
    station_id: str,
    variables: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, pd.DataFrame]:
    """从 SQLite 加载历史数据。确定性。"""
    conn = sqlite3.connect(str(db_path))
    result = {}
    for var in variables:
        query = "SELECT time, value FROM timeseries WHERE station_id=? AND variable=?"
        params: list[Any] = [station_id, var]
        if start_date:
            query += " AND time >= ?"
            params.append(start_date)
        if end_date:
            query += " AND time <= ?"
            params.append(end_date)
        query += " ORDER BY time"
        df = pd.read_sql_query(query, conn, params=params, parse_dates=["time"])
        if not df.empty:
            result[var] = df
    conn.close()
    return result


def calibrate_manning(
    cfg: CascadeModelConfig,
    observed_levels: dict[str, np.ndarray],
    inflow_series: np.ndarray,
    *,
    n_range: tuple[float, float] = (0.01, 0.06),
    n_steps: int = 10,
    dt: float = 10.0,
) -> dict[str, Any]:
    """率定 Manning's n：网格搜索最小化水位 RMSE。确定性（固定网格，无随机优化）。"""
    n_values = np.linspace(n_range[0], n_range[1], n_steps)
    best_n = cfg.manning_n
    best_rmse = float("inf")
    results = []

    for n_val in n_values:
        cfg_trial = CascadeModelConfig(**{**cfg.__dict__, "manning_n": float(n_val)})
        # 修改 channels manning_n
        for ch in cfg_trial.channels:
            ch["manning_n"] = float(n_val)

        try:
            sim = run_unsteady(cfg_trial, inflow_series=inflow_series, dt=dt, warmup_steps=100)
        except Exception:
            continue

        # 计算 RMSE（对所有有观测的站点）
        total_rmse = 0.0
        count = 0
        for station, obs in observed_levels.items():
            if station in sim.timeseries:
                sim_arr = np.array(sim.timeseries[station])
                min_len = min(len(obs), len(sim_arr))
                if min_len > 0:
                    rmse = float(np.sqrt(np.mean((obs[:min_len] - sim_arr[:min_len])**2)))
                    total_rmse += rmse
                    count += 1

        avg_rmse = total_rmse / count if count > 0 else float("inf")
        results.append({"manning_n": float(n_val), "rmse": avg_rmse})
        if avg_rmse < best_rmse:
            best_rmse = avg_rmse
            best_n = float(n_val)

    return {
        "best_manning_n": best_n,
        "best_rmse": best_rmse,
        "search_results": results,
        "n_range": list(n_range),
        "n_steps": n_steps,
    }


# ── 验证 ────────────────────────────────────────────────────────────────────

def validate_model(
    cfg: CascadeModelConfig,
    observed_levels: dict[str, np.ndarray],
    inflow_series: np.ndarray,
    *,
    dt: float = 10.0,
) -> dict[str, Any]:
    """用独立时段验证模型。确定性。"""
    sim = run_unsteady(cfg, inflow_series=inflow_series, dt=dt)

    metrics = {}
    for station, obs in observed_levels.items():
        if station not in sim.timeseries:
            continue
        sim_arr = np.array(sim.timeseries[station])
        min_len = min(len(obs), len(sim_arr))
        if min_len == 0:
            continue
        obs_cut = obs[:min_len]
        sim_cut = sim_arr[:min_len]
        rmse = float(np.sqrt(np.mean((obs_cut - sim_cut)**2)))
        mae = float(np.mean(np.abs(obs_cut - sim_cut)))
        # Nash-Sutcliffe 效率系数
        ss_res = np.sum((obs_cut - sim_cut)**2)
        ss_tot = np.sum((obs_cut - np.mean(obs_cut))**2)
        nse = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("-inf")
        metrics[station] = {
            "rmse_m": rmse, "mae_m": mae, "nse": float(nse),
            "obs_count": min_len,
            "obs_range": [float(np.min(obs_cut)), float(np.max(obs_cut))],
            "sim_range": [float(np.min(sim_cut)), float(np.max(sim_cut))],
        }

    return {
        "case_id": cfg.case_id,
        "manning_n": cfg.manning_n,
        "n_stations_validated": len(metrics),
        "metrics": metrics,
    }
