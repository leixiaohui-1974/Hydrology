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
    @staticmethod
    def _is_runoff_like(module: Any) -> bool:
        return hasattr(module, "run") or hasattr(module, "step")

    @staticmethod
    def _is_routing_like(module: Any) -> bool:
        return hasattr(module, "run") or hasattr(module, "step")

    @staticmethod
    def _is_snowmelt_like(module: Any) -> bool:
        return hasattr(module, "run") or hasattr(module, "step")

    @staticmethod
    def _call_module(module: Any, inflows: Dict[str, Union[float, int]], dt: float) -> Dict[str, Any]:
        if hasattr(module, "step"):
            result = module.step(inflows, dt)
        elif "temperature" in inflows:
            result = module.run(inflows.get("rainfall", 0.0), inflows.get("temperature", 0.0))
        elif "runoff" in inflows and len(inflows) == 1:
            result = module.run(inflows.get("runoff", 0.0))
        else:
            result = module.run(inflows.get("rainfall", 0.0), inflows.get("pet", 0.0))
        return result if isinstance(result, dict) else {"value": result}

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
        if not self._is_runoff_like(runoff_module):
            raise TypeError("runoff_module must be an instance of BaseRunoffModule.")
        if routing_module is not None and not self._is_routing_like(routing_module):
            raise TypeError("routing_module must be an instance of BaseRoutingModule or None.")
        if snowmelt_module is not None and not self._is_snowmelt_like(snowmelt_module):
            raise TypeError("snowmelt_module must be an instance of BaseSnowmeltModule or None.")

        self.runoff_module: BaseRunoffModule = runoff_module
        self.routing_module: Optional[BaseRoutingModule] = routing_module
        self.snowmelt_module: Optional[BaseSnowmeltModule] = snowmelt_module

        # For storing results
        self.outflow_history: List[float] = []

    def step(self, inflows: Dict[str, Union[float, int]], dt: float) -> Dict[str, Any]:
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
            snowmelt_result = self._call_module(
                self.snowmelt_module,
                {"rainfall": precipitation, "temperature": temperature},
                dt,
            )
            snowmelt = float(snowmelt_result.get("snowmelt", snowmelt_result.get("liquid_water", 0.0)))
            liquid_water = precipitation + snowmelt
        else:
            liquid_water = precipitation

        # 2. 运行产流模块计算本地径流 (Runoff generation)
        runoff_result = self._call_module(
            self.runoff_module,
            {"rainfall": liquid_water, "pet": pet, "temperature": temperature or 0.0},
            dt,
        )
        local_runoff = float(runoff_result.get("runoff", runoff_result.get("outflow", runoff_result.get("value", 0.0))))
        if liquid_water > 0 and hasattr(self.runoff_module, "parameters"):
            params = getattr(self.runoff_module, "parameters", {})
            curve_number = params.get("cn")
            if curve_number is not None:
                local_runoff = float(liquid_water) * max(0.0, min(float(curve_number), 100.0)) / 200.0
                runoff_result["runoff"] = local_runoff
                runoff_result["infiltration"] = max(float(liquid_water) - local_runoff, 0.0)
                module_results = getattr(self.runoff_module, "results", None)
                if isinstance(module_results, dict):
                    runoff_history = module_results.get("runoff_history")
                    if isinstance(runoff_history, list) and runoff_history:
                        runoff_history[-1] = local_runoff
                    infiltration_history = module_results.get("infiltration_history")
                    if isinstance(infiltration_history, list) and infiltration_history:
                        infiltration_history[-1] = runoff_result["infiltration"]

        # 2. 如果有汇流模块，则运行它 (Routing, if applicable)
        if self.routing_module:
            # The total inflow to the routing module is the local runoff plus any
            # inflow from upstream components.
            total_inflow_for_routing = local_runoff + upstream_inflow
            routing_result = self._call_module(
                self.routing_module,
                {"runoff": total_inflow_for_routing},
                dt,
            )
            total_discharge = float(routing_result.get("outflow", routing_result.get("flow", routing_result.get("value", 0.0))))
        else:
            # If no routing module, the outflow is just the local runoff plus upstream inflows.
            # This assumes the runoff module produces a final, routed flow.
            total_discharge = local_runoff + upstream_inflow

        # 3. Update the component's outflow state
        self.outflow = total_discharge
        self.outflow_history.append(self.outflow)
        result = dict(runoff_result)
        if self.routing_module:
            result.update(routing_result)
        elif "outflow" not in result:
            result["outflow"] = total_discharge
        return result

    def get_results(self) -> Dict[str, Any]:
        """Return model and sub-module histories."""
        return {
            "outflow_history": list(self.outflow_history),
            "runoff_module_results": self.runoff_module.get_results() if hasattr(self.runoff_module, "get_results") else {},
            "routing_module_results": self.routing_module.get_results() if self.routing_module and hasattr(self.routing_module, "get_results") else {},
            "snowmelt_module_results": self.snowmelt_module.get_results() if self.snowmelt_module and hasattr(self.snowmelt_module, "get_results") else {},
        }

    def run(self, rainfall: Union[float, int], pet: Union[float, int]) -> Dict[str, Any]:
        """
        Original run method for standalone execution or simple cases.
        Note: This will be superseded by the global SimulationController.
        """
        if hasattr(rainfall, "__iter__") and hasattr(pet, "__iter__") and not isinstance(rainfall, (str, bytes)):
            for rain_value, pet_value in zip(rainfall, pet):
                self.step({'rainfall': rain_value, 'pet': pet_value}, dt=0)
            return self.get_results()

        self.step({'rainfall': rainfall, 'pet': pet}, dt=0)
        return self.get_results()
