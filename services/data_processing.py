"""
This module contains backend services for data processing tasks,
such as running preprocessing steps or generating mesh files.
"""
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.spatial import Delaunay
from preprocessing.baseflow_separation import lyne_hollick_filter

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

def generate_mesh_from_params(params):
    """
    Generates a 2D mesh from parameters and saves it to a temporary file.
    """
    try:
        print(f"Generating mesh with params: {params}")

        # Ensure temp directory exists
        temp_dir = 'temp'
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        output_path = os.path.join(temp_dir, params['output_filename'])

        # --- Logic adapted from utils/create_channel_mesh.py ---
        length = params.get('length', 1000)
        width = params.get('width', 100)
        num_x = params.get('num_x', 21)
        num_y = params.get('num_y', 11)

        x = np.linspace(0, length, num_x)
        y = np.linspace(0, width, num_y)
        xv, yv = np.meshgrid(x, y)
        points = np.vstack([xv.ravel(), yv.ravel()]).T

        tri = Delaunay(points)
        triangles = tri.simplices

        mesh_data = {
            "points": points.tolist(),
            "triangles": triangles.tolist()
        }
        with open(output_path, 'w') as f:
            json.dump(mesh_data, f, indent=4)

        print(f"Mesh saved to: {output_path}")
        return {"mesh_path": output_path}

    except Exception as e:
        print(f"Error during mesh generation: {e}")
        return {"error": str(e)}
