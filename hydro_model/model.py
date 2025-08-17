from .runoff import BaseRunoffModule
from .routing import BaseRoutingModule

class HydrologicalModel:
    """
    一个灵活的、模块化的水文模型框架。
    它由一个产流模块和一个汇流模块组成。
    """
    def __init__(self, runoff_module: BaseRunoffModule, routing_module: BaseRoutingModule):
        """
        初始化模型。
        :param runoff_module: 一个产流模块的实例。
        :param routing_module: 一个汇流模块的实例。
        """
        if not isinstance(runoff_module, BaseRunoffModule):
            raise TypeError("runoff_module 必须是 BaseRunoffModule 的一个实例。")
        if not isinstance(routing_module, BaseRoutingModule):
            raise TypeError("routing_module 必须是 BaseRoutingModule 的一个实例。")

        self.runoff_module = runoff_module
        self.routing_module = routing_module

    def run(self, rainfall, pet):
        """
        为单个时间步运行模型。
        :param rainfall: 当前时间步的降雨量 (mm)
        :param pet: 当前时间步的潜在蒸散发量 (mm)
        :return: 总径流量 (mm)
        """
        # 1. 运行产流模块计算本地径流
        local_runoff = self.runoff_module.run(rainfall, pet)

        # 2. 运行汇流模块处理本地径流
        # 注意：对于子流域头部的模型，这里的inflow就是本地产流。
        # 对于河道演算模型，inflow将是上游来水。这个逻辑在Catchment层面处理。
        total_discharge = self.routing_module.run(local_runoff)

        return total_discharge
