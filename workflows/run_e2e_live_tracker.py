#!/usr/bin/env python3
"""协智 (XieZhi) — 多智能体编排与科研

HydroMind 水智工坊 · Agent #20

实时 E2E 追踪器：
- 读取基线报告中的 workflow 列表
- 逐个调用 hm_run_workflow 真实执行
- 持续刷新 Markdown 看板 + JSON 进度文件（可在 Cursor 实时查看）
"""
from __future__ import annotations

import argparse
import html
import json
import time
import uuid
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any
import yaml

WORKSPACE = Path(__file__).resolve().parents[2]
if not (WORKSPACE / "cases").exists():
    WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Hydrology.mcp_server import hm_run_workflow

OUTCOME_COVERAGE_THRESHOLD = 0.95
OUTCOME_TEMPLATES_PATH = WORKSPACE / "Hydrology" / "configs" / "outcome_templates.yaml"
AGENT_REGISTRY_PATH = WORKSPACE / "Hydrology" / "configs" / "agent_registry.yaml"
WORKFLOW_CANONICALIZATION_PATH = WORKSPACE / "hydromind" / "configs" / "platform" / "workflow_canonicalization.v1.yaml"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_outcome_templates() -> dict[str, Any]:
    if not OUTCOME_TEMPLATES_PATH.exists():
        return {}
    return yaml.safe_load(OUTCOME_TEMPLATES_PATH.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def _load_agent_registry() -> dict[str, Any]:
    if not AGENT_REGISTRY_PATH.exists():
        return {}
    return yaml.safe_load(AGENT_REGISTRY_PATH.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def _load_workflow_canonicalization() -> dict[str, Any]:
    if not WORKFLOW_CANONICALIZATION_PATH.exists():
        return {}
    return yaml.safe_load(WORKFLOW_CANONICALIZATION_PATH.read_text(encoding="utf-8")) or {}


def _canonical_workflow_key(workflow_key: str, outcome: dict[str, Any] | None = None) -> str:
    explicit = str(((outcome or {}).get("canonical_workflow_key")) or "").strip()
    if explicit:
        return explicit
    normalized = str(workflow_key or "").strip()
    workflows = dict((_load_workflow_canonicalization().get("workflows") or {}))
    for canonical_key, meta in workflows.items():
        aliases = [str(item).strip() for item in list((meta or {}).get("legacy_aliases") or []) if str(item).strip()]
        if normalized == str(canonical_key).strip() or normalized in aliases:
            return str(canonical_key).strip()
    return normalized


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_work_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for agent in report.get("agent_results", []):
        for wf in agent.get("workflow_results", []):
            key = wf.get("workflow_key")
            if not key:
                continue
            items.append(
                {
                    "agent_id": agent.get("agent_id"),
                    "agent_name": agent.get("agent_name"),
                    "workflow_path": wf.get("workflow_path"),
                    "workflow_key": key,
                }
            )
    return items


def _safe_json_loads(payload: str) -> dict[str, Any] | None:
    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _extract_paths_from_obj(obj: Any) -> list[str]:
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
            # 仅提取可能是文件路径的字符串（绝对/相对）
            if "/" in s and any(
                s.lower().endswith(ext)
                for ext in (
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
                )
            ):
                found.append(s)
    # 去重保持顺序
    dedup: list[str] = []
    seen: set[str] = set()
    for p in found:
        if p in seen:
            continue
        seen.add(p)
        dedup.append(p)
    return dedup


def _to_rel_path(path_str: str) -> str:
    p = Path(path_str)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(WORKSPACE))
        except Exception:
            return str(p)
    return path_str


def _load_outcome_contract(case_id: str, workflow_key: str) -> dict[str, Any] | None:
    p = WORKSPACE / "cases" / case_id / "contracts" / "outcomes" / f"{workflow_key}.latest.json"
    if not p.exists():
        return None
    return _safe_json_loads(p.read_text(encoding="utf-8"))


def _outcome_contract_exists(case_id: str, workflow_key: str) -> bool:
    p = WORKSPACE / "cases" / case_id / "contracts" / "outcomes" / f"{workflow_key}.latest.json"
    return p.exists()


def _unique_executed_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    unique_map: dict[str, dict[str, Any]] = {}
    duplicates: dict[str, int] = {}
    for record in records:
        workflow_key = str(record.get("workflow_key", "")).strip()
        if not workflow_key:
            continue
        duplicates[workflow_key] = duplicates.get(workflow_key, 0) + 1
        unique_map[workflow_key] = record
    duplicate_runs = {key: count for key, count in duplicates.items() if count > 1}
    return list(unique_map.values()), duplicate_runs


def _build_outcome_coverage_report(state: dict[str, Any]) -> dict[str, Any]:
    case_id = str(state.get("case_id", ""))
    executed = [
        record
        for record in state.get("records", [])
        if record.get("status") in {"passed", "failed", "timeout"}
    ]
    unique_executed, duplicate_runs = _unique_executed_records(executed)
    generated = 0
    valid = 0
    evidence_bound = 0
    details: list[dict[str, Any]] = []

    for record in unique_executed:
        workflow_key = str(record.get("workflow_key", ""))
        outcome = _load_outcome_contract(case_id, workflow_key)
        generated_flag = outcome is not None
        validation_errors = outcome.get("validation_errors", []) if isinstance(outcome, dict) else ["missing_outcome"]
        conclusion_items = ((outcome or {}).get("dimensions") or {}).get("conclusion") or []
        recommendation_items = ((outcome or {}).get("dimensions") or {}).get("recommendation") or []
        all_evidence_items = [
            item
            for item in [*conclusion_items, *recommendation_items]
            if isinstance(item, dict)
        ]
        evidence_ok = bool(all_evidence_items) and all(str(item.get("evidence_path", "")).strip() for item in all_evidence_items)

        if generated_flag:
            generated += 1
        if generated_flag and not validation_errors:
            valid += 1
        if generated_flag and evidence_ok:
            evidence_bound += 1

        details.append(
            {
                "workflow_key": workflow_key,
                "status": record.get("status"),
                "outcome_generated": generated_flag,
                "template_id": (outcome or {}).get("template_id"),
                "contract_path": (outcome or {}).get("contract_path"),
                "validation_errors": validation_errors,
                "evidence_bound": evidence_ok,
            }
        )

    total_executed = len(unique_executed)
    coverage = generated / total_executed if total_executed else 0.0
    gate_passed = coverage >= OUTCOME_COVERAGE_THRESHOLD and generated == valid and generated == evidence_bound
    return {
        "case_id": case_id,
        "generated_at": _now_iso(),
        "threshold": OUTCOME_COVERAGE_THRESHOLD,
        "total_executed": total_executed,
        "outcomes_generated": generated,
        "schema_valid_count": valid,
        "evidence_bound_count": evidence_bound,
        "outcome_coverage": coverage,
        "gate_status": "passed" if gate_passed else "blocked",
        "missing_workflows": [item["workflow_key"] for item in details if not item["outcome_generated"]],
        "invalid_workflows": [item["workflow_key"] for item in details if item["validation_errors"]],
        "unevidenced_workflows": [item["workflow_key"] for item in details if item["outcome_generated"] and not item["evidence_bound"]],
        "duplicate_runs": duplicate_runs,
        "details": details,
        "_auto_generated": True,
    }


def _write_outcome_coverage_report(contracts_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    report = _build_outcome_coverage_report(state)
    report_path = contracts_dir / "outcome_coverage_report.latest.json"
    _save_json(report_path, report)
    summary = state.setdefault("summary", {})
    summary["outcomes_generated"] = report.get("outcomes_generated", 0)
    summary["outcome_coverage"] = report.get("outcome_coverage", 0.0)
    summary["outcome_gate_status"] = report.get("gate_status", "blocked")
    summary["outcome_gate_threshold"] = report.get("threshold", OUTCOME_COVERAGE_THRESHOLD)
    summary["schema_valid_count"] = report.get("schema_valid_count", 0)
    summary["evidence_bound_count"] = report.get("evidence_bound_count", 0)
    summary["outcome_coverage_report"] = str(report_path.relative_to(WORKSPACE))
    return report


def _load_outcome_coverage_report_from_state(state: dict[str, Any]) -> dict[str, Any] | None:
    summary = state.get("summary", {}) or {}
    report_rel = str(summary.get("outcome_coverage_report", "")).strip()
    case_id = str(state.get("case_id", "")).strip()
    if report_rel:
        report_path = WORKSPACE / report_rel
    elif case_id:
        report_path = WORKSPACE / "cases" / case_id / "contracts" / "outcome_coverage_report.latest.json"
    else:
        return None
    if not report_path.exists():
        return None
    return _safe_json_loads(report_path.read_text(encoding="utf-8"))


def _summary_for_render(state: dict[str, Any]) -> dict[str, Any]:
    summary = dict(state.get("summary", {}) or {})
    report = _load_outcome_coverage_report_from_state(state)
    if isinstance(report, dict):
        summary["outcomes_generated"] = report.get("outcomes_generated", summary.get("outcomes_generated", 0))
        summary["outcome_coverage"] = report.get("outcome_coverage", summary.get("outcome_coverage", 0.0))
        summary["outcome_gate_status"] = report.get("gate_status", summary.get("outcome_gate_status", "blocked"))
        summary["outcome_gate_threshold"] = report.get("threshold", summary.get("outcome_gate_threshold", OUTCOME_COVERAGE_THRESHOLD))
        summary["schema_valid_count"] = report.get("schema_valid_count", summary.get("schema_valid_count", 0))
        summary["evidence_bound_count"] = report.get("evidence_bound_count", summary.get("evidence_bound_count", 0))
    effective_records = _records_with_effective_status(state)
    summary["passed"] = sum(1 for record in effective_records if record.get("status") == "passed")
    summary["failed"] = sum(1 for record in effective_records if record.get("status") == "failed")
    summary["timeout"] = sum(1 for record in effective_records if record.get("status") == "timeout")
    return summary


def _effective_record_status(case_id: str, record: dict[str, Any]) -> str:
    status = str(record.get("status", "") or "")
    if status in {"failed", "timeout"}:
        return status
    if status != "passed":
        return status or "pending"
    workflow_key = str(record.get("workflow_key", "") or "")
    if not workflow_key:
        return status
    outcome = _load_outcome_contract(case_id, workflow_key)
    if not outcome:
        return status
    outcome_status = str(outcome.get("status", "") or "").strip().lower()
    if outcome_status in {"failed", "quality_failed"}:
        return "failed"
    process_items = ((outcome.get("dimensions") or {}).get("process") or [])
    for item in process_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("label", "")).strip() != "执行状态":
            continue
        process_status = str(item.get("value", "") or "").strip().lower()
        if process_status in {"failed", "quality_failed"}:
            return "failed"
    conclusion_items = ((outcome.get("dimensions") or {}).get("conclusion") or [])
    for item in conclusion_items:
        if not isinstance(item, dict):
            continue
        conclusion_text = str(item.get("value", "") or "")
        if "执行失败" in conclusion_text or "失败项" in conclusion_text:
            return "failed"
    return status


def _records_with_effective_status(state: dict[str, Any]) -> list[dict[str, Any]]:
    case_id = str(state.get("case_id", "") or "")
    effective: list[dict[str, Any]] = []
    for record in state.get("records", []):
        cloned = dict(record)
        cloned["status"] = _effective_record_status(case_id, record)
        effective.append(cloned)
    return effective


def _collect_step_outcomes(state: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    case_id = str(state.get("case_id", ""))
    for r in _records_with_effective_status(state):
        if r.get("status") not in {"passed", "failed", "timeout"}:
            continue
        oc = _load_outcome_contract(case_id, str(r.get("workflow_key", "")))
        summary = "待生成 outcome 契约"
        artifacts: list[str] = []
        accuracy = "-"
        conclusion = "-"
        if oc:
            process_items = ((oc.get("dimensions") or {}).get("process") or [])
            if process_items and isinstance(process_items, list):
                summary = str((process_items[-1] or {}).get("value", summary))
            artifacts = [
                str(item.get("path"))
                for item in (oc.get("artifacts") or [])
                if isinstance(item, dict) and item.get("exists")
            ][:4]
            metrics = oc.get("metrics") or {}
            if isinstance(metrics, dict) and metrics:
                first_pairs = [f"{k}={v}" for k, v in list(metrics.items())[:2]]
                accuracy = ", ".join(first_pairs) if first_pairs else "-"
            cons_items = ((oc.get("dimensions") or {}).get("conclusion") or [])
            rec_items = ((oc.get("dimensions") or {}).get("recommendation") or [])
            cons = str((cons_items[0] or {}).get("value", "")) if cons_items else ""
            rec = str((rec_items[0] or {}).get("value", "")) if rec_items else ""
            conclusion = f"{cons} / {rec}".strip(" /") if (cons or rec) else "-"
        outcomes.append(
            {
                "workflow_key": r.get("workflow_key"),
                "agent_name": r.get("agent_name"),
                "status": r.get("status"),
                "summary": summary,
                "artifacts": artifacts,
                "accuracy": accuracy,
                "conclusion": conclusion,
            }
        )
    return outcomes


def _fallback_navigation_assets(case_id: str, contracts_dir: Path) -> dict[str, list[str]]:
    # 兜底：如果 outcome 未覆盖，回退到 contracts 目录启发式聚合。
    all_files = sorted(contracts_dir.glob("*"))
    buckets: dict[str, list[str]] = {
        "topology": [],
        "gis": [],
        "chart": [],
        "table": [],
        "conclusion": [],
        "advice": [],
    }
    for fp in all_files:
        if not fp.is_file():
            continue
        rel = str(fp.relative_to(WORKSPACE))
        name = fp.name.lower()
        if any(k in name for k in ("topology", "network", "delineation", "outlets", "basin")):
            buckets["topology"].append(rel)
        if any(k in name for k in ("gis", "dem", "shp", "geo", "watershed")):
            buckets["gis"].append(rel)
        if fp.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".html"}:
            buckets["chart"].append(rel)
        if fp.suffix.lower() in {".csv", ".xlsx"} or "table" in name:
            buckets["table"].append(rel)
        if any(k in name for k in ("report", "assessment", "autorun", "precision")) and fp.suffix.lower() in {".md", ".json"}:
            buckets["conclusion"].append(rel)
        if any(k in name for k in ("autonomy", "assessment", "selfdiag", "revalidation")) and fp.suffix.lower() in {".md", ".json"}:
            buckets["advice"].append(rel)

    # 兜底关键成果（若命中为空）
    fallback = {
        "topology": [
            f"cases/{case_id}/contracts/pipeline_report.latest.json",
            f"cases/{case_id}/contracts/watershed_delineation_result.latest.json",
        ],
        "gis": [f"cases/{case_id}/contracts/watershed_dem_architecture_report.md"],
        "chart": [f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html"],
        "table": [f"cases/{case_id}/contracts/d1d4_precision_report.latest.json"],
        "conclusion": [f"cases/{case_id}/contracts/autonomy_assessment.latest.md"],
        "advice": [f"cases/{case_id}/contracts/autonomy_autorun.latest.md"],
    }
    for key, vals in fallback.items():
        if not buckets[key]:
            buckets[key].extend(vals)
    for key in buckets:
        # 去重 + 限流
        uniq = list(dict.fromkeys(buckets[key]))
        buckets[key] = uniq[:6]
    return buckets


def _coerce_text(value: Any, limit: int = 180) -> str:
    text = str(value).replace("\n", " ").strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _template_meta(template_id: str) -> dict[str, str]:
    templates = (_load_outcome_templates().get("templates", {}) or {})
    item = templates.get(template_id, {}) if isinstance(templates, dict) else {}
    return {
        "name": str(item.get("name", template_id or "未命名模板")),
        "business_goal": str(item.get("business_goal", "")),
    }


def _is_display_result_asset(case_id: str, path_str: str) -> bool:
    rel = _to_rel_path(path_str)
    prefixes = (
        f"cases/{case_id}/contracts/",
        f"cases/{case_id}/source_selection/",
        "reports/acceptance/",
    )
    return rel.startswith(prefixes)


def _discover_workflow_result_assets(case_id: str, workflow_key: str) -> list[str]:
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    candidates = [
        contracts_dir / f"{workflow_key}.latest.html",
        contracts_dir / f"{workflow_key}.latest.md",
        contracts_dir / f"{workflow_key}.latest.json",
        contracts_dir / f"{workflow_key}.html",
        contracts_dir / f"{workflow_key}.md",
        contracts_dir / f"{workflow_key}.json",
    ]
    found: list[str] = []
    for path in candidates:
        if path.exists():
            found.append(str(path.relative_to(WORKSPACE)))
    return found


def _result_asset_paths(case_id: str, workflow_key: str, outcome: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    contract_path = str(outcome.get("contract_path", "")).strip()
    evidence_path = str(outcome.get("evidence_path", "")).strip()
    if evidence_path:
        candidates.append(_to_rel_path(evidence_path))
    for art in outcome.get("artifacts", []) or []:
        if isinstance(art, dict) and art.get("path"):
            candidates.append(_to_rel_path(str(art["path"])))
    candidates.extend(_discover_workflow_result_assets(case_id, workflow_key))
    if contract_path:
        candidates.append(_to_rel_path(contract_path))

    curated: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if _is_display_result_asset(case_id, path):
            curated.append(path)
    return curated[:6]


def _outcome_cards(state: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    case_id = str(state.get("case_id", ""))
    effective_records = _records_with_effective_status(state)
    unique_records, _ = _unique_executed_records(effective_records)
    by_key = {str(record.get("workflow_key", "")): record for record in unique_records}

    for workflow_key, record in reversed(list(by_key.items())):
        if not workflow_key:
            continue
        outcome = _load_outcome_contract(case_id, workflow_key)
        if not outcome:
            continue
        template_id = str(outcome.get("template_id", ""))
        template_meta = _template_meta(template_id)
        dims = outcome.get("dimensions", {}) or {}
        result_items = dims.get("result") or []
        process_items = dims.get("process") or []
        accuracy_items = dims.get("accuracy") or []
        conclusion_items = dims.get("conclusion") or []
        recommendation_items = dims.get("recommendation") or []
        summary_entry = process_items[-1] if process_items else (result_items[0] if result_items else {})
        accuracy_entry = accuracy_items[0] if accuracy_items else {}
        conclusion_entry = conclusion_items[0] if conclusion_items else {}
        recommendation_entry = recommendation_items[0] if recommendation_items else {}
        process_trace = [
            _coerce_text(item.get("value", ""))
            for item in process_items[:4]
            if isinstance(item, dict) and item.get("value")
        ]
        cards.append(
            {
                "workflow_key": workflow_key,
                "canonical_workflow_key": _canonical_workflow_key(workflow_key, outcome),
                "agent_name": record.get("agent_name"),
                "status": record.get("status"),
                "template_id": template_id,
                "template_name": template_meta["name"],
                "category": outcome.get("category"),
                "business_goal": template_meta["business_goal"],
                "summary": _coerce_text((summary_entry or {}).get("value", "待生成结果摘要")),
                "accuracy": _coerce_text((accuracy_entry or {}).get("value", "-")),
                "conclusion": _coerce_text((conclusion_entry or {}).get("value", "-")),
                "recommendation": _coerce_text((recommendation_entry or {}).get("value", "-")),
                "contract_path": str(outcome.get("contract_path", "")),
                "evidence_path": str(outcome.get("evidence_path", "")),
                "process_trace": process_trace,
                "result_assets": _result_asset_paths(case_id, workflow_key, outcome),
            }
        )
    return cards


def _agent_meta(agent_id: str, agent_name: str) -> dict[str, Any]:
    agents = (_load_agent_registry().get("agents", {}) or {})
    if agent_id and agent_id in agents:
        meta = agents.get(agent_id, {}) or {}
        return {
            "agent_id": agent_id,
            "agent_name": meta.get("name", agent_name or agent_id),
            "subtitle": meta.get("subtitle", ""),
            "description": meta.get("description", ""),
            "lifecycle_phase": meta.get("lifecycle_phase", ""),
            "projects": meta.get("projects", []),
        }
    for key, info in agents.items():
        if str((info or {}).get("name", "")).strip() == agent_name:
            meta = info or {}
            return {
                "agent_id": key,
                "agent_name": meta.get("name", agent_name or key),
                "subtitle": meta.get("subtitle", ""),
                "description": meta.get("description", ""),
                "lifecycle_phase": meta.get("lifecycle_phase", ""),
                "projects": meta.get("projects", []),
            }
    return {
        "agent_id": agent_id,
        "agent_name": agent_name or agent_id or "未命名 Agent",
        "subtitle": "",
        "description": "",
        "lifecycle_phase": "",
        "projects": [],
    }


def _agent_cards(state: dict[str, Any]) -> list[dict[str, Any]]:
    source_report = str(state.get("source_report", "")).strip()
    report_data = _load_json(Path(source_report)) if source_report and Path(source_report).exists() else {}
    all_items = _build_work_items(report_data) if report_data else []
    current = state.get("current") or {}
    current_key = str(current.get("workflow_key", ""))
    cards: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    status_by_workflow = {
        str(record.get("workflow_key", "")): record
        for record in _records_with_effective_status(state)
        if record.get("workflow_key")
    }

    for item in all_items:
        agent_id = str(item.get("agent_id", "") or "")
        agent_name = str(item.get("agent_name", "") or "")
        group_key = (agent_id, agent_name)
        if group_key not in grouped:
            grouped[group_key] = {
                **_agent_meta(agent_id, agent_name),
                "assigned_workflows": [],
                "passed": 0,
                "failed": 0,
                "timeout": 0,
                "pending": 0,
                "current_workflow": "",
            }
        workflow_key = str(item.get("workflow_key", ""))
        grouped[group_key]["assigned_workflows"].append(workflow_key)
        if workflow_key == current_key:
            grouped[group_key]["current_workflow"] = workflow_key
        record = status_by_workflow.get(workflow_key)
        if not record:
            grouped[group_key]["pending"] += 1
            continue
        status = str(record.get("status", ""))
        if status == "passed":
            grouped[group_key]["passed"] += 1
        elif status == "failed":
            grouped[group_key]["failed"] += 1
        elif status == "timeout":
            grouped[group_key]["timeout"] += 1
        else:
            grouped[group_key]["pending"] += 1

    for _, value in grouped.items():
        value["assigned_workflows"] = list(dict.fromkeys(value["assigned_workflows"]))
        cards.append(value)
    cards.sort(key=lambda item: (item.get("agent_id") or item.get("agent_name") or ""))
    return cards


def _business_navigation_assets(state: dict[str, Any]) -> dict[str, list[str]]:
    case_id = str(state.get("case_id", ""))
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    buckets: dict[str, list[str]] = {
        "topology": [],
        "gis": [],
        "chart": [],
        "table": [],
        "conclusion": [],
        "advice": [],
    }
    slot_to_bucket = {
        "topology": "topology",
        "gis": "gis",
        "charts": "chart",
        "tables": "table",
        "conclusions": "conclusion",
        "recommendations": "advice",
    }
    for rec in _records_with_effective_status(state):
        wf = str(rec.get("workflow_key", ""))
        if not wf:
            continue
        oc = _load_outcome_contract(case_id, wf)
        if not oc:
            continue
        slots = oc.get("slots") or {}
        if not isinstance(slots, dict):
            continue
        for slot_name, slot_items in slots.items():
            bucket_name = slot_to_bucket.get(slot_name)
            if not bucket_name or not isinstance(slot_items, list):
                continue
            for item in slot_items:
                if isinstance(item, dict) and item.get("path"):
                    rel_path = _to_rel_path(str(item["path"]))
                    if _is_display_result_asset(case_id, rel_path):
                        buckets[bucket_name].append(rel_path)

        for result_path in _result_asset_paths(case_id, wf, oc):
            lower = result_path.lower()
            if lower.endswith((".html", ".png", ".jpg", ".jpeg", ".svg")):
                buckets["chart"].append(result_path)
            elif lower.endswith((".geojson", ".shp")) or "source_selection" in lower:
                buckets["gis"].append(result_path)
            elif lower.endswith((".csv", ".xlsx")):
                buckets["table"].append(result_path)
            elif lower.endswith((".md", ".json")):
                buckets["conclusion"].append(result_path)

    for key in buckets:
        buckets[key] = list(dict.fromkeys(buckets[key]))[:6]

    fallback = _fallback_navigation_assets(case_id, contracts_dir)
    for key in buckets:
        if not buckets[key]:
            buckets[key] = fallback.get(key, [])
    return buckets


def _render_dashboard(md_path: Path, state: dict[str, Any]) -> None:
    summary = _summary_for_render(state)
    total = summary.get("total", 0)
    done = summary.get("passed", 0) + summary.get("failed", 0) + summary.get("timeout", 0)
    progress = (done / total * 100.0) if total else 0.0
    current = state.get("current")
    retry_cfg = state.get("retry", {}) or {}
    retry_max = retry_cfg.get("max_retries", 0)
    execution_profile = state.get("execution_profile", "unknown")
    source_report = state.get("source_report", "")
    current_workflow_label = str((current or {}).get("workflow_key") or "idle")
    current_agent_label = str((current or {}).get("agent_name") or "无活动 Agent")
    current_workflow_label = str((current or {}).get("workflow_key") or "idle")
    current_agent_label = str((current or {}).get("agent_name") or "无活动 Agent")

    lines = [
        f"# E2E 实时追踪看板（{state['case_id']}）",
        "",
        f"- run_id: `{state['run_id']}`",
        f"- started_at: {state['started_at']}",
        f"- last_updated_at: {state['last_updated_at']}",
        f"- execution_profile: `{execution_profile}`",
        f"- retry_max: `{retry_max}`",
        f"- source_report: `{source_report}`",
        "",
        "## 总览",
        "",
        f"- 进度: **{done}/{total} ({progress:.1f}%)**",
        f"- passed: **{summary.get('passed', 0)}**",
        f"- failed: **{summary.get('failed', 0)}**",
        f"- timeout: **{summary.get('timeout', 0)}**",
        f"- pending: **{summary.get('pending', 0)}**",
        f"- retries_used: **{summary.get('retries_used', 0)}**",
        f"- outcomes_generated: **{summary.get('outcomes_generated', 0)}**",
        f"- outcome_coverage: **{summary.get('outcome_coverage', 0.0):.1%}**",
        f"- outcome_gate_status: **{summary.get('outcome_gate_status', 'blocked')}** (threshold={summary.get('outcome_gate_threshold', OUTCOME_COVERAGE_THRESHOLD):.0%})",
        f"- outcome_coverage_report: `{summary.get('outcome_coverage_report', '')}`",
        "",
        "## 当前执行",
        "",
    ]
    if current:
        lines.extend(
            [
                f"- agent: `{current.get('agent_name')} ({current.get('agent_id')})`",
                f"- workflow: `{current.get('workflow_key')}`",
                f"- path: `{current.get('workflow_path')}`",
                f"- started_at: {current.get('started_at')}",
            ]
        )
    else:
        lines.append("- 当前无运行项")

    effective_records = _records_with_effective_status(state)
    failed_items = [r for r in reversed(effective_records) if r.get("status") in {"failed", "timeout"}]
    fail_count = len(failed_items)
    outcomes = _collect_step_outcomes(state)
    assets = _business_navigation_assets(state)
    outcome_cards = _outcome_cards(state)
    agent_cards = _agent_cards(state)

    lines.extend(
        [
            "",
            f"## 失败红榜（当前 {fail_count} 条）",
            "",
            "| status | attempts | agent | workflow_key | last_failed_at | error_excerpt |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for item in failed_items[:20]:
        excerpt = str(item.get("excerpt", "")).replace("\n", " ")
        if len(excerpt) > 140:
            excerpt = excerpt[:140] + "..."
        lines.append(
            f"| {item.get('status')} | {item.get('attempts', 1)} | {item.get('agent_name')} | "
            f"{item.get('workflow_key')} | {item.get('ended_at')} | {excerpt} |"
        )
    if not failed_items:
        lines.append("| - | - | - | - | - | 当前无失败项 |")

    lines.extend(
        [
            "",
            "## 步骤业务成果（最新 20 条）",
            "",
            "| status | agent | workflow_key | 业务成果摘要 | 精度要点 | 结论与建议 | 关键产物 |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for item in list(reversed(outcomes))[:20]:
        artifacts = "<br>".join(item.get("artifacts", [])[:3]) if item.get("artifacts") else "-"
        summary = str(item.get("summary", "")).replace("\n", " ")
        accuracy = str(item.get("accuracy", "-")).replace("\n", " ")
        conclusion = str(item.get("conclusion", "-")).replace("\n", " ")
        lines.append(
            f"| {item.get('status')} | {item.get('agent_name')} | {item.get('workflow_key')} | {summary} | {accuracy} | {conclusion} | {artifacts} |"
        )
    if not outcomes:
        lines.append("| - | - | - | 暂无成果 | - | - | - |")

    lines.extend(
        [
            "",
            "## 模板成果卡片（结果资产优先）",
            "",
        ]
    )
    for card in outcome_cards[:12]:
        result_assets = card.get("result_assets") or []
        lines.extend(
            [
                f"### {card.get('workflow_key')} · {card.get('template_name')}",
                f"- category: `{card.get('category')}` · agent: `{card.get('agent_name')}` · status: `{card.get('status')}`",
                f"- 业务目标: {card.get('business_goal') or '未配置业务目标'}",
                f"- 结果摘要: {card.get('summary')}",
                f"- 精度要点: {card.get('accuracy')}",
                f"- 结论: {card.get('conclusion')}",
                f"- 建议: {card.get('recommendation')}",
                f"- 结果入口: {'; '.join(result_assets) if result_assets else '待补充结果资产'}",
                "",
            ]
        )
    if not outcome_cards:
        lines.extend(["- 暂无 outcome 卡片", ""])

    lines.extend(
        [
            "",
            "## Agent 职责与承接工作",
            "",
        ]
    )
    for card in agent_cards:
        projects = ", ".join(card.get("projects") or []) or "-"
        workflows = ", ".join((card.get("assigned_workflows") or [])[:8]) or "-"
        lines.extend(
            [
                f"### {card.get('agent_name')}（{card.get('agent_id') or 'unknown'}） · {card.get('subtitle') or '未配置副标题'}",
                f"- 生命周期阶段: {card.get('lifecycle_phase') or '-'} · 项目: {projects}",
                f"- 职责: {_coerce_text(card.get('description') or '当前未接入更详细职责说明。', 220)}",
                f"- 承接 workflow: {workflows}",
                f"- 当前状态: passed={card.get('passed')} · failed={card.get('failed')} · timeout={card.get('timeout')} · pending={card.get('pending')}",
                f"- 当前执行: {card.get('current_workflow') or '无'}",
                "",
            ]
        )
    if not agent_cards:
        lines.extend(["- 暂无 Agent 职责卡片", ""])

    lines.extend(
        [
            "",
            "## 业务成果导航区（模板化六件套）",
            "",
            f"- 拓扑图: {'; '.join(assets['topology'])}",
            f"- GIS图: {'; '.join(assets['gis'])}",
            f"- 图表: {'; '.join(assets['chart'])}",
            f"- 表格: {'; '.join(assets['table'])}",
            f"- 结论: {'; '.join(assets['conclusion'])}",
            f"- 建议: {'; '.join(assets['advice'])}",
            "",
            "## 最近执行记录（最新 30 条）",
            "",
            "| status | attempts | agent | workflow_key | duration_s | started_at | ended_at |",
            "|---|---:|---|---|---:|---|---|",
        ]
    )
    for item in list(reversed(effective_records))[0:30]:
        lines.append(
            f"| {item.get('status')} | {item.get('attempts', 1)} | {item.get('agent_name')} | {item.get('workflow_key')} | "
            f"{item.get('duration_s', 0):.2f} | {item.get('started_at')} | {item.get('ended_at')} |"
        )
    if not state.get("records"):
        lines.append("| - | - | - | - | - | - | - |")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines), encoding="utf-8")


def _render_dashboard_html(html_path: Path, state: dict[str, Any]) -> None:
    summary = _summary_for_render(state)
    total = summary.get("total", 0)
    done = summary.get("passed", 0) + summary.get("failed", 0) + summary.get("timeout", 0)
    progress = (done / total * 100.0) if total else 0.0
    current = state.get("current")
    outcomes = _collect_step_outcomes(state)
    assets = _business_navigation_assets(state)
    outcome_cards = _outcome_cards(state)
    agent_cards = _agent_cards(state)
    default_agent_id = str((agent_cards[0] or {}).get("agent_id") or (agent_cards[0] or {}).get("agent_name") or "overview") if agent_cards else "overview"
    effective_records = _records_with_effective_status(state)
    records_by_workflow = {
        str(record.get("workflow_key", "")): record
        for record in effective_records
        if record.get("workflow_key")
    }
    retry_cfg = state.get("retry", {}) or {}
    retry_max = retry_cfg.get("max_retries", 0)
    execution_profile = state.get("execution_profile", "unknown")
    source_report = state.get("source_report", "")
    current_workflow_label = str((current or {}).get("workflow_key") or "idle")
    current_agent_label = str((current or {}).get("agent_name") or "无活动 Agent")
    rows = []
    for item in list(reversed(effective_records))[0:40]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('status')))}</td>"
            f"<td>{item.get('attempts', 1)}</td>"
            f"<td>{html.escape(str(item.get('agent_name')))}</td>"
            f"<td>{html.escape(str(item.get('workflow_key')))}</td>"
            f"<td>{item.get('duration_s', 0):.2f}</td>"
            f"<td>{html.escape(str(item.get('started_at')))}</td>"
            f"<td>{html.escape(str(item.get('ended_at')))}</td>"
            "</tr>"
        )
    failed_rows = []
    failed_items = [r for r in reversed(effective_records) if r.get("status") in {"failed", "timeout"}]
    for item in failed_items[0:20]:
        excerpt = str(item.get("excerpt", "")).replace("\n", " ")
        if len(excerpt) > 180:
            excerpt = excerpt[:180] + "..."
        failed_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('status')))}</td>"
            f"<td>{html.escape(str(item.get('workflow_key')))}</td>"
            f"<td title='{html.escape(excerpt)}'>{html.escape(str(item.get('agent_name')))}</td>"
            "</tr>"
        )
    outcome_rows = []
    for item in list(reversed(outcomes))[0:20]:
        artifacts = "<br>".join(html.escape(p) for p in item.get("artifacts", [])[:3]) if item.get("artifacts") else "-"
        accuracy = html.escape(str(item.get("accuracy", "-")))
        conclusion = html.escape(str(item.get("conclusion", "-")))
        outcome_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('status')))}</td>"
            f"<td>{html.escape(str(item.get('agent_name')))}</td>"
            f"<td>{html.escape(str(item.get('workflow_key')))}</td>"
            f"<td>{html.escape(str(item.get('summary')))}</td>"
            f"<td>{accuracy}</td>"
            f"<td>{conclusion}</td>"
            f"<td>{artifacts}</td>"
            "</tr>"
        )
    assets_html = "".join(
        [
            f"<li><b>拓扑图</b>: {html.escape('; '.join(assets['topology']))}</li>",
            f"<li><b>GIS图</b>: {html.escape('; '.join(assets['gis']))}</li>",
            f"<li><b>图表</b>: {html.escape('; '.join(assets['chart']))}</li>",
            f"<li><b>表格</b>: {html.escape('; '.join(assets['table']))}</li>",
            f"<li><b>结论</b>: {html.escape('; '.join(assets['conclusion']))}</li>",
            f"<li><b>建议</b>: {html.escape('; '.join(assets['advice']))}</li>",
        ]
    )
    current_html = (
        f"<div>agent: <b>{html.escape(str(current.get('agent_name')))}</b> "
        f"workflow: <code>{html.escape(str(current.get('workflow_key')))}</code> "
        f"path: <code>{html.escape(str(current.get('workflow_path')))}</code></div>"
        if current
        else "<div>当前无运行项</div>"
    )
    cards_html = []
    for card in outcome_cards[:12]:
        assets_html_list = "<br>".join(html.escape(path) for path in (card.get("result_assets") or [])) or "待补充结果资产"
        cards_html.append(
            "<div class='card' style='margin-bottom:12px'>"
            f"<div><b>{html.escape(str(card.get('workflow_key')))}</b> · {html.escape(str(card.get('template_name')))}</div>"
            f"<div style='margin-top:6px;font-size:12px;color:#555'>category={html.escape(str(card.get('category')))} · agent={html.escape(str(card.get('agent_name')))} · status={html.escape(str(card.get('status')))}</div>"
            f"<div style='margin-top:8px'><b>业务目标</b>: {html.escape(str(card.get('business_goal') or '未配置业务目标'))}</div>"
            f"<div><b>结果摘要</b>: {html.escape(str(card.get('summary')))}</div>"
            f"<div><b>精度要点</b>: {html.escape(str(card.get('accuracy')))}</div>"
            f"<div><b>结论</b>: {html.escape(str(card.get('conclusion')))}</div>"
            f"<div><b>建议</b>: {html.escape(str(card.get('recommendation')))}</div>"
            f"<div><b>结果入口</b>: {assets_html_list}</div>"
            "</div>"
        )
    agent_cards_html = []
    for card in agent_cards:
        agent_anchor = str(card.get("agent_id") or card.get("agent_name") or "unknown")
        workflows = "<br>".join(html.escape(workflow) for workflow in (card.get("assigned_workflows") or [])[:8]) or "-"
        outcome_blocks = []
        for workflow_key in card.get("assigned_workflows") or []:
            outcome = next((item for item in outcome_cards if item.get("workflow_key") == workflow_key), None)
            record = records_by_workflow.get(workflow_key, {})
            if outcome:
                assets_block = "<br>".join(html.escape(path) for path in (outcome.get("result_assets") or [])) or "待补充结果资产"
                outcome_blocks.append(
                    "<div class='result-card'>"
                    f"<div class='result-head'><b>{html.escape(str(workflow_key))}</b><span>{html.escape(str(record.get('status') or card.get('current_workflow') or 'pending'))}</span></div>"
                    f"<div><b>模板</b>: {html.escape(str(outcome.get('template_name')))}</div>"
                    f"<div><b>结果摘要</b>: {html.escape(str(outcome.get('summary')))}</div>"
                    f"<div><b>精度要点</b>: {html.escape(str(outcome.get('accuracy')))}</div>"
                    f"<div><b>结论</b>: {html.escape(str(outcome.get('conclusion')))}</div>"
                    f"<div><b>建议</b>: {html.escape(str(outcome.get('recommendation')))}</div>"
                    f"<div><b>结果入口</b>: {assets_block}</div>"
                    "</div>"
                )
            else:
                outcome_blocks.append(
                    "<div class='result-card'>"
                    f"<div class='result-head'><b>{html.escape(str(workflow_key))}</b><span>{html.escape(str(record.get('status') or 'pending'))}</span></div>"
                    "<div>当前还没有 outcome 合同，通常表示 workflow 未执行或结果还未固化。</div>"
                    "</div>"
                )
        projects = ", ".join(card.get("projects") or []) or "-"
        agent_cards_html.append(
            f"<button class='agent-nav-btn' data-agent='{html.escape(agent_anchor)}' onclick=\"showAgent('{html.escape(agent_anchor)}')\">"
            f"<div><b>{html.escape(str(card.get('agent_name')))}</b></div>"
            f"<div class='agent-nav-meta'>{html.escape(str(card.get('subtitle') or '未配置副标题'))}</div>"
            f"<div class='agent-nav-meta'>passed={card.get('passed')} · failed={card.get('failed')} · timeout={card.get('timeout')} · pending={card.get('pending')}</div>"
            "</button>"
        )
    agent_panels_html = []
    for card in agent_cards:
        agent_anchor = str(card.get("agent_id") or card.get("agent_name") or "unknown")
        workflows = "<br>".join(html.escape(workflow) for workflow in (card.get("assigned_workflows") or [])[:12]) or "-"
        workflow_nav_items = []
        workflow_detail_panels = []
        default_workflow_key = str((card.get("assigned_workflows") or [""])[0] or "")
        for workflow_key in card.get("assigned_workflows") or []:
            outcome = next((item for item in outcome_cards if item.get("workflow_key") == workflow_key), None)
            record = records_by_workflow.get(workflow_key, {})
            nav_summary = html.escape(str((outcome or {}).get("summary") or "待生成结果摘要"))
            workflow_nav_items.append(
                f"<button class='workflow-nav-btn' data-agent='{html.escape(agent_anchor)}' data-workflow='{html.escape(str(workflow_key))}' onclick=\"showWorkflow('{html.escape(agent_anchor)}','{html.escape(str(workflow_key))}')\">"
                f"<div style='display:flex;justify-content:space-between;gap:8px;align-items:flex-start;'><b>{html.escape(str(workflow_key))}</b><span class='badge'>{html.escape(str(record.get('status') or 'pending'))}</span></div>"
                f"<div class='agent-nav-meta'>{nav_summary}</div>"
                "</button>"
            )
            if outcome:
                result_assets = outcome.get("result_assets") or []
                assets_block = (
                    "<ul class='asset-list'>"
                    + "".join(f"<li>{html.escape(path)}</li>" for path in result_assets[:4])
                    + "</ul>"
                ) if result_assets else "<div class='asset-list-empty'>待补充结果资产</div>"
                process_trace = outcome.get("process_trace") or []
                process_trace_block = (
                    "<ul class='asset-list'>"
                    + "".join(f"<li>{html.escape(item)}</li>" for item in process_trace[:4])
                    + "</ul>"
                ) if process_trace else "<div class='asset-list-empty'>当前没有更细的过程摘要。</div>"
                contract_path = html.escape(str(outcome.get("contract_path") or ""))
                evidence_path = html.escape(str(outcome.get("evidence_path") or ""))
                started_at = html.escape(str(record.get("started_at") or ""))
                ended_at = html.escape(str(record.get("ended_at") or ""))
                duration_s = html.escape(str(record.get("duration_s") or ""))
                attempts = html.escape(str(record.get("attempts") or 1))
                workflow_detail_panels.append(
                    f"<section class='workflow-detail-panel' data-agent='{html.escape(agent_anchor)}' data-workflow='{html.escape(str(workflow_key))}'>"
                    "<div class='result-card'>"
                    f"<div class='result-head'><div><b>{html.escape(str(workflow_key))}</b><div class='agent-nav-meta'>{html.escape(str(outcome.get('template_name')))} · {html.escape(str(outcome.get('category')))}</div></div><span class='badge'>{html.escape(str(record.get('status') or 'pending'))}</span></div>"
                    "<div class='timeline'>"
                    f"<div class='timeline-item'><div class='timeline-title'>Execution</div><div class='timeline-body'>started_at={started_at}<br>ended_at={ended_at}<br>duration_s={duration_s}<br>attempts={attempts}</div></div>"
                    f"<div class='timeline-item'><div class='timeline-title'>Contract</div><div class='timeline-body'>contract_path={contract_path or '-'}<br>evidence_path={evidence_path or '-'}</div></div>"
                    f"<div class='timeline-item'><div class='timeline-title'>Business Goal</div><div class='timeline-body'>{html.escape(str(outcome.get('business_goal') or '未配置业务目标'))}</div></div>"
                    f"<div class='timeline-item'><div class='timeline-title'>Process</div><div class='timeline-body'>{process_trace_block}</div></div>"
                    f"<div class='timeline-item'><div class='timeline-title'>Result Summary</div><div class='timeline-body'>{html.escape(str(outcome.get('summary')))}</div></div>"
                    f"<div class='timeline-item'><div class='timeline-title'>Accuracy</div><div class='timeline-body'>{html.escape(str(outcome.get('accuracy')))}</div></div>"
                    f"<div class='timeline-item'><div class='timeline-title'>Conclusion</div><div class='timeline-body'>{html.escape(str(outcome.get('conclusion')))}</div></div>"
                    f"<div class='timeline-item'><div class='timeline-title'>Recommendation</div><div class='timeline-body'>{html.escape(str(outcome.get('recommendation')))}</div></div>"
                    f"<div class='timeline-item'><div class='timeline-title'>Evidence Assets</div><div class='timeline-body'>{assets_block}</div></div>"
                    "</div>"
                    "</div>"
                    "</section>"
                )
            else:
                started_at = html.escape(str(record.get("started_at") or ""))
                ended_at = html.escape(str(record.get("ended_at") or ""))
                duration_s = html.escape(str(record.get("duration_s") or ""))
                workflow_detail_panels.append(
                    f"<section class='workflow-detail-panel' data-agent='{html.escape(agent_anchor)}' data-workflow='{html.escape(str(workflow_key))}'>"
                    "<div class='result-card'>"
                    f"<div class='result-head'><b>{html.escape(str(workflow_key))}</b><span class='badge'>{html.escape(str(record.get('status') or 'pending'))}</span></div>"
                    "<div class='timeline'>"
                    f"<div class='timeline-item'><div class='timeline-title'>Execution</div><div class='timeline-body'>started_at={started_at}<br>ended_at={ended_at}<br>duration_s={duration_s}</div></div>"
                    "<div class='timeline-item'><div class='timeline-title'>Contract</div><div class='timeline-body'>当前还没有 outcome 合同，通常表示 workflow 未执行或结果还未固化。</div></div>"
                    "</div>"
                    "</div>"
                    "</section>"
                )
        projects = ", ".join(card.get("projects") or []) or "-"
        empty_results_block = "<div class='result-card'>暂无工作流结果</div>"
        agent_panels_html.append(
            f"<section class='agent-panel' data-agent='{html.escape(agent_anchor)}'>"
            "<div class='agent-overview'>"
            "<div class='overview-card'>"
            f"<div style='font-size:18px;font-weight:800;color:#f8fafc;'>{html.escape(str(card.get('agent_name')))}</div>"
            f"<div class='agent-nav-meta'>{html.escape(str(card.get('subtitle') or '未配置副标题'))} · 生命周期阶段 {html.escape(str(card.get('lifecycle_phase') or '-'))}</div>"
            f"<div style='margin-top:10px;font-size:13px;line-height:1.7;'><b>职责</b>: {html.escape(_coerce_text(card.get('description') or '当前未接入更详细职责说明。', 320))}</div>"
            f"<div style='margin-top:10px;font-size:13px;line-height:1.7;'><b>项目</b>: {html.escape(projects)}</div>"
            f"<div style='margin-top:10px;font-size:13px;line-height:1.7;'><b>当前执行</b>: {html.escape(str(card.get('current_workflow') or '无'))}</div>"
            "</div>"
            "<div class='overview-card'>"
            "<div style='font-size:13px;font-weight:700;color:#f8fafc;'>承接 workflow</div>"
            f"<div class='agent-nav-meta' style='margin-top:8px;'>{workflows}</div>"
            "<div class='overview-kpis'>"
            f"<div class='overview-chip'><div class='kpi-label'>Passed</div><div class='kpi-value' style='font-size:16px'>{card.get('passed')}</div></div>"
            f"<div class='overview-chip'><div class='kpi-label'>Failed</div><div class='kpi-value' style='font-size:16px'>{card.get('failed')}</div></div>"
            f"<div class='overview-chip'><div class='kpi-label'>Timeout</div><div class='kpi-value' style='font-size:16px'>{card.get('timeout')}</div></div>"
            f"<div class='overview-chip'><div class='kpi-label'>Pending</div><div class='kpi-value' style='font-size:16px'>{card.get('pending')}</div></div>"
            "</div>"
            "</div>"
            "</div>"
            "<div class='section-title'>该 Agent 的 workflow 结果</div>"
            "<div class='workflow-inspector'>"
            f"<div class='workflow-nav'>{''.join(workflow_nav_items) if workflow_nav_items else empty_results_block}</div>"
            f"<div class='workflow-detail-stack' data-default-workflow='{html.escape(default_workflow_key)}'>{''.join(workflow_detail_panels) if workflow_detail_panels else empty_results_block}</div>"
            "</div>"
            "</section>"
        )
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>E2E Live Dashboard</title>
<meta http-equiv="refresh" content="2">
<style>
body{{font-family:ui-sans-serif,system-ui,Arial;margin:0;background:#020617;color:#e2e8f0;}}
h1,h2,h3{{margin:0;}}
a{{color:#7dd3fc;}}
.app{{display:grid;grid-template-columns:320px 1fr;min-height:100vh;}}
.sidebar{{padding:18px;border-right:1px solid #1e293b;background:#0f172a;overflow:auto;}}
.detail{{padding:22px 24px;overflow:auto;background:#020617;}}
.stack{{display:flex;flex-direction:column;gap:12px;}}
.card{{padding:12px 14px;border:1px solid #1e293b;border-radius:14px;background:#0b1220;}}
.header-card{{padding:14px 16px;}}
.header-meta{{margin-top:8px;font-size:12px;color:#94a3b8;line-height:1.6;}}
.kpi-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.kpi-card{{padding:10px 12px;border:1px solid #1e293b;border-radius:12px;background:#0a1324;}}
.progress-track{{margin-top:12px;height:10px;border-radius:999px;background:#111827;overflow:hidden;border:1px solid #1e293b;}}
.progress-fill{{height:100%;background:linear-gradient(90deg,#38bdf8,#22c55e);}}
.kpi-label{{font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em;}}
.kpi-value{{margin-top:6px;font-size:18px;font-weight:700;color:#f8fafc;}}
.kpi-sub{{margin-top:4px;font-size:11px;color:#64748b;}}
.status-row{{display:flex;justify-content:space-between;gap:12px;font-size:13px;padding:6px 0;border-bottom:1px solid #172033;}}
.status-row:last-child{{border-bottom:none;}}
.agent-nav-btn{{display:block;width:100%;text-align:left;padding:12px;border:1px solid #1e293b;border-radius:12px;background:#0b1220;color:#e2e8f0;cursor:pointer;}}
.agent-nav-btn.active{{border-color:#38bdf8;background:#082032;box-shadow:inset 0 0 0 1px rgba(56,189,248,.15);}}
.agent-nav-title{{font-size:14px;font-weight:700;color:#f8fafc;}}
.agent-nav-meta{{font-size:12px;color:#94a3b8;margin-top:5px;line-height:1.5;}}
.agent-panel{{display:none;}}
.agent-overview{{display:grid;grid-template-columns:1.1fr .9fr;gap:14px;margin-bottom:16px;}}
.overview-card{{padding:14px;border:1px solid #1e293b;border-radius:14px;background:#0b1220;}}
.overview-kpis{{display:grid;grid-template-columns:repeat(4, minmax(0, 1fr));gap:10px;margin-top:12px;}}
.overview-chip{{padding:8px 10px;border:1px solid #1e293b;border-radius:12px;background:#08111f;font-size:12px;}}
.section-title{{margin:18px 0 10px;font-size:14px;font-weight:700;color:#f8fafc;}}
.workflow-inspector{{display:grid;grid-template-columns:280px 1fr;gap:14px;align-items:start;}}
.workflow-nav{{display:flex;flex-direction:column;gap:10px;}}
.workflow-nav-btn{{display:block;width:100%;text-align:left;padding:12px;border:1px solid #1e293b;border-radius:12px;background:#08111f;color:#e2e8f0;cursor:pointer;}}
.workflow-nav-btn.active{{border-color:#22c55e;background:#0b2a1d;}}
.workflow-detail-stack{{min-width:0;}}
.workflow-detail-panel{{display:none;}}
.result-card{{padding:14px;border:1px solid #1e293b;border-radius:14px;background:#0b1220;font-size:13px;line-height:1.6;}}
.result-head{{display:flex;justify-content:space-between;gap:12px;margin-bottom:10px;color:#f8fafc;align-items:flex-start;}}
.badge{{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;border:1px solid #334155;font-size:11px;color:#cbd5e1;background:#0f172a;}}
.timeline{{display:flex;flex-direction:column;gap:10px;margin-top:10px;}}
.timeline-item{{border-left:2px solid #1e293b;padding-left:12px;}}
.timeline-title{{font-size:12px;font-weight:700;color:#93c5fd;text-transform:uppercase;letter-spacing:.04em;}}
.timeline-body{{margin-top:4px;color:#cbd5e1;font-size:13px;line-height:1.6;word-break:break-word;}}
.asset-list{{margin-top:8px;padding-left:18px;color:#cbd5e1;}}
.asset-list li{{margin:4px 0;word-break:break-all;}}
.asset-list-empty{{margin-top:8px;color:#94a3b8;font-size:12px;}}
.mini-table{{width:100%;border-collapse:collapse;font-size:12px;}}
.mini-table th,.mini-table td{{border-bottom:1px solid #1e293b;padding:7px 4px;text-align:left;vertical-align:top;}}
.mini-table th{{color:#94a3b8;font-weight:600;}}
.mini-table tr:last-child td{{border-bottom:none;}}
.nav-list{{padding-left:18px;margin:8px 0 0;}}
.nav-list li{{margin:6px 0;word-break:break-all;font-size:12px;color:#cbd5e1;}}
.side-details{{border:1px solid #1e293b;border-radius:12px;background:#0b1220;padding:10px 12px;}}
.side-details summary{{cursor:pointer;color:#f8fafc;font-size:13px;font-weight:700;list-style:none;}}
.side-details summary::-webkit-details-marker{{display:none;}}
.side-details-body{{margin-top:10px;}}
@media (max-width: 1100px) {{
  .app{{grid-template-columns:1fr;}}
  .sidebar{{border-right:none;border-bottom:1px solid #1e293b;}}
  .agent-overview{{grid-template-columns:1fr;}}
  .workflow-inspector{{grid-template-columns:1fr;}}
}}
</style></head><body>
<div class="app">
<aside class="sidebar">
  <div class="stack">
    <section class="card header-card">
      <h1 style="font-size:20px;font-weight:800;">E2E 实时追踪</h1>
      <div style="margin-top:6px;font-size:14px;color:#cbd5e1;">case: <b>{html.escape(state['case_id'])}</b></div>
      <div class="header-meta">
        run_id: <code>{html.escape(state['run_id'])}</code><br>
        started_at: {html.escape(state['started_at'])}<br>
        last_updated_at: {html.escape(state['last_updated_at'])}<br>
        execution_profile: <code>{html.escape(str(execution_profile))}</code> · retry_max: <code>{retry_max}</code>
      </div>
    </section>

    <section class="card">
      <h2 style="font-size:14px;font-weight:700;margin-bottom:10px;">全局进度</h2>
      <div class="progress-track"><div class="progress-fill" style="width:{progress:.1f}%"></div></div>
      <div class="kpi-grid">
        <div class="kpi-card"><div class="kpi-label">Progress</div><div class="kpi-value">{done}/{total}</div><div class="kpi-sub">{progress:.1f}%</div></div>
        <div class="kpi-card"><div class="kpi-label">Passed</div><div class="kpi-value">{summary.get('passed', 0)}</div><div class="kpi-sub">成功步数</div></div>
        <div class="kpi-card"><div class="kpi-label">Timeout</div><div class="kpi-value">{summary.get('timeout', 0)}</div><div class="kpi-sub">超时步数</div></div>
        <div class="kpi-card"><div class="kpi-label">Gate</div><div class="kpi-value">{html.escape(str(summary.get('outcome_gate_status', 'blocked')))}</div><div class="kpi-sub">{summary.get('outcome_coverage', 0.0):.1%}</div></div>
      </div>
    </section>

    <section class="card">
      <h2 style="font-size:14px;font-weight:700;margin-bottom:10px;">当前执行</h2>
      {current_html}
    </section>

    <section class="card">
      <h2 style="font-size:14px;font-weight:700;margin-bottom:10px;">Agent 列表</h2>
      <div class="stack">
        {''.join(agent_cards_html) if agent_cards_html else '<div class="card">暂无 Agent</div>'}
      </div>
    </section>

    <section class="card">
      <h2 style="font-size:14px;font-weight:700;margin-bottom:10px;">结果导航</h2>
      <div class="status-row"><span>source_report</span><span><code>{html.escape(str(source_report))}</code></span></div>
      <div class="status-row"><span>coverage_report</span><span><code>{html.escape(str(summary.get('outcome_coverage_report', '')))}</code></span></div>
      <details class="side-details">
        <summary>展开结果导航区</summary>
        <div class="side-details-body">
          <ul class="nav-list">{assets_html}</ul>
        </div>
      </details>
    </section>

    <section class="card">
      <details class="side-details">
        <summary>失败红榜（{len(failed_items)}）</summary>
        <div class="side-details-body">
          <table class="mini-table"><thead><tr><th>status</th><th>workflow</th><th>agent</th></tr></thead>
          <tbody>{''.join(failed_rows) if failed_rows else '<tr><td colspan="3">当前无失败项</td></tr>'}</tbody></table>
        </div>
      </details>
    </section>
  </div>
</aside>

<main class="detail">
  <section class="card" style="margin-bottom:16px;position:sticky;top:0;z-index:2;">
    <h2 style="font-size:18px;font-weight:800;">Agent 结果工作面</h2>
    <div class="header-meta">左侧选择一个 Agent，右侧只看这个 Agent 的职责、状态和所承接 workflow 的详细结果。这样更适合盯端到端测试，而不是读一整页杂糅信息。</div>
    <div class="kpi-grid" style="margin-top:12px;">
      <div class="kpi-card"><div class="kpi-label">Progress</div><div class="kpi-value">{done}/{total}</div><div class="kpi-sub">{progress:.1f}%</div></div>
      <div class="kpi-card"><div class="kpi-label">Current</div><div class="kpi-value" style="font-size:14px">{html.escape(current_workflow_label)}</div><div class="kpi-sub">{html.escape(current_agent_label)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Gate</div><div class="kpi-value">{html.escape(str(summary.get('outcome_gate_status', 'blocked')))}</div><div class="kpi-sub">{summary.get('outcome_coverage', 0.0):.1%}</div></div>
      <div class="kpi-card"><div class="kpi-label">Updated</div><div class="kpi-value" style="font-size:14px">{html.escape(str(state['last_updated_at']))}</div><div class="kpi-sub">自动刷新保留当前 Agent</div></div>
    </div>
  </section>
  {''.join(agent_panels_html) if agent_panels_html else '<div class="card">暂无 Agent 详情</div>'}
</main>
</div>
<script>
function showAgent(agentId) {{
  document.querySelectorAll('.agent-panel').forEach((panel) => {{
    panel.style.display = panel.dataset.agent === agentId ? 'block' : 'none';
  }});
  document.querySelectorAll('.agent-nav-btn').forEach((button) => {{
    button.classList.toggle('active', button.dataset.agent === agentId);
  }});
  const detailStack = document.querySelector('.agent-panel[data-agent=\"' + agentId + '\"] .workflow-detail-stack');
  const defaultWorkflow = detailStack ? detailStack.dataset.defaultWorkflow : '';
  if (defaultWorkflow) {{
    showWorkflow(agentId, defaultWorkflow);
  }}
  if (location.hash !== '#' + agentId) {{
    history.replaceState(null, '', '#' + agentId);
  }}
}}
function showWorkflow(agentId, workflowKey) {{
  document.querySelectorAll('.workflow-detail-panel').forEach((panel) => {{
    const isVisible = panel.dataset.agent === agentId && panel.dataset.workflow === workflowKey;
    panel.style.display = isVisible ? 'block' : 'none';
  }});
  document.querySelectorAll('.workflow-nav-btn').forEach((button) => {{
    const isActive = button.dataset.agent === agentId && button.dataset.workflow === workflowKey;
    button.classList.toggle('active', isActive);
  }});
}}
window.addEventListener('DOMContentLoaded', () => {{
  const target = location.hash.replace('#', '') || '{html.escape(default_agent_id)}';
  showAgent(target);
}});
</body></html>"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(page, encoding="utf-8")


def _classify_status(result_or_ok: Any, excerpt: str) -> str:
    ok = bool(result_or_ok)
    if isinstance(result_or_ok, dict):
        ok = bool(result_or_ok.get("ok"))
        payload = result_or_ok.get("result")
        if ok and isinstance(payload, dict):
            outcome_status = str(payload.get("outcome_status", "")).strip().lower()
            if outcome_status == "quality_failed":
                return "failed"
            if payload.get("quality_gate_passed") is False:
                return "failed"
            if str(payload.get("quality_status", "")).strip().lower() == "failed":
                return "failed"
            workflow_key = str(result_or_ok.get("workflow", "") or "").strip()
            if workflow_key == "strict_revalidation_ext":
                report_hint = str(
                    payload.get("quality_report_path")
                    or "reports/acceptance/strict_revalidation_summary.json"
                ).strip()
                report_path = Path(report_hint)
                if not report_path.is_absolute():
                    report_path = WORKSPACE / report_path
                if report_path.exists():
                    strict_summary = _safe_json_loads(report_path.read_text(encoding="utf-8"))
                    if isinstance(strict_summary, dict):
                        modules = strict_summary.get("modules", {})
                        failed_tests = 0
                        if isinstance(modules, dict):
                            for module in modules.values():
                                if isinstance(module, dict):
                                    failed_tests += int(module.get("failed_tests", 0) or 0)
                        quality_gate = strict_summary.get("quality_gate", {})
                        gate_passed = None
                        if isinstance(quality_gate, dict):
                            gate_passed = quality_gate.get("passed")
                        if gate_passed is None:
                            gate_passed = strict_summary.get("quality_gate_passed")
                        if gate_passed is None:
                            gate_passed = failed_tests == 0
                        if not bool(gate_passed):
                            return "failed"
    if ok:
        return "passed"
    if "timed out" in excerpt.lower():
        return "timeout"
    return "failed"


def run_live_tracker(
    case_id: str,
    source_report: str,
    execution_profile: str = "fast_validation",
    max_workflows: int = 0,
    dashboard_md: str = "",
    dashboard_html: str = "",
    progress_json: str = "",
    retry_max: int = 1,
    retry_backoff_sec: float = 2.0,
) -> dict[str, Any]:
    source_path = (WORKSPACE / source_report).resolve()
    source_report_rel = _to_rel_path(str(source_path))
    report = _load_json(source_path)
    items = _build_work_items(report)
    if max_workflows > 0:
        items = items[:max_workflows]

    contracts = WORKSPACE / "cases" / case_id / "contracts"
    md_path = Path(dashboard_md) if dashboard_md else contracts / "E2E_LIVE_DASHBOARD.md"
    html_path = Path(dashboard_html) if dashboard_html else contracts / "E2E_LIVE_DASHBOARD.html"
    json_path = Path(progress_json) if progress_json else contracts / "e2e_live_progress.latest.json"

    state: dict[str, Any] = {
        "run_id": f"live-{uuid.uuid4().hex[:10]}",
        "case_id": case_id,
        "started_at": _now_iso(),
        "last_updated_at": _now_iso(),
        "execution_profile": execution_profile,
        "retry": {
            "max_retries": retry_max,
            "backoff_sec": retry_backoff_sec,
        },
        "source_report": source_report_rel,
        "summary": {
            "total": len(items),
            "passed": 0,
            "failed": 0,
            "timeout": 0,
            "pending": len(items),
            "retries_used": 0,
            "outcomes_generated": 0,
            "outcome_coverage": 0.0,
            "outcome_gate_status": "blocked",
            "outcome_gate_threshold": OUTCOME_COVERAGE_THRESHOLD,
            "outcome_coverage_report": "",
        },
        "current": None,
        "records": [],
        "_auto_generated": True,
    }
    _write_outcome_coverage_report(contracts, state)
    _save_json(json_path, state)
    _render_dashboard(md_path, state)
    _render_dashboard_html(html_path, state)

    for item in items:
        started = time.time()
        state["current"] = {**item, "started_at": _now_iso()}
        state["last_updated_at"] = _now_iso()
        _save_json(json_path, state)
        _render_dashboard(md_path, state)

        status = "failed"
        excerpt = ""
        attempts = 0
        for attempt in range(retry_max + 1):
            attempts = attempt + 1
            try:
                result = hm_run_workflow(
                    workflow=item["workflow_key"],
                    case_id=case_id,
                    execution_profile=execution_profile,
                )
                excerpt = json.dumps(result, ensure_ascii=False)[:800]
                status = _classify_status(result, excerpt)
                status = _effective_record_status(
                    case_id,
                    {"workflow_key": item["workflow_key"], "status": status},
                )
            except TimeoutError as exc:
                excerpt = str(exc)[:800]
                status = "timeout"
            except Exception as exc:
                excerpt = str(exc)[:800]
                status = _classify_status(False, excerpt)
            if status == "passed":
                break
            if attempt < retry_max:
                state["summary"]["retries_used"] += 1
                state["last_updated_at"] = _now_iso()
                _save_json(json_path, state)
                _render_dashboard(md_path, state)
                _render_dashboard_html(html_path, state)
                time.sleep(retry_backoff_sec)

        ended = time.time()
        rec = {
            **item,
            "status": status,
            "started_at": state["current"]["started_at"],
            "ended_at": _now_iso(),
            "duration_s": round(ended - started, 2),
            "attempts": attempts,
            "excerpt": excerpt,
        }
        state["records"].append(rec)
        state["current"] = None
        state["summary"][status] += 1
        state["summary"]["pending"] = max(0, state["summary"]["pending"] - 1)
        state["last_updated_at"] = _now_iso()
        _write_outcome_coverage_report(contracts, state)
        _save_json(json_path, state)
        _render_dashboard(md_path, state)
        _render_dashboard_html(html_path, state)

    return {
        "run_id": state["run_id"],
        "case_id": case_id,
        "total": state["summary"]["total"],
        "passed": state["summary"]["passed"],
        "failed": state["summary"]["failed"],
        "timeout": state["summary"]["timeout"],
        "dashboard_md": str(md_path),
        "dashboard_html": str(html_path),
        "progress_json": str(json_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E 实时追踪器")
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--source-report",
        default="cases/{case_id}/contracts/mcp_all_agents_e2e_report.v8_fast.fix.json",
        help="输入 E2E 基线报告（相对 workspace，支持 {case_id} 占位符）",
    )
    parser.add_argument("--execution-profile", default="fast_validation", choices=["default", "fast_validation"])
    parser.add_argument("--max-workflows", type=int, default=0, help="仅执行前 N 个 workflow；0 表示全部")
    parser.add_argument("--dashboard-md", default="")
    parser.add_argument("--dashboard-html", default="")
    parser.add_argument("--progress-json", default="")
    parser.add_argument("--retry-max", type=int, default=1, help="失败后自动重试次数")
    parser.add_argument("--retry-backoff-sec", type=float, default=2.0, help="重试间隔秒数")
    args = parser.parse_args()

    if "{case_id}" not in args.source_report and not args.source_report.endswith(".json"):
        raise ValueError("--source-report must contain the '{case_id}' placeholder to avoid hardcoding or must be explicitly absolute.")
        
    source_report_path = args.source_report.replace("{case_id}", args.case_id)
    result = run_live_tracker(
        case_id=args.case_id,
        source_report=source_report_path,
        execution_profile=args.execution_profile,
        max_workflows=args.max_workflows,
        dashboard_md=args.dashboard_md,
        dashboard_html=args.dashboard_html,
        progress_json=args.progress_json,
        retry_max=args.retry_max,
        retry_backoff_sec=args.retry_backoff_sec,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
