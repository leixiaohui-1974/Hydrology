"""wxq 模型 JSON 完整物理数据提取器。

一次性从 wxq 11150大渡河智能体.json 提取所有水力学物理数据，
写入知识层 YAML/JSON，供水力学模拟器强制加载。

提取内容：
  1. 不规则断面 yz（113 组完整坐标 + A(H)/P(H)/B(H)/R(H) 曲线）
  2. 闸门过流参数（zb, b, c1-c4, down_zb, down_b, down_m）
  3. 水轮机 Q-H-P 曲面（流量-水头-出力三维曲线）
  4. 河段 Manning's n + 断面关联
  5. 节点拓扑

产品化原则：
  - 此脚本输出的知识层数据是模拟器的唯一数据来源
  - 模拟器缺数据必须报错，不允许静默降级
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

WORKSPACE = Path(__file__).resolve().parents[2]


# ── 断面几何计算 ──────────────────────────────────────────────────────────

@dataclass
class SectionHydraulics:
    """单个水位下的断面水力特性。"""
    H: float
    area: float       # 过水面积 A (m²)
    perimeter: float   # 湿周 P (m)
    width: float       # 水面宽 B (m)
    radius: float      # 水力半径 R = A/P (m)


def compute_section_hydraulics(
    yz: list[list[float]], water_level: float,
) -> SectionHydraulics:
    """从不规则断面 yz 计算给定水位下的完整水力特性。

    yz: [[y1, z1], [y2, z2], ...] 横距-高程点列
    """
    if len(yz) < 2:
        return SectionHydraulics(water_level, 0, 0, 0, 0)

    area = 0.0
    perimeter = 0.0
    wet_y_min = float("inf")
    wet_y_max = float("-inf")

    for i in range(len(yz) - 1):
        y1, z1 = yz[i]
        y2, z2 = yz[i + 1]
        d1 = water_level - z1
        d2 = water_level - z2

        if d1 <= 0 and d2 <= 0:
            continue

        dy = abs(y2 - y1)

        if d1 >= 0 and d2 >= 0:
            area += 0.5 * (d1 + d2) * dy
            dz = z2 - z1
            perimeter += math.sqrt(dy * dy + dz * dz)
            wet_y_min = min(wet_y_min, y1, y2)
            wet_y_max = max(wet_y_max, y1, y2)

        elif d1 > 0 and d2 <= 0:
            frac = d1 / (d1 - d2) if abs(d1 - d2) > 1e-10 else 0.5
            y_cross = y1 + frac * (y2 - y1)
            area += 0.5 * d1 * abs(y_cross - y1)
            seg_dy = abs(y_cross - y1)
            seg_dz = abs(water_level - z1)
            perimeter += math.sqrt(seg_dy * seg_dy + seg_dz * seg_dz)
            wet_y_min = min(wet_y_min, y1)
            wet_y_max = max(wet_y_max, y_cross)

        elif d1 <= 0 and d2 > 0:
            frac = (-d1) / (d2 - d1) if abs(d2 - d1) > 1e-10 else 0.5
            y_cross = y1 + frac * (y2 - y1)
            area += 0.5 * d2 * abs(y2 - y_cross)
            seg_dy = abs(y2 - y_cross)
            seg_dz = abs(water_level - z2)
            perimeter += math.sqrt(seg_dy * seg_dy + seg_dz * seg_dz)
            wet_y_min = min(wet_y_min, y_cross)
            wet_y_max = max(wet_y_max, y2)

    width = max(0.0, wet_y_max - wet_y_min) if wet_y_min < wet_y_max else 0.0
    radius = area / perimeter if perimeter > 1e-10 else 0.0

    return SectionHydraulics(water_level, area, perimeter, width, radius)


def build_section_curves(
    yz: list[list[float]], z_min: float, z_max: float, n_levels: int = 30,
) -> list[dict]:
    """构建断面完整水力曲线 A(H), P(H), B(H), R(H)。"""
    levels = np.linspace(z_min, z_max, n_levels)
    curves = []
    for h in levels:
        sh = compute_section_hydraulics(yz, float(h))
        curves.append({
            "H": round(sh.H, 3),
            "A": round(sh.area, 3),
            "P": round(sh.perimeter, 3),
            "B": round(sh.width, 3),
            "R": round(sh.radius, 4),
        })
    return curves


# ── 主提取器 ──────────────────────────────────────────────────────────────

STATION_MAP = {
    "瀑布沟前": "s1", "瀑布沟后": "s1",
    "深溪沟前": "s2", "深溪沟后": "s2",
    "枕头坝前": "s3", "枕头坝后": "s3",
    "沙坪前": "s4", "沙坪后": "s4",
}

CHANNEL_STATION = {
    "sm-pbg":  "s1",
    "pbg-sxg": "s2",
    "sxg-ztb": "s3",
    "ztb-sp":  "s4",
}


def extract_all(wxq_json_path: str, case_id: str = "daduhe") -> dict[str, Any]:
    """从 wxq JSON 提取全部水力学物理数据。"""
    with open(wxq_json_path, encoding="utf-8") as f:
        raw = json.load(f)

    root_key = list(raw.keys())[0]
    bd = raw[root_key]["baseData"]
    init_data = raw[root_key].get("initialData", {})

    out_dir = WORKSPACE / "Hydrology" / "knowledge" / case_id
    ts = datetime.now().isoformat(timespec="seconds")
    report: dict[str, Any] = {"timestamp": ts, "source": wxq_json_path}

    # ── 1. 断面 yz + 水力曲线 ──────────────────────────────────────────

    sections_raw = bd.get("sections", {})
    channels_raw = bd.get("channels", {})

    all_sections: dict[str, dict] = {}
    for sk, sv in sections_raw.items():
        yz = sv.get("yz", [])
        if not yz or len(yz) < 3:
            continue
        zs = [pt[1] for pt in yz]
        all_sections[str(sk)] = {
            "name": str(sv.get("name", sk)),
            "location": float(sv.get("location", 0)),
            "yz": yz,
            "z_min": min(zs),
            "z_max": max(zs),
            "n_points": len(yz),
        }

    channel_sections: dict[str, list[dict]] = {}
    for ch_name, ch_def in channels_raw.items():
        sec_names = ch_def.get("sec_names", [])
        nc = ch_def.get("nc", 0.015)
        secs = []
        for sn in sec_names:
            if sn in all_sections:
                s = all_sections[sn].copy()
                s["manning_n"] = nc if isinstance(nc, (int, float)) else 0.015
                secs.append(s)
        channel_sections[ch_name] = secs

    # 计算逐断面水力曲线
    section_curves: dict[str, dict] = {}
    for ch_name, secs in channel_sections.items():
        sid = CHANNEL_STATION.get(ch_name, ch_name)
        for sec in secs:
            z_lo = sec["z_min"]
            z_hi = sec["z_max"]
            curves = build_section_curves(sec["yz"], z_lo, z_hi, n_levels=40)
            section_curves[sec["name"]] = {
                "channel": ch_name,
                "station": sid,
                "location": sec["location"],
                "z_min": sec["z_min"],
                "z_max": sec["z_max"],
                "n_points": sec["n_points"],
                "manning_n": sec["manning_n"],
                "curves": curves,
            }

    # 写断面 yz 完整数据
    sections_path = out_dir / "sections" / "yz_profiles.json"
    sections_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(sections_path, {
        "_generated": ts,
        "_source": Path(wxq_json_path).name,
        "_description": "113 组不规则断面完整 yz 坐标",
        "sections": all_sections,
        "channel_sections": {
            ch: [s["name"] for s in secs]
            for ch, secs in channel_sections.items()
        },
    })

    # 写断面水力曲线 A(H)/P(H)/B(H)/R(H)
    hydraulics_path = out_dir / "sections" / "section_hydraulics.json"
    _write_json(hydraulics_path, {
        "_generated": ts,
        "_source": Path(wxq_json_path).name,
        "_description": "逐断面水力曲线 A(H)/P(H)/B(H)/R(H)",
        "sections": section_curves,
    })

    # 写河段聚合的水库 A(H) 曲线（用于水量平衡模型）
    reservoir_ah = _compute_reservoir_ah_curves(channel_sections)
    ah_path = out_dir / "curves" / "ah_curves.json"
    _write_json(ah_path, {
        "_generated": ts,
        "_source": Path(wxq_json_path).name,
        "_description": "各水库水位-面积关系 A(H)（从实测断面沿程积分）",
        **reservoir_ah,
    })

    report["sections"] = {
        "total": len(all_sections),
        "by_channel": {ch: len(secs) for ch, secs in channel_sections.items()},
        "paths": [str(sections_path), str(hydraulics_path), str(ah_path)],
    }

    # ── 2. 闸门过流参数 ────────────────────────────────────────────────

    gates_raw = bd.get("gates", {})
    gates_data: dict[str, dict] = {}
    for gk, gv in gates_raw.items():
        sid = _match_station(gk)
        is_maintenance = "检修" in str(gk) or "检修" in str(gv.get("name", ""))
        gates_data[gk] = {
            "station": sid,
            "node_up": gv["node1"],
            "node_dn": gv["node2"],
            "sill_elev_m": gv["zb"],
            "width_m": gv["b"],
            "gate_type": gv.get("type", 1),
            "is_maintenance": is_maintenance,
            "Cd_free": gv["c1"],
            "Cd_submerged_1": gv["c2"],
            "Cd_submerged_2": gv["c3"],
            "Cd_submerged_3": gv["c4"],
            "downstream_bed_elev_m": gv.get("down_zb"),
            "downstream_width_m": gv.get("down_b"),
            "downstream_slope": gv.get("down_m"),
        }

    gates_path = out_dir / "hydraulics" / "gates.json"
    gates_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(gates_path, {
        "_generated": ts,
        "_source": Path(wxq_json_path).name,
        "_description": "闸门过流参数（完整 c1~c4 四种流态系数）",
        "gates": gates_data,
    })

    report["gates"] = {
        "total": len(gates_data),
        "by_station": _count_by_field(gates_data, "station"),
        "path": str(gates_path),
    }

    # ── 3. 水轮机 Q-H-P 曲面 ──────────────────────────────────────────

    turbines_raw = bd.get("turbines", {})
    curves_raw = bd.get("curves", {})

    turbine_defs: dict[str, dict] = {}
    for tk, tv in turbines_raw.items():
        sid = _match_station(tk)
        turbine_defs[tk] = {
            "station": sid,
            "node_up": tv["node1"],
            "node_dn": tv["node2"],
            "curve_name": tv.get("curve", ""),
        }

    turbine_curves: dict[str, dict] = {}
    for curve_name, cv in curves_raw.items():
        data = cv.get("data", [])
        qs = sorted(set(d[0] for d in data))
        hs = sorted(set(d[1] for d in data))
        turbine_curves[curve_name] = {
            "n_points": len(data),
            "Q_range_m3s": [min(qs), max(qs)],
            "H_range_m": [min(hs), max(hs)],
            "P_range_MW": [min(d[2] for d in data), max(d[2] for d in data)],
            "data": data,
        }

    turbines_path = out_dir / "hydraulics" / "turbines.json"
    _write_json(turbines_path, {
        "_generated": ts,
        "_source": Path(wxq_json_path).name,
        "_description": "水轮机 Q-H-P 三维曲面（流量-水头-出力）",
        "turbine_definitions": turbine_defs,
        "turbine_curves": turbine_curves,
    })

    # 写初始工况
    init_turbines = init_data.get("turbines", {})
    init_gates = init_data.get("gates", {})
    init_boundaries = init_data.get("boundaries", {})

    init_path = out_dir / "hydraulics" / "initial_conditions.json"
    _write_json(init_path, {
        "_generated": ts,
        "_source": Path(wxq_json_path).name,
        "_description": "初始工况（水轮机出力、闸门开度、边界条件）",
        "turbine_flows": init_turbines,
        "gate_openings": init_gates,
        "boundaries": init_boundaries,
    })

    report["turbines"] = {
        "total_units": len(turbine_defs),
        "curves": list(turbine_curves.keys()),
        "by_station": _count_by_field(turbine_defs, "station"),
        "path": str(turbines_path),
    }

    # ── 4. 节点和河段拓扑 ──────────────────────────────────────────────

    nodes_raw = bd.get("nodes", {})
    topology: dict[str, Any] = {
        "nodes": {},
        "channels": {},
    }
    for nk, nv in nodes_raw.items():
        topology["nodes"][nk] = {
            "zb": nv.get("zb"),
            "Amin": nv.get("Amin"),
            "node_type": nv.get("nodeType"),
            "x": nv.get("x"),
            "y": nv.get("y"),
        }
    for ck, cv in channels_raw.items():
        topology["channels"][ck] = {
            "node1": cv["node1"],
            "node2": cv["node2"],
            "manning_n": cv.get("nc", 0.015),
            "n_sections": len(cv.get("sec_names", [])),
            "section_names": cv.get("sec_names", []),
        }

    topo_path = out_dir / "hydraulics" / "topology.json"
    _write_json(topo_path, {
        "_generated": ts,
        "_source": Path(wxq_json_path).name,
        "_description": "完整节点+河段拓扑",
        **topology,
    })

    report["topology"] = {
        "nodes": len(nodes_raw),
        "channels": len(channels_raw),
        "path": str(topo_path),
    }

    # ── 汇总 ──────────────────────────────────────────────────────────

    report_path = out_dir / "hydraulics" / "_extraction_report.json"
    _write_json(report_path, report)

    print(f"\n{'='*60}")
    print(f"  wxq 物理数据提取完成")
    print(f"{'='*60}")
    print(f"  断面: {len(all_sections)} 个 yz 剖面, {len(section_curves)} 条水力曲线")
    print(f"  闸门: {len(gates_data)} 个 (含 c1~c4 流态系数)")
    print(f"  水轮机: {len(turbine_defs)} 台, {len(turbine_curves)} 条 Q-H-P 曲面")
    print(f"  拓扑: {len(nodes_raw)} 节点, {len(channels_raw)} 河段")
    print(f"  输出: {out_dir / 'hydraulics'}")
    print(f"  输出: {out_dir / 'sections'}")
    print(f"  输出: {out_dir / 'curves'}")
    print(f"{'='*60}")

    return report


# ── 内部工具函数 ──────────────────────────────────────────────────────────

STATION_NAME_PREFIXES = {
    "瀑布": "s1", "深溪": "s2", "枕头": "s3", "沙坪": "s4",
    "龚嘴": "s5", "铜街": "s6",
}


def _match_station(name: str) -> str:
    for prefix, sid in STATION_NAME_PREFIXES.items():
        if prefix in name:
            return sid
    return "unknown"


def _count_by_field(data: dict[str, dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for v in data.values():
        k = v.get(field, "unknown")
        counts[k] = counts.get(k, 0) + 1
    return counts


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  → {path.relative_to(WORKSPACE)}")


POOL_RANGES = {
    "s1": (790.0, 852.0),
    "s2": (655.0, 662.0),
    "s3": (620.0, 627.0),
    "s4": (549.0, 556.0),
}


def _compute_reservoir_ah_curves(
    channel_sections: dict[str, list[dict]],
) -> dict[str, Any]:
    """对每个水库，用河段断面沿程积分算水库 A(H)。"""
    result = {}
    for ch_name, secs in channel_sections.items():
        sid = CHANNEL_STATION.get(ch_name)
        if not sid or not secs:
            continue

        z_lo, z_hi = POOL_RANGES.get(sid, (secs[0]["z_min"], secs[0]["z_max"]))
        sorted_secs = sorted(secs, key=lambda s: s["location"])

        levels = np.linspace(z_lo, z_hi, 30)
        curve = []
        for h in levels:
            widths = []
            locs = []
            for sec in sorted_secs:
                yz = sec["yz"]
                wet_y = [pt[0] for pt in yz if pt[1] < h]
                w = (max(wet_y) - min(wet_y)) if len(wet_y) >= 2 else 0.0
                widths.append(w)
                locs.append(sec["location"])

            total_area = 0.0
            for i in range(1, len(widths)):
                dl = locs[i] - locs[i - 1]
                total_area += 0.5 * (widths[i] + widths[i - 1]) * dl

            curve.append({
                "H": round(float(h), 3),
                "A_m2": round(total_area, 2),
            })

        result[sid] = {
            "name": {"s1": "瀑布沟", "s2": "深溪沟", "s3": "枕头坝", "s4": "沙坪"}[sid],
            "channel": ch_name,
            "n_sections": len(secs),
            "curve": curve,
        }

    return result


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="wxq 模型数据完整提取")
    parser.add_argument("--case-id", default="daduhe")
    parser.add_argument("--wxq-json", default=str(
        WORKSPACE / "wxq-1d" / "大渡河" / "11150大渡河智能体.json"))
    args = parser.parse_args()
    extract_all(args.wxq_json, args.case_id)


if __name__ == "__main__":
    main()
