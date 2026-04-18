# ALGORITHM_REGISTRY:
#   id: section_analysis_config
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""断面分析配置。配置驱动，零硬编码。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SectionAnalysisConfig:
    """断面分析全局配置——全部从 Case YAML 注入，不写死任何值。"""

    case_id: str = ""
    n_levels: int = 30
    manning_n_default: float = 0.025
    output_curves: list[str] = field(default_factory=lambda: ["A", "P", "B", "R"])

    sources: list[dict[str, Any]] = field(default_factory=list)
    """多数据源声明。每项示例:
    {"type": "wxq_json", "path": "wxq-1d/.../xxx.json", "channel_map": {...}}
    {"type": "terrain_txt", "path": ".../龚嘴.txt", "station": "s5", "encoding": "gbk"}
    {"type": "xlsx_terrain", "path": ".../河道地形.xlsx", "channel": "sm-pbg"}
    """

    channels: list[dict[str, Any]] = field(default_factory=list)
    """河段定义（从 Case YAML topology.channels 注入）。"""

    reservoir_levels: dict[str, dict[str, float]] = field(default_factory=dict)
    """水库特征水位。key=station_id, val={"normal_pool": x, "dead_pool": y}"""

    @classmethod
    def from_case_config(cls, cfg: dict[str, Any]) -> "SectionAnalysisConfig":
        """从 Case YAML 字典构建。"""
        sa = cfg.get("section_analysis", {})
        topo = cfg.get("knowledge", {}).get("topology", {})
        reservoirs = cfg.get("knowledge", {}).get("reservoirs", {})

        channels = topo.get("channels", [])
        if isinstance(channels, dict):
            channels = list(channels.values())

        res_levels: dict[str, dict[str, float]] = {}
        if isinstance(reservoirs, dict):
            for name, info in reservoirs.items():
                if isinstance(info, dict):
                    sid = info.get("station_id", name)
                    np_val = info.get("normal_pool") or info.get("normal_pool_m") or info.get("normal_level") or 0
                    dp_val = info.get("dead_pool") or info.get("dead_pool_m") or info.get("dead_level") or 0
                    if np_val and dp_val:
                        res_levels[sid] = {
                            "normal_pool": float(np_val),
                            "dead_pool": float(dp_val),
                        }

        return cls(
            case_id=cfg.get("case_id", ""),
            n_levels=sa.get("n_levels", 30),
            manning_n_default=sa.get("manning_n_default", 0.025),
            output_curves=sa.get("output_curves", ["A", "P", "B", "R"]),
            sources=sa.get("sources", []),
            channels=channels,
            reservoir_levels=res_levels,
        )
