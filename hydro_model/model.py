"""
Hydrological Model Module
=========================

This module contains the HydrologicalModel class, which serves as a
container for different runoff and routing modules.
"""
from typing import Optional
from .runoff import BaseRunoffModule
from .routing import BaseRoutingModule
from common.base_model import BaseModelComponent

class HydrologicalModel(BaseModelComponent):
    """
    一个灵活的、模块化的水文模型框架。
    它由一个产流模块和一个可选的汇流模块组成。
    This component represents a catchment or sub-catchment.
    """
    def __init__(self, name: str, runoff_module: BaseRunoffModule, routing_module: Optional[BaseRoutingModule] = None):
        """
        初始化模型。
        :param name: The unique name of this component.
        :param runoff_module: 一个产流模块的实例。
        :param routing_module: 一个可选的汇流模块的实例。
        """
        super().__init__(name)
        if not isinstance(runoff_module, BaseRunoffModule):
            raise TypeError("runoff_module 必须是 BaseRunoffModule 的一个实例。")
        if routing_module is not None and not isinstance(routing_module, BaseRoutingModule):
            raise TypeError("routing_module 必须是 BaseRoutingModule 的一个实例或 None。")

        self.runoff_module = runoff_module
        self.routing_module = routing_module

    def step(self, inflows: dict, dt: float):
        """
        为单个时间步运行模型, conforming to the BaseModelComponent interface.

        Args:
            inflows (dict): A dictionary of all inflows. This must include
                            special keys 'rainfall' and 'pet' for this component.
                            It can also include outflows from upstream components.
            dt (float): The time step duration (not directly used by these simple
                        modules but required by the interface).
        """
        # --- Get external forcings from the inflows dict ---
        rainfall = inflows.get('rainfall', 0.0)
        pet = inflows.get('pet', 0.0)

        # --- Get inflows from other model components ---
        # Sum up all inflows that are not external forcings
        upstream_inflow = sum(v for k, v in inflows.items() if k not in ['rainfall', 'pet'])

        # 1. 运行产流模块计算本地径流 (Runoff generation)
        local_runoff = self.runoff_module.run(rainfall, pet)

        # 2. 如果有汇流模块，则运行它 (Routing, if applicable)
        if self.routing_module:
            # The total inflow to the routing module is the local runoff plus any
            # inflow from upstream components.
            total_inflow_for_routing = local_runoff + upstream_inflow
            total_discharge = self.routing_module.run(total_inflow_for_routing)
        else:
            # If no routing module, the outflow is just the local runoff plus upstream inflows.
            # This assumes the runoff module produces a final, routed flow.
            total_discharge = local_runoff + upstream_inflow

        # 3. Update the component's outflow state
        self.outflow = total_discharge

    def run(self, rainfall, pet):
        """
        Original run method for standalone execution or simple cases.
        Note: This will be superseded by the global SimulationController.
        """
        inflows = {'rainfall': rainfall, 'pet': pet}
        self.step(inflows, dt=0) # dt is not used here
        return self.get_outflow()
