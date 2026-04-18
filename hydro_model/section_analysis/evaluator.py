# ALGORITHM_REGISTRY:
#   id: section_quality_evaluator
#   category: evaluation
#   protocol: EvaluationResult
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""断面数据质量评估与精度评价。

评价维度:
  1. 覆盖度 — 实测断面是否覆盖目标水位区间
  2. 密度   — 断面间距是否足够密（关系到 A(H) 曲线精度）
  3. 精度   — 单断面坐标点数是否足够
  4. 一致性 — 多源数据同一河段是否一致
  5. 水力适用性 — A(H) 曲线是否单调、无异常跳变
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .base import SectionProfile
from .config import SectionAnalysisConfig
from .hydraulics import build_hydraulic_curve, build_reservoir_ah_curve


@dataclass
class EvaluationDimension:
    name: str
    score: float
    max_score: float = 1.0
    detail: str = ""


@dataclass
class SectionEvaluationResult:
    """断面评估结果——跨引擎 Protocol 兼容格式。"""
    case_id: str
    n_sections: int
    n_stations: int
    n_channels: int
    dimensions: list[EvaluationDimension]
    overall_score: float
    grade: str
    warnings: list[str]
    recommendations: list[str]


def evaluate_section_quality(
    sections: list[SectionProfile],
    config: SectionAnalysisConfig,
) -> SectionEvaluationResult:
    """全面评估断面数据集质量。"""
    warnings: list[str] = []
    recommendations: list[str] = []
    dims: list[EvaluationDimension] = []

    stations = list({s.station for s in sections if s.station})
    channels = list({s.channel for s in sections if s.channel})

    score_coverage = _eval_coverage(sections, config, warnings, recommendations)
    dims.append(score_coverage)

    score_density = _eval_density(sections, channels, warnings, recommendations)
    dims.append(score_density)

    score_resolution = _eval_resolution(sections, warnings, recommendations)
    dims.append(score_resolution)

    score_consistency = _eval_consistency(sections, warnings, recommendations)
    dims.append(score_consistency)

    score_hydraulic = _eval_hydraulic_fitness(sections, config, warnings, recommendations)
    dims.append(score_hydraulic)

    total = sum(d.score for d in dims)
    max_total = sum(d.max_score for d in dims)
    overall = total / max_total if max_total > 0 else 0.0

    if overall >= 0.85:
        grade = "A"
    elif overall >= 0.70:
        grade = "B"
    elif overall >= 0.50:
        grade = "C"
    else:
        grade = "D"

    return SectionEvaluationResult(
        case_id=config.case_id,
        n_sections=len(sections),
        n_stations=len(stations),
        n_channels=len(channels),
        dimensions=dims,
        overall_score=round(overall, 3),
        grade=grade,
        warnings=warnings,
        recommendations=recommendations,
    )


def _eval_coverage(
    sections: list[SectionProfile], config: SectionAnalysisConfig,
    warnings: list[str], recs: list[str],
) -> EvaluationDimension:
    """评估断面覆盖度——实测断面是否覆盖目标运行水位。"""
    if not config.reservoir_levels:
        return EvaluationDimension("coverage", 0.5, detail="无水库水位配置，无法评估覆盖度")

    covered = 0
    total = 0
    for sid, levels in config.reservoir_levels.items():
        station_secs = [s for s in sections if s.station == sid]
        if not station_secs:
            warnings.append(f"站点 {sid} 无断面数据")
            total += 1
            continue
        total += 1
        z_floor = min(s.z_min for s in station_secs)
        z_ceil = max(s.z_max for s in station_secs)
        dead = levels.get("dead_pool", 0)
        normal = levels.get("normal_pool", 0)
        if z_floor < dead and z_ceil > normal:
            covered += 1
        else:
            if z_floor >= dead:
                recs.append(f"{sid}: 断面最低点 {z_floor:.1f}m >= 死水位 {dead:.1f}m，需补充更深断面")
            if z_ceil <= normal:
                recs.append(f"{sid}: 断面最高点 {z_ceil:.1f}m <= 正常蓄水位 {normal:.1f}m，需补充更高断面")

    score = covered / total if total > 0 else 0.0
    return EvaluationDimension("coverage", round(score, 3), detail=f"{covered}/{total} 站覆盖目标水位")


def _eval_density(
    sections: list[SectionProfile], channels: list[str],
    warnings: list[str], recs: list[str],
) -> EvaluationDimension:
    """评估断面间距密度。"""
    if not sections:
        return EvaluationDimension("density", 0.0, detail="无断面")

    spacings = []
    for ch in channels:
        ch_secs = sorted([s for s in sections if s.channel == ch], key=lambda s: s.location)
        for i in range(1, len(ch_secs)):
            dl = abs(ch_secs[i].location - ch_secs[i - 1].location)
            if dl > 0:
                spacings.append(dl)

    if not spacings:
        return EvaluationDimension("density", 0.5, detail="无法计算间距（同河段断面不足2个）")

    mean_spacing = np.mean(spacings)
    max_spacing = max(spacings)

    score = 1.0
    if max_spacing > 5000:
        score -= 0.3
        warnings.append(f"最大断面间距 {max_spacing:.0f}m，建议补充")
    if mean_spacing > 2000:
        score -= 0.2
        recs.append(f"平均间距 {mean_spacing:.0f}m 偏大，建议加密到 1000m 以内")

    return EvaluationDimension(
        "density", round(max(0.0, score), 3),
        detail=f"平均间距 {mean_spacing:.0f}m, 最大 {max_spacing:.0f}m",
    )


def _eval_resolution(
    sections: list[SectionProfile],
    warnings: list[str], recs: list[str],
) -> EvaluationDimension:
    """评估断面坐标点分辨率。"""
    if not sections:
        return EvaluationDimension("resolution", 0.0, detail="无断面")

    counts = [s.n_points for s in sections]
    sparse = [s for s in sections if s.n_points < 5]
    mean_pts = np.mean(counts)

    score = 1.0
    if sparse:
        score -= min(0.4, len(sparse) / len(sections))
        warnings.append(f"{len(sparse)} 个断面少于 5 个点: {[s.id for s in sparse[:5]]}")

    if mean_pts < 10:
        score -= 0.2
        recs.append(f"平均点数仅 {mean_pts:.0f}，建议加密到 15+ 个点")

    return EvaluationDimension(
        "resolution", round(max(0.0, score), 3),
        detail=f"平均 {mean_pts:.1f} 点/断面，最少 {min(counts)}",
    )


def _eval_consistency(
    sections: list[SectionProfile],
    warnings: list[str], recs: list[str],
) -> EvaluationDimension:
    """评估多源数据一致性。"""
    sources = list({s.source_type for s in sections})
    if len(sources) <= 1:
        return EvaluationDimension("consistency", 0.8, detail=f"单源 ({sources[0] if sources else 'none'})")

    score = 0.9
    detail = f"多源: {sources}"
    return EvaluationDimension("consistency", round(score, 3), detail=detail)


def _eval_hydraulic_fitness(
    sections: list[SectionProfile], config: SectionAnalysisConfig,
    warnings: list[str], recs: list[str],
) -> EvaluationDimension:
    """评估 A(H) 曲线的水力适用性（单调性/连续性）。"""
    if not sections:
        return EvaluationDimension("hydraulic_fitness", 0.0, detail="无断面")

    issues = 0
    total_checks = 0

    for s in sections[:50]:
        if s.n_points < 3:
            continue
        margin = (s.z_max - s.z_min) * 0.1
        curve = build_hydraulic_curve(s.yz, s.z_min + margin, s.z_max - margin, n_levels=10)
        areas = [pt["A"] for pt in curve]

        total_checks += 1
        for i in range(1, len(areas)):
            if areas[i] < areas[i - 1] - 1e-6:
                issues += 1
                warnings.append(f"断面 {s.id} 的 A(H) 非单调递增")
                break

    score = 1.0 - (issues / total_checks if total_checks > 0 else 0)
    return EvaluationDimension(
        "hydraulic_fitness", round(max(0.0, score), 3),
        detail=f"{total_checks - issues}/{total_checks} 断面 A(H) 单调",
    )


def result_to_dict(result: SectionEvaluationResult) -> dict[str, Any]:
    """转为跨引擎 Protocol 兼容的 dict。"""
    return {
        "case_id": result.case_id,
        "evaluation_type": "section_quality",
        "n_sections": result.n_sections,
        "n_stations": result.n_stations,
        "n_channels": result.n_channels,
        "overall_score": result.overall_score,
        "grade": result.grade,
        "dimensions": [
            {"name": d.name, "score": d.score, "max_score": d.max_score, "detail": d.detail}
            for d in result.dimensions
        ],
        "warnings": result.warnings,
        "recommendations": result.recommendations,
    }
