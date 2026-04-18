import geopandas as gpd
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
shapefile_path = os.path.join(SCRIPT_DIR, 'subbasins.shp')
output_shapefile_path = os.path.join(SCRIPT_DIR, 'subbasins_dissolved.shp')

print(f"--- Dissolving Shapefile: {shapefile_path} ---")
try:
    gdf = gpd.read_file(shapefile_path)

    # Dissolve the geometries by the 'zone_id' column
    # The aggregation function will take the first value for other columns, which is fine for this example.
    dissolved_gdf = gdf.dissolve(by='zone_id', aggfunc='first')

    # Save the dissolved shapefile
    dissolved_gdf.to_file(output_shapefile_path)

    print(f"Shapefile successfully dissolved and saved to: {output_shapefile_path}")
    print("\nNew Dissolved Shapefile Info:")
    print(dissolved_gdf.info())
    print(dissolved_gdf)

except Exception as e:
    print(f"\nAn error occurred: {e}")
