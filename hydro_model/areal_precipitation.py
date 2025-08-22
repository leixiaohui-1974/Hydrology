import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.ops import unary_union
from geovoronoi import voronoi_regions_from_coords
import json
import os

class ArealPrecipitation:
    """
    Calculates areal precipitation for sub-basins using various interpolation methods.
    """
    def __init__(self, subbasins_shapefile, rain_gauges_file):
        """
        Initializes the ArealPrecipitation module.
        """
        self.subbasins_gdf = gpd.read_file(subbasins_shapefile)
        self.gauges_gdf = self._load_gauges(rain_gauges_file)

        if self.subbasins_gdf.crs != self.gauges_gdf.crs:
            self.gauges_gdf = self.gauges_gdf.to_crs(self.subbasins_gdf.crs)

    def _load_gauges(self, rain_gauges_file):
        """Loads rain gauge locations and converts them to a GeoDataFrame."""
        gauges_df = pd.read_csv(rain_gauges_file)
        # Create GeoDataFrame using the same CRS as the subbasins
        return gpd.GeoDataFrame(
            gauges_df,
            geometry=gpd.points_from_xy(gauges_df.x, gauges_df.y),
            crs=self.subbasins_gdf.crs
        )

    def clean_rainfall_data(self, rainfall_df):
        """
        Cleans the input rainfall data.
        """
        for col in rainfall_df.columns:
            if rainfall_df[col].dtype.kind not in 'ifc':
                 rainfall_df[col] = pd.to_numeric(rainfall_df[col], errors='coerce')
        cleaned_df = rainfall_df.interpolate(method='linear', limit_direction='both')
        cleaned_df[cleaned_df < 0] = 0
        return cleaned_df

    def calculate_areal_rainfall(self, rainfall_df, method='idw', **kwargs):
        """
        Calculates areal rainfall for each sub-basin.
        """
        cleaned_rainfall_df = self.clean_rainfall_data(rainfall_df)

        if method.lower() == 'idw':
            power = kwargs.get('power', 2)
            return self._calculate_idw(cleaned_rainfall_df, power)
        elif method.lower() == 'thiessen':
            cache_file = kwargs.get('cache_file')
            return self._calculate_thiessen(cleaned_rainfall_df, cache_file)
        else:
            raise ValueError("Unsupported interpolation method. Use 'idw' or 'thiessen'.")

    def _calculate_idw(self, rainfall_df, power):
        """Calculates areal rainfall using Inverse Distance Weighting (IDW)."""
        areal_rainfall = {}
        self.subbasins_gdf['centroid'] = self.subbasins_gdf.geometry.centroid
        for subbasin_id, subbasin in self.subbasins_gdf.iterrows():
            centroid = subbasin['centroid']
            distances = self.gauges_gdf.geometry.distance(centroid)
            if np.any(distances == 0):
                weights = np.where(distances == 0, 1, 0)
            else:
                weights = 1 / (distances ** power)
            normalized_weights = weights / np.sum(weights)
            weighted_rainfall = rainfall_df.mul(normalized_weights, axis='columns')
            areal_rainfall[subbasin_id] = weighted_rainfall.sum(axis=1)
        return pd.DataFrame(areal_rainfall)

    def _calculate_thiessen(self, rainfall_df, cache_file=None):
        """
        Calculates areal rainfall using Thiessen Polygons, powered by the geovoronoi library.
        Uses a cache file to store/retrieve weights if provided.
        """
        weights = None
        if cache_file and os.path.exists(cache_file):
            print(f"Loading Thiessen weights from cache: {cache_file}")
            with open(cache_file, 'r') as f:
                weights = json.load(f)

        if weights is None:
            print("Calculating Thiessen polygon weights using geovoronoi...")

            # --- 1. Prepare inputs for geovoronoi ---
            # Get the overall boundary of all sub-basins
            boundary_shape = unary_union(self.subbasins_gdf.geometry)
            # Get gauge coordinates as a numpy array
            coords = np.array([p.coords[0] for p in self.gauges_gdf.geometry])

            # --- 2. Perform Voronoi tessellation clipped to the boundary ---
            region_polys, region_pts_idx = voronoi_regions_from_coords(coords, boundary_shape)

            # --- 3. Create a GeoDataFrame from the resulting Voronoi polygons ---
            voronoi_gdf = gpd.GeoDataFrame(geometry=list(region_polys.values()), crs=self.subbasins_gdf.crs)

            # Assign station_id to each Voronoi polygon
            voronoi_gdf['station_id'] = [self.gauges_gdf.iloc[region_pts_idx[k][0]]['station_id'] for k in region_polys.keys()]

            # --- 4. Calculate weights for each sub-basin ---
            weights = {}
            for subbasin_id, subbasin in self.subbasins_gdf.iterrows():
                subbasin_poly = subbasin.geometry
                subbasin_area = subbasin_poly.area
                weights[str(subbasin_id)] = {}

                clipped_voronoi = gpd.overlay(voronoi_gdf, gpd.GeoDataFrame([subbasin], columns=['geometry'], crs=self.subbasins_gdf.crs), how='intersection')

                for _, row in clipped_voronoi.iterrows():
                    gauge_id = row['station_id']
                    if gauge_id and gauge_id in rainfall_df.columns:
                        weight = row.geometry.area / subbasin_area
                        weights[str(subbasin_id)][gauge_id] = weight

            if cache_file:
                print(f"Saving Thiessen weights to cache: {cache_file}")
                with open(cache_file, 'w') as f:
                    json.dump(weights, f, indent=4)

        # --- 5. Apply weights to calculate areal rainfall ---
        areal_rainfall = {}
        for subbasin_id, subbasin_weights in weights.items():

            weighted_series_list = [
                rainfall_df[gauge] * w
                for gauge, w in subbasin_weights.items()
                if gauge in rainfall_df.columns
            ]

            if not weighted_series_list:
                # If no valid gauges found for this subbasin, create a zero series
                areal_rainfall[subbasin_id] = pd.Series(0.0, index=rainfall_df.index)
            else:
                # Sum all the weighted series to get the final areal rainfall series
                areal_rainfall[subbasin_id] = sum(weighted_series_list)

        return pd.DataFrame(areal_rainfall)
