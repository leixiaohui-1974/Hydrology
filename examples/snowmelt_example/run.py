import sys
import os
import matplotlib.pyplot as plt
import pandas as pd

# Adjust path to import from the root of the project
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(SCRIPT_DIR, '../..')))

from common.config_parser import ConfigParser
from hydro_model.model import HydrologicalModel

def run_and_plot():
    """
    Runs the snowmelt example and plots the results.
    """
    config_file = os.path.join(SCRIPT_DIR, 'config.yaml')
    output_plot_file = os.path.join(SCRIPT_DIR, 'snowmelt_results_plot.png')

    print(f"--- Running Snowmelt Example from: {config_file} ---")

    # --- 1. Build and Run Simulation ---
    parser = ConfigParser(config_file)
    controller, sim_params, global_inputs = parser.build_simulation()

    num_steps = sim_params.get('num_steps', 1)
    list(controller.run(num_steps=num_steps, dt=sim_params.get('dt_seconds'), global_inputs=global_inputs))

    print("\n--- Simulation Complete ---")

    # --- 2. Get and Process Results ---
    model = controller.components["SnowyCatchment"]
    snow_results = model.snowmelt_module.get_results()
    hydro_results = model.get_results()

    # Load original data for plotting
    precip_df = pd.read_csv(os.path.join(SCRIPT_DIR, 'rainfall.csv'), index_col='date', parse_dates=True)
    temp_df = pd.read_csv(os.path.join(SCRIPT_DIR, 'temperature.csv'), index_col='date', parse_dates=True)

    # --- 3. Create Plot ---
    print("--- Generating Plots ---")
    fig, axes = plt.subplots(3, 1, figsize=(14, 15), sharex=True)

    # Plot 1: Inputs
    ax1 = axes[0]
    ax1.bar(precip_df.index, precip_df.iloc[:, 0], label='Precipitation (mm)', color='c')
    ax1.set_ylabel("Precipitation (mm)")
    ax1.set_title("Inputs and Outputs")
    ax1.grid(True, linestyle='--', alpha=0.6)

    ax1_twin = ax1.twinx()
    ax1_twin.plot(temp_df.index, temp_df.iloc[:, 0], 'r-o', label='Temperature (°C)', markersize=4)
    ax1_twin.set_ylabel("Temperature (°C)", color='r')

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1_twin.get_legend_handles_labels()
    ax1_twin.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    # Plot 2: Snowpack State
    ax2 = axes[1]
    ax2.plot(precip_df.index, snow_results['SWE'], 'b-o', label='Snow Water Equivalent (mm)', markersize=4)
    ax2_twin = ax2.twinx()
    ax2_twin.bar(precip_df.index, snow_results['Melt'], label='Snowmelt (mm)', color='g', alpha=0.7)
    ax2.set_ylabel("SWE (mm)", color='b')
    ax2_twin.set_ylabel("Melt (mm)", color='g')
    ax2.set_title("Snowpack Dynamics")
    ax2.grid(True, linestyle='--', alpha=0.6)
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_twin.get_legend_handles_labels()
    ax2_twin.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    # Plot 3: Outflow
    ax3 = axes[2]
    ax3.plot(precip_df.index, hydro_results['outflow'], 'k-o', label='Catchment Outflow', markersize=4)
    ax3.set_ylabel("Discharge (mm)")
    ax3.set_title("Simulated Runoff")
    ax3.legend(loc='upper left')
    ax3.grid(True, linestyle='--', alpha=0.6)
    ax3.set_xlabel("Date")

    plt.tight_layout()
    plt.savefig(output_plot_file)
    print(f"Plot saved to: {output_plot_file}")

if __name__ == "__main__":
    run_and_plot()
