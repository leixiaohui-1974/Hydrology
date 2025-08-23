"""
Main Python script for the Eel-based GUI.
"""
import eel
import yaml
import csv
import json
import numpy as np
import easygui
import queue
import threading
from common.config_parser import ConfigParser
from .config_generator import generate_config_from_gui_data
from services.data_processing import run_preprocessing_preview, generate_mesh_from_params

# --- Backend State Management ---
class SimulationState:
    """
    A simple class to encapsulate the state of the simulation.
    This avoids using global variables and makes the state management
    more explicit and robust.
    """
    def __init__(self):
        self.controller = None

# Create a single instance of the state class to be used throughout the application.
sim_state = SimulationState()


# Initialize Eel, specifying the web folder
eel.init('web')

# Expose the data processing services to the frontend
eel.expose(run_preprocessing_preview, 'run_preprocessing_preview')
eel.expose(generate_mesh_from_params, 'generate_mesh_from_params')


@eel.expose
def update_live_data(data_packet):
    """A simple pass-through function to send data to the JS front-end."""
    # This function is called by the data_listener_thread, not directly by JS.
    # It pushes data to the connected JS client.
    eel.update_live_data(data_packet)

def data_listener_thread(q):
    """
    Awaits data from the simulation queue and forwards it to the GUI.
    This runs in a separate thread.
    """
    print("Data listener thread started.")
    while True:
        try:
            # Block until an item is available
            data_packet = q.get()

            # The sentinel value 'None' signals the end of the simulation
            if data_packet is None:
                print("Sentinel received, terminating listener thread.")
                break

            # Send the data to the front-end
            update_live_data(data_packet)

        except Exception as e:
            print(f"Error in listener thread: {e}")
            break
    print("Data listener thread finished.")


@eel.expose
def start_simulation(gui_data):
    """
    Endpoint called by the frontend to start a simulation.

    This function sets up the necessary infrastructure for a non-blocking
    simulation with live feedback to the GUI.

    Workflow:
    1. A queue (`data_queue`) is created to pass live data from the
       simulation thread to a listener thread.
    2. A separate `data_listener_thread` is started. It waits for data on the
       queue and uses Eel to push it to the frontend. This must be a real
       Python thread because `queue.get()` is a blocking operation.
    3. The main simulation logic (`simulation_thread_logic`) is started in a
       background greenlet using `eel.spawn()`. This allows the GUI to remain
       responsive while the simulation runs.

    Args:
        gui_data (dict): The entire state of the frontend application, including
                         the network layout, component properties, and data sources.

    Returns:
        str: A message indicating that the simulation has started.
    """
    print("Received request to start simulation with dynamic GUI data.")

    # 1. Create a queue for live data communication.
    data_queue = queue.Queue()

    # 2. Start the data listener thread.
    # This must be a real thread, not an Eel greenlet, because q.get() is blocking.
    listener = threading.Thread(target=data_listener_thread, args=(data_queue,))
    listener.daemon = True # Allows the main program to exit even if this thread is running.
    listener.start()

    # 3. Start the simulation in a background greenlet.
    # We pass the raw gui_data; translation to a config dict happens inside the thread.
    eel.spawn(simulation_thread_logic, data_queue, gui_data)

    print("Simulation and listener threads started.")
    return "Simulation started."

def simulation_thread_logic(q, gui_data):
    """The actual simulation logic, run in a separate greenlet."""
    try:
        # Translate monitored components from nodeId to component name
        monitored_components_by_id = gui_data.get("monitored_components", {})
        nodes_map = gui_data.get("nodes", {})
        monitored_components_by_name = {
            nodes_map[node_id]['name']: variables
            for node_id, variables in monitored_components_by_id.items()
            if node_id in nodes_map
        }
        print(f"DEBUG: Translated monitored components to: {monitored_components_by_name}")

        config_dict = generate_config_from_gui_data(gui_data)
        # Pass the raw nodes dictionary to the parser for link resolution
        config_dict['nodes'] = gui_data.get('nodes', {})
        parser = ConfigParser(config_dict, base_path='.')
        controller, sim_params, global_inputs = parser.build_simulation()
        sim_state.controller = controller

        dt = sim_params.get('dt_seconds', 60)
        num_steps = sim_params.get('num_steps', 1)

        # The run method is now a generator that we iterate through
        # It will put data into the queue as it runs
        for status in controller.run(num_steps, dt, global_inputs, monitored_components=monitored_components_by_name, data_queue=q):
            eel.update_status(status)

        # --- After simulation, collect results from all components ---
        print("--- Collecting final results from components ---")
        for name, component in controller.components.items():
            if hasattr(component, 'get_results'):
                try:
                    controller.results[name] = component.get_results()
                    print(f"Collected results for component: {name}")
                except Exception as e:
                    print(f"Could not get results for component {name}: {e}")

        sim_state.controller.results = controller.results

        eel.simulation_finished({"message": "Simulation completed successfully!"})
    except Exception as e:
        print(f"An error occurred during simulation: {e}")
        # Put sentinel in queue to stop listener thread on error
        q.put(None)
        eel.simulation_finished({"error": str(e)})

@eel.expose
def get_results():
    """
    Endpoint called by the frontend to retrieve all simulation results.

    This function is called after the `simulation_finished` event is received
    by the frontend. It processes the results stored in the global
    `last_run_controller` and sends them back in a JSON-serializable format.

    Key Processing Steps:
    1.  **2D Model Velocity Calculation:** For 2D model results, it calculates
        the velocity components `u` and `v` from the momentum (`uh`, `vh`) and
        water depth (`h`) arrays. It handles division by zero to avoid errors
        in dry cells.
    2.  **NumPy to List Conversion:** It recursively iterates through the results
        dictionary and converts all NumPy arrays into nested lists. This is
        crucial because JSON does not natively support NumPy arrays.

    Returns:
        dict or None: A dictionary containing the processed results for all
                      components, ready for JSON serialization. Returns `None`
                      if no results are available.
    """
    if not sim_state.controller or not sim_state.controller.results:
        print("No results to send.")
        return None

    print("Sending results to front-end...")
    serializable_results = {}
    for comp_name, data in sim_state.controller.results.items():
        # For 2D models, calculate velocity components before sending to frontend
        if 'h' in data and 'uh' in data and 'vh' in data:
            h = np.array(data['h'])
            uh = np.array(data['uh'])
            vh = np.array(data['vh'])

            # Safely calculate u = uh/h and v = vh/h, avoiding division by zero
            u = np.divide(uh, h, out=np.zeros_like(uh), where=h > 1e-6)
            v = np.divide(vh, h, out=np.zeros_like(vh), where=h > 1e-6)

            # Add the new velocity arrays to the data dictionary
            data['u'] = u
            data['v'] = v

        # Convert all NumPy arrays in the results to lists for JSON compatibility
        serializable_results[comp_name] = {}
        for var_name, time_series in data.items():
            if isinstance(time_series, np.ndarray):
                 serializable_results[comp_name][var_name] = time_series.tolist()
            elif isinstance(time_series, list) and len(time_series) > 0 and isinstance(time_series[0], np.ndarray):
                serializable_results[comp_name][var_name] = [arr.tolist() for arr in time_series]
            else:
                serializable_results[comp_name][var_name] = time_series

    return serializable_results


@eel.expose
def open_file_dialog():
    """
    Opens a native file dialog to select a file.
    """
    try:
        file_path = easygui.fileopenbox()
        return file_path
    except Exception as e:
        # This can happen in environments without a display server
        print(f"Could not open file dialog: {e}")
        # In a real app, you might return a specific error message
        # or handle it more gracefully. For now, we return None.
        return None



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
