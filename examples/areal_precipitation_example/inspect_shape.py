import geopandas as gpd
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
shapefile_path = os.path.join(SCRIPT_DIR, 'subbasins_dissolved.shp')

print(f"--- Inspecting Shapefile: {shapefile_path} ---")
try:
    gdf = gpd.read_file(shapefile_path)
    print("Shapefile inspection successful.")
    print("\nColumns:", gdf.columns)
    print("\nData Head:")
    print(gdf.head())
    print("\nBounds of the entire layer:")
    print(gdf.total_bounds)
except Exception as e:
    print(f"\nAn error occurred: {e}")
