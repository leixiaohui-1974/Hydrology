import os
import geopandas as gpd
from shapely.geometry import Point
from whitebox.whitebox_tools import WhiteboxTools

def main():
    wbt = WhiteboxTools()
    wbt.verbose = True

    # --- Setup Directories and Paths ---
    work_dir = os.path.abspath(os.getcwd())
    temp_dir = os.path.join(work_dir, "temp_gis")
    results_dir = os.path.join(work_dir, "results")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    # --- Input Files ---
    dem_file = os.path.join(work_dir, "gis_data/dem.tif")
    land_use_file = os.path.join(work_dir, "gis_data/land_use.shp")
    soil_file = os.path.join(work_dir, "gis_data/soil.shp")

    # --- Intermediate Files ---
    filled_dem = os.path.join(temp_dir, "filled_dem.tif")
    d8_pointer = os.path.join(temp_dir, "d8_pointer.tif")
    flow_acc = os.path.join(temp_dir, "flow_acc.tif") # D8 Flow Accumulation
    streams = os.path.join(temp_dir, "streams.tif")
    subbasins_raster = os.path.join(temp_dir, "subbasins.tif")

    # --- Final Output ---
    subbasins_vector = os.path.join(results_dir, "subbasins_with_zones.shp")

    # --- 1. DEM Pre-processing ---
    print("Step 1: Pre-processing DEM...")
    wbt.fill_depressions(dem_file, filled_dem)
    wbt.d8_pointer(filled_dem, d8_pointer)
    wbt.d8_flow_accumulation(filled_dem, flow_acc, out_type='cells')

    # --- 2. Stream and Sub-basin Delineation ---
    print("Step 2: Extracting streams and delineating sub-basins...")
    wbt.extract_streams(flow_acc, streams, threshold=500.0, zero_background=True)
    wbt.subbasins(d8_pointer, streams, subbasins_raster)

    # --- 3. Convert Sub-basins to Vector ---
    print("Step 3: Converting sub-basin raster to vector polygons...")
    wbt.raster_to_vector_polygons(subbasins_raster, subbasins_vector)

    # --- 4. Perform Zoning using Geopandas ---
    print("Step 4: Assigning parameter zones based on overlay...")
    subbasins_gdf = gpd.read_file(subbasins_vector)
    land_use_gdf = gpd.read_file(land_use_file)
    soil_gdf = gpd.read_file(soil_file)

    # Re-project to a projected CRS for accurate area calculations
    projected_crs = "EPSG:3857"
    subbasins_proj = subbasins_gdf.to_crs(projected_crs)
    land_use_proj = land_use_gdf.to_crs(projected_crs)
    soil_proj = soil_gdf.to_crs(projected_crs)

    # Calculate dominant land use
    overlay_lu = gpd.overlay(subbasins_proj, land_use_proj, how='intersection')
    overlay_lu['area'] = overlay_lu.geometry.area
    dominant_lu = overlay_lu.loc[overlay_lu.groupby('VALUE')['area'].idxmax()]
    dominant_lu = dominant_lu.set_index('VALUE')[['land_use']]

    # Calculate dominant soil type
    overlay_soil = gpd.overlay(subbasins_proj, soil_proj, how='intersection')
    overlay_soil['area'] = overlay_soil.geometry.area
    dominant_soil = overlay_soil.loc[overlay_soil.groupby('VALUE')['area'].idxmax()]
    dominant_soil = dominant_soil.set_index('VALUE')[['soil_type']]

    # Join results back to the original subbasins GeoDataFrame
    subbasins_gdf = subbasins_gdf.join(dominant_lu, on='VALUE').join(dominant_soil, on='VALUE')
    subbasins_gdf['zone_id'] = subbasins_gdf['land_use'].fillna('Unknown') + '-' + subbasins_gdf['soil_type'].fillna('Unknown')

    # Save the final result
    subbasins_gdf.to_file(subbasins_vector, driver='ESRI Shapefile')

    print(f"\nProcessing complete. Final sub-basins with zones saved to: {subbasins_vector}")

if __name__ == "__main__":
    main()
