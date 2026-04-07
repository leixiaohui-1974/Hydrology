"""Generate staged E2E outcome verification assets for a case."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys
import subprocess
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

HIGH_VALUE_WORKFLOWS = [
    "hyd_cal",
    "d1d4",
    "autonomy_assess",
    "autonomy_autorun",
    "strict_revalidation_ext",
    "ensemble_forecast",
    "dl_autolearn",
    "data_audit",
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_outcome(case_id: str, workflow_key: str) -> dict[str, Any]:
    path = WORKSPACE / "cases" / case_id / "contracts" / "outcomes" / f"{workflow_key}.latest.json"
    if not path.exists():
        return {}
    return _load_json(path)


def _build_outcome_coverage_report(progress: dict[str, Any]) -> dict[str, Any]:
    case_id = str(progress.get("case_id", ""))
    executed = [
        record
        for record in progress.get("records", [])
        if record.get("status") in {"passed", "failed", "timeout"}
    ]
    unique_map: dict[str, dict[str, Any]] = {}
    duplicate_runs: dict[str, int] = {}
    for record in executed:
        workflow_key = str(record.get("workflow_key", "")).strip()
        if not workflow_key:
            continue
        duplicate_runs[workflow_key] = duplicate_runs.get(workflow_key, 0) + 1
        unique_map[workflow_key] = record
    unique_executed = list(unique_map.values())
    details: list[dict[str, Any]] = []
    generated = 0
    valid = 0
    evidence_bound = 0

    for record in unique_executed:
        workflow_key = str(record.get("workflow_key", ""))
        outcome = _load_outcome(case_id, workflow_key)
        validation_errors = outcome.get("validation_errors", []) if outcome else ["missing_outcome"]
        conclusion_items = ((outcome or {}).get("dimensions") or {}).get("conclusion") or []
        recommendation_items = ((outcome or {}).get("dimensions") or {}).get("recommendation") or []
        evidence_items = [
            item
            for item in [*conclusion_items, *recommendation_items]
            if isinstance(item, dict)
        ]
        evidence_ok = bool(evidence_items) and all(str(item.get("evidence_path", "")).strip() for item in evidence_items)
        if outcome:
            generated += 1
        if outcome and not validation_errors:
            valid += 1
        if outcome and evidence_ok:
            evidence_bound += 1
        details.append(
            {
                "workflow_key": workflow_key,
                "status": record.get("status"),
                "outcome_generated": bool(outcome),
                "template_id": outcome.get("template_id") if outcome else None,
                "contract_path": outcome.get("contract_path") if outcome else None,
                "validation_errors": validation_errors,
                "evidence_bound": evidence_ok,
            }
        )

    total_executed = len(unique_executed)
    coverage = generated / total_executed if total_executed else 0.0
    gate_passed = coverage >= 0.95 and generated == valid and generated == evidence_bound
    return {
        "case_id": case_id,
        "generated_at": progress.get("last_updated_at"),
        "threshold": 0.95,
        "total_executed": total_executed,
        "outcomes_generated": generated,
        "schema_valid_count": valid,
        "evidence_bound_count": evidence_bound,
        "outcome_coverage": coverage,
        "gate_status": "passed" if gate_passed else "blocked",
        "missing_workflows": [item["workflow_key"] for item in details if not item["outcome_generated"]],
        "invalid_workflows": [item["workflow_key"] for item in details if item["validation_errors"]],
        "unevidenced_workflows": [item["workflow_key"] for item in details if item["outcome_generated"] and not item["evidence_bound"]],
        "duplicate_runs": {key: count for key, count in duplicate_runs.items() if count > 1},
        "details": details,
        "_auto_generated": True,
    }


def _planned_workflows(source_report: dict[str, Any]) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    for agent in source_report.get("agent_results", []):
        for wf in agent.get("workflow_results", []):
            workflow_key = wf.get("workflow_key")
            if not workflow_key:
                continue
            planned.append(
                {
                    "workflow_key": workflow_key,
                    "agent_id": agent.get("agent_id"),
                    "agent_name": agent.get("agent_name"),
                    "source_status": wf.get("status"),
                    "workflow_path": wf.get("workflow_path"),
                }
            )
    return planned


def _status_counter(records: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(record.get("status", "unknown") for record in records)
    return dict(counter)


def _high_value_status(case_id: str, progress: dict[str, Any], planned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    record_map = {record.get("workflow_key"): record for record in progress.get("records", [])}
    current_key = (progress.get("current") or {}).get("workflow_key")
    planned_map = {item["workflow_key"]: item for item in planned}
    items: list[dict[str, Any]] = []
    for workflow_key in HIGH_VALUE_WORKFLOWS:
        outcome = _load_outcome(case_id, workflow_key)
        record = record_map.get(workflow_key)
        status = "pending"
        if workflow_key == current_key:
            status = "running"
        elif record:
            status = str(record.get("status", "unknown"))
        items.append(
            {
                "workflow_key": workflow_key,
                "status": status,
                "template_id": outcome.get("template_id"),
                "contract_path": outcome.get("contract_path"),
                "validation_errors": outcome.get("validation_errors", []),
                "agent_name": planned_map.get(workflow_key, {}).get("agent_name"),
            }
        )
    return items


def _build_report(case_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    progress_path = contracts_dir / "e2e_live_progress.latest.json"
    progress = _load_json(progress_path)
    source_report = _load_json(WORKSPACE / Path(progress["source_report"]))
    planned = _planned_workflows(source_report)
    coverage_report = _build_outcome_coverage_report(progress)
    record_keys = {record.get("workflow_key") for record in progress.get("records", []) if record.get("workflow_key")}
    current_key = (progress.get("current") or {}).get("workflow_key")
    pending_workflows = [
        item
        for item in planned
        if item["workflow_key"] not in record_keys and item["workflow_key"] != current_key
    ]
    skipped_not_in_registry = [
        {
            "agent_name": agent.get("agent_name"),
            "workflow_path": wf.get("workflow_path"),
        }
        for agent in source_report.get("agent_results", [])
        for wf in agent.get("workflow_results", [])
        if wf.get("status") == "skipped_not_in_mcp_registry"
    ]

    progress_summary = progress.get("summary", {})
    closure_ok = (
        progress_summary.get("passed", 0)
        + progress_summary.get("failed", 0)
        + progress_summary.get("timeout", 0)
        + progress_summary.get("pending", 0)
        == progress_summary.get("total", 0)
    )

    hardcoding_gate_status = "passed"
    try:
        linter_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "enforce_zero_hardcoding.py"
        res = subprocess.run([sys.executable, str(linter_path)], capture_output=True, text=True)
        if res.returncode != 0:
            hardcoding_gate_status = "failed"
            coverage_report["gate_status"] = "failed_by_hardcoding_linter"
            print(f"🚨 ZERO HARDCODING GATE FAILED. E2E Acceptance rejected.\\nDetails: {res.stdout[:500]}...", file=sys.stderr)
    except Exception:
        hardcoding_gate_status = "error"

    report = {
        "case_id": case_id,
        "generated_at": progress.get("last_updated_at"),
        "verification_stage": "stage2_execution_integrity_and_stage3_outcome_quality",
        "run_context": {
            "run_id": progress.get("run_id"),
            "execution_profile": progress.get("execution_profile"),
            "retry_max": (progress.get("retry") or {}).get("max_retries"),
            "source_report": progress.get("source_report"),
        },
        "stage2_execution_integrity": {
            "summary": progress_summary,
            "closure_check_passed": closure_ok,
            "record_status_counter": _status_counter(progress.get("records", [])),
            "duplicate_run_counter": coverage_report.get("duplicate_runs", {}),
            "current_workflow": progress.get("current"),
            "pending_workflows": pending_workflows,
            "skipped_not_in_registry": skipped_not_in_registry,
            "failure_buckets": {
                "code_error": [],
                "environment_dependency": [],
                "data_unreachable": [],
                "timeout_policy": [],
            },
        },
        "stage3_outcome_quality": {
            "coverage_report_path": f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
            "coverage_report": coverage_report,
            "zero_hardcoding_gate": hardcoding_gate_status,
            "high_value_workflows": _high_value_status(case_id, progress, planned),
        },
        "known_risks": [
            "业务成果导航区仍有跨 case 产物路径，需要在阶段4验证前收紧边界。",
            "section_analysis 受 openpyxl/pandas 依赖影响，存在 xlsx 解析降级。",
            "部分 workflow outcome 仍偏通用摘要，需要继续补 workflow 级专用提取。",
        ],
        "_auto_generated": True,
    }

    md_lines = [
        f"# {case_id} outcome 阶段性验收报告",
        "",
        f"- case_id: `{case_id}`",
        f"- run_id: `{progress.get('run_id')}`",
        f"- generated_at: `{progress.get('last_updated_at')}`",
        f"- execution_profile: `{progress.get('execution_profile')}`",
        "",
        "## 阶段2：执行完整性",
        "",
        f"- total: **{progress_summary.get('total', 0)}**",
        f"- passed: **{progress_summary.get('passed', 0)}**",
        f"- failed: **{progress_summary.get('failed', 0)}**",
        f"- timeout: **{progress_summary.get('timeout', 0)}**",
        f"- pending: **{progress_summary.get('pending', 0)}**",
        f"- closure_check_passed: **{closure_ok}**",
        "",
        "### 当前执行",
        "",
        f"- current_workflow: `{current_key or ''}`",
        f"- current_agent: `{(progress.get('current') or {}).get('agent_name', '')}`",
        "",
        f"### 待执行工作流（{len(pending_workflows)}）",
        "",
    ]
    md_lines.extend(
        [f"- `{item['workflow_key']}` · {item.get('agent_name', '')}" for item in pending_workflows]
        or ["- 当前无待执行工作流"]
    )
    md_lines.extend(
        [
            "",
            "## 阶段3：outcome 覆盖率与质量",
            "",
            f"- outcomes_generated: **{coverage_report['outcomes_generated']} / {coverage_report['total_executed']}**",
            f"- outcome_coverage: **{coverage_report['outcome_coverage']:.1%}**",
            f"- schema_valid_count: **{coverage_report['schema_valid_count']}**",
            f"- evidence_bound_count: **{coverage_report['evidence_bound_count']}**",
            f"- gate_status: **{coverage_report['gate_status']}**",
            "",
            "### 高价值 workflow 状态",
            "",
        ]
    )
    md_lines.extend(
        [
            f"- `{item['workflow_key']}` · status={item['status']} · template={item.get('template_id') or '-'} · contract={item.get('contract_path') or '-'}"
            for item in report["stage3_outcome_quality"]["high_value_workflows"]
        ]
    )
    md_lines.extend(
        [
            "",
            "## 已知风险",
            "",
            *[f"- {item}" for item in report["known_risks"]],
            "",
        ]
    )

    return report, {"markdown": "\n".join(md_lines) + "\n", "coverage_report": coverage_report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()

    report, rendered = _build_report(args.case_id)
    contracts_dir = WORKSPACE / "cases" / args.case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    _save_json(contracts_dir / "outcome_coverage_report.latest.json", rendered["coverage_report"])
    _save_json(contracts_dir / "e2e_outcome_verification_report.json", report)
    (contracts_dir / "e2e_outcome_verification_report.md").write_text(
        rendered["markdown"],
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
