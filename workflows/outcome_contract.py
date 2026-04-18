from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
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
WORKFLOW_CANONICALIZATION_PATH = WORKSPACE / "hydromind" / "configs" / "platform" / "workflow_canonicalization.v1.yaml"
if not WORKFLOW_CANONICALIZATION_PATH.exists():
    WORKFLOW_CANONICALIZATION_PATH = WORKSPACE.parent / "hydromind" / "configs" / "platform" / "workflow_canonicalization.v1.yaml"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def _workflow_alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    payload = _load_yaml(WORKFLOW_CANONICALIZATION_PATH)
    workflows = payload.get("workflows") if isinstance(payload, dict) else {}
    if not isinstance(workflows, dict):
        return mapping
    for canonical_key, meta in workflows.items():
        canonical = str(canonical_key).strip()
        if not canonical:
            continue
        aliases = [canonical, *list((meta or {}).get("legacy_aliases") or [])]
        for alias in aliases:
            normalized = str(alias).strip()
            if normalized:
                mapping[normalized] = canonical
    return mapping


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


def _existing_workspace_paths(paths: list[str]) -> list[str]:
    return [
        normalized
        for normalized in _unique_preserve_order([_to_rel_path(path) for path in paths if path])
        if _exists_in_workspace(normalized)
    ]


def _collect_step_output_paths(report: dict[str, Any]) -> list[str]:
    outputs: list[str] = []
    for step in report.get("steps", []):
        if not isinstance(step, dict):
            continue
        step_outputs = step.get("outputs", {})
        if not isinstance(step_outputs, dict):
            continue
        for value in step_outputs.values():
            if isinstance(value, str):
                outputs.append(value)
    return _existing_workspace_paths(outputs)


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
            f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
            f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.md",
            f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
            f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
            f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
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
    normalized = str(workflow or "").strip()
    item = wf_map.get(normalized, {})
    if not item:
        alias_map = _workflow_alias_map()
        canonical = alias_map.get(normalized, normalized)
        for legacy_key, candidate in wf_map.items():
            if alias_map.get(str(legacy_key).strip(), str(legacy_key).strip()) == canonical:
                item = candidate or {}
                break
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
            f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
            f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.md",
            f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
            f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
            f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
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
    launch_review = detail_report.get("launch_review_path", {}) if isinstance(detail_report.get("launch_review_path"), dict) else {}

    if not launch_review:
        live_dashboard = [
            path
            for path in [
                f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
                f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.md",
            ]
            if _exists_in_workspace(path)
        ]
        verification_assets = [
            path
            for path in [
                f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
                f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
                f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
            ]
            if _exists_in_workspace(path)
        ]
        if strict_evidence:
            launch_review["strict_revalidation_summary"] = strict_evidence
        if live_dashboard:
            launch_review["live_dashboard"] = live_dashboard
        if verification_assets:
            launch_review["verification_assets"] = verification_assets
        if launch_review:
            launch_review["review_sequence"] = [
                *([launch_review["strict_revalidation_summary"]] if launch_review.get("strict_revalidation_summary") else []),
                *(launch_review.get("live_dashboard", []) or []),
                *(launch_review.get("verification_assets", []) or []),
            ]

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
    if launch_review:
        recommendation_entries.append(
            _make_entry(
                "启动/审查路径",
                launch_review,
                evidence_path=evidence,
                confidence=0.9,
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
                        "launch_review": launch_review,
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
    failed_count = sum(
        int(module.get("failed_tests", 0))
        for module in modules.values()
        if isinstance(module, dict) and isinstance(module.get("failed_tests"), (int, float))
    )
    metrics = {
        key: value
        for key, value in {
            "pass_rate": physics.get("pass_rate"),
            "physics_score": physics.get("average_score"),
            "control_score": control.get("average_score"),
            "failed_tests": failed_count,
        }.items()
        if isinstance(value, (int, float))
    }
    quality_gate = detail.get("quality_gate", {}) if isinstance(detail.get("quality_gate"), dict) else {}
    quality_passed = quality_gate.get("passed")
    if quality_passed is None:
        quality_passed = detail.get("quality_gate_passed")
    if quality_passed is None:
        quality_passed = failed_count == 0
    quality_status = str(quality_gate.get("status", "") or detail.get("quality_status", "") or "").strip()
    if not quality_status:
        quality_status = "passed" if bool(quality_passed) else "failed"
    quality_reason = str(quality_gate.get("reason", "") or detail.get("quality_reason", "") or "").strip()
    if not quality_reason:
        quality_reason = (
            "all strict revalidation checks passed"
            if bool(quality_passed)
            else f"strict revalidation failed_tests={failed_count}"
        )
    process_status = "completed" if bool(quality_passed) else "quality_failed"
    conclusion_text = (
        f"严格复核未达标：{quality_reason}。"
        if not bool(quality_passed)
        else "严格复核通过，未发现失败项。"
    )
    recommendation_text = (
        "优先处理 strict_revalidation_summary.json 中的 failed_samples，并复跑相关模块。"
        if not bool(quality_passed)
        else "保持当前测试基线，继续执行自治闭环与验收链路。"
    )
    return {
        "artifacts": summary_path,
        "metrics": metrics,
        "dimensions": {
            "process": [
                _make_entry("执行状态", process_status, evidence_path=evidence, confidence=0.95),
                _make_entry(
                    "质量门禁",
                    {
                        "passed": bool(quality_passed),
                        "status": quality_status,
                        "failed_tests": failed_count,
                        "reason": quality_reason,
                    },
                    evidence_path=evidence,
                    confidence=0.93,
                ),
            ],
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


def _specialize_source_to_delineation(case_id: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}

    pipeline_report_path = f"cases/{case_id}/contracts/pipeline_report.latest.json"
    data_pack_path = f"cases/{case_id}/contracts/data_pack.latest.json"
    delineation_path = f"cases/{case_id}/contracts/watershed_delineation_result.latest.json"
    control_station_mapping_path = f"cases/{case_id}/source_selection/product_outputs/control_station_mapping.json"
    ready_outlets_path = f"cases/{case_id}/source_selection/product_outputs/outlets.delineation_ready.json"
    source_reliability_path = f"cases/{case_id}/source_selection/product_outputs/source_reliability.json"
    coordinate_validation_path = f"cases/{case_id}/source_selection/product_outputs/coordinate_validation.json"
    source_selector_path = f"cases/{case_id}/source_selection/index.html"

    pipeline_report = _read_json_if_exists(pipeline_report_path)
    delineation_report = _read_json_if_exists(delineation_path)
    control_station_mapping = _read_json_if_exists(control_station_mapping_path)
    ready_outlets = _read_json_if_exists(ready_outlets_path)
    coordinate_validation = _read_json_if_exists(coordinate_validation_path)

    evidence_paths = _existing_workspace_paths(
        [
            pipeline_report_path,
            *_collect_step_output_paths(pipeline_report),
            data_pack_path,
            delineation_path,
            control_station_mapping_path,
            ready_outlets_path,
            source_reliability_path,
            coordinate_validation_path,
            source_selector_path,
        ]
    )
    evidence = evidence_paths[0] if evidence_paths else ""

    mappings = control_station_mapping.get("mappings", []) if isinstance(control_station_mapping.get("mappings"), list) else []
    outlets = ready_outlets.get("outlets", []) if isinstance(ready_outlets.get("outlets"), list) else []
    basins = delineation_report.get("basins", []) if isinstance(delineation_report.get("basins"), list) else []
    summary = pipeline_report.get("summary", {}) if isinstance(pipeline_report.get("summary"), dict) else {}
    step_status = {
        str(step.get("stage")): str(step.get("status"))
        for step in pipeline_report.get("steps", [])
        if isinstance(step, dict) and step.get("stage")
    }

    ready_outlet_count = ready_outlets.get("count") if isinstance(ready_outlets.get("count"), int) else len(outlets)
    basin_count = len(basins) or (summary.get("basins") and len(summary.get("basins"))) or 0
    total_area_km2 = delineation_report.get("total_area_km2", summary.get("total_area_km2"))
    anomaly_count = coordinate_validation.get("anomaly_count")

    result_summary = {
        "mapped_stations": len(mappings),
        "ready_outlets": ready_outlet_count,
        "basin_count": basin_count,
        "total_area_km2": total_area_km2,
        "step_status": step_status,
        "coordinate_anomaly_count": anomaly_count,
    }

    # Task 4: Generic Area Error Analyzer
    try:
        import yaml
        from pathlib import Path
        import json
        
        true_areas = {}
        topology = {}
        
        def _parse_for_stations(node):
            if isinstance(node, dict):
                if 'name' in node and ('basin_area_km2' in node or 'downstream_station' in node):
                    name = node['name']
                    if 'basin_area_km2' in node and node['basin_area_km2'] is not None:
                        true_areas[name] = float(node['basin_area_km2'])
                    if 'downstream_station' in node and node['downstream_station']:
                        topology[name] = node['downstream_station']
                for k, v in node.items():
                    _parse_for_stations(v)
            elif isinstance(node, list):
                for item in node:
                    _parse_for_stations(item)

        def _load_and_parse_yaml(path: Path):
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        cfg = yaml.safe_load(f) or {}
                        _parse_for_stations(cfg)
                except Exception:
                    pass

        _load_and_parse_yaml(Path(f"Hydrology/configs/{case_id}.yaml"))
        _load_and_parse_yaml(Path(f"Hydrology/knowledge/{case_id}/params/control.yaml"))
        _load_and_parse_yaml(Path(f"Hydrology/knowledge/{case_id}/topology/topology.yaml"))
        for p in Path("Hydrology/configs").glob(f"{case_id}.pre_split_*.yaml"):
            _load_and_parse_yaml(p)

        knowledge_path = Path(f"cases/{case_id}/contracts/knowledge.latest.json")
        if knowledge_path.exists():
            try:
                with open(knowledge_path, 'r', encoding='utf-8') as f:
                    _parse_for_stations(json.load(f))
            except Exception:
                pass

        upstreams = {}
        for st, down in topology.items():
            upstreams.setdefault(down, []).append(st)

        local_areas = {b["name"]: float(b.get("area_km2", 0.0)) for b in basins if "name" in b}
        
        memo = {}
        def get_acc_area(node: str) -> float:
            if node in memo:
                return memo[node]
            area = local_areas.get(node, 0.0)
            for up in upstreams.get(node, []):
                area += get_acc_area(up)
            memo[node] = area
            return area

        acc_areas = {name: get_acc_area(name) for name in local_areas.keys()}
        
        area_metrics = {}
        for name in local_areas.keys():
            loc_area = local_areas[name]
            acc_area = acc_areas[name]
            true_area = true_areas.get(name)
            
            metrics_dict = {
                "local_area_km2": loc_area,
                "accumulated_area_km2": acc_area,
            }
            
            if true_area is not None and true_area > 0:
                metrics_dict["true_accumulated_area_km2"] = true_area
                acc_err = abs(acc_area - true_area) / true_area
                metrics_dict["accumulated_area_error_pct"] = round(acc_err * 100, 2)
                
                true_local = true_area
                for up in upstreams.get(name, []):
                    if up in true_areas:
                        true_local -= true_areas[up]
                
                if true_local > 0:
                    loc_err = abs(loc_area - true_local) / true_local
                    metrics_dict["true_local_area_km2"] = true_local
                    metrics_dict["local_area_error_pct"] = round(loc_err * 100, 2)
                    
            area_metrics[name] = metrics_dict
            
        if area_metrics:
            result_summary["area_metrics"] = area_metrics
            if pipeline_report:
                pipeline_report.setdefault("metrics", {})["area_errors"] = area_metrics
                try:
                    with open(pipeline_report_path, 'w', encoding='utf-8') as f:
                        json.dump(pipeline_report, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
    except Exception as e:
        result_summary["area_metrics_error"] = str(e)
    conclusion_text = (
        f"source_to_delineation 已将 workflow 报告、{len(mappings)} 个 control-station mapping、"
        f"{ready_outlet_count} 个可用 outlet 与 {basin_count} 个 basin 结果绑定到同一条证据链。"
    )
    recommendation_text = (
        "HydroDesk 与验收链路应优先消费 pipeline_report/control_station_mapping/"
        "outlets.delineation_ready/watershed_delineation_result，而不是只回退到单一路径或 stdout 摘要。"
    )

    return {
        "artifacts": evidence_paths,
        "dimensions": {
            "result": [
                _make_entry("识地链路摘要", result_summary, evidence_path=evidence, confidence=0.94),
            ],
            "conclusion": [
                _make_entry("识地结论", conclusion_text, evidence_path=evidence, confidence=0.94),
            ],
            "recommendation": [
                _make_entry("识地建议", recommendation_text, evidence_path=evidence, confidence=0.91),
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
        "source_to_delineation": _specialize_source_to_delineation,
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
