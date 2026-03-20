from abc import ABC
from typing import Union, Any, List
import numpy as np

class BaseRoutingModule(ABC):
    """
    汇流模块的抽象基类。
    所有汇流模块都应从此类继承。
    """
    def __init__(self, name: str = "routing_module", **kwargs: Any) -> None:
        self.name = name
        self.parameters: dict[str, Any] = {}

    def run(self, inflow: Union[float, int]) -> float:
        """
        运行汇流计算一个时间步。
        :param inflow: 当前时间步的上游来水或本地产流 (mm)
        :return: 经过汇流演算后的出流量 (mm)
        """
        result = self.step({"runoff": inflow}, dt=1.0)
        if isinstance(result, dict):
            return float(result.get("outflow", result.get("flow", 0.0)))
        return float(result)

    def step(self, inflows: dict[str, Union[float, int]], dt: float) -> dict[str, float]:
        outflow = self.run(inflows.get("runoff", 0.0))
        return {"outflow": float(outflow)}

class SimpleRouting(BaseRoutingModule):
    """
    从旧的 SimpleConceptualModel 中重构出的简单汇流模块。
    它将入流分为快速和慢速两部分，并通过两个线性水库进行演算。
    """
    def __init__(self, k_q: float, k_s: float, **kwargs: Any) -> None:
        super().__init__(kwargs.get("name", "simple_routing"))
        """
        :param k_q: 快速流出流系数
        :param k_s: 慢速流出流系数
        """
        self.k_q: float = k_q
        self.k_s: float = k_s
        self.Q_s: float = 0.0  # 慢速流（基流）的当前蓄量

    def run(self, inflow: Union[float, int]) -> float:
        # 流量划分
        quick_flow_runoff = inflow * 0.7  # 70% of runoff is quick flow
        slow_flow_runoff = inflow * 0.3  # 30% of runoff is slow flow

        # 慢速流演算
        self.Q_s += slow_flow_runoff
        slow_flow_discharge = self.Q_s * self.k_s
        self.Q_s -= slow_flow_discharge

        # 快速流演算（为简单起见，假设为直接出流）
        quick_flow_discharge = quick_flow_runoff * self.k_q

        total_discharge = quick_flow_discharge + slow_flow_discharge

        return total_discharge

class MuskingumRouting(BaseRoutingModule):
    """
    使用马斯京根法进行河道汇流演算的模块。
    """
    def __init__(self, K: float, x: float, dt: float = 1.0, **kwargs: Any) -> None:
        super().__init__(kwargs.get("name", "muskingum_routing"))
        """
        :param K: 蓄流时间常数 (与时间步 dt 单位相同)。
        :param x: 权重因子 (0 到 0.5)。
        :param dt: 时间步长 (默认为1.0)。
        """
        if not (0 <= x <= 0.5):
            raise ValueError("参数 x 必须在 [0, 0.5] 范围内。")
        if not (2 * K * x <= dt):
            print(f"Warning: 参数组合 (K={K}, x={x}, dt={dt}) 可能导致C1为负，结果可能不稳定。")

        self.K: float = K
        self.x: float = x
        self.dt: float = dt

        # 计算系数
        denominator = K * (1 - x) + 0.5 * dt
        self.C1: float = (0.5 * dt - K * x) / denominator
        self.C2: float = (0.5 * dt + K * x) / denominator
        self.C3: float = (K * (1 - x) - 0.5 * dt) / denominator

        # 初始化前一时间步的状态
        self.I_prev: float = 0.0
        self.O_prev: float = 0.0

    def run(self, inflow: Union[float, int]) -> float:
        """
        执行一步马斯京根演算。
        :param inflow: 当前时间步的入流量 I_t
        :return: 当前时间步的出流量 O_t
        """
        I_t = float(inflow)

        # 马斯京根方程
        O_t = self.C1 * I_t + self.C2 * self.I_prev + self.C3 * self.O_prev

        # 更新状态以备下一时间步使用
        self.I_prev = I_t
        self.O_prev = O_t

        return O_t

class UnitHydrographRouting(BaseRoutingModule):
    """
    使用单位线法进行汇流演算的模块。
    """
    def __init__(self, uh_ordinates: Union[List[float], np.ndarray] | None = None, **kwargs: Any) -> None:
        super().__init__(kwargs.get("name", "unit_hydrograph_routing"))
        """
        :param uh_ordinates: 单位线纵坐标的列表或numpy数组。
                             其总和应接近1.0（代表1单位输入的响应）。
        """
        self.uh: np.ndarray = np.array(uh_ordinates or [0.5, 0.3, 0.2])
        # 存储过去的有效降雨历史
        self.rainfall_history: List[float] = []

    def run(self, inflow: Union[float, int]) -> float:
        """
        执行一步单位线卷积演算。
        :param inflow: 当前时间步的有效降雨量 (mm)
        :return: 当前时间步的总直接径流 (mm)
        """
        self.rainfall_history.append(float(inflow))

        # 使用numpy的卷积功能来计算总径流过程线
        # 我们只关心当前时间步的出流，即卷积结果的最后一个有效值
        # 卷积结果的长度是 len(history) + len(uh) - 1
        if not self.rainfall_history:
            return 0.0

        direct_runoff_hydrograph = np.convolve(self.rainfall_history, self.uh)

        # 当前时间步的出流是过程线的第 t 个值 (0-indexed)
        current_timestep = len(self.rainfall_history) - 1

        if current_timestep < len(direct_runoff_hydrograph):
            return float(direct_runoff_hydrograph[current_timestep])
        else:
            return 0.0  # 发生在降雨结束后


# Backward-compatible alias used by the older test suite and examples.
UnitHydrographModule = UnitHydrographRouting

class MuskingumCungeRouting(BaseRoutingModule):
    """
    使用马斯京根-康基法进行河道汇流演算。
    该方法根据河道物理特性和水流条件动态计算汇流参数。
    """
    def __init__(self, length: float, slope: float, manning_n: float, width: float, dt: float = 1.0, **kwargs: Any) -> None:
        super().__init__(kwargs.get("name", "muskingum_cunge_routing"))
        """
        :param length: 河段长度 (m)。
        :param slope: 河床坡度 (m/m)。
        :param manning_n: 曼宁糙率系数。
        :param width: 河道宽度 (m)，假设为宽浅矩形。
        :param dt: 时间步长 (s)。这里需要注意单位，模型以天为单位，需转换。
        """
        self.length: float = length
        self.slope: float = slope
        self.n: float = manning_n
        self.width: float = width
        self.dt_seconds: float = dt * 24 * 3600  # 将天转换为秒

        # 初始化状态
        self.I_prev: float = 0.0
        self.O_prev: float = 0.0
        self.y_prev: float = 0.0  # 用于存储前一时间步的水深

    def run(self, inflow: Union[float, int]) -> float:
        I_t = float(inflow)

        # 防止流量为0时出现除零错误
        if I_t <= 1e-6 and self.I_prev <= 1e-6:
            self.I_prev = I_t
            self.O_prev = I_t
            return I_t

        # 1. 估算水力学参数
        Q_avg = (I_t + self.I_prev) / 2.0
        Q_avg = max(Q_avg, 1e-6) # 避免Q_avg为0

        # 2. 计算波速 c (celerity) 和水深 y
        # Q = A*v = (B*y) * (1/n * (B*y/(B+2y))^(2/3) * S^(1/2))
        # 简化为宽浅矩形 (B >> y), R_h ~ y
        # Q ~ (B*y) * (1/n * y^(2/3) * S^(1/2))
        # y ~ (Q*n / (B*S^0.5))^(3/5)
        y = (Q_avg * self.n / (self.width * self.slope**0.5))**0.6
        self.y_prev = y  # 存储水深供外部访问

        # c = dQ/dA = (5/3) * v
        v = Q_avg / (self.width * y)
        c = (5.0 / 3.0) * v
        c = max(c, 1e-6)

        # 3. 计算水力扩散系数 q
        q = Q_avg / (2 * self.width * self.slope)

        # 4. 动态计算 K 和 x
        K = self.length / c
        x = 0.5 * (1 - q / (c * self.length))
        x = max(0, min(0.5, x)) # 保证 x 在物理范围内

        # 5. 计算马斯京根系数 C1, C2, C3
        denominator = K * (1 - x) + 0.5 * self.dt_seconds
        if denominator < 1e-6:
            # 如果分母过小，流量变化不大，直接传递
            return I_t

        C1 = (0.5 * self.dt_seconds - K * x) / denominator
        C2 = (0.5 * self.dt_seconds + K * x) / denominator
        C3 = (K * (1 - x) - 0.5 * self.dt_seconds) / denominator

        # 6. 应用马斯京根方程
        O_t = C1 * I_t + C2 * self.I_prev + C3 * self.O_prev
        O_t = max(0, O_t) # 确保流量不为负

        # 7. 更新状态
        self.I_prev = I_t
        self.O_prev = O_t

        return O_t
