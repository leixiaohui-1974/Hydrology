# ALGORITHM_REGISTRY:
#   id: section_data_model
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""断面数据模型与解析器协议。

所有解析器实现 BaseSectionParser.parse() → list[SectionProfile]，
上层统一消费，不关心数据来源。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class SectionProfile:
    """单个断面的统一数据模型。"""

    id: str
    name: str
    yz: list[list[float]]
    location: float = 0.0
    channel: str = ""
    station: str = ""
    source_type: str = ""
    source_path: str = ""

    z_min: float = 0.0
    z_max: float = 0.0
    n_points: int = 0
    width: float = 0.0

    manning_n: float = 0.025
    geo_x1: float | None = None
    geo_y1: float | None = None
    geo_x2: float | None = None
    geo_y2: float | None = None

    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.yz:
            zs = [pt[1] for pt in self.yz]
            self.z_min = min(zs)
            self.z_max = max(zs)
            self.n_points = len(self.yz)
            ys = [pt[0] for pt in self.yz]
            self.width = max(ys) - min(ys) if len(ys) > 1 else 0.0


class BaseSectionParser(Protocol):
    """断面解析器协议——所有 parser 必须实现。"""

    def parse(self, path: str, **kwargs: Any) -> list[SectionProfile]:
        """解析文件，返回断面列表。"""
        ...

    @staticmethod
    def can_handle(path: str) -> bool:
        """判断此解析器能否处理该路径。"""
        ...
