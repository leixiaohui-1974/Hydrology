"""
Configuration Parser Module
===========================

This module provides a parser to read a YAML configuration file and
build a complete, runnable simulation network.
"""
import os
import yaml
import numpy as np
import pandas as pd
from .controller import SimulationController
from .junction import Junction

# Import all possible model components to build a factory mapping
from hydro_model.model import HydrologicalModel
from hydro_model.runoff import SCSCurveNumberModule, SimpleRunoffModule, XinanjiangRunoffModule, HymodRunoffModule
from hydro_model.routing import SimpleRouting, MuskingumRouting, MuskingumCungeRouting
from hydro_model.areal_precipitation import ArealPrecipitation
from hydro_model.parameter_zone import ParameterZone

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
            "SimpleRunoffModule": SimpleRunoffModule, "XinanjiangRunoffModule": XinanjiangRunoffModule,
            "HymodRunoffModule": HymodRunoffModule,
            "SimpleRouting": SimpleRouting,
            "MuskingumRouting": MuskingumRouting, "MuskingumCungeRouting": MuskingumCungeRouting,
            "RiverReach": RiverReach, "RectangularCrossSection": RectangularCrossSection,
            "Gate": Gate, "Pump": Pump
        }

    def _instantiate_component(self, comp_config: dict, dt: float = None):
        """
        Instantiates a single component from its configuration dictionary.
        Optionally passes the simulation time step 'dt' to the component.
        """
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
                comp_params[key] = self._instantiate_component(value, dt=dt)
            elif isinstance(value, list) and value and isinstance(value[0], dict) and 'type' in value[0]:
                 comp_params[key] = [self._instantiate_component(v, dt=dt) for v in value]

        # 2. Add the component name if it's a main model component
        if 'name' in comp_config:
            comp_params['name'] = comp_config['name']

        # 3. Inject dt if the component needs it
        if dt is not None and comp_type_str in ["MuskingumRouting", "MuskingumCungeRouting"]:
            if 'dt' not in comp_params:
                comp_params['dt'] = dt

        # 4. Pre-process parameters for specific complex components
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

    def _build_parameter_zones(self, controller):
        """Builds and adds ParameterZone objects to the controller."""
        zone_configs = self.config.get("parameter_zones", [])
        if not zone_configs:
            return

        for zone_config in zone_configs:
            zone_id = zone_config.get("zone_id")
            component_names = zone_config.get("components", [])
            obs_comp = zone_config.get("observation_component")

            if not zone_id or not component_names or not obs_comp:
                raise ValueError("Parameter zone config must have 'zone_id', 'components', and 'observation_component'.")

            # Get the actual component objects from the controller
            try:
                components = [controller.components[name] for name in component_names]
            except KeyError as e:
                raise ValueError(f"Component '{e.args[0]}' listed in parameter zone '{zone_id}' not found in the simulation components.")

            # Create and add the zone
            zone = ParameterZone(zone_id, components, obs_comp)
            controller.add_parameter_zone(zone)
            print(f"Built parameter zone '{zone_id}' with components: {component_names}")

    def build_simulation(self) -> tuple:
        """
        Builds the SimulationController and simulation parameters from the config.
        """
        controller = SimulationController()
        config_dir = os.path.dirname(self.filepath)

        # 0. Get simulation parameters first, especially dt
        sim_params = self.config.get("simulation_parameters", {})
        dt = sim_params.get("dt_seconds")

        # 1. Build all components, passing dt to them
        for comp_config in self.config.get("components", []):
            component = self._instantiate_component(comp_config, dt=dt)
            controller.add_component(component)

        # 2. Connect the network
        for conn in self.config.get("network", []):
            controller.connect(conn['from'], conn['to'])

        # 3. Build parameter zones now that all components exist
        self._build_parameter_zones(controller)

        # 4. Handle Areal Precipitation if configured
        areal_precip_config = self.config.get("areal_precipitation")
        global_inputs_config = self.config.get("global_inputs", {})

        if areal_precip_config:
            print("--- Performing Areal Precipitation Calculation ---")
            # Get paths relative to the main config file
            subbasins_shp = os.path.join(config_dir, areal_precip_config['subbasins_shapefile'])
            gauges_csv = os.path.join(config_dir, areal_precip_config['rain_gauges_file'])

            # Instantiate the module
            areal_module = ArealPrecipitation(subbasins_shp, gauges_csv)

            # Load the raw, multi-column rainfall data
            rainfall_input_config = global_inputs_config.get('rainfall')
            if not rainfall_input_config or 'file' not in rainfall_input_config:
                raise ValueError("A 'rainfall' input file must be specified in 'global_inputs' when using 'areal_precipitation'.")

            rainfall_file = os.path.join(config_dir, rainfall_input_config['file'])
            raw_rainfall_df = pd.read_csv(rainfall_file, index_col=0, parse_dates=True)

            # Calculate areal rainfall
            method = areal_precip_config.get('method', 'idw')
            method_params = areal_precip_config.get('parameters', {})
            areal_rainfall_df = areal_module.calculate_areal_rainfall(raw_rainfall_df, method, **method_params)

            print(f"Areal rainfall calculated using '{method}' method.")

            # This processed DataFrame becomes the new source for rainfall input
            global_inputs_config['rainfall']['processed_df'] = areal_rainfall_df


        # 5. Load global inputs
        global_inputs = {}
        for key, input_config in global_inputs_config.items():
            # If data was pre-processed (like areal rainfall), use it
            if 'processed_df' in input_config:
                # The components expect rainfall per subbasin. The columns of the processed_df
                # should correspond to subbasin IDs, which need to be mapped to component names.
                # For now, we assume a direct mapping or a single rainfall input.
                # This part may need refinement based on how components are named.
                # Let's assume the component that needs rainfall is named after the input key.
                rainfall_component_name = key
                if rainfall_component_name in controller.components:
                     # Find the corresponding subbasin ID for the component.
                     # This logic assumes the component name is or can be mapped to a subbasin ID.
                     # A more robust solution might need an explicit mapping in the config.
                     # For now, let's assume the first column of the processed data is for the first hydro model.
                     # A better approach: The component name should match a column in the areal_rainfall_df
                    # Map interpolated rainfall to components by matching column names (subbasin IDs) to component names
                    for subbasin_id in areal_rainfall_df.columns:
                        component_name = str(subbasin_id) # Ensure the ID is a string for matching
                        if component_name in controller.components:
                            global_inputs[component_name] = areal_rainfall_df[subbasin_id].values
                            print(f"Mapped interpolated rainfall for subbasin '{component_name}' to component.")
                        else:
                            print(f"Warning: No component found with name '{component_name}' to assign interpolated rainfall to.")

            elif 'file' in input_config:
                data_path = os.path.join(config_dir, input_config['file'])
                # This part now only handles non-rainfall inputs if areal precip was used
                if key == 'rainfall' and areal_precip_config:
                    continue # Skip raw rainfall loading if it was processed

                col_idx = input_config.get('column_index', 1)
                data = np.loadtxt(data_path, delimiter=',', skiprows=1, usecols=col_idx)
                global_inputs[key] = data
            elif 'values' in input_config:
                global_inputs[key] = np.array(input_config['values'])

        return controller, sim_params, global_inputs
