import os
import geopandas as gpd
from whitebox.whitebox_tools import WhiteboxTools

def main():
    wbt = WhiteboxTools()
    wbt.verbose = True

    # --- Setup Directories and Paths ---
    work_dir = os.path.abspath(os.path.dirname(__file__))
    temp_dir = os.path.join(work_dir, "temp_gis")
    results_dir = os.path.join(work_dir, "results")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    # --- Input Files ---
    dem_file = os.path.join(work_dir, "../gis_data/dem.tif")

    # --- Intermediate Files ---
    filled_dem = os.path.join(temp_dir, "filled_dem.tif")
    d8_pointer = os.path.join(temp_dir, "d8_pointer.tif")
    flow_acc = os.path.join(temp_dir, "flow_acc.tif")
    streams = os.path.join(temp_dir, "streams.tif")
    subbasins_raster = os.path.join(temp_dir, "subbasins.tif")
    subbasins_vector_temp = os.path.join(temp_dir, "subbasins_temp.shp")

    # --- Final Output ---
    subbasins_with_zones_shp = os.path.join(results_dir, "subbasins_with_zones.shp")

    # --- 1. DEM Pre-processing ---
    print("Step 1: Pre-processing DEM...")
    wbt.fill_depressions(dem_file, filled_dem)
    wbt.d8_pointer(filled_dem, d8_pointer)
    wbt.d8_flow_accumulation(filled_dem, flow_acc, out_type='cells')

    # --- 2. Delineate Sub-basins ---
    print("Step 2: Delineating individual sub-basins...")
    wbt.extract_streams(flow_acc, streams, threshold=100.0, zero_background=True)
    wbt.subbasins(d8_pointer, streams, subbasins_raster)
    wbt.raster_to_vector_polygons(subbasins_raster, subbasins_vector_temp)

    # --- 3. Assign zones based on an assumption ---
    print("\n--- Step 3: Assigning Parameter Zones ---")
    gdf = gpd.read_file(subbasins_vector_temp)
    print(f"Found {len(gdf)} sub-basins. Grouping them into two zones.")

    # Assumption: Group sub-basins into two zones based on their VALUE.
    # This is an arbitrary grouping to satisfy the user's request for an example.
    # Zone 1 will be the upper catchments, Zone 2 will be the lower ones.
    zone_map = {
        7.0: 'zone1',
        1.0: 'zone1',
        2.0: 'zone1',
        6.0: 'zone2',
        3.0: 'zone2',
        5.0: 'zone2',
        4.0: 'zone2'
    }

    gdf['zone_id'] = gdf['VALUE'].map(zone_map)

    # Check if any zones are unassigned
    if gdf['zone_id'].isnull().any():
        print("Warning: Some sub-basins were not assigned to a zone.")
        print(gdf[gdf['zone_id'].isnull()])
        gdf['zone_id'] = gdf['zone_id'].fillna('unassigned')

    print("Zone assignment complete:")
    print(gdf[['VALUE', 'zone_id']].head())

    # --- 4. Save final output ---
    gdf.to_file(subbasins_with_zones_shp, driver='ESRI Shapefile')
    print(f"\nProcessing complete. Final sub-basins with zones saved to: {subbasins_with_zones_shp}")


if __name__ == "__main__":
    main()
