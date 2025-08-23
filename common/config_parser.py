import os
import yaml
import json
import numpy as np
import pandas as pd
from .controller import SimulationController
from .junction import Junction

from hydro_model.model import HydrologicalModel
from hydro_model.runoff import (SCSCurveNumberModule, SimpleRunoffModule, XinanjiangRunoffModule,
                                HymodRunoffModule, SnowmeltRunoffModule)
from hydro_model.routing import SimpleRouting, MuskingumRouting, MuskingumCungeRouting
from hydro_model.areal_precipitation import ArealPrecipitation
from hydro_model.parameter_zone import ParameterZone

from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import (RectangularCrossSection, TrapezoidalCrossSection,
                                            IrregularCrossSection)
from preissmann_model.structures import Gate, Pump, Weir
from model_2d.model import Model2D
from model_2d.mesh import Mesh

from preprocessing.runoff_analysis import calculate_runoff_coefficient
from preprocessing.baseflow_separation import lyne_hollick_filter
from .db_loader import load_from_db

class ConfigParser:
    """
    Parses a configuration from a file or a dictionary to build a SimulationController.
    """
    def __init__(self, config_source: str or dict, base_path: str = '.'):
        if isinstance(config_source, dict):
            self.config = config_source
            self.config_dir = base_path
        elif isinstance(config_source, str):
            self.filepath = config_source
            with open(self.filepath, 'r') as f:
                self.config = yaml.safe_load(f)
            self.config_dir = os.path.dirname(self.filepath)
        else:
            raise TypeError("config_source must be a file path (str) or a dictionary.")

        self.component_factory = self._build_factory()
        self.data_registry = {}

    def _build_factory(self):
        # This can be refactored to be more dynamic in the future
        return {
            "HydrologicalModel": HydrologicalModel, "HydraulicModel": HydraulicModel,
            "Junction": Junction,
            "SCSCurveNumberModule": SCSCurveNumberModule,
            "SimpleRunoffModule": SimpleRunoffModule,
            "XinanjiangRunoffModule": XinanjiangRunoffModule,
            "HymodRunoffModule": HymodRunoffModule,
            "SnowmeltRunoffModule": SnowmeltRunoffModule,
            "SimpleRouting": SimpleRouting,
            "MuskingumRouting": MuskingumRouting, "MuskingumCungeRouting": MuskingumCungeRouting,
            "RiverReach": RiverReach,
            "RectangularCrossSection": RectangularCrossSection,
            "TrapezoidalCrossSection": TrapezoidalCrossSection,
            "IrregularCrossSection": IrregularCrossSection,
            "Gate": Gate, "Pump": Pump, "Weir": Weir,
            "HydraulicModel2D": Model2D
        }

    def _instantiate_component(self, comp_config: dict, dt: float = None):
        # This recursive instantiation is the core of the parser
        comp_type_str = comp_config.get("type")
        comp_params = comp_config.get("parameters", {})
        if not comp_type_str: raise ValueError("Component config must have a 'type'.")
        comp_class = self.component_factory.get(comp_type_str)
        if not comp_class: raise ValueError(f"Unknown component type: {comp_type_str}")

        for key, value in comp_params.items():
            # Prevent recursion into data-only parameters that happen to have a 'type' key
            if key in ['boundary_conditions']:
                continue
            if isinstance(value, dict) and 'type' in value:
                comp_params[key] = self._instantiate_component(value, dt=dt)
            elif isinstance(value, list) and value and isinstance(value[0], dict) and 'type' in value[0]:
                 comp_params[key] = [self._instantiate_component(v, dt=dt) for v in value]

        if 'name' in comp_config: comp_params['name'] = comp_config['name']

        if dt is not None and comp_type_str in ["MuskingumRouting", "MuskingumCungeRouting"]:
            if 'dt' not in comp_params: comp_params['dt'] = dt

        if comp_type_str == "RiverReach":
            if 'num_nodes' in comp_params and 'length' in comp_params:
                num_nodes = comp_params.pop('num_nodes')
                length = comp_params.pop('length')
                template_cs = comp_params['cross_sections'][0]
                comp_params['cross_sections'] = [template_cs for _ in range(num_nodes)]
                dx = length / (num_nodes - 1)
                comp_params['lengths'] = np.full(num_nodes - 1, dx)

        elif comp_type_str == "HydraulicModel2D":
            mesh_file_path = os.path.join(self.config_dir, comp_params.pop('mesh_file'))
            # The DEM file is used for setting elevation, which can be done
            # after mesh creation. For now, we just pop it from the params.
            comp_params.pop('dem_file', None) # Safely remove dem_file if it exists

            if not os.path.exists(mesh_file_path):
                raise FileNotFoundError(f"Mesh file not found: {mesh_file_path}")

            with open(mesh_file_path, 'r') as f:
                mesh_data = json.load(f)

            mesh = Mesh()
            mesh.build_from_points_and_triangles(mesh_data['points'], mesh_data['triangles'])

            # Configure boundary conditions
            bcs = comp_params.pop('boundary_conditions', [])
            for bc in bcs:
                bc_type = bc['type']
                for edge_id in bc['edge_ids']:
                    mesh.set_boundary_edge_type(edge_id, bc_type)

            # Add the mesh object to the component parameters
            comp_params['mesh'] = mesh

        return comp_class(**comp_params)

    def _load_data_sources(self):
        """Loads all initial data sources from files or DB into the data registry."""
        print("--- Loading Data Sources ---")
        db_params = self.config.get('database_connection')
        for name, config in self.config.get("data_sources", {}).items():
            if 'file' in config:
                path = os.path.join(self.config_dir, config['file'])
                self.data_registry[name] = pd.read_csv(path, index_col=0, parse_dates=True)
                print(f"Loaded source '{name}' from file: {config['file']}")
            elif 'database_source' in config:
                if not db_params: raise ValueError("Database source specified but no 'database_connection' config found.")
                query = config['database_source'].get('query')
                if not query: raise ValueError(f"Data source '{name}' is missing a 'query'.")
                self.data_registry[name] = load_from_db(db_params, query)
                print(f"Loaded source '{name}' from database.")

    def _run_areal_precipitation(self):
        """Runs the areal precipitation calculation if configured."""
        config = self.config.get("areal_precipitation")
        if not config:
            return

        print("\n--- Performing Areal Precipitation Calculation ---")
        input_name = config['input_name']
        output_name = config['output_name']

        if input_name not in self.data_registry:
            raise ValueError(f"Input '{input_name}' for areal precipitation not found in data registry.")

        areal_module = ArealPrecipitation(
            os.path.join(self.config_dir, config['subbasins_shapefile']),
            os.path.join(self.config_dir, config['rain_gauges_file'])
        )

        raw_rainfall_df = self.data_registry[input_name]
        method = config.get('method', 'idw')
        params = config.get('parameters', {})

        if 'cache_file' in params:
            params['cache_file'] = os.path.join(self.config_dir, params['cache_file'])

        result = areal_module.calculate_areal_rainfall(raw_rainfall_df, method, **params)

        if method == 'kriging':
            mean_df, variance_df = result
            self.data_registry[output_name] = mean_df
            self.data_registry[f"{output_name}_variance"] = variance_df
            print(f"Areal rainfall calculated using '{method}'. New data sources created: '{output_name}' and '{output_name}_variance'.")
        else:
            self.data_registry[output_name] = result
            print(f"Areal rainfall calculated using '{method}'. New data source '{output_name}' created.")

    def _run_preprocessing(self):
        """Runs all configured preprocessing steps."""
        config = self.config.get("preprocessing")
        if not config: return

        print("\n--- Running Preprocessing Steps ---")
        if 'runoff_coefficient' in config:
            print("[Preprocessing] Calculating Runoff Coefficient...")
            rc_conf = config['runoff_coefficient']
            rainfall_df = self.data_registry[rc_conf['rainfall_input']]
            flow_df = self.data_registry[rc_conf['flow_input']]
            calculate_runoff_coefficient(
                rainfall_df.iloc[:, 0], flow_df.iloc[:, 0], rc_conf['catchment_area_km2']
            )

        if 'baseflow_separation' in config:
            print("[Preprocessing] Performing Baseflow Separation...")
            bs_conf = config['baseflow_separation']
            flow_df = self.data_registry[bs_conf['flow_input']]
            params = bs_conf.get('parameters', {})
            separated_df = lyne_hollick_filter(flow_df.iloc[:, 0], **params)
            self.data_registry[bs_conf['output_baseflow']] = separated_df[['baseflow']]
            self.data_registry[bs_conf['output_quickflow']] = separated_df[['quick_flow']]
            print(f"Baseflow separation complete. New inputs available: '{bs_conf['output_baseflow']}', '{bs_conf['output_quickflow']}'")

    def _prepare_global_inputs(self, num_steps):
        """
        Prepares the final global_inputs dictionary for the SimulationController.
        The controller expects a flat dictionary: {variable_name: numpy_array}.
        """
        print("\n--- Preparing Global Inputs for Simulation ---")
        final_global_inputs = {}
        input_configs = self.config.get("global_inputs", [])

        for input_config in input_configs:
            # The 'target_component' is mainly for readability in the config.
            # The key of the 'inputs' dict is the variable name that components will look for.
            for var_name, source_info in input_config.get('inputs', {}).items():
                if var_name in final_global_inputs:
                    print(f"Warning: Global input '{var_name}' is being overwritten. The last definition in the config will be used.")

                if 'from_source' in source_info:
                    source_name = source_info['from_source']
                    col_name = source_info['from_column']
                    if source_name not in self.data_registry:
                        raise ValueError(f"Data source '{source_name}' not found.")
                    if col_name not in self.data_registry[source_name].columns:
                        raise ValueError(f"Column '{col_name}' not found in source '{source_name}'.")
                    final_global_inputs[var_name] = self.data_registry[source_name][col_name].to_numpy()

                elif 'value' in source_info:
                    constant_value = source_info['value']
                    final_global_inputs[var_name] = np.full(num_steps, constant_value)

            # This handles the special case for inflows where the component name
            # itself is the key for the input (e.g., for HydraulicModel2D).
            comp_name = input_config.get('target_component')
            if comp_name and comp_name not in input_config.get('inputs', {}):
                 # This block is for when the input is defined directly under the component name
                 # e.g., global_inputs: - target_component: Channel2D, inputs: { Channel2D: { value: 10.0 } }
                 # In this case, var_name would be "Channel2D"
                 pass # The loop above already handles this logic correctly.

        print(f"Prepared global inputs: {list(final_global_inputs.keys())}")
        return final_global_inputs

    def build_simulation(self) -> tuple:
        """Builds the SimulationController and simulation parameters from the config."""
        controller = SimulationController()
        sim_params = self.config.get("simulation_parameters", {})
        dt = sim_params.get("dt_seconds", 1)
        num_steps = sim_params.get("num_steps", 1)

        for comp_config in self.config.get("components", []):
            controller.add_component(self._instantiate_component(comp_config, dt=dt))

        for conn in self.config.get("network", []):
            controller.connect(conn['from'], conn['to'])

        self._load_data_sources()
        self._run_areal_precipitation()
        self._run_preprocessing()

        global_inputs = self._prepare_global_inputs(num_steps)

        return controller, sim_params, global_inputs
