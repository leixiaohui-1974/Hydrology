import pandas as pd
import geopandas as gpd
import numpy as np
from scipy.spatial import Voronoi, cKDTree
from shapely.geometry import Polygon, Point

class ArealPrecipitation:
    """
    Calculates areal precipitation for sub-basins using various interpolation methods.
    """
    def __init__(self, subbasins_shapefile, rain_gauges_file):
        """
        Initializes the ArealPrecipitation module.

        Args:
            subbasins_shapefile (str): Path to the sub-basins shapefile.
            rain_gauges_file (str): Path to the rain gauges CSV file.
        """
        self.subbasins_gdf = gpd.read_file(subbasins_shapefile)
        self.gauges_gdf = self._load_gauges(rain_gauges_file)

        # Ensure both GeoDataFrames use the same CRS
        if self.subbasins_gdf.crs != self.gauges_gdf.crs:
            self.gauges_gdf = self.gauges_gdf.to_crs(self.subbasins_gdf.crs)

    def _load_gauges(self, rain_gauges_file):
        """Loads rain gauge locations and converts them to a GeoDataFrame."""
        gauges_df = pd.read_csv(rain_gauges_file)
        geometry = [Point(xy) for xy in zip(gauges_df['x'], gauges_df['y'])]
        return gpd.GeoDataFrame(gauges_df, geometry=geometry, crs="EPSG:32610") # Assuming a UTM zone

    def clean_rainfall_data(self, rainfall_df):
        """
        Cleans the input rainfall data.
        - Fills missing values (NaNs) using linear interpolation.
        - Replaces negative rainfall values with 0.
        """
        # Ensure all rainfall columns are numeric
        for col in rainfall_df.columns:
            if rainfall_df[col].dtype.kind not in 'ifc':
                 rainfall_df[col] = pd.to_numeric(rainfall_df[col], errors='coerce')

        # Fill missing values
        cleaned_df = rainfall_df.interpolate(method='linear', limit_direction='both')

        # Replace negative values with 0
        cleaned_df[cleaned_df < 0] = 0

        return cleaned_df

    def calculate_areal_rainfall(self, rainfall_df, method='idw', **kwargs):
        """
        Calculates areal rainfall for each sub-basin.

        Args:
            rainfall_df (pd.DataFrame): DataFrame with gauge rainfall time series.
                                        Index is datetime, columns are gauge IDs.
            method (str): Interpolation method ('idw' or 'thiessen').
            **kwargs: Additional arguments for the chosen method (e.g., power for IDW).

        Returns:
            pd.DataFrame: Areal rainfall time series for each sub-basin.
                          Index is datetime, columns are sub-basin IDs.
        """
        cleaned_rainfall_df = self.clean_rainfall_data(rainfall_df)

        if method.lower() == 'idw':
            power = kwargs.get('power', 2)
            return self._calculate_idw(cleaned_rainfall_df, power)
        elif method.lower() == 'thiessen':
            return self._calculate_thiessen(cleaned_rainfall_df)
        else:
            raise ValueError("Unsupported interpolation method. Use 'idw' or 'thiessen'.")

    def _calculate_idw(self, rainfall_df, power):
        """Calculates areal rainfall using Inverse Distance Weighting (IDW)."""
        areal_rainfall = {}

        # Get sub-basin centroids
        self.subbasins_gdf['centroid'] = self.subbasins_gdf.geometry.centroid

        for subbasin_id, subbasin in self.subbasins_gdf.iterrows():
            centroid = subbasin['centroid']
            distances = self.gauges_gdf.geometry.distance(centroid)

            # Handle case where a gauge is at the centroid
            if np.any(distances == 0):
                weights = np.where(distances == 0, 1, 0)
            else:
                weights = 1 / (distances ** power)

            normalized_weights = weights / np.sum(weights)

            # Apply weights to the rainfall data
            weighted_rainfall = rainfall_df.mul(normalized_weights, axis='columns')
            areal_rainfall[subbasin_id] = weighted_rainfall.sum(axis=1)

        return pd.DataFrame(areal_rainfall)

    def _calculate_thiessen(self, rainfall_df):
        """Calculates areal rainfall using Thiessen Polygons."""
        # Create Voronoi polygons for the gauges
        points = np.array([list(p.coords)[0] for p in self.gauges_gdf.geometry])
        vor = Voronoi(points)

        # Create GeoDataFrame from Voronoi polygons
        lines = [LineString(vor.vertices[line]) for line in vor.ridge_vertices if -1 not in line]
        voronoi_polys = list(gpd.geoseries.split(gpd.GeoSeries(lines).unary_union))

        voronoi_gdf = gpd.GeoDataFrame(geometry=voronoi_polys, crs=self.subbasins_gdf.crs)

        # Associate Voronoi polygons with gauges
        voronoi_gdf['station_id'] = None
        for i, p in self.gauges_gdf.iterrows():
            containing_poly_idx = voronoi_gdf.contains(p.geometry).idxmax()
            voronoi_gdf.loc[containing_poly_idx, 'station_id'] = p['station_id']

        # Calculate areal rainfall
        areal_rainfall = {}
        for subbasin_id, subbasin in self.subbasins_gdf.iterrows():
            subbasin_poly = subbasin.geometry
            subbasin_area = subbasin_poly.area

            # Clip Voronoi polygons to the current sub-basin
            clipped_voronoi = gpd.overlay(voronoi_gdf, gpd.GeoDataFrame([subbasin], columns=['geometry'], crs=self.subbasins_gdf.crs), how='intersection')

            # Calculate weights based on the area of intersection
            weights = {}
            for _, row in clipped_voronoi.iterrows():
                gauge_id = row['station_id']
                weight = row.geometry.area / subbasin_area
                if gauge_id in rainfall_df.columns:
                    weights[gauge_id] = weight

            # Apply weights
            weighted_sum = sum(rainfall_df[gauge] * w for gauge, w in weights.items())
            areal_rainfall[subbasin_id] = weighted_sum

        return pd.DataFrame(areal_rainfall)
