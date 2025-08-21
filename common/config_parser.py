"""
Configuration Parser Module
===========================

This module provides a parser to read a YAML configuration file and
build a complete, runnable simulation network.
"""
import yaml
import numpy as np
from .controller import SimulationController
from .junction import Junction

# Import all possible model components to build a factory mapping
from hydro_model.model import HydrologicalModel
from hydro_model.runoff import SCSCurveNumberModule, SimpleRunoffModule, XinanjiangModel, ShaanbeiModel, WetSpaModel, HymodModel
from hydro_model.routing import SimpleRouting, MuskingumRouting, MuskingumCungeRouting

from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from preissmann_model.structures import Gate, Pump


class ConfigParser:
    """
    Parses a YAML configuration file to build and configure a SimulationController.
    """
    def __init__(self, config_filepath: str):
        self.filepath = config_filepath
        with open(self.filepath, 'r') as f:
            self.config = yaml.safe_load(f)

        self.component_factory = self._build_factory()

    def _build_factory(self):
        """Creates a mapping of component type strings to classes."""
        return {
            "HydrologicalModel": HydrologicalModel, "HydraulicModel": HydraulicModel,
            "Junction": Junction, "SCSCurveNumberModule": SCSCurveNumberModule,
            "SimpleRunoffModule": SimpleRunoffModule, "SimpleRouting": SimpleRouting,
            "MuskingumRouting": MuskingumRouting, "MuskingumCungeRouting": MuskingumCungeRouting,
            "RiverReach": RiverReach, "RectangularCrossSection": RectangularCrossSection,
            "Gate": Gate, "Pump": Pump,
            "XinanjiangModel": XinanjiangModel, "ShaanbeiModel": ShaanbeiModel,
            "WetSpaModel": WetSpaModel, "HymodModel": HymodModel
        }

    def _instantiate_component(self, comp_config: dict):
        """Instantiates a single component from its configuration dictionary."""
        comp_type_str = comp_config.get("type")
        comp_params = comp_config.get("parameters", {})

        if not comp_type_str:
            raise ValueError("Component config must have a 'type'.")

        comp_class = self.component_factory.get(comp_type_str)
        if not comp_class:
            raise ValueError(f"Unknown component type: {comp_type_str}")

        # 1. Recursively instantiate any sub-components first
        for key, value in comp_params.items():
            if isinstance(value, dict) and 'type' in value:
                comp_params[key] = self._instantiate_component(value)
            elif isinstance(value, list) and value and isinstance(value[0], dict) and 'type' in value[0]:
                 comp_params[key] = [self._instantiate_component(v) for v in value]

        # 2. Add the component name if it's a main model component
        if 'name' in comp_config:
            comp_params['name'] = comp_config['name']

        # 3. Pre-process parameters for specific complex components
        if comp_type_str == "RiverReach":
            comp_params = self._build_river_reach_params(comp_params)

        return comp_class(**comp_params)

    def _build_river_reach_params(self, params: dict) -> dict:
        """
        Helper method to construct RiverReach parameters from high-level config.
        It expects that the 'cross_sections' parameter has already been instantiated
        into a list of CrossSection objects.
        """
        num_nodes = params.pop('num_nodes')
        length = params.pop('length')

        # We assume a prismatic channel, so all cross-sections are the same.
        # We take the first one from the list as the template.
        template_cs = params['cross_sections'][0]
        params['cross_sections'] = [template_cs for _ in range(num_nodes)]

        # Create the lengths array
        dx = length / (num_nodes - 1)
        params['lengths'] = np.full(num_nodes - 1, dx)

        # Remove high-level params that are not direct inputs to RiverReach
        params.pop('width', None) # Remove 'width' if it exists

        return params

    def build_simulation(self) -> tuple:
        """
        Builds the SimulationController and simulation parameters from the config.
        """
        controller = SimulationController()

        for comp_config in self.config.get("components", []):
            component = self._instantiate_component(comp_config)
            controller.add_component(component)

        for conn in self.config.get("network", []):
            controller.connect(conn['from'], conn['to'])

        sim_params = self.config.get("simulation_parameters", {})

        global_inputs = {}
        for key, input_config in self.config.get("global_inputs", {}).items():
            if 'file' in input_config:
                # we are expecting a csv with a header and a date column
                with open(input_config['file'], 'r') as f:
                    header = f.readline()
                    num_cols = len(header.split(','))

                use_cols = tuple(range(1, num_cols))
                data = np.loadtxt(input_config['file'], delimiter=',', skiprows=1, usecols=use_cols)

                if len(data.shape) == 1:
                    global_inputs[key] = data
                else:
                    global_inputs[key] = data[:,0] # take first data column
            elif 'values' in input_config:
                global_inputs[key] = np.array(input_config['values'])

        return controller, sim_params, global_inputs
