"""
Hydrological Model Module
=========================

This module contains the HydrologicalModel class, which serves as a
container for different runoff and routing modules.
"""
from typing import Optional, Dict, List, Any, Union
from .runoff import BaseRunoffModule, BaseSnowmeltModule
from .routing import BaseRoutingModule
from common.base_model import BaseModelComponent

class HydrologicalModel(BaseModelComponent):
    """
    A flexible, modular hydrological model framework.
    It consists of a runoff module and optional snowmelt and routing modules.
    """
    def __init__(self,
                 name: str,
                 runoff_module: BaseRunoffModule,
                 routing_module: Optional[BaseRoutingModule] = None,
                 snowmelt_module: Optional[BaseSnowmeltModule] = None) -> None:
        """
        Initializes the model.
        :param name: The unique name of this component.
        :param runoff_module: An instance of a runoff module.
        :param routing_module: An optional instance of a routing module.
        :param snowmelt_module: An optional instance of a snowmelt module.
        """
        super().__init__(name)
        if not isinstance(runoff_module, BaseRunoffModule):
            raise TypeError("runoff_module must be an instance of BaseRunoffModule.")
        if routing_module is not None and not isinstance(routing_module, BaseRoutingModule):
            raise TypeError("routing_module must be an instance of BaseRoutingModule or None.")
        if snowmelt_module is not None and not isinstance(snowmelt_module, BaseSnowmeltModule):
            raise TypeError("snowmelt_module must be an instance of BaseSnowmeltModule or None.")

        self.runoff_module: BaseRunoffModule = runoff_module
        self.routing_module: Optional[BaseRoutingModule] = routing_module
        self.snowmelt_module: Optional[BaseSnowmeltModule] = snowmelt_module

        # For storing results
        self.outflow_history: List[float] = []

    def step(self, inflows: Dict[str, Union[float, int]], dt: float) -> None:
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
        precipitation = inflows.get('rainfall', 0.0) # 'rainfall' key is used for precipitation
        pet = inflows.get('pet', 0.0)
        temperature = inflows.get('temperature') # Can be None if not provided

        # --- Get inflows from other model components ---
        upstream_inflow = sum(v for k, v in inflows.items() if k not in ['rainfall', 'pet', 'temperature'])

        # 1. Run snowmelt module first, if it exists
        if self.snowmelt_module:
            if temperature is None:
                raise ValueError(f"Component '{self.name}' has a snowmelt module but no 'temperature' input was provided.")
            liquid_water = self.snowmelt_module.run(precipitation, temperature)
        else:
            liquid_water = precipitation

        # 2. 运行产流模块计算本地径流 (Runoff generation)
        local_runoff = self.runoff_module.run(liquid_water, pet)

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
        self.outflow_history.append(self.outflow)

    def get_results(self) -> Dict[str, List[float]]:
        """Returns the stored history of outflows."""
        return {"outflow": self.outflow_history}

    def run(self, rainfall: Union[float, int], pet: Union[float, int]) -> float:
        """
        Original run method for standalone execution or simple cases.
        Note: This will be superseded by the global SimulationController.
        """
        inflows = {'rainfall': rainfall, 'pet': pet}
        self.step(inflows, dt=0) # dt is not used here
        return self.get_outflow()
