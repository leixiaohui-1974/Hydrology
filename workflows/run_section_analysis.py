#!/usr/bin/env python3
# ALGORITHM_REGISTRY:
#   id: section_analysis_workflow
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""识地 (ShiDi) — 地形分析与DEM处理

HydroMind 水智工坊 · Agent #3

断面分析产品化工作流 — 零硬编码。

所有映射（channel→station、name→sid、路径匹配）均从 Case YAML 的
knowledge.topology / knowledge.reservoirs 动态派生，
换 case-id 零代码修改即可运行。

Usage:
    python3 run_section_analysis.py --case-id zhongxian
    python3 run_section_analysis.py --case-id zhongxian --config path/to/custom.yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from hydro_model.section_analysis import run_section_pipeline
from hydro_model.section_analysis.config import SectionAnalysisConfig
from hydro_model.section_analysis.evaluator import evaluate_section_quality, result_to_dict
from workflows._shared import (
    load_case_config, write_json, save_knowledge_file, WORKSPACE,
    build_name_to_sid, build_channel_to_station, build_channel_keywords, build_channel_map,
)



# ── 数据源自动发现 ─────────────────────────────────────────────────


def _auto_discover_sources(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """从 Case YAML 自动发现断面数据源。

    优先使用 section_analysis.sources（显式配置）；
    否则从 topology_json_paths + scan_dirs 自动扫描。
    所有映射均从 _shared 共享函数派生，零硬编码。
    """
    sa = cfg.get("section_analysis", {})
    if sa.get("sources"):
        return sa["sources"]

    sources: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    topo_paths = cfg.get("topology_json_paths", [])
    if isinstance(topo_paths, str):
        topo_paths = [topo_paths]
    for p in topo_paths:
        abs_p = Path(p) if Path(p).is_absolute() else WORKSPACE / p
        if abs_p.exists() and abs_p.suffix == ".json":
            sources.append({
                "type": "wxq_json",
                "path": str(abs_p),
                "channel_map": build_channel_map(cfg),
            })
            seen_paths.add(str(abs_p.resolve()))
            break

    name_to_sid = build_name_to_sid(cfg)
    ch_keywords = build_channel_keywords(cfg)
    ch_to_station = build_channel_to_station(cfg)
    target_stations = cfg.get("target_stations", [])

    scan_dirs = cfg.get("scan_dirs", [])
    for sd in scan_dirs:
        sd_path = Path(sd) if Path(sd).is_absolute() else WORKSPACE / sd
        if not sd_path.exists():
            continue

        for f in sd_path.rglob("*"):
            real = str(f.resolve())
            if real in seen_paths:
                continue

            suffix = f.suffix.lower()
            if suffix == ".txt":
                txt_type = _detect_txt_type(f)
                if txt_type:
                    station = _guess_station(f.stem, str(f), name_to_sid, target_stations, ch_keywords, ch_to_station)
                    sources.append({"type": txt_type, "path": real, "station": station})
                    seen_paths.add(real)

            elif suffix in (".xlsx", ".xls"):
                if _looks_like_section_xlsx(f):
                    station = _guess_station(f.stem, str(f), name_to_sid, target_stations, ch_keywords, ch_to_station)
                    channel = _guess_channel_from_path(str(f), ch_keywords)
                    if not station and channel:
                        station = ch_to_station.get(channel, "")
                    sources.append({"type": "xlsx_terrain", "path": real, "station": station, "channel": channel})
                    seen_paths.add(real)

    return sources


# ── 纯逻辑检测函数（无硬编码数据） ─────────────────────────────────


def _detect_txt_type(path: Path) -> str | None:
    """通过文件头部内容检测 TXT 类型，返回解析器名或 None。"""
    try:
        raw = path.read_bytes()[:2000]
    except Exception:
        return None
    for enc in ("utf-8", "gbk", "gb2312", "latin1"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        return None

    first_line = text.split("\n")[0].strip()
    if "河道地形" in first_line:
        return "wxq_terrain_txt"
    if "断面" in text[:500] or "section" in text[:500].lower():
        return "terrain_txt"
    return None


def _looks_like_section_xlsx(path: Path) -> bool:
    """启发式判断 xlsx 是否可能包含断面数据。

    匹配条件：文件名或父目录含 "断面"/"地形"/"terrain"/"section"/"yz"。
    """
    path_str = str(path).lower()
    indicators = ("断面", "地形", "terrain", "section", "yz", "横断面", "河道")
    return any(ind in path_str for ind in indicators)


def _guess_channel_from_path(path_str: str, ch_keywords: list[tuple[str, str]]) -> str:
    """从文件路径推断所属 channel，使用配置派生的关键词。"""
    for keyword, ch_name in ch_keywords:
        if keyword in path_str:
            return ch_name
    return ""


def _guess_station(
    stem: str,
    full_path: str,
    name_to_sid: dict[str, str],
    target_stations: list[str],
    ch_keywords: list[tuple[str, str]],
    ch_to_station: dict[str, str],
) -> str:
    """从文件名/路径推断 station ID，全部基于配置数据。"""
    for name, sid in name_to_sid.items():
        if name in stem:
            return sid

    for s in target_stations:
        if s in stem:
            return name_to_sid.get(s, s)

    channel = _guess_channel_from_path(full_path, ch_keywords)
    if channel:
        return ch_to_station.get(channel, "")

    return ""


# ── 主流程 ─────────────────────────────────────────────────────────


def run_analysis(case_id: str, config_path: str | None = None) -> dict[str, Any]:
    """主入口：配置驱动断面分析全流程。"""
    cfg = load_case_config(case_id, config_path)

    sources = _auto_discover_sources(cfg)
    if not sources:
        print("[WARN] 未找到断面数据源，请在 case YAML 中配置 section_analysis.sources 或 scan_dirs")
        return {"error": "no_sources"}

    cfg.setdefault("section_analysis", {})["sources"] = sources

    sa_config = SectionAnalysisConfig.from_case_config(cfg)
    print(f"=== 断面分析: {case_id} | {len(sources)} 个数据源 ===")
    for s in sources:
        print(f"  [{s['type']}] {Path(s.get('path', '')).name}")

    result = run_section_pipeline(sa_config, workspace_root=str(WORKSPACE))

    print(f"\n--- 解析结果 ---")
    for ps in result.get("parse_summary", []):
        status = ps["status"]
        icon = "OK" if status == "ok" else "FAIL"
        print(f"  [{icon}] {ps['type']}: {ps['n_sections']} 断面 ({Path(ps.get('path', '')).name})")

    print(f"\n总计: {result['n_sections_total']} 个断面")

    ev = result.get("evaluation", {})
    if ev:
        print(f"\n--- 质量评估: {ev.get('grade', '?')} ({ev.get('overall_score', 0):.1%}) ---")
        for d in ev.get("dimensions", []):
            print(f"  {d['name']}: {d['score']:.2f}/{d['max_score']:.2f} — {d['detail']}")
        for w in ev.get("warnings", []):
            print(f"  [WARN] {w}")
        for r in ev.get("recommendations", []):
            print(f"  [REC] {r}")

    reservoir_ah = result.get("reservoir_ah", {})
    if reservoir_ah:
        print(f"\n--- 水库 A(H) 曲线 ---")
        for sid, data in reservoir_ah.items():
            curve = data.get("ah_curve", [])
            if curve:
                print(f"  {sid}: {data['n_sections']} 断面, "
                      f"A({curve[0]['H']:.0f}m)={curve[0]['A_km2']:.4f} km² → "
                      f"A({curve[-1]['H']:.0f}m)={curve[-1]['A_km2']:.4f} km²")

    _write_outputs(case_id, result)
    return result


def _write_outputs(case_id: str, result: dict[str, Any]) -> None:
    """写入合约和知识文件。"""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    contract = {
        "_auto_generated": True,
        "_generated_at": ts,
        "_workflow": "section_analysis",
        "case_id": case_id,
        "n_sections_total": result["n_sections_total"],
        "parse_summary": result["parse_summary"],
        "evaluation": result["evaluation"],
        "reservoir_ah_summary": {
            sid: {
                "n_sections": d["n_sections"],
                "h_range": [d["ah_curve"][0]["H"], d["ah_curve"][-1]["H"]] if d.get("ah_curve") else [],
                "a_range_km2": [d["ah_curve"][0]["A_km2"], d["ah_curve"][-1]["A_km2"]] if d.get("ah_curve") else [],
            }
            for sid, d in result.get("reservoir_ah", {}).items()
        },
    }
    contract_path = WORKSPACE / "cases" / case_id / "contracts" / "section_analysis.latest.json"
    write_json(contract_path, contract)
    print(f"\n合约: {contract_path}")

    knowledge_sections = {
        "_generated_at": ts,
        "_source": "section_analysis_workflow",
    }
    for sid, data in result.get("reservoir_ah", {}).items():
        knowledge_sections[sid] = {
            "n_sections": data["n_sections"],
            "ah_curve": data.get("ah_curve", []),
        }
    save_knowledge_file(case_id, "curves/ah_curves_product.yaml", knowledge_sections)

    if result.get("evaluation"):
        save_knowledge_file(case_id, "quality/section_evaluation.yaml", result["evaluation"])

    print(f"知识已固化到 knowledge/{case_id}/curves/ + quality/")


def main():
    parser = argparse.ArgumentParser(description="断面分析产品化工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    run_analysis(case_id=args.case_id, config_path=args.config)


if __name__ == "__main__":
    main()
