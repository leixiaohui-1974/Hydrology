from __future__ import annotations

import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize, shapes
from shapely.geometry import Point, shape


def _init_whitebox_tools() -> Any:
    import whitebox.whitebox_tools as wbt_mod

    package_dir = Path(wbt_mod.__file__).resolve().parent
    bundled_dir = package_dir / "WBT"
    if bundled_dir.exists():
        wbt_mod.download_wbt = lambda *args, **kwargs: None

    wbt = wbt_mod.WhiteboxTools()
    if bundled_dir.exists():
        wbt.set_whitebox_dir(str(bundled_dir))
    wbt.set_verbose_mode(False)
    return wbt


def _run_whitebox_tool(wbt: Any, tool_name: str, args: list[str], *, work_dir: Path) -> None:
    exe_dir = Path(wbt.exe_path).resolve()
    exe = exe_dir / wbt.exe_name
    cmd = [str(exe), f"--run={tool_name}", f"--wd={work_dir}", *args, "-v=false", "--compress_rasters=False"]
    proc = subprocess.run(
        cmd,
        cwd=exe_dir,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        raise RuntimeError(f"WhiteboxTools {tool_name} failed with code {proc.returncode}: {detail.strip()}")


def _build_pour_points(
    *,
    outlets: list[dict[str, Any]],
    dem_path: Path,
    output_vector: Path,
    output_raster: Path,
) -> dict[int, dict[str, Any]]:
    with rasterio.open(dem_path) as ds:
        dem_crs = ds.crs
        shape_hw = (ds.height, ds.width)
        transform = ds.transform
        dem_bounds = ds.bounds

    gdf = gpd.GeoDataFrame(
        {
            "outlet_id": list(range(1, len(outlets) + 1)),
            "name": [str(item["name"]) for item in outlets],
            "lon": [float(item["lon"]) for item in outlets],
            "lat": [float(item["lat"]) for item in outlets],
        },
        geometry=[Point(float(item["lon"]), float(item["lat"])) for item in outlets],
        crs="EPSG:4326",
    )
    if dem_crs:
        gdf = gdf.to_crs(dem_crs)
    output_vector.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_vector, driver="ESRI Shapefile")

    burned = np.zeros(shape_hw, dtype="int32")
    outside_outlets: list[str] = []
    for row in gdf.itertuples():
        x = float(row.geometry.x)
        y = float(row.geometry.y)
        if not (dem_bounds.left <= x <= dem_bounds.right and dem_bounds.bottom <= y <= dem_bounds.top):
            outside_outlets.append(str(row.name))
            continue
        col, r = ~transform * (x, y)
        row_idx = int(round(r))
        col_idx = int(round(col))
        if 0 <= row_idx < shape_hw[0] and 0 <= col_idx < shape_hw[1]:
            burned[row_idx, col_idx] = int(row.outlet_id)
        else:
            outside_outlets.append(str(row.name))

    assigned_outlets = int(np.count_nonzero(burned))
    if outside_outlets:
        raise ValueError(
            "Outlet coordinates fall outside DEM extent: "
            f"{', '.join(outside_outlets)}; "
            f"dem_bounds=({dem_bounds.left}, {dem_bounds.bottom}, {dem_bounds.right}, {dem_bounds.top})"
        )
    if assigned_outlets == 0:
        raise ValueError("No outlets were rasterized onto the DEM grid")

    with rasterio.open(dem_path) as src:
        profile = src.profile.copy()
    profile.update(dtype="int32", nodata=0, count=1)
    with rasterio.open(output_raster, "w", **profile) as dst:
        dst.write(burned, 1)

    mapping: dict[int, dict[str, Any]] = {}
    for row in gdf.itertuples():
        mapping[int(row.outlet_id)] = {
            "name": row.name,
            "lon": float(row.lon),
            "lat": float(row.lat),
        }
    return mapping


def _snap_pour_points_to_streams(
    *,
    pour_points_raster: Path,
    flow_acc_raster: Path,
    output_raster: Path,
    snap_distance: float,
) -> None:
    """Snap each pour point to the highest flow-accumulation cell within snap_distance pixels."""
    with rasterio.open(pour_points_raster) as pp_ds:
        pp_data = pp_ds.read(1)
        profile = pp_ds.profile.copy()
        res_x = abs(pp_ds.transform.a)
        res_y = abs(pp_ds.transform.e)

    with rasterio.open(flow_acc_raster) as fa_ds:
        fa_data = fa_ds.read(1)

    avg_res_m = ((res_x + res_y) / 2.0) * 111_320.0  # approximate degrees to meters
    search_radius = max(1, int(round(snap_distance / avg_res_m)))

    snapped = np.zeros_like(pp_data)
    rows_pp, cols_pp = np.where(pp_data > 0)
    for r, c in zip(rows_pp, cols_pp):
        outlet_id = pp_data[r, c]
        r_min = max(0, r - search_radius)
        r_max = min(pp_data.shape[0], r + search_radius + 1)
        c_min = max(0, c - search_radius)
        c_max = min(pp_data.shape[1], c + search_radius + 1)
        window = fa_data[r_min:r_max, c_min:c_max]
        best = np.unravel_index(np.argmax(window), window.shape)
        snapped[r_min + best[0], c_min + best[1]] = outlet_id

    profile.update(dtype="int32", nodata=0, count=1)
    with rasterio.open(output_raster, "w", **profile) as dst:
        dst.write(snapped.astype("int32"), 1)


def _polygonize_watersheds(watersheds_raster: Path) -> gpd.GeoDataFrame:
    with rasterio.open(watersheds_raster) as src:
        data = src.read(1)
        mask = np.isfinite(data) & (data > 0)
        records: list[dict[str, Any]] = []
        for geometry, value in shapes(data, mask=mask, transform=src.transform):
            if value is None or int(value) <= 0:
                continue
            records.append({"VALUE": int(value), "geometry": shape(geometry)})

        if not records:
            return gpd.GeoDataFrame(columns=["VALUE", "geometry"], geometry="geometry", crs=src.crs)

        merged: dict[int, list[Any]] = defaultdict(list)
        for record in records:
            merged[int(record["VALUE"])].append(record["geometry"])

        collapsed = [
            {"VALUE": value, "geometry": geom_list[0] if len(geom_list) == 1 else geom_list[0].union(geom_list[1])}
            for value, geom_list in merged.items()
        ]
        for item in collapsed:
            if item["VALUE"] in merged and len(merged[item["VALUE"]]) > 2:
                geom = merged[item["VALUE"]][0]
                for extra in merged[item["VALUE"]][1:]:
                    geom = geom.union(extra)
                item["geometry"] = geom
        return gpd.GeoDataFrame(collapsed, geometry="geometry", crs=src.crs)


def run_whitebox_watershed_delineation(
    *,
    dem_path: str,
    outlets: list[dict[str, Any]],
    subtract_upstream: bool = True,
    stream_threshold: float = 100.0,
    snap_distance: float = 250.0,
) -> dict[str, Any]:
    dem = Path(dem_path).resolve()
    if dem.suffix.lower() not in {".tif", ".tiff"}:
        raise ValueError(f"WhiteboxTools mainline requires GeoTIFF DEM input, got: {dem}")
    if not dem.exists():
        raise FileNotFoundError(f"DEM does not exist: {dem}")
    if not outlets:
        raise ValueError("At least one outlet is required")

    wbt = _init_whitebox_tools()

    with tempfile.TemporaryDirectory(prefix="hydrology-whitebox-") as tmpdir_raw:
        tmpdir = Path(tmpdir_raw)
        filled_dem = tmpdir / "filled_dem.tif"
        d8_pointer = tmpdir / "d8_pointer.tif"
        flow_acc = tmpdir / "flow_acc.tif"
        streams = tmpdir / "streams.tif"
        pour_points = tmpdir / "pour_points.shp"
        pour_points_raster = tmpdir / "pour_points.tif"
        watersheds_raster = tmpdir / "watersheds.tif"

        outlet_mapping = _build_pour_points(
            outlets=outlets,
            dem_path=dem,
            output_vector=pour_points,
            output_raster=pour_points_raster,
        )

        _run_whitebox_tool(
            wbt,
            "BreachDepressionsLeastCost",
            [f"--dem={dem}", f"--output={filled_dem}", "--dist=50", "--fill"],
            work_dir=tmpdir,
        )
        _run_whitebox_tool(
            wbt,
            "D8Pointer",
            [f"--dem={filled_dem}", f"--output={d8_pointer}"],
            work_dir=tmpdir,
        )
        _run_whitebox_tool(
            wbt,
            "D8FlowAccumulation",
            [f"--input={filled_dem}", f"--output={flow_acc}", "--out_type=cells"],
            work_dir=tmpdir,
        )
        _run_whitebox_tool(
            wbt,
            "ExtractStreams",
            [f"--flow_accum={flow_acc}", f"--output={streams}", f"--threshold={stream_threshold}", "--zero_background"],
            work_dir=tmpdir,
        )
        snapped_pour_points = tmpdir / "snapped_pour_points.tif"
        _snap_pour_points_to_streams(
            pour_points_raster=pour_points_raster,
            flow_acc_raster=flow_acc,
            output_raster=snapped_pour_points,
            snap_distance=snap_distance,
        )
        _run_whitebox_tool(
            wbt,
            "Watershed",
            [f"--d8_pntr={d8_pointer}", f"--pour_pts={snapped_pour_points}", f"--output={watersheds_raster}"],
            work_dir=tmpdir,
        )
        if not watersheds_raster.exists():
            raise RuntimeError(f"WhiteboxTools watershed did not create output raster: {watersheds_raster}")

        polygons = _polygonize_watersheds(watersheds_raster)
        if polygons.empty:
            raise RuntimeError("WhiteboxTools watershed produced no polygons")

        if polygons.crs and polygons.crs.is_geographic:
            centroid = polygons.dissolve().centroid.iloc[0]
            utm_zone = int((centroid.x + 180) / 6) + 1
            hemisphere = "north" if centroid.y >= 0 else "south"
            utm_epsg = 32600 + utm_zone if hemisphere == "north" else 32700 + utm_zone
            area_gdf = polygons.to_crs(epsg=utm_epsg)
        elif polygons.crs:
            area_gdf = polygons
        else:
            area_gdf = polygons
        areas_km2 = area_gdf.geometry.area / 1_000_000.0

        basins = []
        for idx, row in enumerate(polygons.itertuples(), start=0):
            raw_value = getattr(row, "VALUE", None)
            try:
                outlet_id = int(raw_value) if raw_value is not None else idx + 1
            except Exception:
                outlet_id = idx + 1
            outlet = outlet_mapping.get(outlet_id, {"name": f"outlet-{outlet_id}", "lon": None, "lat": None})
            basins.append(
                {
                    "outlet_id": outlet_id,
                    "name": outlet["name"],
                    "area_km2": float(areas_km2.iloc[idx]),
                    "boundary": row.geometry.__geo_interface__,
                }
            )

        basins.sort(key=lambda item: item["area_km2"], reverse=True)
        if subtract_upstream:
            # Whitebox mainline currently emits independent watershed polygons. Upstream subtraction is
            # retained as an explicit metadata flag for compatibility, not as a secondary geometry pass.
            pass

        return {
            "engine": "whiteboxtools_mainline",
            "dem_path": str(dem),
            "stream_threshold": stream_threshold,
            "snap_distance": snap_distance,
            "subtract_upstream": subtract_upstream,
            "basins": basins,
            "total_area_km2": float(sum(item["area_km2"] for item in basins)),
        }
