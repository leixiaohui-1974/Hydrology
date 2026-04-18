"""DEM 地形分析与流域划分模块。

提供从 DEM 到子流域的完整流水线：
填洼 -> 流向 -> 汇流累积 -> 河网提取 -> 流域划分 -> 边界提取
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    from pysheds.grid import Grid
    HAS_PYSHEDS = True
except ImportError:
    HAS_PYSHEDS = False

try:
    import rasterio
    from rasterio.transform import from_bounds
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    from skimage.measure import find_contours
    HAS_SKIMAGE = True
except ImportError:
    HAS_SKIMAGE = False

try:
    import netCDF4
    HAS_NETCDF4 = True
except ImportError:
    HAS_NETCDF4 = False


@dataclass
class DEMData:
    """DEM 数据容器，存储高程矩阵及空间参考信息。"""

    elevation: np.ndarray       # 高程矩阵 (rows, cols)
    lat: np.ndarray             # 纬度数组
    lon: np.ndarray             # 经度数组
    crs: str = "EPSG:4326"
    nodata: float = -9999.0

    @property
    def resolution_m(self) -> float:
        """近似空间分辨率（米），以纬度步长估算。"""
        if len(self.lat) < 2:
            return 0.0
        return float(abs(self.lat[1] - self.lat[0]) * 111000.0)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """返回 (lon_min, lat_min, lon_max, lat_max)。"""
        return (
            float(np.min(self.lon)), float(np.min(self.lat)),
            float(np.max(self.lon)), float(np.max(self.lat)),
        )

    @classmethod
    def from_netcdf(cls, nc_path: str | Path) -> "DEMData":
        """从 NetCDF 文件加载 DEM，自动处理 scale_factor/add_offset。

        Args:
            nc_path: NetCDF 文件路径。

        Returns:
            DEMData 实例。
        """
        if not HAS_NETCDF4:
            raise ImportError("需要安装 netCDF4：pip install netCDF4")
        nc_path = Path(nc_path)
        if not nc_path.exists():
            raise FileNotFoundError(f"NetCDF 文件不存在：{nc_path}")
        with netCDF4.Dataset(str(nc_path), "r") as ds:
            elev_var_name: str | None = None
            for candidate in ("elevation", "dem", "z", "topo", "Band1", "height", "alt", "data"):
                if candidate in ds.variables:
                    elev_var_name = candidate
                    break
            if elev_var_name is None:
                for vname, var in ds.variables.items():
                    if var.ndim >= 2 and vname not in ("lat", "lon", "latitude", "longitude", "time"):
                        elev_var_name = vname
                        break
            if elev_var_name is None:
                raise ValueError(f"无法在 {nc_path} 中找到高程变量")
            lat_var_name: str | None = None
            lon_var_name: str | None = None
            for lname in ("lat", "latitude", "y", "Y"):
                if lname in ds.variables:
                    lat_var_name = lname
                    break
            for lname in ("lon", "longitude", "x", "X"):
                if lname in ds.variables:
                    lon_var_name = lname
                    break
            if lat_var_name is None or lon_var_name is None:
                raise ValueError(f"无法在 {nc_path} 中找到 lat/lon 变量")
            lat_arr = np.array(ds.variables[lat_var_name][:], dtype=np.float64)
            lon_arr = np.array(ds.variables[lon_var_name][:], dtype=np.float64)
            elev_var = ds.variables[elev_var_name]
            raw = np.array(elev_var[:], dtype=np.float64)
            while raw.ndim > 2:
                raw = raw[0]
            scale = float(getattr(elev_var, "scale_factor", 1.0))
            offset = float(getattr(elev_var, "add_offset", 0.0))
            if scale != 1.0 or offset != 0.0:
                raw = raw * scale + offset
            nodata_val = float(getattr(elev_var, "_FillValue",
                               getattr(elev_var, "missing_value", -9999.0)))
            crs_str = "EPSG:4326"
        raw[raw <= -9000] = nodata_val
        logger.info("从 NetCDF 加载 DEM：%s，形状 %s", nc_path.name, raw.shape)
        return cls(elevation=raw, lat=lat_arr, lon=lon_arr, crs=crs_str, nodata=nodata_val)

    @classmethod
    def from_tif(cls, tif_path: str | Path) -> "DEMData":
        """从 GeoTIFF 文件加载 DEM。

        Args:
            tif_path: GeoTIFF 文件路径。

        Returns:
            DEMData 实例。
        """
        if not HAS_RASTERIO:
            raise ImportError("需要安装 rasterio：pip install rasterio")
        tif_path = Path(tif_path)
        if not tif_path.exists():
            raise FileNotFoundError(f"TIF 文件不存在：{tif_path}")
        with rasterio.open(str(tif_path)) as src:
            elevation = src.read(1).astype(np.float64)
            transform = src.transform
            nrows, ncols = elevation.shape
            lon_arr = transform.c + transform.a * (np.arange(ncols) + 0.5)
            lat_arr = transform.f + transform.e * (np.arange(nrows) + 0.5)
            nodata_val = float(src.nodata) if src.nodata is not None else -9999.0
            crs_str = src.crs.to_string() if src.crs else "EPSG:4326"
        elevation[elevation <= -9000] = nodata_val
        logger.info("从 TIF 加载 DEM：%s，形状 %s", tif_path.name, elevation.shape)
        return cls(elevation=elevation, lat=lat_arr, lon=lon_arr, crs=crs_str, nodata=nodata_val)

    def to_tif(self, output_path: str | Path) -> Path:
        """将 DEM 数据写出为 GeoTIFF（pysheds 需要 TIF 输入）。

        Args:
            output_path: 输出文件路径。

        Returns:
            写出文件的 Path。
        """
        if not HAS_RASTERIO:
            raise ImportError("需要安装 rasterio：pip install rasterio")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lon_min, lat_min, lon_max, lat_max = self.bounds
        nrows, ncols = self.elevation.shape
        transform = from_bounds(lon_min, lat_min, lon_max, lat_max, ncols, nrows)
        with rasterio.open(
            str(path), "w", driver="GTiff",
            height=nrows, width=ncols, count=1,
            dtype=self.elevation.dtype, crs=self.crs,
            transform=transform, nodata=self.nodata,
        ) as dst:
            dst.write(self.elevation, 1)
        logger.info("DEM 写出到：%s", path)
        return path


@dataclass
class FlowDirectionResult:
    """流向分析结果容器。"""

    fdir: np.ndarray
    acc: np.ndarray
    filled_dem: np.ndarray
    dirmap: tuple = (64, 128, 1, 2, 4, 8, 16, 32)


@dataclass
class SubBasin:
    """单个子流域信息容器。"""

    basin_id: int
    name: str = ""
    mask: np.ndarray | None = None
    boundary: list[list[float]] = field(default_factory=list)
    area_km2: float = 0.0
    outlet_lat: float = 0.0
    outlet_lon: float = 0.0
    color: str = "#81C784"


@dataclass
class WatershedResult:
    """流域划分完整结果容器。"""

    dem: DEMData
    flow: FlowDirectionResult
    basins: list[SubBasin]
    total_area_km2: float = 0.0


class TerrainAnalyzer:
    """DEM 地形分析器，封装 pysheds 流向/汇流/流域划分功能。"""

    def __init__(self) -> None:
        """初始化分析器，检查 pysheds 依赖。"""
        if not HAS_PYSHEDS:
            raise ImportError(
                "需要安装 pysheds：pip install pysheds"
            )
        self._grid: Any = None
        self._dem_tif: str | None = None
        self._dem_data: DEMData | None = None

    def load_dem(self, dem: DEMData) -> None:
        """加载 DEM，写临时 TIF 并初始化 pysheds Grid。

        Args:
            dem: DEMData 实例。
        """
        if not HAS_RASTERIO:
            raise ImportError("load_dem 需要 rasterio：pip install rasterio")
        self._dem_data = dem
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tif", prefix="dem_terrain_")
        os.close(tmp_fd)
        self._dem_tif = tmp_path
        dem.to_tif(tmp_path)
        self._grid = Grid.from_raster(tmp_path)
        nrows, ncols = dem.elevation.shape
        logger.info("DEM 加载完成：形状 (%d, %d)，分辨率约 %.0f m，范围 %s",
                    nrows, ncols, dem.resolution_m, dem.bounds)

    def compute_flow_direction(self) -> FlowDirectionResult:
        """计算流向与汇流累积。

        流程：填坑 -> 填洼 -> 平地抬升 -> 流向(D8) -> 汇流累积。

        Returns:
            FlowDirectionResult 实例。
        """
        if self._grid is None or self._dem_tif is None:
            raise RuntimeError("请先调用 load_dem()")
        dirmap = (64, 128, 1, 2, 4, 8, 16, 32)
        dem_raster = self._grid.read_raster(self._dem_tif)
        pit_filled = self._grid.fill_pits(dem_raster)
        flooded = self._grid.fill_depressions(pit_filled)
        try:
            inflated = self._grid.resolve_flats(flooded, eps=1e-5)
        except TypeError:
            inflated = self._grid.resolve_flats(flooded)
        fdir = self._grid.flowdir(inflated, dirmap=dirmap)
        acc = self._grid.accumulation(fdir, dirmap=dirmap)
        max_acc = int(np.max(np.array(acc)))
        logger.info("流向计算完成，最大汇流累积值：%d 像元", max_acc)
        return FlowDirectionResult(
            fdir=np.array(fdir, dtype=np.int32),
            acc=np.array(acc, dtype=np.float64),
            filled_dem=np.array(inflated, dtype=np.float64),
            dirmap=dirmap,
        )

    def delineate_basins(
        self,
        flow: FlowDirectionResult,
        outlets: list[dict[str, Any]],
        subtract_upstream: bool = True,
    ) -> list[SubBasin]:
        """根据出口点划分子流域。

        Args:
            flow: 流向分析结果。
            outlets: 出口点列表，必须从上游到下游排序。
            subtract_upstream: 是否使用递减法。

        Returns:
            子流域列表。
        """
        if self._dem_data is None or self._grid is None:
            raise RuntimeError("请先调用 load_dem()")
        lat = self._dem_data.lat
        lon = self._dem_data.lon
        acc = flow.acc

        def lonlat_to_rowcol(lon_val: float, lat_val: float) -> tuple[int, int]:
            """经纬度转栅格行列索引。"""
            col = int(np.argmin(np.abs(lon - lon_val)))
            row = int(np.argmin(np.abs(lat - lat_val)))
            return row, col

        def snap_to_pour_point(row: int, col: int, radius: int = 15) -> tuple[int, int]:
            """在 radius 范围内找汇流累积最大像元（汇水点捕捉）。"""
            r_min = max(0, row - radius)
            r_max = min(acc.shape[0], row + radius + 1)
            c_min = max(0, col - radius)
            c_max = min(acc.shape[1], col + radius + 1)
            window = acc[r_min:r_max, c_min:c_max]
            idx = np.unravel_index(np.argmax(window), window.shape)
            return r_min + int(idx[0]), c_min + int(idx[1])

        raw_masks: list[np.ndarray] = []
        for o in outlets:
            row, col = lonlat_to_rowcol(float(o["lon"]), float(o["lat"]))
            row, col = snap_to_pour_point(row, col)
            try:
                catch = self._grid.catchment(x=col, y=row, fdir=flow.fdir,
                                              dirmap=flow.dirmap, xytype="index")
            except Exception:
                catch = self._grid.catchment(col, row, flow.fdir,
                                              dirmap=flow.dirmap, xytype="index")
            mask = np.array(catch, dtype=bool)
            raw_masks.append(mask)
            logger.info("  出口 %s：snap 到 (%d,%d)，集水面积 %d 像元",
                        o.get("name", ""), row, col, int(mask.sum()))

        if subtract_upstream:
            interval_masks: list[np.ndarray] = [raw_masks[0]]
            for i in range(1, len(raw_masks)):
                interval_masks.append(raw_masks[i] & ~raw_masks[i - 1])
        else:
            interval_masks = raw_masks

        cell_area_km2 = abs(float(lat[1] - lat[0])) * 111.0 * abs(float(lon[1] - lon[0])) * 95.0
        basins: list[SubBasin] = []
        for i, (mask, o) in enumerate(zip(interval_masks, outlets)):
            area = float(np.sum(mask)) * cell_area_km2
            boundary: list[list[float]] = []
            if HAS_SKIMAGE:
                contours = find_contours(mask.astype(float), 0.5)
                if contours:
                    longest = max(contours, key=len)
                    step = max(1, len(longest) // 300)
                    for pt in longest[::step]:
                        r = int(np.clip(pt[0], 0, len(lat) - 1))
                        c = int(np.clip(pt[1], 0, len(lon) - 1))
                        boundary.append([float(lat[r]), float(lon[c])])
                    if boundary:
                        boundary.append(boundary[0])
            else:
                rows_idx, cols_idx = np.where(mask)
                if len(rows_idx) > 0:
                    r0, r1 = int(rows_idx.min()), int(rows_idx.max())
                    c0, c1 = int(cols_idx.min()), int(cols_idx.max())
                    boundary = [
                        [float(lat[r0]), float(lon[c0])],
                        [float(lat[r0]), float(lon[c1])],
                        [float(lat[r1]), float(lon[c1])],
                        [float(lat[r1]), float(lon[c0])],
                        [float(lat[r0]), float(lon[c0])],
                    ]
            basin = SubBasin(
                basin_id=i + 1,
                name=o.get("name", f"区间{i+1}"),
                mask=mask,
                boundary=boundary,
                area_km2=area,
                outlet_lat=float(o["lat"]),
                outlet_lon=float(o["lon"]),
                color=o.get("color", "#81C784"),
            )
            basins.append(basin)
            logger.info("  子流域 %s：%.0f km2，%d 边界点", basin.name, area, len(boundary))
        return basins

    def extract_stream_network(self, flow: FlowDirectionResult, threshold: int = 500) -> np.ndarray:
        """基于汇流累积阈值提取河网栅格。

        Args:
            flow: 流向分析结果。
            threshold: 汇流累积阈值（像元数），默认 500。

        Returns:
            uint8 河网栅格（1=河道，0=非河道）。
        """
        streams = (flow.acc >= threshold).astype(np.uint8)
        logger.info("河网提取：阈值=%d，河网像元=%d", threshold, int(streams.sum()))
        return streams

    def calc_slope(self, dem: DEMData) -> np.ndarray:
        """计算坡度栅格（度）。

        Args:
            dem: DEMData 实例。

        Returns:
            与 DEM 同形状的坡度数组（0-90 度）。
        """
        dx = dem.resolution_m if dem.resolution_m > 0 else 30.0
        gy, gx = np.gradient(dem.elevation, dx)
        return np.degrees(np.arctan(np.sqrt(gx ** 2 + gy ** 2)))

    def calc_aspect(self, dem: DEMData) -> np.ndarray:
        """计算坡向栅格（度，北=0，顺时针）。

        Args:
            dem: DEMData 实例。

        Returns:
            与 DEM 同形状的坡向数组（0-360 度）。
        """
        dx = dem.resolution_m if dem.resolution_m > 0 else 30.0
        gy, gx = np.gradient(dem.elevation, dx)
        aspect = np.degrees(np.arctan2(-gx, gy))
        aspect[aspect < 0] += 360.0
        return aspect


    # D8 方向偏移约定（pysheds 标准：value -> (row_delta, col_delta)）
    _D8_OFFSETS: dict = {
        64: (-1, 0), 128: (-1, 1), 1: (0, 1),  2: (1, 1),
        4:  (1, 0),   8: (1, -1), 16: (0, -1), 32: (-1, -1),
    }

    def identify_main_stream(
        self,
        flow,
        min_acc_ratio=0.1,
    ):
        from numpy import argmax as _argmax
        if self._dem_data is None or self._grid is None:
            raise RuntimeError("请先调用 load_dem()")
        acc = flow.acc
        fdir = flow.fdir
        nrows, ncols = acc.shape
        flat_idx = int(_argmax(acc))
        outlet_r = flat_idx // ncols
        outlet_c = flat_idx % ncols
        max_acc = float(acc[outlet_r, outlet_c])
        threshold = max_acc * min_acc_ratio
        logger.info("主干追踪：出口 (%d,%d)，最大汇流累积 %.0f，停止阈值 %.0f", outlet_r, outlet_c, max_acc, threshold)
        main_stream = []
        visited = set()
        cur_r, cur_c = outlet_r, outlet_c
        while True:
            pos = (cur_r, cur_c)
            if pos in visited:
                break
            visited.add(pos)
            main_stream.append(pos)
            best_acc_val = -1.0
            best_r, best_c = -1, -1
            for dr, dc in [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]:
                nr, nc = cur_r + dr, cur_c + dc
                if nr < 0 or nr >= nrows or nc < 0 or nc >= ncols:
                    continue
                nbr_dir = int(fdir[nr, nc])
                if nbr_dir not in self._D8_OFFSETS:
                    continue
                n_dr, n_dc = self._D8_OFFSETS[nbr_dir]
                if cur_r == nr + n_dr and cur_c == nc + n_dc:
                    n_acc = float(acc[nr, nc])
                    if n_acc > best_acc_val:
                        best_acc_val = n_acc
                        best_r, best_c = nr, nc
            if best_r < 0 or best_acc_val < threshold:
                break
            cur_r, cur_c = best_r, best_c
        logger.info("主干追踪完成：共 %d 个像元", len(main_stream))
        return main_stream

    def find_confluences(
        self,
        flow,
        main_stream,
        min_tributary_ratio=0.05,
    ):
        if self._dem_data is None or self._grid is None:
            raise RuntimeError("请先调用 load_dem()")
        acc = flow.acc
        fdir = flow.fdir
        nrows, ncols = acc.shape
        max_acc = float(np.max(acc))
        trib_threshold = max_acc * min_tributary_ratio
        main_set = set(main_stream)
        confluence_map = {}
        for r, c in main_stream:
            acc_main = float(acc[r, c])
            for dr, dc in [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]:
                nr, nc = r + dr, c + dc
                if nr < 0 or nr >= nrows or nc < 0 or nc >= ncols:
                    continue
                if (nr, nc) in main_set:
                    continue
                nbr_dir = int(fdir[nr, nc])
                if nbr_dir not in self._D8_OFFSETS:
                    continue
                n_dr, n_dc = self._D8_OFFSETS[nbr_dir]
                if r == nr + n_dr and c == nc + n_dc:
                    trib_acc = float(acc[nr, nc])
                    if trib_acc < trib_threshold:
                        continue
                    key = (r, c)
                    if key not in confluence_map:
                        confluence_map[key] = {"row": r, "col": c, "acc_main": acc_main, "acc_tributary": trib_acc}
                    elif trib_acc > confluence_map[key]["acc_tributary"]:
                        confluence_map[key]["acc_tributary"] = trib_acc
        confluences = sorted(confluence_map.values(), key=lambda x: x["acc_tributary"], reverse=True)
        logger.info("支流汇合点识别完成：阈值 acc=%.0f，共 %d 个汇合点", trib_threshold, len(confluences))
        return confluences

    def generate_gauging_stations(
        self,
        flow,
        n_stations=5,
        include_outlet=True,
    ):
        if self._dem_data is None or self._grid is None:
            raise RuntimeError("请先调用 load_dem()")
        lat = self._dem_data.lat
        lon = self._dem_data.lon
        main_stream = self.identify_main_stream(flow)
        confluences = self.find_confluences(flow, main_stream)
        main_index = {pos: idx for idx, pos in enumerate(main_stream)}

        def _make_station(row, col, stype, sid):
            return {"station_id": sid, "x": float(lon[col]), "y": float(lat[row]), "type": stype, "row": row, "col": col}

        stations = []
        seen = set()
        if include_outlet and main_stream:
            r0, c0 = main_stream[0]
            stations.append(_make_station(r0, c0, "outlet", "outlet"))
            seen.add((r0, c0))
        conf_count = 0
        for conf in confluences:
            if conf_count >= n_stations:
                break
            pos = (conf["row"], conf["col"])
            if pos in seen or pos not in main_index:
                continue
            conf_count += 1
            stations.append(_make_station(pos[0], pos[1], "confluence", f"confluence_{conf_count}"))
            seen.add(pos)
        if main_stream:
            rh, ch = main_stream[-1]
            if (rh, ch) not in seen:
                stations.append(_make_station(rh, ch, "headwater", "headwater"))
                seen.add((rh, ch))
        stations.sort(key=lambda s: main_index.get((s["row"], s["col"]), 0), reverse=True)
        logger.info("水文站生成完成：共 %d 个站点（汇合点 %d 个，出口=%s）", len(stations), conf_count, include_outlet)
        return stations

    def partition_by_stations(
        self,
        flow,
        stations,
        subbasins_mask=None,
    ):
        if self._dem_data is None or self._grid is None:
            raise RuntimeError("请先调用 load_dem()")

        # pysheds catchment() 需要 Raster 对象（带 nodata 属性），重新计算一次 fdir Raster
        _dem_raster = self._grid.read_raster(self._dem_tif)
        _pit = self._grid.fill_pits(_dem_raster)
        _flood = self._grid.fill_depressions(_pit)
        try:
            _infl = self._grid.resolve_flats(_flood, eps=1e-5)
        except TypeError:
            _infl = self._grid.resolve_flats(_flood)
        _fdir_raster = self._grid.flowdir(_infl, dirmap=flow.dirmap)

        def _catchment(row, col):
            try:
                catch = self._grid.catchment(x=col, y=row, fdir=_fdir_raster, dirmap=flow.dirmap, xytype="index")
            except Exception:
                catch = self._grid.catchment(col, row, _fdir_raster, dirmap=flow.dirmap, xytype="index")
            return np.array(catch, dtype=bool)

        raw_masks = []
        for st in stations:
            r, c = st["row"], st["col"]
            mask = _catchment(r, c)
            raw_masks.append(mask)
            logger.info("  站点 %s (%d,%d)：集水面积 %d 像元", st["station_id"], r, c, int(mask.sum()))
        result = {}
        for i, st in enumerate(stations):
            if i == 0:
                zone = raw_masks[0].copy()
            else:
                zone = raw_masks[i] & ~raw_masks[i - 1]
            key = f"zone_{st['station_id']}"
            result[key] = zone
            logger.info("  分区 %s：%d 像元", key, int(zone.sum()))
        logger.info("参数分区划分完成：共 %d 个分区", len(result))
        return result

    def cleanup(self) -> None:
        """清理临时文件，释放资源。"""
        if self._dem_tif and os.path.exists(self._dem_tif):
            try:
                os.unlink(self._dem_tif)
                logger.debug("已删除临时文件：%s", self._dem_tif)
            except OSError as exc:
                logger.warning("删除临时文件失败：%s，原因：%s", self._dem_tif, exc)
            finally:
                self._dem_tif = None
