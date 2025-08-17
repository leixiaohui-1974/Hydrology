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

@eel.expose
def start_simulation(config_path):
    """
    Loads a config file and runs the simulation, streaming updates to the front-end.
    """
    global last_run_controller
    print(f"Received request to start simulation with config: {config_path}")

    def simulation_thread():
        """The actual simulation logic, run in a separate greenlet."""
        global last_run_controller
        try:
            parser = ConfigParser(config_path)
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
