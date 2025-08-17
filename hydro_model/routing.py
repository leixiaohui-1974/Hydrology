from abc import ABC, abstractmethod
import numpy as np

class BaseRoutingModule(ABC):
    """
    汇流模块的抽象基类。
    所有汇流模块都应从此类继承。
    """
    @abstractmethod
    def run(self, inflow):
        """
        运行汇流计算一个时间步。
        :param inflow: 当前时间步的上游来水或本地产流 (mm)
        :return: 经过汇流演算后的出流量 (mm)
        """
        pass

class SimpleRouting(BaseRoutingModule):
    """
    从旧的 SimpleConceptualModel 中重构出的简单汇流模块。
    它将入流分为快速和慢速两部分，并通过两个线性水库进行演算。
    """
    def __init__(self, k_q, k_s, **kwargs):
        """
        :param k_q: 快速流出流系数
        :param k_s: 慢速流出流系数
        """
        self.k_q = k_q
        self.k_s = k_s
        self.Q_s = 0.0  # 慢速流（基流）的当前蓄量

    def run(self, inflow):
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
    def __init__(self, K, x, dt=1.0, **kwargs):
        """
        :param K: 蓄流时间常数 (与时间步 dt 单位相同)。
        :param x: 权重因子 (0 到 0.5)。
        :param dt: 时间步长 (默认为1.0)。
        """
        if not (0 <= x <= 0.5):
            raise ValueError("参数 x 必须在 [0, 0.5] 范围内。")
        if not (2 * K * x <= dt):
            print(f"Warning: 参数组合 (K={K}, x={x}, dt={dt}) 可能导致C1为负，结果可能不稳定。")

        self.K = K
        self.x = x
        self.dt = dt

        # 计算系数
        denominator = K * (1 - x) + 0.5 * dt
        self.C1 = (0.5 * dt - K * x) / denominator
        self.C2 = (0.5 * dt + K * x) / denominator
        self.C3 = (K * (1 - x) - 0.5 * dt) / denominator

        # 初始化前一时间步的状态
        self.I_prev = 0.0
        self.O_prev = 0.0

    def run(self, inflow):
        """
        执行一步马斯京根演算。
        :param inflow: 当前时间步的入流量 I_t
        :return: 当前时间步的出流量 O_t
        """
        I_t = inflow

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
    def __init__(self, uh_ordinates, **kwargs):
        """
        :param uh_ordinates: 单位线纵坐标的列表或numpy数组。
                             其总和应接近1.0（代表1单位输入的响应）。
        """
        self.uh = np.array(uh_ordinates)
        # 存储过去的有效降雨历史
        self.rainfall_history = []

    def run(self, inflow):
        """
        执行一步单位线卷积演算。
        :param inflow: 当前时间步的有效降雨量 (mm)
        :return: 当前时间步的总直接径流 (mm)
        """
        self.rainfall_history.append(inflow)

        # 使用numpy的卷积功能来计算总径流过程线
        # 我们只关心当前时间步的出流，即卷积结果的最后一个有效值
        # 卷积结果的长度是 len(history) + len(uh) - 1
        if not self.rainfall_history:
            return 0.0

        direct_runoff_hydrograph = np.convolve(self.rainfall_history, self.uh)

        # 当前时间步的出流是过程线的第 t 个值 (0-indexed)
        current_timestep = len(self.rainfall_history) - 1

        if current_timestep < len(direct_runoff_hydrograph):
            return direct_runoff_hydrograph[current_timestep]
        else:
            return 0.0 # 发生在降雨结束后
