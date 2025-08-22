import sys
import os
import matplotlib.pyplot as plt
import numpy as np

# Adjust path to import from the root of the project
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(SCRIPT_DIR, '../..')))

from common.config_parser import ConfigParser
from preissmann_model.model import HydraulicModel

def run_and_plot():
    """
    Runs the hydraulic features example and plots the results.
    """
    config_file = os.path.join(SCRIPT_DIR, 'config.yaml')
    output_plot_file = os.path.join(SCRIPT_DIR, 'hydraulic_results_plot.png')

    print(f"--- Running Hydraulic Features Example from: {config_file} ---")

    # --- 1. Build and Run Simulation ---
    parser = ConfigParser(config_file)
    controller, sim_params, global_inputs = parser.build_simulation()

    num_steps = sim_params.get('num_steps', 1)
    # The main controller run method is a generator. We need to consume it to run the simulation.
    list(controller.run(num_steps=num_steps, dt=sim_params.get('dt_seconds'), global_inputs=global_inputs))

    print("\n--- Simulation Complete ---")

    # --- 2. Get and Process Results ---
    # Find the hydraulic model component to get its results
    hydraulic_model = None
    for component in controller.components.values():
        if isinstance(component, HydraulicModel):
            hydraulic_model = component
            break

    if hydraulic_model is None:
        print("Error: No HydraulicModel component found in the simulation.")
        return

    results = hydraulic_model.get_results()
    Z = results['Z'] # Shape: (num_steps, num_nodes)
    Q = results['Q'] # Shape: (num_steps, num_nodes)
    x_coords = results['x_coords']
    weir_node_index = 4 # As defined in the config

    # --- 3. Create Plot ---
    print("--- Generating Plots ---")
    fig, axes = plt.subplots(2, 1, figsize=(14, 12))

    # Plot 1: Water Surface Profile at the end of the simulation
    ax1 = axes[0]
    final_Z = Z[-1, :]
    ax1.plot(x_coords, final_Z, 'b-o', label='Water Surface Elevation')
    ax1.plot(x_coords, hydraulic_model.Z_bed, 'k-', label='Bed Elevation')
    # Plot weir crest
    weir_x = x_coords[weir_node_index]
    weir_crest = hydraulic_model.structures[0].crest_elevation
    ax1.plot([weir_x - 20, weir_x + 20], [weir_crest, weir_crest], 'r--', linewidth=2, label='Weir Crest')
    ax1.set_title(f"Water Surface Profile at End of Simulation (T={num_steps*sim_params['dt_seconds']/60} min)")
    ax1.set_xlabel("Distance along reach (m)")
    ax1.set_ylabel("Elevation (m)")
    ax1.legend()
    ax1.grid(True)

    # Plot 2: Hydrographs upstream and downstream of the weir
    ax2 = axes[1]
    time_steps = np.arange(num_steps) * sim_params['dt_seconds'] / 60 # Time in minutes
    ax2.plot(time_steps, Q[:, weir_node_index - 1], 'g-o', label=f'Upstream Q (Node {weir_node_index-1})')
    ax2.plot(time_steps, Q[:, weir_node_index], 'm-o', label=f'Downstream Q (Node {weir_node_index})')
    ax2.set_title("Discharge Hydrographs Around Weir")
    ax2.set_xlabel("Time (minutes)")
    ax2.set_ylabel("Discharge (m^3/s)")
    ax2.legend()
    ax2.grid(True)

    plt.tight_layout()
    plt.savefig(output_plot_file)
    print(f"Plot saved to: {output_plot_file}")

if __name__ == "__main__":
    run_and_plot()
