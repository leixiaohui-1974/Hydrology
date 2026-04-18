#!/usr/bin/env python3
"""
create_gis_data.py
生成配套 GIS 数据（不生成 DEM，DEM 已存在）
自动从 gis_data/dem.tif 读取范围，适配任意流域。
"""

import csv
import rasterio
import geopandas as gpd
from shapely.geometry import LineString, Polygon
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
OUT_DIR = SCRIPT_DIR / "../gis_data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── DEM 范围（自动从 dem.tif 读取） ──────────────────────────────────────────
DEM_PATH = OUT_DIR / "dem.tif"
with rasterio.open(str(DEM_PATH)) as _ds:
    _b = _ds.bounds
    LEFT   = _b.left
    BOTTOM = _b.bottom
    RIGHT  = _b.right
    TOP    = _b.top
CRS    = "EPSG:4326"

CENTER_LAT = (BOTTOM + TOP) / 2
CENTER_LON = (LEFT + RIGHT) / 2
print(f"DEM 范围: {LEFT:.4f}~{RIGHT:.4f}E, {BOTTOM:.4f}~{TOP:.4f}N")

# ═════════════════════════════════════════════════════════════════════════════
# 1. 土地利用 land_use.shp
#    西北高地(lat > CENTER_LAT) → Forest
#    东南低地(lat ≤ CENTER_LAT) → Urban
# ═════════════════════════════════════════════════════════════════════════════
forest_poly = Polygon([
    (LEFT,        CENTER_LAT),
    (RIGHT,       CENTER_LAT),
    (RIGHT,       TOP),
    (LEFT,        TOP),
    (LEFT,        CENTER_LAT),
])

urban_poly = Polygon([
    (LEFT,        BOTTOM),
    (RIGHT,       BOTTOM),
    (RIGHT,       CENTER_LAT),
    (LEFT,        CENTER_LAT),
    (LEFT,        BOTTOM),
])

land_use_gdf = gpd.GeoDataFrame(
    {"land_use": ["Forest", "Urban"]},
    geometry=[forest_poly, urban_poly],
    crs=CRS,
)
land_use_gdf.to_file(OUT_DIR / "land_use.shp")
print(f"[OK] land_use.shp  → {OUT_DIR / 'land_use.shp'}")

# ═════════════════════════════════════════════════════════════════════════════
# 2. 土壤 soil.shp
#    西部(lon < CENTER_LON) → Clay
#    东部(lon ≥ CENTER_LON) → Sand
# ═════════════════════════════════════════════════════════════════════════════
clay_poly = Polygon([
    (LEFT,        BOTTOM),
    (CENTER_LON,  BOTTOM),
    (CENTER_LON,  TOP),
    (LEFT,        TOP),
    (LEFT,        BOTTOM),
])

sand_poly = Polygon([
    (CENTER_LON,  BOTTOM),
    (RIGHT,       BOTTOM),
    (RIGHT,       TOP),
    (CENTER_LON,  TOP),
    (CENTER_LON,  BOTTOM),
])

soil_gdf = gpd.GeoDataFrame(
    {"soil_type": ["Clay", "Sand"]},
    geometry=[clay_poly, sand_poly],
    crs=CRS,
)
soil_gdf.to_file(OUT_DIR / "soil.shp")
print(f"[OK] soil.shp      → {OUT_DIR / 'soil.shp'}")

# ═════════════════════════════════════════════════════════════════════════════
# 3. 河流 river.shp
#    从西北流向东南的简化折线，完全在 DEM 范围内
# ═════════════════════════════════════════════════════════════════════════════
river_coords = [
    (-97.45, 32.80),   # 西北起点（略内缩于边界）
    (-97.40, 32.75),
    (-97.35, 32.68),
    (-97.28, 32.62),
    (-97.20, 32.55),   # 东南终点（略内缩于边界）
]
river_line = LineString(river_coords)

river_gdf = gpd.GeoDataFrame(
    {"river_name": ["Main River"]},
    geometry=[river_line],
    crs=CRS,
)
river_gdf.to_file(OUT_DIR / "river.shp")
print(f"[OK] river.shp     → {OUT_DIR / 'river.shp'}")

# ═════════════════════════════════════════════════════════════════════════════
# 4. rain_gauges.csv
# ═════════════════════════════════════════════════════════════════════════════
rain_gauges = [
    ("rainfall_1", -97.40, 32.70),
    ("rainfall_2", -97.25, 32.60),
    ("rainfall_3", -97.35, 32.55),
]

rain_csv_path = OUT_DIR / "rain_gauges.csv"
with open(rain_csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["station_id", "x", "y"])
    writer.writerows(rain_gauges)
print(f"[OK] rain_gauges.csv → {rain_csv_path}")

# ═════════════════════════════════════════════════════════════════════════════
# 5. gauging_stations.csv
# ═════════════════════════════════════════════════════════════════════════════
gauging_stations = [
    ("outlet",   -97.25, 32.55),
    ("upstream", -97.40, 32.75),
]

gauge_csv_path = OUT_DIR / "gauging_stations.csv"
with open(gauge_csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["station_id", "x", "y"])
    writer.writerows(gauging_stations)
print(f"[OK] gauging_stations.csv → {gauge_csv_path}")

# ═════════════════════════════════════════════════════════════════════════════
# 完成
# ═════════════════════════════════════════════════════════════════════════════
print("\n所有配套 GIS 数据生成完毕。")
print(f"输出目录: {OUT_DIR.resolve()}")
