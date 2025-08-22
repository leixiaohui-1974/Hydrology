import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.ops import unary_union
from geovoronoi import voronoi_regions_from_coords
from pykrige.ok import OrdinaryKriging
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
        # Ensure 'zone_id' or a similar unique identifier exists and set it as index
        if 'zone_id' in self.subbasins_gdf.columns:
            self.subbasins_gdf = self.subbasins_gdf.set_index('zone_id')
        else:
            print("Warning: 'zone_id' column not found in subbasins shapefile. Using default integer index.")

        self.gauges_gdf = self._load_gauges(rain_gauges_file)

        if self.subbasins_gdf.crs != self.gauges_gdf.crs:
            self.gauges_gdf = self.gauges_gdf.to_crs(self.subbasins_gdf.crs)

    def _load_gauges(self, rain_gauges_file):
        """Loads rain gauge locations and converts them to a GeoDataFrame."""
        gauges_df = pd.read_csv(rain_gauges_file)
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
        For Kriging, this returns a tuple: (rainfall_df, variance_df).
        For other methods, it returns just the rainfall_df.
        """
        cleaned_rainfall_df = self.clean_rainfall_data(rainfall_df)

        if method.lower() == 'idw':
            power = kwargs.get('power', 2)
            return self._calculate_idw(cleaned_rainfall_df, power)
        elif method.lower() == 'thiessen':
            cache_file = kwargs.get('cache_file')
            return self._calculate_thiessen(cleaned_rainfall_df, cache_file)
        elif method.lower() == 'kriging':
            # Kriging method now returns a tuple (mean, variance)
            return self._calculate_kriging(cleaned_rainfall_df, **kwargs)
        else:
            raise ValueError("Unsupported interpolation method. Use 'idw', 'thiessen', or 'kriging'.")

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
        """
        weights = None
        if cache_file and os.path.exists(cache_file):
            print(f"Loading Thiessen weights from cache: {cache_file}")
            with open(cache_file, 'r') as f:
                weights = json.load(f)

        if weights is None:
            print("Calculating Thiessen polygon weights using geovoronoi...")
            boundary_shape = unary_union(self.subbasins_gdf.geometry)
            coords = np.array([p.coords[0] for p in self.gauges_gdf.geometry])
            region_polys, region_pts_idx = voronoi_regions_from_coords(coords, boundary_shape)
            voronoi_gdf = gpd.GeoDataFrame(geometry=list(region_polys.values()), crs=self.subbasins_gdf.crs)
            voronoi_gdf['station_id'] = [self.gauges_gdf.iloc[region_pts_idx[k][0]]['station_id'] for k in region_polys.keys()]

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

        areal_rainfall = {}
        for subbasin_id, subbasin_weights in weights.items():
            weighted_series_list = [rainfall_df[gauge] * w for gauge, w in subbasin_weights.items() if gauge in rainfall_df.columns]
            if not weighted_series_list:
                areal_rainfall[subbasin_id] = pd.Series(0.0, index=rainfall_df.index)
            else:
                areal_rainfall[subbasin_id] = sum(weighted_series_list)
        return pd.DataFrame(areal_rainfall)

    def _calculate_kriging(self, rainfall_df, variogram_model='linear', grid_resolution=10, **kwargs):
        """
        Calculates areal rainfall and estimation variance using Ordinary Kriging.
        This method is computationally intensive as it loops through each time step.
        Returns a tuple of two DataFrames: (mean_rainfall, mean_variance).
        """
        print("Calculating areal rainfall and variance using Ordinary Kriging...")
        print(f"DEBUG: Sub-basin GDF index is: {self.subbasins_gdf.index.tolist()}")

        gauge_coords = self.gauges_gdf.get_coordinates(ignore_index=True)
        gauge_x = gauge_coords['x'].to_numpy()
        gauge_y = gauge_coords['y'].to_numpy()

        mean_results = {str(subbasin_id): [] for subbasin_id in self.subbasins_gdf.index}
        variance_results = {str(subbasin_id): [] for subbasin_id in self.subbasins_gdf.index}

        subbasin_grids = {}
        for subbasin_id, subbasin in self.subbasins_gdf.iterrows():
            minx, miny, maxx, maxy = subbasin.geometry.bounds
            grid_x = np.linspace(minx, maxx, grid_resolution)
            grid_y = np.linspace(miny, maxy, grid_resolution)
            xv, yv = np.meshgrid(grid_x, grid_y)
            points_in_bounds = gpd.GeoSeries([gpd.points_from_xy([x], [y])[0] for x, y in zip(xv.flatten(), yv.flatten())])
            points_inside = points_in_bounds[points_in_bounds.within(subbasin.geometry)]
            subbasin_grids[subbasin_id] = (points_inside.x.to_numpy(), points_inside.y.to_numpy())

        for timestamp, row in rainfall_df.iterrows():
            print(f"  Processing timestamp: {timestamp}", end='\r')
            gauge_values = row.to_numpy()

            if np.var(gauge_values) < 1e-6:
                mean_rainfall = np.mean(gauge_values)
                for subbasin_id in self.subbasins_gdf.index:
                    mean_results[str(subbasin_id)].append(mean_rainfall)
                    variance_results[str(subbasin_id)].append(0.0) # Zero variance if all values are the same
                continue

            try:
                ok = OrdinaryKriging(
                    gauge_x, gauge_y, gauge_values,
                    variogram_model=variogram_model, verbose=False, enable_plotting=False
                )
                for subbasin_id in self.subbasins_gdf.index:
                    gridx, gridy = subbasin_grids[subbasin_id]
                    if len(gridx) == 0:
                        mean_results[str(subbasin_id)].append(0.0)
                        variance_results[str(subbasin_id)].append(np.nan) # Variance is undefined
                        continue

                    z, ss = ok.execute('grid', gridx, gridy)
                    mean_results[str(subbasin_id)].append(np.mean(z))
                    variance_results[str(subbasin_id)].append(np.mean(ss))

            except Exception as e:
                print(f"\nWarning: Kriging failed for timestamp {timestamp} with error: {e}.")
                print("         Falling back to inverse distance weighting for this timestep (variance will be NaN).")
                idw_series = self._calculate_idw(pd.DataFrame([row]), power=2)
                for subbasin_id in self.subbasins_gdf.index:
                    mean_results[str(subbasin_id)].append(idw_series[subbasin_id].iloc[0])
                    variance_results[str(subbasin_id)].append(np.nan)

        print("\nKriging calculation complete.")
        mean_df = pd.DataFrame(mean_results, index=rainfall_df.index)
        variance_df = pd.DataFrame(variance_results, index=rainfall_df.index)
        return mean_df, variance_df
