import numpy as np

class SimpleConceptualModel:
    """
    一个简单的概念性水文模型。

    该模型包括一个土壤水库，并将径流分为快速流和慢速流。
    """
    def __init__(self, params):
        """
        初始化模型。

        :param params: 包含模型参数的字典。
                       - S_max: 土壤最大含水量 (mm)
                       - k_q: 快速流出流系数
                       - k_s: 慢速流出流系数
                       - c_loss: 损失系数 (占 S_max 的比例)
        """
        self.params = params
        self.S_max = params['S_max']
        self.k_q = params['k_q']
        self.k_s = params['k_s']
        self.c_loss = params['c_loss']

        # 初始化状态变量
        self.S = 0.0  # 土壤水库的当前含水量
        self.Q_s = 0.0  # 慢速流（基流）的当前流量

    def run(self, rainfall, pet):
        """
        为单个时间步运行模型。

        :param rainfall: 当前时间步的降雨量 (mm)
        :param pet: 当前时间步的潜在蒸散发量 (mm)
        :return: 总径流量 (mm)
        """
        # 蒸散发损失
        actual_et = min(self.S, pet)
        self.S -= actual_et

        # 产流
        effective_rainfall = rainfall
        if self.S < self.S_max:
            runoff_potential = (self.S / self.S_max) * effective_rainfall
            self.S += effective_rainfall - runoff_potential
            if self.S > self.S_max:
                runoff_potential += self.S - self.S_max
                self.S = self.S_max
        else:
            runoff_potential = effective_rainfall

        # 深层渗漏/损失
        loss = min(self.S, self.S * self.c_loss)
        self.S -= loss

        # 流量划分
        quick_flow_runoff = runoff_potential * 0.7  # 70% of runoff is quick flow
        slow_flow_runoff = runoff_potential * 0.3  # 30% of runoff is slow flow

        # 慢速流演算
        self.Q_s += slow_flow_runoff
        slow_flow_discharge = self.Q_s * self.k_s
        self.Q_s -= slow_flow_discharge

        # 快速流演算（为简单起见，假设为直接出流）
        quick_flow_discharge = quick_flow_runoff * self.k_q

        total_discharge = quick_flow_discharge + slow_flow_discharge

        return total_discharge
