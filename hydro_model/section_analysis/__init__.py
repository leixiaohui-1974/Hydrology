# ALGORITHM_REGISTRY:
#   id: section_analysis_product
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""断面分析产品模块。

产品化设计：
  - 配置驱动，零硬编码
  - 多数据源解析器注册表：wxq_json / terrain_txt / xlsx_terrain
  - 统一水力特性计算：A(H) / P(H) / B(H) / R(H) / Q(H)
  - 质量评估 5 维评分（覆盖/密度/精度/一致性/水力适用性）
  - case_id + source 配置即可驱动全流程

Usage::

    from hydro_model.section_analysis import run_section_pipeline
    from hydro_model.section_analysis.config import SectionAnalysisConfig

    config = SectionAnalysisConfig.from_case_config(case_cfg)
    result = run_section_pipeline(config)

    # 或直接使用子组件
    from hydro_model.section_analysis.parsers import parse_source
    from hydro_model.section_analysis.hydraulics import build_hydraulic_curve
    from hydro_model.section_analysis.evaluator import evaluate_section_quality
"""
from __future__ import annotations

from typing import Any

from .base import SectionProfile
from .config import SectionAnalysisConfig
from .evaluator import evaluate_section_quality, result_to_dict
from .hydraulics import (
    build_hydraulic_curve,
    build_reservoir_ah_curve,
    compute_area,
    compute_hydraulic_properties,
    compute_wetted_perimeter,
    compute_width,
    evaluate_sections,
)
from .parsers import PARSER_REGISTRY, get_parser, parse_source, register_parser


def run_section_pipeline(
    config: SectionAnalysisConfig,
    workspace_root: str = "",
) -> dict[str, Any]:
    """断面分析全流程：解析 → 水力计算 → 质量评估。

    Returns:
        dict with keys: sections, hydraulic_curves, evaluation, reservoir_ah
    """
    from pathlib import Path

    ws = Path(workspace_root) if workspace_root else Path.cwd()

    all_sections: list[SectionProfile] = []
    parse_summary: list[dict[str, Any]] = []

    for source in config.sources:
        src_path = source.get("path", "")
        if src_path and not Path(src_path).is_absolute():
            source = {**source, "path": str(ws / src_path)}
        try:
            profiles = parse_source(source)
            all_sections.extend(profiles)
            parse_summary.append({
                "type": source.get("type"),
                "path": src_path,
                "n_sections": len(profiles),
                "status": "ok",
            })
        except Exception as e:
            parse_summary.append({
                "type": source.get("type"),
                "path": src_path,
                "n_sections": 0,
                "status": f"error: {e}",
            })

    hydraulic_curves: dict[str, Any] = {}
    for s in all_sections:
        if s.n_points < 3:
            continue
        margin_lo = s.z_min + (s.z_max - s.z_min) * 0.02
        margin_hi = s.z_max - (s.z_max - s.z_min) * 0.02
        hydraulic_curves[s.id] = {
            "name": s.name,
            "channel": s.channel,
            "station": s.station,
            "z_range": [round(s.z_min, 2), round(s.z_max, 2)],
            "curve": build_hydraulic_curve(
                s.yz, margin_lo, margin_hi,
                n_levels=config.n_levels,
                manning_n=s.manning_n or config.manning_n_default,
                curves=config.output_curves,
            ),
        }

    reservoir_ah: dict[str, Any] = {}
    for sid, levels in config.reservoir_levels.items():
        station_secs = [s for s in all_sections if s.station == sid]
        if not station_secs:
            continue
        z_lo = levels["dead_pool"] - 5
        z_hi = levels["normal_pool"] + 2
        reservoir_ah[sid] = {
            "n_sections": len(station_secs),
            "ah_curve": build_reservoir_ah_curve(station_secs, z_lo, z_hi, config.n_levels),
        }

    eval_result = evaluate_section_quality(all_sections, config)

    return {
        "case_id": config.case_id,
        "n_sections_total": len(all_sections),
        "parse_summary": parse_summary,
        "hydraulic_curves": hydraulic_curves,
        "reservoir_ah": reservoir_ah,
        "evaluation": result_to_dict(eval_result),
    }


__all__ = [
    "SectionProfile",
    "SectionAnalysisConfig",
    "run_section_pipeline",
    "build_hydraulic_curve",
    "build_reservoir_ah_curve",
    "compute_area",
    "compute_wetted_perimeter",
    "compute_width",
    "compute_hydraulic_properties",
    "evaluate_sections",
    "evaluate_section_quality",
    "PARSER_REGISTRY",
    "register_parser",
    "get_parser",
    "parse_source",
]
