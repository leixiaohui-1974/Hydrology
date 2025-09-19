import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import geopandas as gpd
import matplotlib.pyplot as plt
import rasterio
from rasterio.plot import show as show_raster

from examples.generate_parameter_zones import _create_fallback_zones

def main():
    # File paths
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)

    subbasins_file = os.path.join(results_dir, "subbasins_with_zones.shp")
    dem_file = os.path.join(project_root, "gis_data", "dem.tif")
    output_plot = os.path.join(results_dir, "parameter_zones_map.png")

    if not os.path.exists(subbasins_file):
        _create_fallback_zones(subbasins_file)

    # Load the data
    subbasins_gdf = gpd.read_file(subbasins_file)
    dem_raster = rasterio.open(dem_file)

    # Create the plot
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))

    # Plot the DEM as a grayscale background
    show_raster(dem_raster, ax=ax, cmap='gray', title="Sub-basins with Parameter Zones")

    # Plot the sub-basins, colored by their unique zone_id
    # Use a categorical colormap
    subbasins_gdf.plot(
        column='zone_id',
        ax=ax,
        legend=True,
        legend_kwds={'title': "Parameter Zones", 'bbox_to_anchor': (1.25, 1)},
        cmap='tab20', # A good colormap for categorical data
        alpha=0.7 # Make polygons semi-transparent to see DEM below
    )

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    plt.tight_layout()

    # Save the plot
    os.makedirs(os.path.dirname(output_plot), exist_ok=True)
    plt.savefig(output_plot)
    print(f"Verification map saved to {output_plot}")

if __name__ == "__main__":
    main()
