# ALGORITHM_REGISTRY:
#   id: section_parser_registry
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""断面解析器注册表。

自动发现并注册所有解析器，工作流通过 source["type"] 动态路由。
"""
from __future__ import annotations

from typing import Any

from ..base import BaseSectionParser, SectionProfile

PARSER_REGISTRY: dict[str, type] = {}


def register_parser(name: str, cls: type) -> None:
    PARSER_REGISTRY[name] = cls


def get_parser(source_type: str) -> BaseSectionParser:
    if source_type not in PARSER_REGISTRY:
        raise ValueError(
            f"Unknown parser '{source_type}'. Available: {list(PARSER_REGISTRY.keys())}"
        )
    return PARSER_REGISTRY[source_type]()


def parse_source(source: dict[str, Any]) -> list[SectionProfile]:
    """根据 source 字典路由到对应 parser。"""
    src_type = source.get("type", "")
    parser = get_parser(src_type)
    path = source.get("path", "")
    kwargs = {k: v for k, v in source.items() if k not in ("type", "path")}
    return parser.parse(path, **kwargs)


def _auto_register() -> None:
    from .wxq_json import WxqJsonParser
    register_parser("wxq_json", WxqJsonParser)

    from .terrain_txt import TerrainTxtParser
    register_parser("terrain_txt", TerrainTxtParser)

    from .wxq_terrain_txt import WxqTerrainTxtParser
    register_parser("wxq_terrain_txt", WxqTerrainTxtParser)

    from .xlsx_terrain import XlsxTerrainParser
    register_parser("xlsx_terrain", XlsxTerrainParser)


_auto_register()

__all__ = [
    "PARSER_REGISTRY", "register_parser", "get_parser", "parse_source",
]
