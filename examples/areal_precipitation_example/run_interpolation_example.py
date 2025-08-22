import sys
import os
import matplotlib.pyplot as plt
import pandas as pd
import geopandas as gpd

# --- Get the absolute path of the script's directory ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# --- Adjust path to import from the root of the project ---
sys.path.insert(0, os.path.abspath(os.path.join(SCRIPT_DIR, '../..')))

from common.config_parser import ConfigParser

def run_and_plot():
    """
    Runs the areal precipitation example and plots the results.
    """
    # --- Construct absolute paths to files ---
    config_file = os.path.join(SCRIPT_DIR, 'config.yaml')
    rainfall_file = os.path.join(SCRIPT_DIR, 'rainfall.csv')
    shapefile_path = os.path.join(SCRIPT_DIR, 'subbasins_dissolved.shp')
    output_plot_file = os.path.join(SCRIPT_DIR, 'areal_rainfall_comparison.png')

    print(f"--- Running Areal Precipitation Example from: {config_file} ---")

    # --- 1. Build and Run Simulation ---
    parser = ConfigParser(config_file)
    controller, sim_params, global_inputs = parser.build_simulation()

    num_steps = sim_params.get('num_steps', 1)
    controller.run(num_steps=num_steps, dt=sim_params.get('dt_seconds'), global_inputs=global_inputs)
    print("\n--- Simulation Complete ---")

    # --- 2. Load Data for Plotting ---
    raw_rainfall_df = pd.read_csv(rainfall_file, index_col='date', parse_dates=True)
    subbasins_gdf = gpd.read_file(shapefile_path)

    # Get the subbasin IDs from the shapefile's index
    subbasin_ids = subbasins_gdf.index.tolist()

    # Extract the interpolated rainfall series from the processed inputs
    interpolated_series = {
        sid: pd.Series(global_inputs.get(sid), index=raw_rainfall_df.index) for sid in subbasin_ids
    }

    # --- 3. Create Plot ---
    print("--- Generating Comparison Plot ---")
    fig, axes = plt.subplots(len(subbasin_ids), 1, figsize=(12, 6 * len(subbasin_ids)), sharex=True, squeeze=False)
    axes = axes.flatten()

    for i, sid in enumerate(subbasin_ids):
        ax = axes[i]
        ax.set_title(f"Rainfall for Sub-basin '{sid}'")

        # Plot raw gauge data
        for gauge_col in raw_rainfall_df.columns:
            ax.plot(raw_rainfall_df.index, raw_rainfall_df[gauge_col], label=f'Gauge: {gauge_col}', alpha=0.5, linestyle='--')

        # Plot interpolated data
        if sid in interpolated_series and interpolated_series[sid] is not None and not interpolated_series[sid].empty:
            ax.plot(interpolated_series[sid].index, interpolated_series[sid], label=f'Interpolated for Sub-basin {sid}', color='k', linewidth=2)

        ax.set_ylabel("Rainfall (mm)")
        ax.legend()
        ax.grid(True)

    axes[-1].set_xlabel("Date")
    plt.tight_layout()
    plt.savefig(output_plot_file)
    print(f"Plot saved to: {output_plot_file}")

if __name__ == "__main__":
    run_and_plot()
