"""Miners for the GeoSpatial domain (A1-A5).

Handles DEM, land use, soil, basin boundary, river network.
Uses lightweight probes; heavy GIS libraries are imported lazily.
"""
from __future__ import annotations

import fnmatch
import json
import logging
from pathlib import Path
from typing import Any

from ..registry import MineResult
from ..taxonomy import TYPE_CATALOG, DataType

log = logging.getLogger(__name__)

_GEO_TYPES = [
    DataType.DEM,
    DataType.LAND_USE,
    DataType.SOIL,
    DataType.BASIN_BOUNDARY,
    DataType.RIVER_NETWORK,
]


class GeoSpatialMiner:
    @property
    def handled_types(self) -> list[DataType]:
        return list(_GEO_TYPES)

    def probe(self, path: Path, cfg: dict[str, Any]) -> list[DataType]:
        matched: list[DataType] = []
        name_lower = path.name.lower()
        ext = path.suffix.lower()
        for dt in _GEO_TYPES:
            meta = TYPE_CATALOG[dt]
            if ext not in meta.extensions:
                continue
            if meta.filename_patterns and not any(
                fnmatch.fnmatch(name_lower, p) for p in meta.filename_patterns
            ):
                continue
            matched.append(dt)
        return matched

    def extract(
        self, path: Path, data_type: DataType, cfg: dict[str, Any],
    ) -> list[MineResult]:
        ext = path.suffix.lower()
        if ext in (".tif", ".tiff"):
            return self._extract_raster(path, data_type)
        if ext in (".shp", ".geojson", ".gpkg"):
            return self._extract_vector(path, data_type)
        if ext == ".asc":
            return self._extract_ascii_grid(path, data_type)
        return []

    def _extract_raster(self, path: Path, data_type: DataType) -> list[MineResult]:
        payload: dict[str, Any] = {
            "format": "GeoTIFF",
            "path": str(path),
        }
        try:
            import rasterio
            with rasterio.open(path) as ds:
                b = ds.bounds
                payload.update({
                    "crs": str(ds.crs) if ds.crs else None,
                    "bounds": {
                        "left": b.left, "bottom": b.bottom,
                        "right": b.right, "top": b.top,
                    },
                    "resolution": {"x": ds.res[0], "y": ds.res[1]},
                    "shape": {"width": ds.width, "height": ds.height},
                    "bands": ds.count,
                    "dtype": str(ds.dtypes[0]),
                    "nodata": ds.nodata,
                })
        except ImportError:
            payload["crs"] = None
            payload["note"] = "rasterio not installed; metadata incomplete"
        except Exception as exc:
            payload["error"] = str(exc)

        return [MineResult(
            data_type=data_type,
            source_path=str(path),
            source_kind="raster",
            payload=payload,
            confidence=0.8 if payload.get("crs") else 0.4,
            label=f"{TYPE_CATALOG[data_type].label_cn}: {path.name}",
        )]

    def _extract_vector(self, path: Path, data_type: DataType) -> list[MineResult]:
        payload: dict[str, Any] = {
            "format": path.suffix.lower().lstrip("."),
            "path": str(path),
        }
        try:
            import geopandas as gpd
            gdf = gpd.read_file(path)
            payload.update({
                "crs": str(gdf.crs) if gdf.crs else None,
                "feature_count": len(gdf),
                "geometry_types": list(gdf.geom_type.unique()),
                "columns": list(gdf.columns),
                "bounds": dict(zip(
                    ["minx", "miny", "maxx", "maxy"],
                    gdf.total_bounds.tolist(),
                )),
            })
        except ImportError:
            payload["note"] = "geopandas not installed; metadata incomplete"
        except Exception as exc:
            payload["error"] = str(exc)

        return [MineResult(
            data_type=data_type,
            source_path=str(path),
            source_kind="vector",
            payload=payload,
            confidence=0.7 if payload.get("crs") else 0.3,
            label=f"{TYPE_CATALOG[data_type].label_cn}: {path.name}",
        )]

    def _extract_ascii_grid(self, path: Path, data_type: DataType) -> list[MineResult]:
        payload: dict[str, Any] = {"format": "ASCII_GRID", "path": str(path)}
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:10]
            header: dict[str, str] = {}
            for line in lines:
                parts = line.strip().split()
                if len(parts) == 2 and parts[0].lower() in (
                    "ncols", "nrows", "xllcorner", "yllcorner", "cellsize", "nodata_value",
                ):
                    header[parts[0].lower()] = parts[1]
            payload.update({
                "ncols": int(header.get("ncols", 0)),
                "nrows": int(header.get("nrows", 0)),
                "cellsize": float(header.get("cellsize", 0)),
                "crs": None,
            })
        except Exception as exc:
            payload["error"] = str(exc)

        return [MineResult(
            data_type=data_type,
            source_path=str(path),
            source_kind="ascii_grid",
            payload=payload,
            confidence=0.5,
            label=f"{TYPE_CATALOG[data_type].label_cn}: {path.name}",
        )]
