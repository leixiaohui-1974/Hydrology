"""
generate_parameter_zones.py
使用 WhiteboxTools 进行 DEM 流域划分，并基于空间位置（质心纬度）分配参数分区。
同时生成 catchment_definition.csv，供 run_full_pipeline.py 使用。
"""

import os
import sys
import math
import geopandas as gpd
import pandas as pd
from pathlib import Path
from shapely.geometry import Polygon

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from whitebox.whitebox_tools import WhiteboxTools
except Exception:
    WhiteboxTools = None

try:
    from hydro_model.terrain_analysis import TerrainAnalyzer, DEMData
    HAS_TERRAIN_ANALYZER = True
except ImportError:
    HAS_TERRAIN_ANALYZER = False

CENTER_LAT = (32.5224999999987 + 32.82166666666536) / 2  # ≈ 32.672


def _create_fallback_zones(output_path: str) -> None:
    """在缺少 WhiteboxTools 时生成简化示例分区数据。"""
    print("WhiteboxTools 不可用，生成简化的示例分区数据。")
    polygons = [
        Polygon([(-97.48, 32.52), (-97.33, 32.52), (-97.33, 32.67), (-97.48, 32.67)]),
        Polygon([(-97.33, 32.52), (-97.18, 32.52), (-97.18, 32.67), (-97.33, 32.67)]),
        Polygon([(-97.48, 32.67), (-97.33, 32.67), (-97.33, 32.82), (-97.48, 32.82)]),
    ]
    zones = ['zone1', 'zone2', 'zone1']
    gdf = gpd.GeoDataFrame(
        {'VALUE': [1.0, 2.0, 3.0], 'zone_id': zones},
        geometry=polygons,
        crs='EPSG:4326',
    )
    gdf.to_file(output_path, driver='ESRI Shapefile')
    print(f"已生成示例分区文件: {output_path}")


def _assign_zones_by_centroid(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """基于子流域质心纬度分配参数分区：北部(lat > CENTER_LAT) → zone1，南部 → zone2。"""
    centroids = gdf.geometry.centroid
    gdf = gdf.copy()
    gdf['zone_id'] = centroids.y.apply(lambda lat: 'zone1' if lat > CENTER_LAT else 'zone2')
    return gdf


def _assign_zones_by_stations(gdf, stations):
    if not stations:
        return _assign_zones_by_centroid(gdf)
    gdf = gdf.copy()
    centroids = gdf.geometry.centroid
    zone_ids = []
    for geom in centroids:
        cx, cy = geom.x, geom.y
        best_zone = stations[0]["station_id"]
        best_dist = float("inf")
        for st in stations:
            dist = (cx - st["x"]) ** 2 + (cy - st["y"]) ** 2
            if dist < best_dist:
                best_dist = dist
                best_zone = st["station_id"]
        zone_ids.append("zone_" + best_zone)
    gdf["zone_id"] = zone_ids
    return gdf


def _generate_catchment_definition(
    gdf: gpd.GeoDataFrame,
    output_path: str,
) -> None:
    """
    根据子流域 GeoDataFrame 生成 catchment_definition.csv。
    拓扑关系：按流量累积值排序，每个子流域的 downstream 为累积量最大的相邻子流域。
    简化方案：按质心纬度从北到南排序，形成线性链。
    """
    gdf_sorted = gdf.copy()
    centroids = gdf_sorted.geometry.centroid
    gdf_sorted['_cx'] = centroids.x
    gdf_sorted['_cy'] = centroids.y
    # 北→南排序（纬度降序）
    gdf_sorted = gdf_sorted.sort_values('_cy', ascending=False).reset_index(drop=True)

    # 计算面积（近似：在 EPSG:4326 下用度平方 * 111^2）
    # 更准确：投影到 UTM 14N (EPSG:32614) 计算
    try:
        gdf_proj = gdf_sorted.to_crs('EPSG:32614')
        areas_km2 = (gdf_proj.geometry.area / 1e6).round(2)
    except Exception:
        areas_km2 = (gdf_sorted.geometry.area * (111.0 ** 2)).round(2)

    rows = []
    n = len(gdf_sorted)
    for i in range(n):
        pfaf = str(i + 1)
        downstream = str(i + 2) if i + 1 < n else ''
        rows.append({
            'pfaf_code': pfaf,
            'area_km2': float(areas_km2.iloc[i]),
            'zone_id': gdf_sorted['zone_id'].iloc[i],
            'downstream_pfaf': downstream,
        })

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"catchment_definition.csv 已生成: {output_path}  ({n} 行)")


def main() -> None:
    results_dir = os.path.join(project_root, "examples/results")
    data_dir = os.path.join(project_root, "data")
    os.makedirs(results_dir, exist_ok=True)
    subbasins_with_zones_shp = os.path.join(results_dir, "subbasins_with_zones.shp")
    catchment_csv = os.path.join(data_dir, "catchment_definition.csv")

    if WhiteboxTools is None:
        _create_fallback_zones(subbasins_with_zones_shp)
        gdf = gpd.read_file(subbasins_with_zones_shp)
        _generate_catchment_definition(gdf, catchment_csv)
        return

    try:
        wbt = WhiteboxTools()
        wbt.verbose = True
    except Exception as exc:
        print(f"WhiteboxTools 初始化失败: {exc}")
        _create_fallback_zones(subbasins_with_zones_shp)
        gdf = gpd.read_file(subbasins_with_zones_shp)
        _generate_catchment_definition(gdf, catchment_csv)
        return

    work_dir = project_root
    temp_dir = os.path.join(work_dir, "examples/temp_gis")
    os.makedirs(temp_dir, exist_ok=True)

    dem_file = os.path.join(work_dir, "gis_data/dem.tif")
    filled_dem = os.path.join(temp_dir, "filled_dem.tif")
    d8_pointer = os.path.join(temp_dir, "d8_pointer.tif")
    flow_acc = os.path.join(temp_dir, "flow_acc.tif")
    streams = os.path.join(temp_dir, "streams.tif")
    subbasins_raster = os.path.join(temp_dir, "subbasins.tif")
    subbasins_vector_temp = os.path.join(temp_dir, "subbasins_temp.shp")

    try:
        print("Step 1: Pre-processing DEM...")
        wbt.fill_depressions(dem_file, filled_dem)
        wbt.d8_pointer(filled_dem, d8_pointer)
        wbt.d8_flow_accumulation(filled_dem, flow_acc, out_type='cells')

        print("Step 2: Delineating individual sub-basins...")
        wbt.extract_streams(flow_acc, streams, threshold=100.0, zero_background=True)
        wbt.subbasins(d8_pointer, streams, subbasins_raster)
        wbt.raster_to_vector_polygons(subbasins_raster, subbasins_vector_temp)

        print("--- Step 2.5: Auto-generating gauging stations on main stream ---")
        gauging_stations_list = []
        if HAS_TERRAIN_ANALYZER:
            try:
                _analyzer = TerrainAnalyzer()
                _dem_data = DEMData.from_tif(dem_file)
                _analyzer.load_dem(_dem_data)
                _flow_result = _analyzer.compute_flow_direction()
                gauging_stations_list = _analyzer.generate_gauging_stations(_flow_result, n_stations=3)
                print(f"自动生成水文站 {len(gauging_stations_list)} 个：")
                for _st in gauging_stations_list:
                    print(f"  {_st['station_id']:20s}  lon={_st['x']:.4f}  lat={_st['y']:.4f}  type={_st['type']}")
                import csv as _csv_mod
                _gauge_path = os.path.join(project_root, 'gis_data', 'gauging_stations.csv')
                os.makedirs(os.path.dirname(_gauge_path), exist_ok=True)
                with open(_gauge_path, 'w', newline='', encoding='utf-8') as _gf:
                    _gw = _csv_mod.writer(_gf)
                    _gw.writerow(['station_id', 'x', 'y', 'type'])
                    for _st in gauging_stations_list:
                        _gw.writerow([_st['station_id'], _st['x'], _st['y'], _st['type']])
                print(f"gauging_stations.csv 已保存到: {_gauge_path}")
                _zone_masks = _analyzer.partition_by_stations(_flow_result, gauging_stations_list)
                print(f"参数分区划分完成：{list(_zone_masks.keys())}")
                _analyzer.cleanup()
            except Exception as _ge:
                print(f"水文站自动生成失败（降级到质心分区）：{_ge}")
        else:
            print("TerrainAnalyzer 不可用，跳过水文站自动生成步骤")

        print("--- Step 3: Assigning Parameter Zones ---")
        gdf = gpd.read_file(subbasins_vector_temp)
        print(f"Found {len(gdf)} sub-basins.")

        if gauging_stations_list:
            gdf = _assign_zones_by_stations(gdf, gauging_stations_list)
        else:
            gdf = _assign_zones_by_centroid(gdf)
        zone_counts = gdf['zone_id'].value_counts().to_dict()
        print(f"Zone assignment complete: {zone_counts}")

        gdf.to_file(subbasins_with_zones_shp, driver='ESRI Shapefile')
        print(f"Sub-basins with zones saved to: {subbasins_with_zones_shp}")

        print("--- Step 4: Generating catchment_definition.csv ---")
        _generate_catchment_definition(gdf, catchment_csv)

    except Exception as exc:
        print(f"WhiteboxTools 流程执行失败: {exc}")
        _create_fallback_zones(subbasins_with_zones_shp)
        gdf = gpd.read_file(subbasins_with_zones_shp)
        _generate_catchment_definition(gdf, catchment_csv)


if __name__ == "__main__":
    main()
