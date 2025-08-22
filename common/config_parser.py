import os
import yaml
import numpy as np
import pandas as pd
from .controller import SimulationController
from .junction import Junction

from hydro_model.model import HydrologicalModel
from hydro_model.runoff import SCSCurveNumberModule, SimpleRunoffModule, XinanjiangRunoffModule, HymodRunoffModule
from hydro_model.routing import SimpleRouting, MuskingumRouting, MuskingumCungeRouting
from hydro_model.areal_precipitation import ArealPrecipitation
from hydro_model.parameter_zone import ParameterZone

from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from preissmann_model.structures import Gate, Pump

from preprocessing.runoff_analysis import calculate_runoff_coefficient
from preprocessing.baseflow_separation import lyne_hollick_filter

class ConfigParser:
    """
    Parses a YAML configuration file to build and configure a SimulationController.
    """
    def __init__(self, config_filepath: str):
        self.filepath = config_filepath
        with open(self.filepath, 'r') as f:
            self.config = yaml.safe_load(f)
        self.config_dir = os.path.dirname(self.filepath)
        self.component_factory = self._build_factory()
        self.data_registry = {}

    def _build_factory(self):
        # (omitted for brevity - same as before)
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
        # (omitted for brevity - same as before)
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
        return comp_class(**comp_params)

    def _load_initial_data(self):
        """Loads all initial data sources from files into the data registry."""
        print("--- Loading Initial Data Sources ---")
        for name, config in self.config.get("global_inputs", {}).items():
            if 'file' in config:
                path = os.path.join(self.config_dir, config['file'])
                self.data_registry[name] = pd.read_csv(path, index_col=0, parse_dates=True)
                print(f"Loaded '{name}' from {config['file']}")
            elif 'values' in config:
                # For simplicity, this example assumes values are not used in preprocessing
                pass

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

        processed_df = areal_module.calculate_areal_rainfall(raw_rainfall_df, method, **params)
        self.data_registry[output_name] = processed_df
        print(f"Areal rainfall calculated using '{method}'. New data source '{output_name}' created.")

    def _run_preprocessing(self):
        """Runs all configured preprocessing steps."""
        config = self.config.get("preprocessing")
        if not config:
            return

        print("\n--- Running Preprocessing Steps ---")

        if 'runoff_coefficient' in config:
            print("\n[Preprocessing] Calculating Runoff Coefficient...")
            rc_conf = config['runoff_coefficient']
            rainfall_df = self.data_registry[rc_conf['rainfall_input']]
            flow_df = self.data_registry[rc_conf['flow_input']]

            # Assuming the dataframes might have multiple columns, we take the first one.
            # A more complex setup might specify column names.
            calculate_runoff_coefficient(
                rainfall_df.iloc[:, 0],
                flow_df.iloc[:, 0],
                rc_conf['catchment_area_km2']
            )

        if 'baseflow_separation' in config:
            print("\n[Preprocessing] Performing Baseflow Separation...")
            bs_conf = config['baseflow_separation']
            flow_df = self.data_registry[bs_conf['flow_input']]

            params = bs_conf.get('parameters', {})
            separated_df = lyne_hollick_filter(flow_df.iloc[:, 0], **params)

            # Add new data sources to the registry
            self.data_registry[bs_conf['output_baseflow']] = separated_df[['baseflow']]
            self.data_registry[bs_conf['output_quickflow']] = separated_df[['quick_flow']]
            print(f"Baseflow separation complete. New data sources created: '{bs_conf['output_baseflow']}', '{bs_conf['output_quickflow']}'")

    def build_simulation(self) -> tuple:
        """
        Builds the SimulationController and simulation parameters from the config.
        """
        controller = SimulationController()
        sim_params = self.config.get("simulation_parameters", {})
        dt = sim_params.get("dt_seconds")

        for comp_config in self.config.get("components", []):
            controller.add_component(self._instantiate_component(comp_config, dt=dt))
        for conn in self.config.get("network", []):
            controller.connect(conn['from'], conn['to'])

        # --- Data Loading and Preprocessing Pipeline ---
        self._load_initial_data()
        self._run_areal_precipitation()
        self._run_preprocessing()

        # --- Load final global inputs for the simulation ---
        print("\n--- Loading Global Inputs for Simulation ---")
        global_inputs = {}
        for name, data_df in self.data_registry.items():
            # Map data to components by matching column names to component names
            for col_name in data_df.columns:
                if str(col_name) in controller.components:
                    global_inputs[str(col_name)] = data_df[col_name].values
                    print(f"Mapped data from '{name}' (column: {col_name}) to component '{col_name}'.")

            # Also map data to components if the data source name matches the component name
            if name in controller.components:
                global_inputs[name] = data_df.iloc[:, 0].values
                print(f"Mapped data from '{name}' (first column) to component '{name}'.")

        # Also load from the 'values' keyword if present (for simple, non-timeseries inputs)
        for name, config in self.config.get("global_inputs", {}).items():
            if 'values' in config:
                global_inputs[name] = np.array(config['values'])
                print(f"Loaded values for '{name}'.")

        return controller, sim_params, global_inputs
