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

def main():
    # File paths
    subbasins_file = "results/subbasins_with_zones.shp"
    dem_file = "../gis_data/dem.tif"
    output_plot = "results/parameter_zones_map.png"

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
