# ALGORITHM_REGISTRY:
#   id: section_hydraulics_engine
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""断面水力特性计算引擎。

从 yz 断面几何出发，计算任意水位下的:
  A(H)  过水面积 [m²]
  P(H)  湿周 [m]
  B(H)  水面宽度 [m]
  R(H)  水力半径 [m]  (= A/P)
  Q(H)  Manning 公式流量 [m³/s]

全部为纯函数，零副作用，可供求解器 / 率定 / 评价模块直接调用。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from .base import SectionProfile


@dataclass
class HydraulicPoint:
    """单个水位点的水力特性。"""
    H: float
    A: float = 0.0
    P: float = 0.0
    B: float = 0.0
    R: float = 0.0
    Q: float = 0.0


def compute_area(yz: list[list[float]], water_level: float) -> float:
    """梯形积分计算过水面积。"""
    if len(yz) < 2:
        return 0.0
    area = 0.0
    for i in range(len(yz) - 1):
        y1, z1 = yz[i]
        y2, z2 = yz[i + 1]
        d1 = max(0.0, water_level - z1)
        d2 = max(0.0, water_level - z2)
        if d1 > 0 or d2 > 0:
            area += 0.5 * (d1 + d2) * abs(y2 - y1)
    return area


def compute_wetted_perimeter(yz: list[list[float]], water_level: float) -> float:
    """计算湿周（水体与河床接触的长度）。"""
    if len(yz) < 2:
        return 0.0
    perimeter = 0.0
    for i in range(len(yz) - 1):
        y1, z1 = yz[i]
        y2, z2 = yz[i + 1]
        d1 = max(0.0, water_level - z1)
        d2 = max(0.0, water_level - z2)
        if d1 <= 0 and d2 <= 0:
            continue
        if d1 > 0 and d2 > 0:
            seg_len = math.sqrt((y2 - y1) ** 2 + (z2 - z1) ** 2)
            perimeter += seg_len
        else:
            if d1 <= 0:
                y_cross = y1 + (y2 - y1) * (water_level - z1) / (z2 - z1) if z2 != z1 else y1
                seg_len = math.sqrt((y2 - y_cross) ** 2 + (water_level - z2) ** 2)
            else:
                y_cross = y1 + (y2 - y1) * (water_level - z1) / (z2 - z1) if z2 != z1 else y2
                seg_len = math.sqrt((y_cross - y1) ** 2 + (water_level - z1) ** 2)
            perimeter += seg_len
    return perimeter


def compute_width(yz: list[list[float]], water_level: float) -> float:
    """计算水面宽度。"""
    if len(yz) < 2:
        return 0.0
    wet_y = [pt[0] for pt in yz if pt[1] < water_level]
    if not wet_y:
        return 0.0
    return max(wet_y) - min(wet_y)


def compute_hydraulic_properties(
    yz: list[list[float]], water_level: float, manning_n: float = 0.025, slope: float = 0.001,
) -> HydraulicPoint:
    """一次性计算给定水位下的所有水力特性。"""
    a = compute_area(yz, water_level)
    p = compute_wetted_perimeter(yz, water_level)
    b = compute_width(yz, water_level)
    r = a / p if p > 0 else 0.0
    q = (1.0 / manning_n) * a * r ** (2.0 / 3.0) * math.sqrt(slope) if r > 0 else 0.0
    return HydraulicPoint(H=water_level, A=a, P=p, B=b, R=r, Q=q)


def build_hydraulic_curve(
    yz: list[list[float]],
    z_min: float,
    z_max: float,
    n_levels: int = 30,
    manning_n: float = 0.025,
    slope: float = 0.001,
    curves: list[str] | None = None,
) -> list[dict[str, float]]:
    """构建完整水力曲线 A(H)/P(H)/B(H)/R(H)/Q(H)。"""
    if curves is None:
        curves = ["A", "P", "B", "R"]
    levels = np.linspace(z_min, z_max, n_levels)
    result = []
    for h in levels:
        hp = compute_hydraulic_properties(yz, float(h), manning_n, slope)
        pt: dict[str, float] = {"H": float(h)}
        if "A" in curves:
            pt["A"] = round(hp.A, 3)
        if "P" in curves:
            pt["P"] = round(hp.P, 3)
        if "B" in curves:
            pt["B"] = round(hp.B, 3)
        if "R" in curves:
            pt["R"] = round(hp.R, 4)
        if "Q" in curves:
            pt["Q"] = round(hp.Q, 3)
        result.append(pt)
    return result


def build_reservoir_ah_curve(
    sections: list[SectionProfile],
    z_min: float,
    z_max: float,
    n_levels: int = 30,
) -> list[dict[str, float]]:
    """从多个断面构建水库水面面积曲线 A(H)（沿程梯形积分）。"""
    sorted_secs = sorted(sections, key=lambda s: s.location)
    levels = np.linspace(z_min, z_max, n_levels)
    curve = []
    for h in levels:
        h_val = float(h)
        widths = [compute_width(s.yz, h_val) for s in sorted_secs]
        locations = [s.location for s in sorted_secs]
        total_area = 0.0
        n_wet = sum(1 for w in widths if w > 0)
        for i in range(1, len(widths)):
            dl = locations[i] - locations[i - 1]
            avg_w = 0.5 * (widths[i] + widths[i - 1])
            total_area += avg_w * dl
        curve.append({
            "H": h_val,
            "A_m2": round(total_area, 2),
            "A_km2": round(total_area / 1e6, 6),
            "n_wet_sections": n_wet,
        })
    return curve


def evaluate_sections(
    sections: list[SectionProfile],
    reservoir_levels: dict[str, float] | None = None,
) -> dict[str, Any]:
    """断面数据质量评估。"""
    if not sections:
        return {"status": "empty", "n_sections": 0}

    z_beds = [s.z_min for s in sections]
    widths = [s.width for s in sections]
    point_counts = [s.n_points for s in sections]

    report: dict[str, Any] = {
        "n_sections": len(sections),
        "z_bed_range": [round(min(z_beds), 2), round(max(z_beds), 2)],
        "width_range": [round(min(widths), 1), round(max(widths), 1)],
        "points_per_section": {
            "min": min(point_counts),
            "max": max(point_counts),
            "mean": round(sum(point_counts) / len(point_counts), 1),
        },
        "sources": list({s.source_type for s in sections}),
        "stations": list({s.station for s in sections if s.station}),
        "channels": list({s.channel for s in sections if s.channel}),
    }

    sparse = [s for s in sections if s.n_points < 5]
    if sparse:
        report["quality_warnings"] = [
            f"稀疏断面 ({len(sparse)} 个少于 5 点): {[s.id for s in sparse[:5]]}"
        ]

    if reservoir_levels:
        coverage = {}
        for sid, levels in reservoir_levels.items():
            station_secs = [s for s in sections if s.station == sid]
            if station_secs:
                z_floor = min(s.z_min for s in station_secs)
                covers_dead = z_floor < levels.get("dead_pool", 0)
                covers_normal = any(s.z_max > levels.get("normal_pool", 0) for s in station_secs)
                coverage[sid] = {
                    "n_sections": len(station_secs),
                    "z_bed_min": round(z_floor, 2),
                    "covers_dead_pool": covers_dead,
                    "covers_normal_pool": covers_normal,
                }
        report["reservoir_coverage"] = coverage

    return report
