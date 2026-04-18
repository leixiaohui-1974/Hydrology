import sys
import os
import matplotlib.pyplot as plt
import numpy as np

# Adjust path to import from the root of the project
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(SCRIPT_DIR, '../..')))

from common.config_parser import ConfigParser
from model_2d.model import Model2D

def run_and_plot():
    """
    Runs the 2D hydraulic model example and plots the results.
    """
    config_file = os.path.join(SCRIPT_DIR, 'config.yaml')
    output_plot_file = os.path.join(SCRIPT_DIR, '2d_results_plot.png')

    print(f"--- Running 2D Hydraulic Model Example from: {config_file} ---")

    # --- 1. Build and Run Simulation ---
    parser = ConfigParser(config_file)
    controller, sim_params, global_inputs = parser.build_simulation()

    num_steps = sim_params.get('num_steps', 1)
    list(controller.run(num_steps=num_steps, dt=sim_params.get('dt_seconds'), global_inputs=global_inputs))

    print("\n--- Simulation Complete ---")

    # --- 2. Get and Process Results ---
    model_2d = controller.components["Channel2D"]
    results = model_2d.get_results()

    h = results['h'][-1, :] # Water depth at the final timestep
    points = results['points']
    triangles = results['triangles']

    # --- 3. Create Plot ---
    print("--- Generating Plot ---")
    fig, ax = plt.subplots(figsize=(12, 5))

    # Use tripcolor for plotting data on an unstructured triangular grid
    tpc = ax.tripcolor(points[:, 0], points[:, 1], triangles, facecolors=h, cmap='viridis',
                       edgecolors='k', linewidth=0.2)

    fig.colorbar(tpc, label='Water Depth (m)')
    ax.set_title(f"2D Model Water Depth at End of Simulation")
    ax.set_xlabel("X-coordinate (m)")
    ax.set_ylabel("Y-coordinate (m)")
    ax.set_aspect('equal', 'box')

    plt.tight_layout()
    plt.savefig(output_plot_file)
    print(f"Plot saved to: {output_plot_file}")

if __name__ == "__main__":
    run_and_plot()
