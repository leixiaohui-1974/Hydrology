from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

import yaml


WORKSPACE = Path(__file__).resolve().parents[2]
BASE_DIR = Path(__file__).resolve().parents[1]

SCHEMA_PATH = BASE_DIR / "configs" / "outcome_contract.schema.json"
TEMPLATES_PATH = BASE_DIR / "configs" / "outcome_templates.yaml"
MAPPING_PATH = BASE_DIR / "configs" / "workflow_template_mapping.yaml"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _safe_to_jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        if isinstance(value, dict):
            return {str(k): _safe_to_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_safe_to_jsonable(v) for v in value]
        return str(value)


def _unique_preserve_order(items: list[str]) -> list[str]:
    uniq: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def _extract_paths(obj: Any) -> list[str]:
    exts = {
        ".md",
        ".json",
        ".html",
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
        ".csv",
        ".xlsx",
        ".shp",
        ".geojson",
        ".yaml",
        ".yml",
    }
    found: list[str] = []
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for v in cur.values():
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
        elif isinstance(cur, str):
            s = cur.strip()
            if "/" in s and Path(s).suffix.lower() in exts:
                found.append(s)
    return _unique_preserve_order(found)


def _to_rel_path(path_str: str) -> str:
    p = Path(path_str)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(WORKSPACE))
        except Exception:
            return str(p)
    return path_str


def _exists_in_workspace(path_str: str) -> bool:
    p = Path(path_str)
    if p.is_absolute():
        return p.exists()
    return (WORKSPACE / p).exists()


def _read_json_if_exists(path_str: str) -> dict[str, Any]:
    rel_path = _to_rel_path(path_str)
    target = WORKSPACE / rel_path
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_result_paths(case_id: str, workflow: str, result: Any) -> list[str]:
    candidates = [_to_rel_path(path) for path in _extract_paths(result)]

    workflow_defaults = {
        "hyd_cal": [
            f"cases/{case_id}/contracts/hydraulic_calibration.latest.json",
            f"cases/{case_id}/contracts/D2_hydraulic_report.md",
        ],
        "d1d4": [
            f"cases/{case_id}/contracts/d1d4_precision_report.latest.json",
        ],
        "autonomy_assess": [
            f"cases/{case_id}/contracts/autonomy_assessment.latest.json",
            f"cases/{case_id}/contracts/autonomy_assessment.latest.md",
        ],
        "autonomy_autorun": [
            f"cases/{case_id}/contracts/autonomy_autorun.latest.json",
            f"cases/{case_id}/contracts/autonomy_autorun.latest.md",
            f"cases/{case_id}/contracts/autonomy_assessment.latest.json",
            f"cases/{case_id}/contracts/autonomy_assessment.latest.md",
            "reports/acceptance/strict_revalidation_summary.json",
        ],
        "strict_revalidation_ext": [
            "reports/acceptance/strict_revalidation_summary.json",
        ],
        "ensemble_forecast": [
            f"cases/{case_id}/contracts/ensemble_forecast.latest.json",
        ],
    }
    candidates.extend(workflow_defaults.get(workflow, []))

    curated: list[str] = []
    for rel_path in _unique_preserve_order(candidates):
        normalized = _to_rel_path(rel_path)
        if not _exists_in_workspace(normalized):
            continue
        if normalized.startswith(f"cases/{case_id}/") or normalized.startswith("reports/acceptance/"):
            curated.append(normalized)
            continue
        if normalized.startswith("cases/"):
            continue
        curated.append(normalized)
    return _prioritize_result_assets(case_id, curated)


def _prioritize_result_assets(case_id: str, paths: list[str]) -> list[str]:
    trusted_prefixes = (
        f"cases/{case_id}/contracts/",
        f"cases/{case_id}/source_selection/",
        f"knowledge/{case_id}/",
        "reports/acceptance/",
    )
    normalized = _unique_preserve_order([_to_rel_path(path) for path in paths if path])
    trusted = [path for path in normalized if path.startswith(trusted_prefixes)]
    if trusted:
        return trusted
    return normalized


def _collect_metric_candidates(obj: Any) -> dict[str, float]:
    keys = {
        "nse",
        "rmse",
        "kge",
        "mae",
        "r2",
        "pbias",
        "pass_rate",
        "overall_score",
        "score",
        "accuracy",
    }
    out: dict[str, float] = {}
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(v, (int, float)) and str(k).lower() in keys:
                    out[str(k).lower()] = float(v)
                else:
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return out


def _filter_metrics(metrics: dict[str, Any], mapping: dict[str, Any], algorithm_tags: list[str]) -> dict[str, Any]:
    packs = mapping.get("algorithm_metric_packs", {}) if isinstance(mapping, dict) else {}
    preferred_keys: list[str] = []
    for tag in algorithm_tags or ["default"]:
        preferred_keys.extend(packs.get(tag, []))
    preferred_keys.extend(packs.get("default", []))
    ordered_keys = _unique_preserve_order([str(key).lower() for key in preferred_keys])

    filtered: dict[str, Any] = {}
    for key in ordered_keys:
        if key in metrics:
            filtered[key] = metrics[key]
    for key, value in metrics.items():
        if key not in filtered:
            filtered[key] = value
    return filtered


def _build_slots(artifacts: list[dict[str, Any]], mapping: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    slot_rules = mapping.get("artifact_slot_mapping", {})
    slots: dict[str, list[dict[str, Any]]] = {
        "topology": [],
        "gis": [],
        "charts": [],
        "tables": [],
        "conclusions": [],
        "recommendations": [],
    }

    for art in artifacts:
        path = str(art.get("path", ""))
        lower = path.lower()
        assigned = False
        for slot, hints in slot_rules.items():
            if any(h in lower for h in hints):
                slots.setdefault(slot, []).append(art)
                assigned = True
                break
        if assigned:
            continue
        suffix = Path(lower).suffix
        if suffix in {".png", ".jpg", ".jpeg", ".svg", ".html"}:
            slots["charts"].append(art)
        elif suffix in {".csv", ".xlsx"}:
            slots["tables"].append(art)
        elif suffix in {".md", ".json"}:
            slots["conclusions"].append(art)
    for key in slots:
        slots[key] = slots[key][:6]
    return slots


def _make_entry(label: str, value: Any, evidence_path: str = "", confidence: float = 0.8) -> dict[str, Any]:
    return {
        "label": label,
        "value": _safe_to_jsonable(value),
        "evidence_path": evidence_path,
        "confidence": float(confidence),
        "_auto_generated": True,
        "generated_at": _utc_now(),
    }


def _build_accuracy_entries(metrics: dict[str, Any], evidence_path: str) -> list[dict[str, Any]]:
    if metrics:
        return [_make_entry("精度指标", metrics, evidence_path=evidence_path, confidence=0.85)]
    return [
        _make_entry(
            "精度指标",
            {"status": "pending_evaluation"},
            evidence_path=evidence_path,
            confidence=0.55,
        )
    ]


def _workflow_summary(result: Any, status: str) -> str:
    if status != "completed":
        return "执行失败，待排查。"
    if not isinstance(result, dict):
        return "工作流执行完成。"
    if "summary" in result:
        return "工作流已生成 summary。"
    if "report_path" in result:
        return "工作流已生成业务报告。"
    if result.get("kind") == "external_script":
        return "外部脚本执行完成。"
    return "工作流执行完成。"


def _conclusion_and_recommendation(
    result: Any,
    status: str,
    evidence_path: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conclusions: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    if status != "completed":
        conclusions.append(_make_entry("执行结论", "本次运行失败，结论降级为待复核。", evidence_path=evidence_path, confidence=0.95))
        recommendations.append(
            _make_entry(
                "建议动作",
                "优先查看失败工作流日志与输入参数，重试后复核精度指标。",
                evidence_path=evidence_path,
                confidence=0.95,
            )
        )
        return conclusions, recommendations

    if isinstance(result, dict):
        verdict = result.get("verdict") or result.get("final_verdict")
        if verdict:
            conclusions.append(_make_entry("评审结论", f"结论={verdict}", evidence_path=evidence_path, confidence=0.9))
        weak_dims = result.get("weak_dimensions")
        if weak_dims:
            recommendations.append(
                _make_entry(
                    "改进建议",
                    f"优先修复薄弱维度: {weak_dims}",
                    evidence_path=evidence_path,
                    confidence=0.85,
                )
            )
        rec_text = result.get("recommendation_text")
        if rec_text:
            recommendations.append(_make_entry("自动建议", rec_text, evidence_path=evidence_path, confidence=0.8))

    if not conclusions:
        conclusions.append(
            _make_entry(
                "执行结论",
                "执行完成，建议结合精度指标做人工复核。",
                evidence_path=evidence_path,
                confidence=0.7,
            )
        )
    if not recommendations:
        recommendations.append(
            _make_entry(
                "建议动作",
                "继续执行下游评估/复核工作流，闭环验证结果稳定性。",
                evidence_path=evidence_path,
                confidence=0.7,
            )
        )
    return conclusions, recommendations


def _select_template(workflow: str, mapping: dict[str, Any]) -> tuple[str, str, list[str]]:
    wf_map = mapping.get("workflows", {})
    default_template = mapping.get("default_template", "generic_template")
    item = wf_map.get(workflow, {})
    template_id = item.get("template_id", default_template)
    category = item.get("category", "general")
    algorithm_tags = item.get("algorithm_tags", ["default"])
    return template_id, category, algorithm_tags


def _specialize_hyd_cal(case_id: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    evidence_paths = _resolve_result_paths(case_id, "hyd_cal", result)
    evidence = evidence_paths[0] if evidence_paths else ""
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    avg_val_nse = summary.get("avg_val_nse")
    metrics = {
        key: value
        for key, value in {
            "nse": avg_val_nse,
            "rmse": summary.get("avg_cal_rmse"),
            "score": summary.get("n_stations_calibrated"),
        }.items()
        if isinstance(value, (int, float))
    }
    status_text = (
        f"平均验证 NSE={avg_val_nse:.3f}，已达到 0.85 阈值。"
        if isinstance(avg_val_nse, (int, float)) and avg_val_nse >= 0.85
        else f"平均验证 NSE={avg_val_nse:.3f}，低于 0.85 阈值。"
        if isinstance(avg_val_nse, (int, float))
        else "缺少平均验证 NSE，当前只能标记 pending_evaluation。"
    )
    recommendation_text = (
        "维持当前率定参数，继续执行下游评估与实时验证。"
        if isinstance(avg_val_nse, (int, float)) and avg_val_nse >= 0.85
        else "优先复核弱站参数与边界条件，补做验证集精度复核。"
    )
    return {
        "artifacts": evidence_paths,
        "metrics": metrics,
        "dimensions": {
            "result": [
                _make_entry(
                    "率定摘要",
                    {
                        "n_stations_calibrated": summary.get("n_stations_calibrated"),
                        "avg_cal_nse": summary.get("avg_cal_nse"),
                        "avg_val_nse": summary.get("avg_val_nse"),
                    },
                    evidence_path=evidence,
                    confidence=0.92,
                )
            ],
            "accuracy": _build_accuracy_entries(metrics, evidence),
            "conclusion": [_make_entry("率定结论", status_text, evidence_path=evidence, confidence=0.93)],
            "recommendation": [_make_entry("率定建议", recommendation_text, evidence_path=evidence, confidence=0.88)],
        },
    }


def _specialize_d1d4(case_id: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    evidence_paths = _resolve_result_paths(case_id, "d1d4", result)
    evidence = evidence_paths[0] if evidence_paths else ""
    dims = result.get("dimensions", {}) if isinstance(result.get("dimensions"), dict) else {}
    metrics = {
        key: value
        for key, value in {
            "capability_score": result.get("capability_score"),
            "overall_score": result.get("wnal_score"),
            "d1_score": (dims.get("d1") or {}).get("score") if isinstance(dims.get("d1"), dict) else None,
            "d2_score": (dims.get("d2") or {}).get("score") if isinstance(dims.get("d2"), dict) else None,
            "d3_score": (dims.get("d3") or {}).get("score") if isinstance(dims.get("d3"), dict) else None,
            "d4_score": (dims.get("d4") or {}).get("score") if isinstance(dims.get("d4"), dict) else None,
        }.items()
        if isinstance(value, (int, float))
    }
    overall_problems = result.get("overall_problems") or []
    overall_recommendations = result.get("overall_recommendations") or []
    conclusion_text = "；".join(str(item) for item in overall_problems[:3]) or "D1-D4 综合评估已完成。"
    recommendation_entries = [
        _make_entry("治理建议", item, evidence_path=evidence, confidence=0.9)
        for item in overall_recommendations[:4]
    ] or [_make_entry("治理建议", "继续补强低分维度并复跑评估。", evidence_path=evidence, confidence=0.8)]
    return {
        "artifacts": evidence_paths,
        "metrics": metrics,
        "dimensions": {
            "result": [
                _make_entry(
                    "D1-D4 评分",
                    {
                        name: {
                            "score": value.get("score"),
                            "level": value.get("level"),
                        }
                        for name, value in dims.items()
                        if isinstance(value, dict)
                    },
                    evidence_path=evidence,
                    confidence=0.9,
                )
            ],
            "accuracy": _build_accuracy_entries(metrics, evidence),
            "conclusion": [_make_entry("评估结论", conclusion_text, evidence_path=evidence, confidence=0.9)],
            "recommendation": recommendation_entries,
        },
    }


def _specialize_autonomy_assess(case_id: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    evidence_paths = _resolve_result_paths(case_id, "autonomy_assess", result)
    detail_report = _read_json_if_exists(str(result.get("json_report", "")))
    evidence = evidence_paths[0] if evidence_paths else ""
    scores = detail_report.get("scores", {}) if isinstance(detail_report.get("scores"), dict) else {}
    judge = detail_report.get("judge", {}) if isinstance(detail_report.get("judge"), dict) else {}
    actions = detail_report.get("recommended_actions", []) if isinstance(detail_report.get("recommended_actions"), list) else []
    metrics = {
        key: value
        for key, value in {"overall_score": result.get("overall_score"), **scores}.items()
        if isinstance(value, (int, float))
    }
    conclusion_text = (
        f"自治评审 verdict={judge.get('verdict')}，薄弱维度={judge.get('weak_dimensions')}"
        if judge
        else f"自治评审 verdict={result.get('verdict')}"
    )
    recommendation_entries = [
        _make_entry(
            f"建议动作{idx + 1}",
            {
                "dimension": item.get("dimension"),
                "workflow": item.get("workflow"),
                "reason": item.get("reason"),
            },
            evidence_path=evidence,
            confidence=0.92,
        )
        for idx, item in enumerate(actions[:4])
        if isinstance(item, dict)
    ] or [
        _make_entry(
            "建议动作",
            f"建议优先修复薄弱维度: {result.get('weak_dimensions')}",
            evidence_path=evidence,
            confidence=0.85,
        )
    ]
    return {
        "artifacts": evidence_paths,
        "metrics": metrics,
        "dimensions": {
            "result": [
                _make_entry("自治审评概览", {"verdict": result.get("verdict"), "weak_dimensions": result.get("weak_dimensions")}, evidence_path=evidence, confidence=0.93)
            ],
            "accuracy": _build_accuracy_entries(metrics, evidence),
            "conclusion": [_make_entry("自治结论", conclusion_text, evidence_path=evidence, confidence=0.94)],
            "recommendation": recommendation_entries,
        },
    }


def _specialize_autonomy_autorun(case_id: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    evidence_paths = [
        path
        for path in [
            f"cases/{case_id}/contracts/autonomy_autorun.latest.json",
            f"cases/{case_id}/contracts/autonomy_autorun.latest.md",
            f"cases/{case_id}/contracts/autonomy_assessment.latest.json",
            f"cases/{case_id}/contracts/autonomy_assessment.latest.md",
            "reports/acceptance/strict_revalidation_summary.json",
        ]
        if _exists_in_workspace(path)
    ]
    detail_report = _read_json_if_exists(str(result.get("json_report", ""))) or _read_json_if_exists(
        f"cases/{case_id}/contracts/autonomy_autorun.latest.json"
    )
    assess_report = _read_json_if_exists(f"cases/{case_id}/contracts/autonomy_assessment.latest.json")
    strict_report = _read_json_if_exists("reports/acceptance/strict_revalidation_summary.json")

    evidence = evidence_paths[0] if evidence_paths else ""
    assess_evidence = (
        f"cases/{case_id}/contracts/autonomy_assessment.latest.json"
        if _exists_in_workspace(f"cases/{case_id}/contracts/autonomy_assessment.latest.json")
        else evidence
    )
    strict_evidence = (
        "reports/acceptance/strict_revalidation_summary.json"
        if _exists_in_workspace("reports/acceptance/strict_revalidation_summary.json")
        else evidence
    )

    final = detail_report.get("final", {}) if isinstance(detail_report.get("final"), dict) else {}
    judge = assess_report.get("judge", {}) if isinstance(assess_report.get("judge"), dict) else {}
    rounds = detail_report.get("rounds", []) if isinstance(detail_report.get("rounds"), list) else []
    root_cause_hints = final.get("root_cause_hints", []) if isinstance(final.get("root_cause_hints"), list) else []

    modules = strict_report.get("modules", {}) if isinstance(strict_report.get("modules"), dict) else {}
    physics = modules.get("physics", {}) if isinstance(modules.get("physics"), dict) else {}
    control = modules.get("control", {}) if isinstance(modules.get("control"), dict) else {}
    strict_failed = sum(
        int(module.get("failed_tests", 0) or 0)
        for module in modules.values()
        if isinstance(module, dict)
    )
    strict_review = {
        key: value
        for key, value in {
            "scenario_count": strict_report.get("scenario_count"),
            "physics_pass_rate": physics.get("pass_rate"),
            "control_pass_rate": control.get("pass_rate"),
            "failed_tests": strict_failed,
        }.items()
        if isinstance(value, (int, float))
    }

    metrics = {
        key: value
        for key, value in {
            "overall_score": final.get("overall_score", result.get("final_score")),
        }.items()
        if isinstance(value, (int, float))
    }
    conclusion_text = (
        f"自治闭环 {final.get('verdict')}，overall_score={final.get('overall_score')}，"
        f"stop_reason={final.get('stop_reason')}。"
        if final
        else f"自治闭环 final_verdict={result.get('final_verdict')}"
    )

    recommendation_entries: list[dict[str, Any]] = []
    weak_dims = judge.get("weak_dimensions", []) if isinstance(judge.get("weak_dimensions"), list) else []
    if weak_dims:
        recommendation_entries.append(
            _make_entry(
                "治理建议",
                {
                    "verdict": judge.get("verdict"),
                    "weak_dimensions": weak_dims[:3],
                },
                evidence_path=assess_evidence,
                confidence=0.93,
            )
        )
    elif assess_report:
        recommendation_entries.append(
            _make_entry(
                "治理建议",
                f"自治评审已达标（verdict={judge.get('verdict')}），继续通过 strict_revalidation 复核结果稳定性。",
                evidence_path=assess_evidence,
                confidence=0.9,
            )
        )

    if strict_report:
        recommendation_entries.append(
            _make_entry(
                "复核建议",
                {
                    "scenario_count": strict_report.get("scenario_count"),
                    "failed_tests": strict_failed,
                    "control_failed_tests": control.get("failed_tests", 0),
                    "physics_failed_tests": physics.get("failed_tests", 0),
                    "review_path": strict_evidence,
                },
                evidence_path=strict_evidence,
                confidence=0.92,
            )
        )
    for idx, hint in enumerate(root_cause_hints[:2]):
        recommendation_entries.append(
            _make_entry(
                f"根因提示{idx + 1}",
                hint,
                evidence_path=evidence,
                confidence=0.88,
            )
        )
    if not recommendation_entries:
        recommendation_entries.append(
            _make_entry(
                "治理建议",
                "继续执行下游评估/复核工作流，闭环验证结果稳定性。",
                evidence_path=evidence,
                confidence=0.8,
            )
        )

    return {
        "artifacts": evidence_paths,
        "metrics": metrics,
        "dimensions": {
            "result": [
                _make_entry(
                    "自治闭环摘要",
                    {
                        "final_verdict": final.get("verdict", result.get("final_verdict")),
                        "overall_score": final.get("overall_score", result.get("final_score")),
                        "stop_reason": final.get("stop_reason"),
                        "rounds": len(rounds) or result.get("rounds"),
                        "strict_review": strict_review,
                    },
                    evidence_path=evidence,
                    confidence=0.93,
                )
            ],
            "accuracy": _build_accuracy_entries(metrics, evidence),
            "conclusion": [_make_entry("自治闭环结论", conclusion_text, evidence_path=evidence, confidence=0.94)],
            "recommendation": recommendation_entries,
        },
    }


def _specialize_strict_revalidation(case_id: str, result: Any) -> dict[str, Any]:
    summary_path = _resolve_result_paths(case_id, "strict_revalidation_ext", result)
    detail = _read_json_if_exists(summary_path[0]) if summary_path else {}
    evidence = summary_path[0] if summary_path else ""
    modules = detail.get("modules", {}) if isinstance(detail.get("modules"), dict) else {}
    physics = modules.get("physics", {}) if isinstance(modules.get("physics"), dict) else {}
    control = modules.get("control", {}) if isinstance(modules.get("control"), dict) else {}
    metrics = {
        key: value
        for key, value in {
            "pass_rate": physics.get("pass_rate"),
            "physics_score": physics.get("average_score"),
            "control_score": control.get("average_score"),
        }.items()
        if isinstance(value, (int, float))
    }
    failed_count = sum(
        int(module.get("failed_tests", 0))
        for module in modules.values()
        if isinstance(module, dict) and isinstance(module.get("failed_tests"), (int, float))
    )
    conclusion_text = (
        f"严格复核共发现 {failed_count} 个失败项。"
        if failed_count
        else "严格复核通过，未发现失败项。"
    )
    recommendation_text = (
        "优先处理 strict_revalidation_summary.json 中的 failed_samples，并复跑相关模块。"
        if failed_count
        else "保持当前测试基线，继续执行自治闭环与验收链路。"
    )
    return {
        "artifacts": summary_path,
        "metrics": metrics,
        "dimensions": {
            "result": [
                _make_entry("严格复核摘要", {"scenario_count": detail.get("scenario_count"), "modules": list(modules.keys())}, evidence_path=evidence, confidence=0.9)
            ],
            "accuracy": _build_accuracy_entries(metrics, evidence),
            "conclusion": [_make_entry("复核结论", conclusion_text, evidence_path=evidence, confidence=0.92)],
            "recommendation": [_make_entry("复核建议", recommendation_text, evidence_path=evidence, confidence=0.9)],
        },
    }


def _specialize_ensemble_forecast(case_id: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    evidence_paths = _resolve_result_paths(case_id, "ensemble_forecast", result)
    evidence = evidence_paths[0] if evidence_paths else ""
    station_results = result.get("station_results", {}) if isinstance(result.get("station_results"), dict) else {}
    first_station = next(iter(station_results.values()), {}) if station_results else {}
    first_horizon = next(iter(first_station.values()), {}) if isinstance(first_station, dict) and first_station else {}
    reliability = first_horizon.get("reliability", {}) if isinstance(first_horizon, dict) else {}
    deterministic = reliability.get("deterministic", {}) if isinstance(reliability.get("deterministic"), dict) else {}
    pit = reliability.get("pit", {}) if isinstance(reliability.get("pit"), dict) else {}
    metrics = {
        key: value
        for key, value in {
            "nse": deterministic.get("nse"),
            "rmse": deterministic.get("rmse"),
            "mae": deterministic.get("mae"),
            "r2": deterministic.get("r2"),
            "accuracy": reliability.get("coverage_80"),
        }.items()
        if isinstance(value, (int, float))
    }
    reliable = pit.get("is_reliable")
    conclusion_text = (
        f"集合预报可靠性={'达标' if reliable else '待改进'}，deterministic NSE={deterministic.get('nse')}。"
        if reliable is not None
        else "集合预报已生成，可靠性待人工复核。"
    )
    recommendation_text = (
        "优先复核成员权重与区间覆盖率，必要时回退到最佳单模型。"
        if reliable is False
        else "继续跟踪区间覆盖率和确定性指标，滚动校验集合稳定性。"
    )
    return {
        "artifacts": evidence_paths,
        "metrics": metrics,
        "dimensions": {
            "result": [
                _make_entry(
                    "集合预报摘要",
                    {
                        "n_members": first_horizon.get("n_members"),
                        "coverage_80": reliability.get("coverage_80"),
                        "pit_reliable": reliable,
                    },
                    evidence_path=evidence,
                    confidence=0.9,
                )
            ],
            "accuracy": _build_accuracy_entries(metrics, evidence),
            "conclusion": [_make_entry("预报结论", conclusion_text, evidence_path=evidence, confidence=0.9)],
            "recommendation": [_make_entry("预报建议", recommendation_text, evidence_path=evidence, confidence=0.86)],
        },
    }


def _specialize_section_analysis(case_id: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    evaluation = result.get("evaluation", {}) if isinstance(result.get("evaluation"), dict) else {}
    evidence_paths = [
        path
        for path in [
            f"cases/{case_id}/contracts/section_analysis.latest.json",
            f"cases/{case_id}/source_selection/index.html",
            f"cases/{case_id}/contracts/watershed_delineation_result.latest.json",
            f"cases/{case_id}/source_selection/product_outputs/inspection.json",
        ]
        if _exists_in_workspace(path)
    ]
    evidence = evidence_paths[0] if evidence_paths else ""
    metrics = {
        key: value
        for key, value in {
            "overall_score": evaluation.get("overall_score"),
            "score": evaluation.get("overall_score"),
        }.items()
        if isinstance(value, (int, float))
    }
    warnings = evaluation.get("warnings", []) if isinstance(evaluation.get("warnings"), list) else []
    recommendations = evaluation.get("recommendations", []) if isinstance(evaluation.get("recommendations"), list) else []
    grade = evaluation.get("grade")
    return {
        "artifacts": evidence_paths,
        "metrics": metrics,
        "dimensions": {
            "result": [
                _make_entry(
                    "断面分析摘要",
                    {
                        "n_sections_total": result.get("n_sections_total"),
                        "n_stations": evaluation.get("n_stations"),
                        "overall_score": evaluation.get("overall_score"),
                        "grade": grade,
                    },
                    evidence_path=evidence,
                    confidence=0.9,
                )
            ],
            "accuracy": _build_accuracy_entries(metrics, evidence),
            "conclusion": [
                _make_entry(
                    "断面分析结论",
                    f"断面质量等级 {grade}，总体评分 {evaluation.get('overall_score')}.",
                    evidence_path=evidence,
                    confidence=0.9,
                )
            ] + [
                _make_entry("断面警告", item, evidence_path=evidence, confidence=0.85)
                for item in warnings[:2]
            ],
            "recommendation": [
                _make_entry("断面建议", item, evidence_path=evidence, confidence=0.88)
                for item in recommendations[:3]
            ] or [
                _make_entry("断面建议", "建议继续进入流域划分和耦合仿真链路。", evidence_path=evidence, confidence=0.75)
            ],
        },
    }


def _specialize_outcome(workflow: str, case_id: str, result: Any) -> dict[str, Any]:
    builders = {
        "hyd_cal": _specialize_hyd_cal,
        "d1d4": _specialize_d1d4,
        "autonomy_assess": _specialize_autonomy_assess,
        "autonomy_autorun": _specialize_autonomy_autorun,
        "strict_revalidation_ext": _specialize_strict_revalidation,
        "ensemble_forecast": _specialize_ensemble_forecast,
        "section_analysis": _specialize_section_analysis,
    }
    builder = builders.get(workflow)
    if not builder:
        return {}
    return builder(case_id, result)


def _ensure_dimension_evidence(entries: list[dict[str, Any]], fallback_path: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        cloned = dict(item)
        if not cloned.get("evidence_path"):
            cloned["evidence_path"] = fallback_path
        normalized.append(cloned)
    return normalized


def _resolve_outcome_path(case_id: str, workflow_key: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "outcomes" / f"{workflow_key}.latest.json"


def build_outcome_contract(
    workflow: str,
    case_id: str,
    result: Any,
    status: str = "completed",
    execution_profile: str = "default",
) -> dict[str, Any]:
    templates = _load_yaml(TEMPLATES_PATH)
    mapping = _load_yaml(MAPPING_PATH)
    template_id, category, algorithm_tags = _select_template(workflow, mapping)
    template_cfg = (templates.get("templates", {}) or {}).get(template_id, {})

    specialized = _specialize_outcome(workflow, case_id, result)
    specialized_paths = specialized.get("artifacts", []) if isinstance(specialized, dict) else []
    paths = _resolve_result_paths(case_id, workflow, result)
    paths = _prioritize_result_assets(
        case_id,
        [*_unique_preserve_order(specialized_paths), *paths],
    )
    artifacts = [
        {
            "path": p,
            "exists": _exists_in_workspace(p),
            "artifact_type": Path(p).suffix.lower().lstrip("."),
        }
        for p in paths
    ]
    primary_evidence = artifacts[0]["path"] if artifacts else str(_resolve_outcome_path(case_id, workflow).relative_to(WORKSPACE))
    metrics = _filter_metrics(
        specialized.get("metrics", {}) or _collect_metric_candidates(result),
        mapping,
        algorithm_tags,
    )
    slots = _build_slots(artifacts, mapping)
    conclusions, recommendations = _conclusion_and_recommendation(result, status, evidence_path=primary_evidence)

    dimensions = {
        "data": [
            _make_entry("数据源数量", len(artifacts), evidence_path=primary_evidence, confidence=0.75),
            _make_entry("数据质量状态", "可追溯" if artifacts else "待补充", evidence_path=primary_evidence, confidence=0.7),
        ],
        "business": [
            _make_entry("业务目标", template_cfg.get("business_goal", "完成工作流业务目标"), confidence=0.7),
            _make_entry("业务对象", {"case_id": case_id, "workflow": workflow}, confidence=0.8),
        ],
        "process": [
            _make_entry("执行状态", status, confidence=0.95),
            _make_entry("执行摘要", _workflow_summary(result, status), confidence=0.8),
        ],
        "method": [
            _make_entry("模板ID", template_id, confidence=0.9),
            _make_entry("算法标签", algorithm_tags, confidence=0.8),
        ],
        "result": [
            _make_entry("核心结果", _safe_to_jsonable(result), evidence_path=primary_evidence, confidence=0.7),
        ],
        "accuracy": _build_accuracy_entries(metrics, primary_evidence),
        "conclusion": conclusions,
        "recommendation": recommendations,
    }

    specialized_dimensions = specialized.get("dimensions", {}) if isinstance(specialized, dict) else {}
    if isinstance(specialized_dimensions, dict):
        for dim_name, dim_items in specialized_dimensions.items():
            if dim_name in dimensions and isinstance(dim_items, list) and dim_items:
                dimensions[dim_name] = dim_items

    dimensions["conclusion"] = _ensure_dimension_evidence(dimensions["conclusion"], primary_evidence)
    dimensions["recommendation"] = _ensure_dimension_evidence(dimensions["recommendation"], primary_evidence)
    dimensions["accuracy"] = _ensure_dimension_evidence(dimensions["accuracy"], primary_evidence)

    return {
        "schema_version": "1.0.0",
        "contract_type": "workflow_outcome",
        "workflow_key": workflow,
        "case_id": case_id,
        "template_id": template_id,
        "category": category,
        "status": status,
        "execution_profile": execution_profile,
        "generated_at": _utc_now(),
        "_auto_generated": True,
        "dimensions": dimensions,
        "artifacts": artifacts,
        "slots": slots,
        "metrics": metrics,
    }


def validate_outcome_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_top = {
        "schema_version",
        "contract_type",
        "workflow_key",
        "case_id",
        "template_id",
        "category",
        "status",
        "generated_at",
        "dimensions",
        "artifacts",
        "slots",
    }
    for key in required_top:
        if key not in contract:
            errors.append(f"missing field: {key}")
    if contract.get("contract_type") != "workflow_outcome":
        errors.append("contract_type must be workflow_outcome")
    dimensions = contract.get("dimensions", {})
    required_dims = {"data", "business", "process", "method", "result", "accuracy", "conclusion", "recommendation"}
    if not isinstance(dimensions, dict):
        errors.append("dimensions must be object")
    else:
        for dim in required_dims:
            if dim not in dimensions:
                errors.append(f"dimensions.{dim} missing")
            elif not isinstance(dimensions.get(dim), list):
                errors.append(f"dimensions.{dim} must be list")
        for dim in ("conclusion", "recommendation"):
            for idx, entry in enumerate(dimensions.get(dim, []) or []):
                if not isinstance(entry, dict):
                    errors.append(f"dimensions.{dim}[{idx}] must be object")
                    continue
                if not entry.get("evidence_path"):
                    errors.append(f"dimensions.{dim}[{idx}].evidence_path missing")
        accuracy_items = dimensions.get("accuracy", []) or []
        if accuracy_items:
            first_value = (accuracy_items[0] or {}).get("value")
            if not contract.get("metrics") and first_value != {"status": "pending_evaluation"}:
                errors.append("accuracy must downgrade to pending_evaluation when metrics missing")

    for art in contract.get("artifacts", []):
        if not isinstance(art, dict):
            errors.append("artifact must be object")
            continue
        if "path" not in art:
            errors.append("artifact.path missing")
        if "exists" not in art:
            errors.append("artifact.exists missing")
    return errors


def write_outcome_contract(contract: dict[str, Any]) -> Path:
    case_id = str(contract.get("case_id", "")).strip()
    workflow_key = str(contract.get("workflow_key", "")).strip()
    if not case_id or not workflow_key:
        raise ValueError("case_id and workflow_key are required to write outcome contract")

    out_path = _resolve_outcome_path(case_id, workflow_key)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def generate_and_write_outcome(
    workflow: str,
    case_id: str,
    result: Any,
    status: str = "completed",
    execution_profile: str = "default",
) -> dict[str, Any]:
    contract = build_outcome_contract(
        workflow=workflow,
        case_id=case_id,
        result=result,
        status=status,
        execution_profile=execution_profile,
    )
    contract_path = _resolve_outcome_path(case_id, workflow)
    contract["contract_path"] = str(contract_path.relative_to(WORKSPACE))
    fallback_evidence = contract["contract_path"]
    contract["dimensions"]["conclusion"] = _ensure_dimension_evidence(contract["dimensions"]["conclusion"], fallback_evidence)
    contract["dimensions"]["recommendation"] = _ensure_dimension_evidence(contract["dimensions"]["recommendation"], fallback_evidence)
    contract["dimensions"]["accuracy"] = _ensure_dimension_evidence(contract["dimensions"]["accuracy"], fallback_evidence)
    errors = validate_outcome_contract(contract)
    if errors:
        contract["validation_errors"] = errors
    path = write_outcome_contract(contract)
    contract["contract_path"] = str(path.relative_to(WORKSPACE))
    return contract
