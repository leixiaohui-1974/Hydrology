"""DEM 数据管线 — 通用产品模块。

双来源 DEM 获取与预处理：
  1. case 本地目录：cases/{case_id}/dem/
  2. 公开数据下载：SRTM 30m / Copernicus DEM 30m / ALOS World 3D

使用方式::

    from hydro_model.dem_pipeline import DEMPipeline
    pipe = DEMPipeline(case_id="daduhe")
    dem_data = pipe.load()           # 优先 case 本地，fallback 公开下载
    dem_data = pipe.download_srtm()  # 强制从 SRTM 下载
"""
from __future__ import annotations

import logging
import os
import struct
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


SRTM_BASE_URL = "https://srtm.csi.cgiar.org/wp-content/uploads/files/srtm_5x5/TIFF"
COPERNICUS_BASE = "https://prism-dem-open.copernicus.eu/pd-desk-open-access/prismDownload"

DEM_SOURCES = {
    "srtm_30m": {
        "name": "SRTM 30m (NASA/CGIAR)",
        "resolution_m": 30,
        "coverage": "60°N ~ 56°S",
        "url_pattern": SRTM_BASE_URL,
    },
    "copernicus_30m": {
        "name": "Copernicus DEM 30m (ESA)",
        "resolution_m": 30,
        "coverage": "Global",
        "url_pattern": COPERNICUS_BASE,
    },
    "alos_30m": {
        "name": "ALOS World 3D 30m (JAXA)",
        "resolution_m": 30,
        "coverage": "Global",
    },
}


@dataclass
class DEMMetadata:
    """DEM 数据元信息。"""
    source: str = "unknown"
    resolution_m: float = 30.0
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    crs: str = "EPSG:4326"
    shape: tuple[int, int] = (0, 0)
    path: str = ""


class DEMPipeline:
    """DEM 数据获取与预处理管线。"""

    def __init__(
        self,
        case_id: str,
        workspace: Path | str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ):
        self.case_id = case_id
        self.workspace = Path(workspace) if workspace else Path(__file__).resolve().parents[2]
        self.bbox = bbox
        self._case_dem_dir = self.workspace / "cases" / case_id / "dem"
        self._case_dem_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        """优先加载 case 本地 DEM，fallback 公开下载。"""
        local = self._try_local()
        if local:
            return local
        return self._try_download()

    def _try_local(self) -> dict[str, Any] | None:
        """扫描 case DEM 目录。"""
        for ext in ["*.tif", "*.tiff", "*.hgt", "*.nc", "*.asc"]:
            files = list(self._case_dem_dir.glob(ext))
            if files:
                dem_path = files[0]
                logger.info("Found local DEM: %s", dem_path)
                return self._read_dem(dem_path)

        config_dem = self.workspace / "Hydrology" / "configs"
        for f in config_dem.glob(f"{self.case_id}*dem*"):
            return self._read_dem(f)

        return None

    def _try_download(self) -> dict[str, Any]:
        """尝试从公开源下载 DEM。"""
        if not self.bbox:
            logger.warning("No bbox specified, cannot download DEM")
            return {"status": "no_bbox", "sources": list(DEM_SOURCES.keys())}

        for source_id in ["srtm_30m", "copernicus_30m"]:
            try:
                result = self.download(source_id)
                if result.get("status") == "ok":
                    return result
            except Exception as e:
                logger.warning("Download from %s failed: %s", source_id, e)

        return {"status": "download_failed", "sources_tried": list(DEM_SOURCES.keys())}

    def download(self, source: str = "srtm_30m") -> dict[str, Any]:
        """从指定来源下载 DEM。"""
        if source == "srtm_30m":
            return self._download_srtm()
        elif source == "copernicus_30m":
            return self._download_copernicus()
        else:
            raise ValueError(f"Unknown DEM source: {source}. Available: {list(DEM_SOURCES.keys())}")

    def _download_srtm(self) -> dict[str, Any]:
        """下载 SRTM HGT 瓦片。"""
        if not self.bbox:
            return {"status": "no_bbox"}

        lat_min, lon_min, lat_max, lon_max = self.bbox
        tiles = []
        for lat in range(int(np.floor(lat_min)), int(np.ceil(lat_max))):
            for lon in range(int(np.floor(lon_min)), int(np.ceil(lon_max))):
                ns = "N" if lat >= 0 else "S"
                ew = "E" if lon >= 0 else "W"
                tile_name = f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}.hgt"
                tiles.append((tile_name, lat, lon))

        downloaded = []
        for tile_name, lat, lon in tiles:
            out_path = self._case_dem_dir / tile_name
            if out_path.exists():
                downloaded.append(str(out_path))
                continue

            url = f"https://elevation-tiles-prod.s3.amazonaws.com/skadi/{tile_name[:3]}/{tile_name}"
            try:
                logger.info("Downloading SRTM tile: %s", url)
                urllib.request.urlretrieve(url, str(out_path))
                downloaded.append(str(out_path))
            except Exception as e:
                logger.warning("Failed to download %s: %s", tile_name, e)

        if not downloaded:
            return {"status": "no_tiles_downloaded"}

        return {
            "status": "ok",
            "source": "srtm_30m",
            "tiles": downloaded,
            "n_tiles": len(downloaded),
            "output_dir": str(self._case_dem_dir),
        }

    def _download_copernicus(self) -> dict[str, Any]:
        """Copernicus DEM 下载（需要注册，返回指引）。"""
        return {
            "status": "manual_download_required",
            "source": "copernicus_30m",
            "instructions": (
                "Copernicus DEM 需要在 https://spacedata.copernicus.eu 注册后下载。\n"
                f"下载后放入: {self._case_dem_dir}\n"
                f"BBOX: {self.bbox}"
            ),
        }

    def _read_dem(self, path: Path) -> dict[str, Any]:
        """读取 DEM 文件（支持 GeoTIFF, HGT, ASC）。"""
        ext = path.suffix.lower()

        if ext in [".tif", ".tiff"]:
            return self._read_geotiff(path)
        elif ext == ".hgt":
            return self._read_hgt(path)
        elif ext == ".asc":
            return self._read_asc(path)
        else:
            return {"status": "unsupported_format", "path": str(path)}

    def _read_geotiff(self, path: Path) -> dict[str, Any]:
        """读取 GeoTIFF DEM。"""
        try:
            import rasterio
            with rasterio.open(path) as ds:
                elev = ds.read(1)
                bounds = ds.bounds
                return {
                    "status": "ok",
                    "source": "local_geotiff",
                    "path": str(path),
                    "shape": elev.shape,
                    "bbox": (bounds.bottom, bounds.left, bounds.top, bounds.right),
                    "crs": str(ds.crs),
                    "resolution_m": abs(ds.transform[0]) * 111000,
                    "elevation_range": (float(np.nanmin(elev[elev > -9000])),
                                       float(np.nanmax(elev[elev < 9000]))),
                }
        except ImportError:
            return {"status": "rasterio_not_installed", "path": str(path)}

    def _read_hgt(self, path: Path) -> dict[str, Any]:
        """读取 SRTM HGT 文件。"""
        size = path.stat().st_size
        if size == 2884802:
            dim = 1201
        elif size == 25934402:
            dim = 3601
        else:
            return {"status": "unknown_hgt_size", "size": size}

        with open(path, "rb") as f:
            data = f.read()
        elev = np.frombuffer(data, dtype=">i2").reshape(dim, dim).astype(float)
        elev[elev == -32768] = np.nan

        name = path.stem
        lat = int(name[1:3]) * (1 if name[0] == "N" else -1)
        lon = int(name[4:7]) * (1 if name[3] == "E" else -1)

        return {
            "status": "ok",
            "source": "srtm_hgt",
            "path": str(path),
            "shape": (dim, dim),
            "bbox": (lat, lon, lat + 1, lon + 1),
            "crs": "EPSG:4326",
            "resolution_m": 30 if dim == 3601 else 90,
            "elevation_range": (float(np.nanmin(elev)), float(np.nanmax(elev))),
        }

    def _read_asc(self, path: Path) -> dict[str, Any]:
        """读取 ESRI ASCII Grid。"""
        header = {}
        with open(path) as f:
            for _ in range(6):
                line = f.readline().strip().split()
                if len(line) == 2:
                    header[line[0].lower()] = line[1]
        ncols = int(header.get("ncols", 0))
        nrows = int(header.get("nrows", 0))
        xll = float(header.get("xllcorner", 0))
        yll = float(header.get("yllcorner", 0))
        cellsize = float(header.get("cellsize", 0))
        nodata = float(header.get("nodata_value", -9999))

        return {
            "status": "ok",
            "source": "asc_grid",
            "path": str(path),
            "shape": (nrows, ncols),
            "bbox": (yll, xll, yll + nrows * cellsize, xll + ncols * cellsize),
            "resolution_m": cellsize * 111000,
        }

    def list_sources(self) -> list[dict[str, str]]:
        """列出可用 DEM 数据源。"""
        return [
            {"id": k, **{kk: str(vv) for kk, vv in v.items()}}
            for k, v in DEM_SOURCES.items()
        ]
