"""Hydrology Skill 接口 - 可注册为 Claude Code Skill。"""
from __future__ import annotations

from typing import Any, Callable


SKILL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "流域划分": {
        "description": "从 DEM 自动划分子流域，输出边界多边形和面积。",
        "usage": "/流域划分 <dem_path> <outlets_json>",
        "handler": "terrain_analysis.TerrainAnalyzer.delineate_basins",
    },
    "产汇流计算": {
        "description": "运行水文模型（Horton/新安江/SCS + Muskingum），输出出口流量。",
        "usage": "/产汇流计算 <config_yaml>",
        "handler": "model.HydrologicalModel.step",
    },
    "面雨量": {
        "description": "从雨量站数据插值计算各子流域面雨量。",
        "usage": "/面雨量 <method> <stations_csv> <subbasins_shp>",
        "handler": "areal_precipitation.ArealPrecipitationCalculator",
    },
    "DEM分析": {
        "description": "DEM 填洼、流向、汇流累积、坡度、坡向。",
        "usage": "/DEM分析 <dem_path>",
        "handler": "terrain_analysis.TerrainAnalyzer",
    },
}


class SkillRegistry:
    """技能注册表，管理可调用的水文分析技能。"""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, handler: Callable[..., Any]) -> None:
        """注册技能处理函数。"""
        self._handlers[name] = handler

    def call(self, name: str, **kwargs: Any) -> Any:
        """调用已注册的技能，未找到时抛 KeyError。"""
        if name not in self._handlers:
            raise KeyError(f"技能 {name!r} 未注册")
        return self._handlers[name](**kwargs)

    def list_skills(self) -> list[dict[str, str]]:
        """返回所有可用技能列表，每项包含 name/description/usage。"""
        result: list[dict[str, str]] = []
        for sname, meta in SKILL_DEFINITIONS.items():
            result.append({
                "name": sname,
                "description": meta["description"],
                "usage": meta["usage"],
                "registered": str(sname in self._handlers),
            })
        return result

    @classmethod
    def from_definitions(cls) -> "SkillRegistry":
        """从 SKILL_DEFINITIONS 创建实例，handlers 留空。"""
        return cls()


def run_watershed_delineation(
    dem_path: str,
    outlets: list[dict[str, Any]],
    subtract_upstream: bool = True,
) -> dict[str, Any]:
    """流域划分便捷函数：load_dem -> compute_flow_direction -> delineate_basins。

    Args:
        dem_path: DEM 文件路径。
        outlets: 出口点列表，每项包含 lon/lat/name。
        subtract_upstream: 是否递减法。

    Returns:
        {"basins": [...], "total_area_km2": float}
    """
    from .terrain_analysis import TerrainAnalyzer, DEMData
    if dem_path.lower().endswith(".nc"):
        dem = DEMData.from_netcdf(dem_path)
    else:
        dem = DEMData.from_tif(dem_path)
    analyzer = TerrainAnalyzer()
    analyzer.load_dem(dem)
    flow = analyzer.compute_flow_direction()
    basins = analyzer.delineate_basins(flow, outlets, subtract_upstream=subtract_upstream)
    total_area = sum(b.area_km2 for b in basins)
    analyzer.cleanup()
    return {
        "basins": [{"name": b.name, "area_km2": b.area_km2, "boundary": b.boundary} for b in basins],
        "total_area_km2": total_area,
    }


def run_whitebox_watershed_delineation(
    dem_path: str,
    outlets: list[dict[str, Any]],
    subtract_upstream: bool = True,
    stream_threshold: float = 100.0,
    snap_distance: float = 250.0,
) -> dict[str, Any]:
    """WhiteboxTools 主线流域划分。"""
    from .whitebox_delineation import run_whitebox_watershed_delineation as _runner

    return _runner(
        dem_path=dem_path,
        outlets=outlets,
        subtract_upstream=subtract_upstream,
        stream_threshold=stream_threshold,
        snap_distance=snap_distance,
    )


def run_runoff_simulation(
    catchment_config: dict[str, Any],
    forcing: dict[str, list[float]],
    num_steps: int,
    dt: float = 3600.0,
) -> dict[str, Any]:
    """产汇流仿真便捷函数。

    Args:
        catchment_config: 流域参数字典。
        forcing: 驱动数据（precip/pet 序列）。
        num_steps: 仿真步数。
        dt: 时间步长（秒），默认 3600 s。

    Returns:
        {"flows": {...}, "steps": num_steps}
    """
    from .model import HydrologicalModel
    model = HydrologicalModel(dt=dt)
    flows: dict[str, list[float]] = {}
    for step_i in range(num_steps):
        result = model.step(
            headwater_inflows={k: v[step_i] for k, v in forcing.items() if step_i < len(v)},
            lateral_inflows={},
        )
        for node_id, flow_val in result.items():
            flows.setdefault(str(node_id), []).append(float(flow_val))
    return {"flows": flows, "steps": num_steps}


def calc_areal_rainfall(
    method: str,
    stations: list[dict[str, Any]],
    rainfall_data: list[list[float]],
    subbasin_polygons: list[list[Any]] | None = None,
) -> dict[str, Any]:
    """面雨量计算便捷函数。

    Args:
        method: 计算方法（idw/thiessen/kriging）。
        stations: 雨量站列表，每项含 lon/lat/id。
        rainfall_data: 降水数据 [n_stations][n_timesteps]。
        subbasin_polygons: 子流域多边形列表（可选）。

    Returns:
        {"method": method, "results": [...]}
    """
    from .areal_precipitation import ArealPrecipitationCalculator
    calculator = ArealPrecipitationCalculator(stations=stations, method=method)
    results = calculator.calculate(rainfall_data, subbasin_polygons)
    return {"method": method, "results": results}


def analyze_dem_terrain(dem_path: str) -> dict[str, Any]:
    """DEM 地形分析便捷函数：填洼、流向、坡度、坡向。

    Args:
        dem_path: DEM 文件路径。

    Returns:
        分辨率、高程范围、坡度统计、坡向统计。
    """
    import numpy as np
    from .terrain_analysis import TerrainAnalyzer, DEMData
    if dem_path.lower().endswith(".nc"):
        dem = DEMData.from_netcdf(dem_path)
    else:
        dem = DEMData.from_tif(dem_path)
    analyzer = TerrainAnalyzer()
    slope = analyzer.calc_slope(dem)
    aspect = analyzer.calc_aspect(dem)
    valid_elev = dem.elevation[dem.elevation > dem.nodata + 1]
    valid_slope = slope[np.isfinite(slope)]
    valid_aspect = aspect[np.isfinite(aspect)]
    return {
        "resolution_m": dem.resolution_m,
        "elevation_range": [float(valid_elev.min()), float(valid_elev.max())],
        "slope_stats": {
            "mean": float(np.mean(valid_slope)),
            "max": float(np.max(valid_slope)),
            "p90": float(np.percentile(valid_slope, 90)),
        },
        "aspect_stats": {
            "mean": float(np.mean(valid_aspect)),
            "std": float(np.std(valid_aspect)),
        },
    }
