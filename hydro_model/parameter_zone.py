# hydro_model/parameter_zone.py
from typing import List
from .model import HydrologicalModel

class ParameterZone:
    """
    Represents a parameter zone, which is a collection of sub-basins (HydrologicalModel components)
    whose parameters are intended to be adjusted together during calibration.
    """
    def __init__(self, zone_id: str, components: List[HydrologicalModel], observation_component: str):
        self.id = zone_id
        self.components = components
        self.observation_component = observation_component

    def get_parameters(self, param_name: str) -> List[float]:
        """
        Gets a specific parameter from all components in the zone.
        Example: param_name = 'runoff_module.CN'
        """
        values = []
        for component in self.components:
            # This is a bit tricky, we need to get nested attributes
            try:
                module, param = param_name.split('.')
                value = getattr(getattr(component, module), param)
                values.append(value)
            except AttributeError:
                raise AttributeError(f"Component {component.name} or its modules do not have parameter {param_name}")
        return values

    def set_parameters(self, param_name: str, values: List[float]):
        """
        Sets a specific parameter for all components in the zone.
        """
        if len(values) != len(self.components):
            raise ValueError("The number of values must match the number of components in the zone.")

        for i, component in enumerate(self.components):
            try:
                module, param = param_name.split('.')
                setattr(getattr(component, module), param, values[i])
            except AttributeError:
                raise AttributeError(f"Component {component.name} or its modules do not have parameter {param_name}")
