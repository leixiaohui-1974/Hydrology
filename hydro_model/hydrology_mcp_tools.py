"""Hydrology MCP 工具集 - 将水文模型能力暴露为标准 MCP 工具。"""
from __future__ import annotations

from typing import Any

import numpy as np


# MCP 工具描述符（符合 MCP 2024-11-05 规范）
HYDROLOGY_TOOL_DESCRIPTORS: list[dict[str, Any]] = [
    {
        "name": "hydrology.terrain.analyze_dem",
        "description": "DEM 地形分析：填洼、流向、汇流累积。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dem_path": {"type": "string", "description": "DEM 文件路径（.nc 或 .tif）"},
            },
            "required": ["dem_path"],
        },
    },
    {
        "name": "hydrology.terrain.delineate_basins",
        "description": "流域划分：根据出口点从 DEM 划分子流域。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dem_path": {"type": "string"},
                "outlets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "lon": {"type": "number"},
                            "lat": {"type": "number"},
                        },
                        "required": ["lon", "lat"],
                    },
                },
                "subtract_upstream": {"type": "boolean", "default": True},
            },
            "required": ["dem_path", "outlets"],
        },
    },
    {
        "name": "hydrology.terrain.calc_slope",
        "description": "计算坡度栅格（度）。",
        "inputSchema": {
            "type": "object",
            "properties": {"dem_path": {"type": "string"}},
            "required": ["dem_path"],
        },
    },
    {
        "name": "hydrology.terrain.extract_streams",
        "description": "基于汇流累积提取河网。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dem_path": {"type": "string"},
                "threshold": {"type": "integer", "default": 500},
            },
            "required": ["dem_path"],
        },
    },
    {
        "name": "hydrology.model.create_catchment",
        "description": "创建河网拓扑（Catchment），配置产流+汇流模型。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "nodes": {"type": "array", "items": {"type": "object"}},
                "reaches": {"type": "array", "items": {"type": "object"}},
                "runoff_type": {"type": "string", "enum": ["horton", "scs", "xinanjiang", "simple"]},
                "routing_type": {"type": "string", "enum": ["muskingum", "muskingum_cunge", "simple"]},
            },
            "required": ["nodes", "reaches"],
        },
    },
    {
        "name": "hydrology.model.run_simulation",
        "description": "运行水文模型仿真。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "headwater_inflows": {"type": "object"},
                "lateral_inflows": {"type": "object"},
                "num_steps": {"type": "integer"},
                "dt_seconds": {"type": "number", "default": 3600},
            },
            "required": ["num_steps"],
        },
    },
    {
        "name": "hydrology.precip.areal_rainfall",
        "description": "面雨量计算（IDW/Thiessen/Kriging）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["idw", "thiessen", "kriging"]},
                "stations": {"type": "array"},
                "rainfall_data": {"type": "array"},
                "subbasin_polygons": {"type": "array"},
            },
            "required": ["method", "stations", "rainfall_data"],
        },
    },
]


class HydrologyMCPHandler:
    """处理 MCP 工具调用，管理 TerrainAnalyzer 和 Catchment 状态。"""

    def __init__(self) -> None:
        self._analyzer: Any = None   # TerrainAnalyzer 实例缓存
        self._flow: Any = None       # FlowDirectionResult 缓存
        self._dem: Any = None        # DEMData 缓存
        self._catchment: Any = None  # Catchment 实例缓存

    def call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """分发工具调用到对应私有方法。

        Args:
            tool_name: MCP 工具名称。
            params: 工具输入参数字典。

        Returns:
            工具执行结果字典，失败时包含 error 键。
        """
        dispatch: dict[str, Any] = {
            "hydrology.terrain.analyze_dem": self._analyze_dem,
            "hydrology.terrain.delineate_basins": self._delineate_basins,
            "hydrology.terrain.calc_slope": self._calc_slope,
            "hydrology.terrain.extract_streams": self._extract_streams,
            "hydrology.model.create_catchment": self._create_catchment,
            "hydrology.model.run_simulation": self._run_simulation,
            "hydrology.precip.areal_rainfall": self._areal_rainfall,
        }
        handler = dispatch.get(tool_name)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return handler(params)
        except Exception as exc:
            return {"error": str(exc)}

    def _analyze_dem(self, params: dict[str, Any]) -> dict[str, Any]:
        """加载 DEM 并计算流向与汇流累积量。

        Args:
            params: 包含 dem_path 的参数字典。

        Returns:
            DEM 形状、分辨率、高程范围和最大汇流累积量。
        """
        from .terrain_analysis import TerrainAnalyzer, DEMData
        dem_path: str = params["dem_path"]
        if dem_path.lower().endswith(".nc") or dem_path.lower().endswith(".netcdf"):
            dem = DEMData.from_netcdf(dem_path)
        else:
            dem = DEMData.from_tif(dem_path)
        self._analyzer = TerrainAnalyzer()
        self._analyzer.load_dem(dem)
        self._flow = self._analyzer.compute_flow_direction()
        self._dem = dem
        valid = dem.elevation[dem.elevation > -9000]
        return {
            "status": "success",
            "dem_shape": list(dem.elevation.shape),
            "resolution_m": dem.resolution_m,
            "elevation_range": [float(valid.min()), float(valid.max())],
            "max_accumulation": int(np.max(self._flow.acc)),
        }

    def _delineate_basins(self, params: dict[str, Any]) -> dict[str, Any]:
        """划分子流域，若尚未分析 DEM 则自动调用 _analyze_dem。

        Args:
            params: 包含 dem_path、outlets、subtract_upstream 的参数字典。

        Returns:
            子流域列表（名称、面积、边界点数）。
        """
        if self._analyzer is None:
            result = self._analyze_dem(params)
            if "error" in result:
                return result
        basins = self._analyzer.delineate_basins(
            self._flow, params["outlets"],
            subtract_upstream=params.get("subtract_upstream", True),
        )
        return {
            "status": "success",
            "basins": [
                {"name": b.name, "area_km2": b.area_km2, "n_boundary_points": len(b.boundary)}
                for b in basins
            ],
        }

    def _calc_slope(self, params: dict[str, Any]) -> dict[str, Any]:
        """计算坡度统计信息。

        Args:
            params: 包含 dem_path 的参数字典。

        Returns:
            坡度均值、最大值和 90 分位数。
        """
        from .terrain_analysis import DEMData, TerrainAnalyzer
        dem_path: str = params["dem_path"]
        if dem_path.lower().endswith(".nc"):
            dem = DEMData.from_netcdf(dem_path)
        else:
            dem = DEMData.from_tif(dem_path)
        analyzer = TerrainAnalyzer()
        slope = analyzer.calc_slope(dem)
        valid = slope[np.isfinite(slope)]
        return {
            "status": "success",
            "slope_stats": {
                "mean": float(np.mean(valid)),
                "max": float(np.max(valid)),
                "p90": float(np.percentile(valid, 90)),
            },
        }

    def _extract_streams(self, params: dict[str, Any]) -> dict[str, Any]:
        """提取河网，若无缓存先调用 _analyze_dem。

        Args:
            params: 包含 dem_path、threshold 的参数字典。

        Returns:
            河网像元数和占比。
        """
        if self._analyzer is None:
            result = self._analyze_dem(params)
            if "error" in result:
                return result
        threshold = int(params.get("threshold", 500))
        streams = self._analyzer.extract_stream_network(self._flow, threshold=threshold)
        total = streams.size
        return {
            "status": "success",
            "threshold": threshold,
            "stream_pixels": int(streams.sum()),
            "stream_fraction": float(streams.sum()) / total,
        }

    def _create_catchment(self, params: dict[str, Any]) -> dict[str, Any]:
        """构建 Catchment 拓扑。

        Args:
            params: 包含 nodes、reaches 等的参数字典。

        Returns:
            节点数和河段数。
        """
        from .catchment import Catchment
        from .routing import MuskingumRouting, SimpleRouting
        catchment = Catchment()
        for node in params.get("nodes", []):
            catchment.add_node(node["id"])
        routing_type = params.get("routing_type", "simple")
        for reach in params.get("reaches", []):
            if routing_type == "muskingum":
                routing = MuskingumRouting(k=reach.get("k", 1.0), x=reach.get("x", 0.2))
            else:
                routing = SimpleRouting(k=reach.get("k", 1.0))
            catchment.add_reach(reach["id"], reach["upstream"], reach["downstream"], routing)
        self._catchment = catchment
        return {
            "status": "success",
            "n_nodes": len(catchment.nodes),
            "n_reaches": len(catchment.reaches),
        }

    def _run_simulation(self, params: dict[str, Any]) -> dict[str, Any]:
        """运行仿真，需要先调用 _create_catchment。

        Args:
            params: 包含 num_steps 等的参数字典。

        Returns:
            出口流量序列。
        """
        from .model import HydrologicalModel
        if self._catchment is None:
            return {"error": "请先调用 create_catchment"}
        num_steps = int(params["num_steps"])
        dt = float(params.get("dt_seconds", 3600.0))
        model = HydrologicalModel(dt=dt)
        model.catchment = self._catchment
        headwater = params.get("headwater_inflows", {})
        lateral = params.get("lateral_inflows", {})
        outlet_flows: list[float] = []
        for _ in range(num_steps):
            flows = model.step(headwater_inflows=headwater, lateral_inflows=lateral)
            outlet_flows.append(float(list(flows.values())[-1]) if flows else 0.0)
        return {
            "status": "success",
            "steps": num_steps,
            "outlet_flows": outlet_flows,
        }

    def _areal_rainfall(self, params: dict[str, Any]) -> dict[str, Any]:
        """计算面雨量。

        Args:
            params: 包含 method、stations、rainfall_data 的参数字典。

        Returns:
            各子流域面雨量结果。
        """
        from .areal_precipitation import ArealPrecipitationCalculator
        method = str(params["method"])
        calculator = ArealPrecipitationCalculator(
            stations=params["stations"],
            method=method,
        )
        rainfall_data = params["rainfall_data"]
        results = calculator.calculate(rainfall_data, params.get("subbasin_polygons"))
        return {
            "status": "success",
            "method": method,
            "n_subbasins": len(results) if results else 0,
            "results": results if isinstance(results, list) else [],
        }
