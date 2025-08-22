import sys
import os
import matplotlib.pyplot as plt
import pandas as pd

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.config_parser import ConfigParser

def plot_uncertainty(config_file: str):
    """
    Runs the data pipeline from a config file and plots the Kriging variance.
    """
    if not os.path.exists(config_file):
        print(f"Error: Config file not found at '{config_file}'")
        return

    output_dir = os.path.dirname(config_file)
    output_plot_file = os.path.join(output_dir, 'interpolation_variance_plot.png')

    print(f"--- Running Analysis from: {config_file} ---")

    # --- 1. Build Simulation to populate the data registry ---
    parser = ConfigParser(config_file)
    # We don't need the outputs, we just need to run the pipeline
    # to populate the parser's internal data_registry.
    parser.build_simulation()

    # --- 2. Find and extract variance data ---
    variance_data = {}
    for name, data_df in parser.data_registry.items():
        if name.endswith('_variance'):
            variance_data[name] = data_df

    if not variance_data:
        print("No variance data found. Did you run an analysis with the 'kriging' method?")
        return

    # --- 3. Create Plot ---
    print("--- Generating Variance Plot ---")

    # For simplicity, we'll merge all variance data into one plot
    all_variance_df = pd.concat(variance_data.values(), axis=1)

    plt.figure(figsize=(14, 8))

    for col in all_variance_df.columns:
        plt.plot(all_variance_df.index, all_variance_df[col], label=f"Sub-basin: {col}")

    plt.title("Kriging Interpolation Variance Over Time")
    plt.xlabel("Date")
    plt.ylabel("Mean Estimation Variance")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.savefig(output_plot_file)
    print(f"Plot saved to: {output_plot_file}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 analysis/plot_interpolation_uncertainty.py <path_to_config.yaml>")
    else:
        plot_uncertainty(sys.argv[1])
