import os
import yaml
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
            "Gate": Gate, "Pump": Pump, "Weir": Weir
        }

    def _instantiate_component(self, comp_config: dict, dt: float = None):
        comp_type_str = comp_config.get("type")
        comp_params = comp_config.get("parameters", {})
        if not comp_type_str: raise ValueError("Component config must have a 'type'.")
        comp_class = self.component_factory.get(comp_type_str)
        if not comp_class: raise ValueError(f"Unknown component type: {comp_type_str}")

        for key, value in comp_params.items():
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

        return comp_class(**comp_params)

    def _load_data_sources(self):
        """Loads all data sources from files or DB into the data registry."""
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
        # (This method remains largely the same, just using the new data registry)
        pass # Will be re-implemented if needed, for now assume data is ready

    def _run_preprocessing(self):
        # (This method also remains largely the same)
        pass # Will be re-implemented if needed

    def _prepare_global_inputs(self, num_steps):
        """
        Prepares the final global_inputs dictionary for the SimulationController.
        The controller expects a flat dictionary: {variable_name: numpy_array}.
        """
        print("\n--- Preparing Global Inputs for Simulation ---")
        final_global_inputs = {}

        input_configs = self.config.get("global_inputs", [])

        for input_config in input_configs:
            # The target_component is now just for clarity in the config, the controller
            # distributes based on the variable name inside the component's step method.
            comp_name = input_config['target_component']

            for var_name, source_info in input_config['inputs'].items():
                if var_name in final_global_inputs:
                    print(f"Warning: Global input '{var_name}' is being overwritten. This can happen if multiple components require the same input like 'pet'. The last one defined in the config will be used.")

                if 'from_source' in source_info:
                    source_name = source_info['from_source']
                    col_name = source_info['from_column']

                    if source_name not in self.data_registry:
                        raise ValueError(f"Data source '{source_name}' not found in data_registry.")
                    if col_name not in self.data_registry[source_name].columns:
                        raise ValueError(f"Column '{col_name}' not found in data source '{source_name}'.")

                    final_global_inputs[var_name] = self.data_registry[source_name][col_name].to_numpy()

                elif 'value' in source_info:
                    constant_value = source_info['value']
                    final_global_inputs[var_name] = np.full(num_steps, constant_value)

        print(f"Prepared global inputs: {list(final_global_inputs.keys())}")
        return final_global_inputs

    def build_simulation(self) -> tuple:
        """
        Builds the SimulationController and simulation parameters from the config.
        """
        controller = SimulationController()
        sim_params = self.config.get("simulation_parameters", {})
        dt = sim_params.get("dt_seconds")
        num_steps = sim_params.get("num_steps", 1)

        # 1. Build all components
        for comp_config in self.config.get("components", []):
            controller.add_component(self._instantiate_component(comp_config, dt=dt))

        # 2. Connect the network
        for conn in self.config.get("network", []):
            controller.connect(conn['from'], conn['to'])

        # 3. Data Loading and Preprocessing Pipeline
        self._load_data_sources()
        # self._run_areal_precipitation() # These would need to be updated for the new structure
        # self._run_preprocessing()

        # 4. Prepare final inputs for the simulation controller
        global_inputs = self._prepare_global_inputs(num_steps)

        return controller, sim_params, global_inputs
