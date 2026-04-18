# ALGORITHM_REGISTRY:
#   id: wxq_terrain_txt_section_parser
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""wxq 导出河道地形 TXT 解析器。

支持格式（龚嘴.txt / 铜街子.txt 等）:
  行1: "河道地形"
  行2: 断面总数 N
  后续每个断面两行:
    序号 断面名 桩号 糙率
    形状类型 [1] [参数...]
      梯形: 梯形 1 宽度 河底高程 顶高程 边坡
      不规则形: 不规则形 1 点数 y1 z1 y2 z2 ...

支持编码: UTF-8 / GBK / GB2312 / GB18030 自动检测。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..base import SectionProfile

_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin1"]


class WxqTerrainTxtParser:
    """解析 wxq 导出的河道地形 TXT。"""

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
        **kwargs: Any,
    ) -> list[SectionProfile]:
        text = self._read_with_fallback(path, encoding)
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        if len(lines) < 3:
            return []
        if "河道地形" not in lines[0]:
            return []

        try:
            n_sections = int(re.findall(r"\d+", lines[1])[0])
        except (IndexError, ValueError):
            return []

        sections: list[SectionProfile] = []
        idx = 2
        while idx + 1 < len(lines) and len(sections) < n_sections:
            header = lines[idx]
            data = lines[idx + 1]
            idx += 2

            profile = self._parse_pair(header, data, path, station, channel)
            if profile:
                sections.append(profile)

        return sections

    def _parse_pair(
        self, header: str, data: str, path: str, station: str, channel: str,
    ) -> SectionProfile | None:
        h_parts = header.split("\t")
        if len(h_parts) < 3:
            h_parts = header.split()
        if len(h_parts) < 3:
            return None

        try:
            sec_name = h_parts[1]
            location = float(h_parts[2])
            manning_n = float(h_parts[3]) if len(h_parts) > 3 else 0.025
        except (ValueError, IndexError):
            return None

        d_parts = data.split("\t")
        if len(d_parts) < 2:
            d_parts = data.split()

        shape_type = d_parts[0] if d_parts else ""

        if "梯形" in shape_type:
            yz = self._parse_trapezoidal(d_parts)
        elif "不规则" in shape_type:
            yz = self._parse_irregular(d_parts)
        else:
            return None

        if not yz or len(yz) < 2:
            return None

        return SectionProfile(
            id=f"{station}_{sec_name}" if station else sec_name,
            name=sec_name,
            yz=yz,
            location=location,
            channel=channel,
            station=station,
            source_type="wxq_terrain_txt",
            source_path=path,
            manning_n=manning_n,
        )

    @staticmethod
    def _parse_trapezoidal(parts: list[str]) -> list[list[float]]:
        """梯形: 梯形 1 宽度 河底高程 顶高程 边坡"""
        nums = []
        for p in parts:
            try:
                nums.append(float(p))
            except ValueError:
                continue
        if len(nums) < 4:
            return []
        _, width, z_bed, z_top = nums[0], nums[1], nums[2], nums[3]
        slope = nums[4] if len(nums) > 4 else 1.0
        depth = z_top - z_bed
        top_half_width = width / 2 + depth * slope
        return [
            [-top_half_width, z_top],
            [-width / 2, z_bed],
            [width / 2, z_bed],
            [top_half_width, z_top],
        ]

    @staticmethod
    def _parse_irregular(parts: list[str]) -> list[list[float]]:
        """不规则形: 不规则形 1 点数 y1 z1 y2 z2 ..."""
        nums = []
        for p in parts:
            try:
                nums.append(float(p))
            except ValueError:
                continue
        if len(nums) < 5:
            return []
        n_pts = int(nums[1])
        coords = nums[2:]
        yz = []
        for i in range(0, min(len(coords) - 1, n_pts * 2), 2):
            yz.append([coords[i], coords[i + 1]])
        return yz

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
        raise UnicodeDecodeError("all", b"", 0, 1, f"Failed to decode {path}")
