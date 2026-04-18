# ALGORITHM_REGISTRY:
#   id: terrain_txt_section_parser
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""河道地形 TXT 断面解析器。

支持格式:
  - 龚嘴.txt / 铜街子.txt（GBK/GB2312 编码）
  - 每个断面以 "断面 X" 或 "Section X" 行开头
  - 后续行为 (y, z) 坐标对
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..base import SectionProfile

_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin1"]


class TerrainTxtParser:
    """从河道地形 TXT 文件解析断面。"""

    @staticmethod
    def can_handle(path: str) -> bool:
        return path.endswith(".txt")

    def parse(
        self,
        path: str,
        *,
        station: str = "",
        channel: str = "",
        encoding: str | None = None,
        section_pattern: str | None = None,
        **kwargs: Any,
    ) -> list[SectionProfile]:
        text = self._read_with_fallback(path, encoding)
        if section_pattern:
            pat = re.compile(section_pattern)
        else:
            pat = re.compile(r"^(?:断面|section|cs|CS)\s*(\S+)", re.IGNORECASE)

        sections: list[SectionProfile] = []
        current_name: str | None = None
        current_yz: list[list[float]] = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            m = pat.match(line)
            if m:
                if current_name is not None and current_yz:
                    sections.append(self._build_profile(
                        current_name, current_yz, path, station, channel, len(sections),
                    ))
                current_name = m.group(1)
                current_yz = []
                continue

            nums = re.findall(r"[-+]?\d*\.?\d+", line)
            if len(nums) >= 2:
                current_yz.append([float(nums[0]), float(nums[1])])

        if current_name is not None and current_yz:
            sections.append(self._build_profile(
                current_name, current_yz, path, station, channel, len(sections),
            ))

        return sections

    @staticmethod
    def _build_profile(
        name: str, yz: list[list[float]], path: str,
        station: str, channel: str, idx: int,
    ) -> SectionProfile:
        return SectionProfile(
            id=f"{station}_{name}" if station else name,
            name=name,
            yz=yz,
            location=float(idx),
            channel=channel,
            station=station,
            source_type="terrain_txt",
            source_path=path,
        )

    @staticmethod
    def _read_with_fallback(path: str, preferred: str | None = None) -> str:
        encodings = [preferred] + _ENCODINGS if preferred else _ENCODINGS
        for enc in encodings:
            if not enc:
                continue
            try:
                return Path(path).read_text(encoding=enc)
            except (UnicodeDecodeError, LookupError):
                continue
        raise UnicodeDecodeError("all", b"", 0, 1, f"Failed to decode {path} with any encoding")
