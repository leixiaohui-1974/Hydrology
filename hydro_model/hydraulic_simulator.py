"""梯级水力学逐时段模拟器 — 产品化核心模块。

基于已验证的水库水量平衡模型（6 站 avg NSE=0.94），升级为梯级联合模拟器：
  1. 梯级串联: 上游 Q_out → Muskingum 河道演算 → 下游 Q_in
  2. 控制分解: gate_openings + turbine_flows → Q_out
  3. 逐步接口: 每个 dt 接受控制输入，返回水位 → SIL / ODD

两种运行模式：
  - replay:   用历史观测 Q_in / Q_out 驱动（验证精度）
  - scenario: 用控制输入驱动（多场景评价）

Usage::

    sim = CascadeSimulator.from_case("daduhe")
    sim.initialize(H_init={"s1": 840.0, ...})

    # 逐步 (SIL / ODD)
    for t in range(n):
        levels = sim.step(
            upstream_Q=Q_upstream[t],
            turbine_flows={"s1": 300.0, ...},
            gate_openings={"s1": 0.5, ...},
        )

    # 批量 (历史验证)
    result = sim.run_replay(Q_in_series, Q_out_series, H_obs)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

WORKSPACE = Path(__file__).resolve().parents[2]


# ── 站点元数据 ────────────────────────────────────────────────────────────

STATION_META: dict[str, dict[str, Any]] = {
    "s1": {"name": "瀑布沟", "normal_pool": 850.0, "dead_pool": 790.0,
           "n_turbines": 6, "max_turbine_flow": 347.75},
    "s2": {"name": "深溪沟", "normal_pool": 660.0, "dead_pool": 658.0,
           "n_turbines": 4, "max_turbine_flow": 316.0},
    "s3": {"name": "枕头坝", "normal_pool": 625.0, "dead_pool": 622.5,
           "n_turbines": 4, "max_turbine_flow": 450.0},
    "s4": {"name": "沙坪",   "normal_pool": 553.0, "dead_pool": 551.0,
           "n_turbines": 6, "max_turbine_flow": 400.0},
    "s5": {"name": "龚嘴",   "normal_pool": 526.0, "dead_pool": 512.0,
           "n_turbines": 5, "max_turbine_flow": 600.0},
    "s6": {"name": "铜街子", "normal_pool": 474.0, "dead_pool": 472.0,
           "n_turbines": 5, "max_turbine_flow": 600.0},
}

REACH_ORDER = ["s1", "s2", "s3", "s4", "s5", "s6"]

REACH_LINKS: list[tuple[str, str]] = [
    ("s1", "s2"), ("s2", "s3"), ("s3", "s4"), ("s4", "s5"), ("s5", "s6"),
]


# ── 河道演算 ──────────────────────────────────────────────────────────────

@dataclass
class MuskingumReach:
    """Muskingum 河道演算参数。"""
    from_station: str
    to_station: str
    K: float = 1.0      # 传播时间 (h)
    X: float = 0.2      # 权重系数 (0~0.5)

    def route(
        self, Q_in: float, Q_in_prev: float, Q_out_prev: float, dt_h: float,
    ) -> float:
        """单步 Muskingum 演算。"""
        denom = 2 * self.K * (1 - self.X) + dt_h
        if abs(denom) < 1e-10:
            return Q_in
        C0 = (dt_h - 2 * self.K * self.X) / denom
        C1 = (dt_h + 2 * self.K * self.X) / denom
        C2 = (2 * self.K * (1 - self.X) - dt_h) / denom
        return max(0.0, C0 * Q_in + C1 * Q_in_prev + C2 * Q_out_prev)


# ── 单站状态 ──────────────────────────────────────────────────────────────

@dataclass
class StationState:
    """单站运行时状态。"""
    station_id: str
    name: str

    # 水位
    H: float = 0.0
    normal_pool: float = 850.0
    dead_pool: float = 790.0

    # 流量
    Q_in: float = 0.0
    Q_out: float = 0.0
    Q_turbine: float = 0.0
    Q_spill: float = 0.0

    # 率定参数 (from ReservoirBalanceModel)
    A_eff: float = 1e6
    alpha: float = 1.0
    beta: float = 0.0
    H_ref: float = 0.0
    lag: int = 0
    ah_curve: list = field(default_factory=list)

    # 闸门参数
    n_gates: int = 5
    gate_width: float = 10.0
    gate_Cd: float = 0.65
    gate_sill_elev: float = 0.0    # 闸底高程

    # 机组参数
    n_turbines: int = 6
    max_turbine_flow: float = 350.0

    # 入流缓冲 (for lag)
    _Q_in_buffer: list = field(default_factory=list)

    def area_at(self, H: float) -> float:
        """A(H) 插值（真实断面优先，线性近似兜底）。"""
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
        return max(self.A_eff, 1e4)

    def compute_spill(self, gate_opening: float) -> float:
        """闸门泄流量计算 (堰流公式)。

        gate_opening: 0~1 (全关~全开)
        """
        if gate_opening <= 0.0:
            return 0.0
        H_over = self.H - self.gate_sill_elev
        if H_over <= 0.0:
            return 0.0
        W = self.gate_width * self.n_gates * gate_opening
        return self.gate_Cd * W * np.sqrt(2 * 9.81 * H_over)

    def compute_turbine(self, turbine_flow: float) -> float:
        """机组流量限幅。"""
        return max(0.0, min(turbine_flow, self.max_turbine_flow * self.n_turbines))

    def step_water_balance(
        self, Q_in: float, Q_out: float, dt: float, max_dH: float = 3.0,
    ) -> float:
        """单步水量平衡计算，返回新水位。"""
        self._Q_in_buffer.append(Q_in)
        qi_lagged = self._Q_in_buffer[-1 - min(self.lag, len(self._Q_in_buffer) - 1)]

        A = self.area_at(self.H)
        dH = self.alpha * (qi_lagged - Q_out) * dt / A
        dH -= self.beta * (self.H - self.H_ref) * dt / 86400.0
        dH = max(-max_dH, min(max_dH, dH))

        self.H += dH
        self.H = max(self.dead_pool - 5.0, min(self.normal_pool + 5.0, self.H))

        self.Q_in = Q_in
        self.Q_out = Q_out
        return self.H


# ── 梯级联合模拟器 ────────────────────────────────────────────────────────

@dataclass
class CascadeSimulatorConfig:
    dt: float = 3600.0            # 时间步长 (s)
    max_dH_per_step: float = 3.0
    reach_K: dict[str, float] = field(default_factory=dict)   # 各河段 K (h)
    reach_X: dict[str, float] = field(default_factory=dict)   # 各河段 X


DEFAULT_REACH_K = {
    "s1-s2": 2.0,   # 瀑布沟→深溪沟 约60km
    "s2-s3": 1.0,   # 深溪沟→枕头坝 约30km
    "s3-s4": 1.5,   # 枕头坝→沙坪 约40km
    "s4-s5": 3.0,   # 沙坪→龚嘴 约80km
    "s5-s6": 1.0,   # 龚嘴→铜街子 约20km
}


class CascadeSimulator:
    """梯级水力学逐时段联合模拟器。

    核心能力：
      - 梯级串联：上游 Q_out → Muskingum → 下游 Q_in
      - 控制分解：gate_openings + turbine_flows → Q_out
      - 逐步驱动：SIL 接口
      - 历史回溯：replay 精度验证
    """

    def __init__(self, config: CascadeSimulatorConfig | None = None):
        self.config = config or CascadeSimulatorConfig()
        self.stations: dict[str, StationState] = {}
        self.reaches: dict[str, MuskingumReach] = {}
        self.t: int = 0
        self.history: list[dict] = []
        self._initialized = False

    @classmethod
    def from_case(cls, case_id: str) -> "CascadeSimulator":
        """从案例知识层自动构建。"""
        sim = cls()
        sim._load_calibrated_params(case_id)
        sim._load_ah_curves(case_id)
        sim._load_station_topology(case_id)
        sim._build_reaches(case_id)
        return sim

    def _load_calibrated_params(self, case_id: str) -> None:
        """加载 D2 率定后参数。"""
        import yaml
        d2_path = (WORKSPACE / "Hydrology" / "knowledge" / case_id
                   / "precision" / "d2_hydraulics.yaml")
        d2 = {}
        if d2_path.exists():
            with open(d2_path, encoding="utf-8") as f:
                d2 = yaml.safe_load(f) or {}

        for sid in REACH_ORDER:
            meta = STATION_META.get(sid, {})
            params = d2.get("stations", {}).get(sid, {}).get("params", {})

            self.stations[sid] = StationState(
                station_id=sid,
                name=meta.get("name", sid),
                normal_pool=meta.get("normal_pool", 500.0),
                dead_pool=meta.get("dead_pool", 490.0),
                A_eff=params.get("A_eff", 1e6),
                alpha=params.get("alpha", 1.0),
                beta=params.get("beta", 0.0),
                H_ref=meta.get("normal_pool", 500.0) - 20.0,
                lag=params.get("lag", 0),
                n_turbines=meta.get("n_turbines", 4),
                max_turbine_flow=meta.get("max_turbine_flow", 350.0),
            )

    def _load_ah_curves(self, case_id: str) -> None:
        """加载断面 A(H) 曲线。"""
        ah_path = (WORKSPACE / "Hydrology" / "knowledge" / case_id
                   / "curves" / "ah_curves.json")
        if not ah_path.exists():
            return
        with open(ah_path, encoding="utf-8") as f:
            ah_data = json.load(f)
        for sid, st in self.stations.items():
            if sid in ah_data and "curve" in ah_data[sid]:
                st.ah_curve = [
                    (pt["H"], pt["A_m2"])
                    for pt in ah_data[sid]["curve"]
                ]

    def _load_station_topology(self, case_id: str) -> None:
        """从知识层加载闸门/机组参数。"""
        import yaml
        gates_path = (WORKSPACE / "Hydrology" / "knowledge" / case_id
                      / "topology" / "gates.yaml")
        reservoirs_path = (WORKSPACE / "Hydrology" / "knowledge" / case_id
                           / "topology" / "reservoirs.yaml")

        if gates_path.exists():
            with open(gates_path, encoding="utf-8") as f:
                gates = yaml.safe_load(f) or {}
            name_to_sid = {m["name"]: sid for sid, m in STATION_META.items()}
            for gate_name, ginfo in gates.items():
                matched_sid = None
                for sid, meta in STATION_META.items():
                    if meta["name"][:2] in gate_name:
                        matched_sid = sid
                        break
                if matched_sid and matched_sid in self.stations:
                    self.stations[matched_sid].n_gates = ginfo.get("count", 5)

        if reservoirs_path.exists():
            with open(reservoirs_path, encoding="utf-8") as f:
                reservoirs = yaml.safe_load(f) or {}
            for sid, rinfo in reservoirs.items():
                if sid in self.stations:
                    if rinfo.get("normal_pool_m"):
                        self.stations[sid].normal_pool = rinfo["normal_pool_m"]
                    if rinfo.get("dead_pool_m"):
                        self.stations[sid].dead_pool = rinfo["dead_pool_m"]
                        self.stations[sid].gate_sill_elev = rinfo["dead_pool_m"]

    def _build_reaches(self, case_id: str) -> None:
        """构建河段 Muskingum 演算器。"""
        for (s_up, s_dn) in REACH_LINKS:
            key = f"{s_up}-{s_dn}"
            K = self.config.reach_K.get(key, DEFAULT_REACH_K.get(key, 1.5))
            X = self.config.reach_X.get(key, 0.2)
            self.reaches[key] = MuskingumReach(
                from_station=s_up, to_station=s_dn, K=K, X=X,
            )

    # ── 初始化 ─────────────────────────────────────────────────────────

    def initialize(self, H_init: dict[str, float] | None = None) -> None:
        """用初始水位初始化。"""
        for sid, st in self.stations.items():
            st.H = (H_init or {}).get(sid, st.normal_pool - 10.0)
            st._Q_in_buffer = []
        self.t = 0
        self.history = []
        self._reach_prev: dict[str, dict] = {}
        for key in self.reaches:
            self._reach_prev[key] = {"Q_in_prev": 0.0, "Q_out_prev": 0.0}
        self._initialized = True

    # ── 逐步驱动 (核心) ───────────────────────────────────────────────

    def step(
        self,
        upstream_Q: float = 0.0,
        turbine_flows: dict[str, float] | None = None,
        gate_openings: dict[str, float] | None = None,
        lateral_inflows: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """场景模式：用控制输入前进一个时间步。

        Parameters
        ----------
        upstream_Q : 梯级最上游入流 (m³/s)
        turbine_flows : 各站机组总流量 {station_id: m³/s}
        gate_openings : 各站闸门综合开度 {station_id: 0~1}
        lateral_inflows : 区间入流 {station_id: m³/s}

        Returns
        -------
        dict : 各站水位 {station_id: H_m}
        """
        if not self._initialized:
            self.initialize()

        dt = self.config.dt
        turbine_flows = turbine_flows or {}
        gate_openings = gate_openings or {}
        lateral_inflows = lateral_inflows or {}
        levels = {}
        dt_h = dt / 3600.0

        for i, sid in enumerate(REACH_ORDER):
            if sid not in self.stations:
                continue
            st = self.stations[sid]

            # 入流：第一站用 upstream_Q，后续站由河道演算
            if i == 0:
                Q_in = upstream_Q + lateral_inflows.get(sid, 0.0)
            else:
                upstream_sid = REACH_ORDER[i - 1]
                reach_key = f"{upstream_sid}-{sid}"
                if reach_key in self.reaches:
                    reach = self.reaches[reach_key]
                    prev = self._reach_prev[reach_key]
                    Q_from_upstream = self.stations[upstream_sid].Q_out
                    Q_routed = reach.route(
                        Q_from_upstream, prev["Q_in_prev"], prev["Q_out_prev"], dt_h,
                    )
                    prev["Q_in_prev"] = Q_from_upstream
                    prev["Q_out_prev"] = Q_routed
                    Q_in = Q_routed + lateral_inflows.get(sid, 0.0)
                else:
                    Q_in = self.stations[upstream_sid].Q_out + lateral_inflows.get(sid, 0.0)

            # 出流分解
            Q_turb = st.compute_turbine(turbine_flows.get(sid, 0.0))
            Q_spill = st.compute_spill(gate_openings.get(sid, 0.0))
            Q_out = Q_turb + Q_spill
            st.Q_turbine = Q_turb
            st.Q_spill = Q_spill

            st.step_water_balance(Q_in, Q_out, dt, self.config.max_dH_per_step)
            levels[sid] = st.H

        self.history.append({"t": self.t, **levels})
        self.t += 1
        return levels

    def step_replay(
        self,
        Q_in_dict: dict[str, float],
        Q_out_dict: dict[str, float],
    ) -> dict[str, float]:
        """回溯模式：用历史观测 Q_in/Q_out 驱动（验证精度）。

        每站独立用观测的 Q_in 和 Q_out，不做梯级串联。
        """
        if not self._initialized:
            self.initialize()

        dt = self.config.dt
        levels = {}

        for sid in REACH_ORDER:
            if sid not in self.stations:
                continue
            st = self.stations[sid]
            Q_in = Q_in_dict.get(sid, 0.0)
            Q_out = Q_out_dict.get(sid, 0.0)
            st.step_water_balance(Q_in, Q_out, dt, self.config.max_dH_per_step)
            levels[sid] = st.H

        self.history.append({"t": self.t, **levels})
        self.t += 1
        return levels

    def step_cascade(
        self,
        upstream_Q: float = 0.0,
        Q_out_dict: dict[str, float] | None = None,
        lateral_inflows: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """级联模式：Q_out 用观测值，但 Q_in 由上游传播。

        适用于验证河道演算精度（已知各站出流，检查传播后入流是否合理）。
        """
        if not self._initialized:
            self.initialize()

        dt = self.config.dt
        Q_out_dict = Q_out_dict or {}
        lateral_inflows = lateral_inflows or {}
        dt_h = dt / 3600.0
        levels = {}

        for i, sid in enumerate(REACH_ORDER):
            if sid not in self.stations:
                continue
            st = self.stations[sid]

            if i == 0:
                Q_in = upstream_Q + lateral_inflows.get(sid, 0.0)
            else:
                upstream_sid = REACH_ORDER[i - 1]
                reach_key = f"{upstream_sid}-{sid}"
                if reach_key in self.reaches:
                    reach = self.reaches[reach_key]
                    prev = self._reach_prev[reach_key]
                    Q_from_upstream = self.stations[upstream_sid].Q_out
                    Q_routed = reach.route(
                        Q_from_upstream, prev["Q_in_prev"], prev["Q_out_prev"], dt_h,
                    )
                    prev["Q_in_prev"] = Q_from_upstream
                    prev["Q_out_prev"] = Q_routed
                    Q_in = Q_routed + lateral_inflows.get(sid, 0.0)
                else:
                    Q_in = self.stations[upstream_sid].Q_out + lateral_inflows.get(sid, 0.0)

            Q_out = Q_out_dict.get(sid, 0.0)
            st.step_water_balance(Q_in, Q_out, dt, self.config.max_dH_per_step)
            levels[sid] = st.H

        self.history.append({"t": self.t, **levels})
        self.t += 1
        return levels

    # ── 批量运行 ───────────────────────────────────────────────────────

    def run_replay(
        self,
        Q_in_series: dict[str, np.ndarray],
        Q_out_series: dict[str, np.ndarray],
        H_obs: dict[str, np.ndarray] | None = None,
        H_init: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """批量回溯验证，返回各站 H_sim + 精度指标。"""
        any_key = next(iter(Q_in_series))
        n = len(Q_in_series[any_key])

        if H_init is None:
            H_init = {}
            for sid in self.stations:
                if H_obs and sid in H_obs and len(H_obs[sid]) > 0:
                    H_init[sid] = float(H_obs[sid][0])

        self.initialize(H_init)

        H_records: dict[str, list[float]] = {sid: [] for sid in self.stations}

        for t in range(n):
            qi = {sid: float(arr[t]) if t < len(arr) else 0.0
                  for sid, arr in Q_in_series.items()}
            qo = {sid: float(arr[t]) if t < len(arr) else 0.0
                  for sid, arr in Q_out_series.items()}

            levels = self.step_replay(qi, qo)
            for sid in self.stations:
                H_records[sid].append(levels.get(sid, np.nan))

        result: dict[str, Any] = {}
        for sid in self.stations:
            H_sim = np.array(H_records[sid])
            entry: dict[str, Any] = {"H_sim": H_sim, "n": len(H_sim)}
            if H_obs and sid in H_obs:
                from hydro_model.reservoir_balance import compute_metrics
                m = compute_metrics(H_obs[sid][:n], H_sim)
                entry["metrics"] = m
            result[sid] = entry

        return result

    def run_cascade(
        self,
        upstream_Q_series: np.ndarray,
        Q_out_series: dict[str, np.ndarray],
        lateral_inflow_series: dict[str, np.ndarray] | None = None,
        H_obs: dict[str, np.ndarray] | None = None,
        H_init: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """批量级联验证。"""
        n = len(upstream_Q_series)
        lateral_inflow_series = lateral_inflow_series or {}

        if H_init is None:
            H_init = {}
            for sid in self.stations:
                if H_obs and sid in H_obs and len(H_obs[sid]) > 0:
                    H_init[sid] = float(H_obs[sid][0])

        self.initialize(H_init)
        H_records: dict[str, list[float]] = {sid: [] for sid in self.stations}

        for t in range(n):
            qo = {sid: float(arr[t]) if t < len(arr) else 0.0
                  for sid, arr in Q_out_series.items()}
            lat = {sid: float(arr[t]) if t < len(arr) else 0.0
                   for sid, arr in lateral_inflow_series.items()}

            levels = self.step_cascade(
                float(upstream_Q_series[t]), qo, lat,
            )
            for sid in self.stations:
                H_records[sid].append(levels.get(sid, np.nan))

        result: dict[str, Any] = {}
        for sid in self.stations:
            H_sim = np.array(H_records[sid])
            entry: dict[str, Any] = {"H_sim": H_sim, "n": len(H_sim)}
            if H_obs and sid in H_obs:
                from hydro_model.reservoir_balance import compute_metrics
                m = compute_metrics(H_obs[sid][:n], H_sim)
                entry["metrics"] = m
            result[sid] = entry

        return result

    # ── 状态查询 ───────────────────────────────────────────────────────

    def get_levels(self) -> dict[str, float]:
        return {sid: st.H for sid, st in self.stations.items()}

    def get_state(self) -> dict[str, dict]:
        """完整状态快照 (for SIL)。"""
        return {
            sid: {
                "H": st.H, "Q_in": st.Q_in, "Q_out": st.Q_out,
                "Q_turbine": st.Q_turbine, "Q_spill": st.Q_spill,
                "A": st.area_at(st.H),
                "normal_pool": st.normal_pool, "dead_pool": st.dead_pool,
            }
            for sid, st in self.stations.items()
        }

    def get_history_df(self):
        """返回历史水位 DataFrame。"""
        import pandas as pd
        return pd.DataFrame(self.history)
