# ALGORITHM_REGISTRY:
#   id: wxq_json_section_parser
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""wxq 智能体 JSON 断面解析器。

支持格式:
  - 11150大渡河智能体.json
  - model_xxx.json (wxq export)
  - 任何包含 baseData.sections 结构的 JSON
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import BaseSectionParser, SectionProfile


class WxqJsonParser:
    """从 wxq 模型 JSON 提取所有断面。"""

    @staticmethod
    def can_handle(path: str) -> bool:
        return path.endswith(".json")

    def parse(
        self,
        path: str,
        *,
        channel_map: dict[str, dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> list[SectionProfile]:
        """解析 wxq JSON 返回断面列表。

        channel_map 示例:
          {"sm-pbg": {"station": "s1", "prefix": ["SP", "DM"], "manning_n": 0.015}}
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        root_key = list(data.keys())[0]
        bd = data[root_key].get("baseData", {})
        raw_sections = bd.get("sections", {})

        prefix_to_info: dict[str, dict[str, Any]] = {}
        if channel_map:
            for ch_name, ch_meta in channel_map.items():
                for pfx in ch_meta.get("prefix", []):
                    prefix_to_info[pfx] = {
                        "channel": ch_name,
                        "station": ch_meta.get("station", ""),
                        "manning_n": ch_meta.get("manning_n", 0.025),
                    }

        results: list[SectionProfile] = []
        for k, v in raw_sections.items():
            yz = v.get("yz", [])
            if not yz:
                continue

            name = str(v.get("name", k))

            ch_info: dict[str, Any] = {}
            for pfx, info in prefix_to_info.items():
                if name.startswith(pfx):
                    ch_info = info
                    break

            results.append(SectionProfile(
                id=str(k),
                name=name,
                yz=yz,
                location=float(v.get("location", 0)),
                channel=ch_info.get("channel", ""),
                station=ch_info.get("station", ""),
                source_type="wxq_json",
                source_path=path,
                manning_n=ch_info.get("manning_n", 0.025),
                geo_x1=v.get("x1"),
                geo_y1=v.get("y1"),
                geo_x2=v.get("x2"),
                geo_y2=v.get("y2"),
            ))

        return results
