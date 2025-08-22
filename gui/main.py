"""
Main Python script for the Eel-based GUI.
"""
import eel
import yaml
import csv
import numpy as np
from common.config_parser import ConfigParser

# --- Global state for the backend ---
# This is a simple way to keep track of the controller after a run.
# A more robust application might use a dedicated state management class.
last_run_controller = None

# Initialize Eel, specifying the web folder
eel.init('web')

def _generate_config_dict(gui_data):
    """
    Translates the data structure from the GUI into a YAML-like dictionary
    that the ConfigParser can understand.
    """
    print("DEBUG: Generating config from GUI data:", gui_data)

    config = {
        "simulation_parameters": gui_data.get("sim_params", {}),
        "components": [],
        "network": [],
        "global_inputs": gui_data.get("global_inputs", {})
    }

    # This function needs to be more sophisticated to handle nested components
    # like structures within a HydraulicModel.

    # First pass: create all top-level components
    component_map = {} # temp map from name to component config dict
    structures_to_place = []

    for node_id, node_data in gui_data.get("nodes", {}).items():
        # A simple convention: structures are not top-level components
        is_structure = node_data["type"] in ["Gate", "Pump", "Weir"]

        if not is_structure:
            component_config = {
                "name": node_data["name"],
                "type": node_data["type"],
                "parameters": node_data["params"]
            }
            # Ensure structures list exists for hydraulic models
            if node_data["type"] == "HydraulicModel":
                component_config["parameters"]["structures"] = []

            config["components"].append(component_config)
            component_map[node_data["name"]] = component_config
        else:
            structures_to_place.append(node_data)

    # Second pass: place structures into their parents
    for struct_data in structures_to_place:
        parent_name = struct_data["params"].pop("parent_reach", None)
        if parent_name and parent_name in component_map:
            # This is a sub-component, add it to the parent's parameters
            parent_component_config = component_map[parent_name]
            structure_config = {
                "name": struct_data["name"],
                "type": struct_data["type"],
                "parameters": struct_data["params"]
            }
            parent_component_config["parameters"]["structures"].append(structure_config)
        else:
            # It's a top-level component after all, or parent not found
             print(f"Warning: Could not place structure '{struct_data['name']}'. Parent reach '{parent_name}' not found.")


    # Format network connections
    for conn in gui_data.get("connections", []):
        from_name = gui_data["nodes"][conn["from"]]["name"]
        to_name = gui_data["nodes"][conn["to"]]["name"]
        config["network"].append({"from": from_name, "to": to_name})

    # Format data source configurations
    data_sources_config = gui_data.get("data_sources", {})
    if data_sources_config.get("type") == "interpolated":
        config["areal_precipitation"] = data_sources_config.get("areal_precip_config", {})

    if "preprocessing" in data_sources_config:
        config["preprocessing"] = data_sources_config.get("preprocessing", {})

    print("DEBUG: Generated config dict:", config)
    return config

@eel.expose
def start_simulation(gui_data):
    """
    Generates a config from the GUI data and runs the simulation.
    """
    global last_run_controller
    print("Received request to start simulation with dynamic GUI data.")

    def simulation_thread():
        """The actual simulation logic, run in a separate greenlet."""
        global last_run_controller
        try:
            # Generate the config dictionary from the GUI data
            config_dict = _generate_config_dict(gui_data)

            # Initialize the parser with the dictionary instead of a file path
            # We need to provide a base_path for resolving relative file paths
            # in the config (e.g., for global_inputs). Assume project root.
            parser = ConfigParser(config_dict, base_path='.')

            controller, sim_params, global_inputs = parser.build_simulation()
            last_run_controller = controller # Store controller for later access

            dt = sim_params.get('dt_seconds', 60)
            num_steps = sim_params.get('num_steps', 1)

            for status in controller.run(num_steps, dt, global_inputs):
                eel.update_status(status)

            eel.simulation_finished({"message": "Simulation completed successfully!"})
        except Exception as e:
            print(f"An error occurred during simulation: {e}")
            eel.simulation_finished({"error": str(e)})

    eel.spawn(simulation_thread)
    print("Simulation thread spawned.")
    return "Simulation started."

@eel.expose
def get_results():
    """
    Returns the results from the last simulation run to the front-end.
    """
    global last_run_controller
    if not last_run_controller or not last_run_controller.results:
        print("No results to send.")
        return None

    print("Sending results to front-end...")
    # The results dictionary can contain NumPy arrays, which are not directly
    # JSON serializable by default in some setups. Convert them to lists.
    serializable_results = {}
    for comp_name, data in last_run_controller.results.items():
        serializable_results[comp_name] = {}
        for var_name, time_series in data.items():
            if isinstance(time_series[0], np.ndarray):
                serializable_results[comp_name][var_name] = [arr.tolist() for arr in time_series]
            else:
                serializable_results[comp_name][var_name] = time_series

    return serializable_results


import os
import pandas as pd
import matplotlib.pyplot as plt
from preprocessing.baseflow_separation import lyne_hollick_filter

@eel.expose
def run_preprocessing_preview(config):
    """
    Runs a preprocessing step and generates a preview plot.
    """
    print(f"Received preprocessing preview request with config: {config}")
    try:
        # For now, we only handle baseflow separation
        if 'baseflow' in config:
            bs_conf = config['baseflow']
            flow_file = bs_conf['flow_data_path']
            alpha = bs_conf['alpha']

            # Assume file path is relative to project root
            if not os.path.exists(flow_file):
                return {"error": f"Data file not found: {flow_file}"}

            flow_series = pd.read_csv(flow_file, index_col=0, parse_dates=True).iloc[:, 0]

            # Run the separation
            separated_df = lyne_hollick_filter(flow_series, alpha=alpha)

            # Generate the plot
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(separated_df.index, separated_df['total_flow'], label='Total Flow', color='k')
            ax.plot(separated_df.index, separated_df['baseflow'], label='Baseflow', color='b', linestyle='--')
            ax.fill_between(separated_df.index, separated_df['baseflow'], separated_df['total_flow'], color='lightblue', alpha=0.6)
            ax.legend()
            ax.grid(True)
            ax.set_title("Baseflow Separation Preview")
            ax.set_xlabel("Date")
            ax.set_ylabel("Discharge")
            plt.tight_layout()

            # Save plot to a temporary file in the web directory
            # Use a timestamp to avoid browser caching issues
            plot_filename = f"preview_plot_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}.png"
            plot_path = os.path.join('web', plot_filename)
            plt.savefig(plot_path)
            plt.close(fig)

            print(f"Generated preview plot: {plot_path}")
            return {"plot_path": plot_filename} # Return relative path for the web folder

    except Exception as e:
        print(f"An error occurred during preprocessing preview: {e}")
        return {"error": str(e)}


def main():
    """
    Starts the Eel application.
    """
    print("Starting GUI...")
    try:
        eel.start('index.html', size=(1280, 800))
    except (SystemExit, MemoryError, KeyboardInterrupt):
        print("GUI closed.")

if __name__ == "__main__":
    main()
