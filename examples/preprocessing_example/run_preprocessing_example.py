import sys
import os
import matplotlib.pyplot as plt
import pandas as pd

# Adjust path to import from the root of the project
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(SCRIPT_DIR, '../..')))

from common.config_parser import ConfigParser

def run_and_plot():
    """
    Runs the preprocessing example and plots the baseflow separation results.
    """
    config_file = os.path.join(SCRIPT_DIR, 'config.yaml')
    output_plot_file = os.path.join(SCRIPT_DIR, 'baseflow_separation_plot.png')

    print(f"--- Running Preprocessing Example from: {config_file} ---")

    # --- 1. Build Simulation (which triggers preprocessing) ---
    parser = ConfigParser(config_file)
    parser.build_simulation() # This runs the entire preprocessing pipeline

    print("\n--- Preprocessing Complete ---")

    # --- 2. Load Data for Plotting ---
    # The results of the preprocessing steps are stored in the parser's data_registry.
    # We can access them directly for plotting and verification.
    original_flow = parser.data_registry.get('observed_flow')
    baseflow = parser.data_registry.get('flow_base')
    quickflow = parser.data_registry.get('flow_quick')

    if original_flow is None or baseflow is None:
        print("\nError: Flow data not found in parser's data registry. Cannot generate plot.")
        return

    # --- 3. Create Plot ---
    print("\n--- Generating Baseflow Separation Plot ---")
    plt.figure(figsize=(14, 8))

    plt.plot(original_flow.index, original_flow.iloc[:, 0], label='Total Streamflow', color='k', linewidth=2)
    plt.plot(baseflow.index, baseflow.iloc[:, 0], label='Separated Baseflow', color='b', linestyle='--')

    # Fill the area for quick flow
    plt.fill_between(original_flow.index, baseflow.iloc[:, 0], original_flow.iloc[:, 0],
                     where=(original_flow.iloc[:, 0] > baseflow.iloc[:, 0]),
                     color='lightblue', alpha=0.6, label='Quick Flow (Direct Runoff)')

    plt.title("Baseflow Separation using Lyne-Hollick Filter")
    plt.xlabel("Date")
    plt.ylabel("Discharge (m^3/s)")
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.savefig(output_plot_file)
    print(f"Plot saved to: {output_plot_file}")

if __name__ == "__main__":
    run_and_plot()
