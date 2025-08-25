import numpy as np
import rasterio
from rasterio.transform import from_origin
import geopandas as gpd
from shapely.geometry import LineString, Polygon
import os

def create_synthetic_dem():
    """Generates a synthetic DEM and saves it as a GeoTIFF."""
    x = np.linspace(-5, 5, 200)
    y = np.linspace(-5, 5, 200)
    xx, yy = np.meshgrid(x, y)

    dem_data = np.abs(xx) + (yy * -2)
    dem_data = (1000 - dem_data).astype(np.float32)

    transform = from_origin(west=-123.0, north=49.0, xsize=0.01, ysize=0.01)
    crs = "EPSG:4326"

    output_file = '../gis_data/dem.tif'
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with rasterio.open(
        output_file, 'w', driver='GTiff',
        height=dem_data.shape[0], width=dem_data.shape[1],
        count=1, dtype=dem_data.dtype, crs=crs, transform=transform
    ) as dst:
        dst.write(dem_data, 1)
    print(f"Created {output_file}")

def create_synthetic_river():
    """Generates a synthetic river shapefile."""
    line = LineString([(-123.0, 49.0), (-122.5, 49.0), (-122.0, 49.01)])
    gdf = gpd.GeoDataFrame({'id': [1]}, geometry=[line], crs="EPSG:4326")
    output_file = '../gis_data/river.shp'
    gdf.to_file(output_file)
    print(f"Created {output_file}")

def create_synthetic_land_use():
    """Generates a synthetic land use shapefile."""
    poly1 = Polygon([(-123.5, 48.75), (-121.5, 48.75), (-121.5, 49.0), (-123.5, 49.0)])
    poly2 = Polygon([(-123.5, 49.0), (-121.5, 49.0), (-121.5, 49.25), (-123.5, 49.25)])
    gdf = gpd.GeoDataFrame(
        {'land_use': ['Forest', 'Urban']}, geometry=[poly1, poly2], crs="EPSG:4326"
    )
    output_file = '../gis_data/land_use.shp'
    gdf.to_file(output_file)
    print(f"Created {output_file}")

def create_synthetic_soil():
    """Generates a synthetic soil type shapefile."""
    poly1 = Polygon([(-123.5, 48.75), (-122.5, 48.75), (-122.5, 49.25), (-123.5, 49.25)])
    poly2 = Polygon([(-122.5, 48.75), (-121.5, 48.75), (-121.5, 49.25), (-122.5, 49.25)])
    gdf = gpd.GeoDataFrame(
        {'soil_type': ['Clay', 'Sand']}, geometry=[poly1, poly2], crs="EPSG:4326"
    )
    output_file = '../gis_data/soil.shp'
    gdf.to_file(output_file)
    print(f"Created {output_file}")

if __name__ == "__main__":
    create_synthetic_dem()
    create_synthetic_river()
    create_synthetic_land_use()
    create_synthetic_soil()
    print("All synthetic GIS data created.")
