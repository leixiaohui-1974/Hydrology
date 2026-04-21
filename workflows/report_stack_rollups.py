from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _workspace_rel(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _contracts_dir(case_id: str, workspace_root: Path) -> Path:
    return workspace_root / "cases" / case_id.strip() / "contracts"


def _report_rows(case_id: str, workspace_root: Path) -> dict[str, list[dict[str, Any]]]:
    contracts_dir = _contracts_dir(case_id, workspace_root)
    rows = {
        "stage_reports": [],
        "workflow_reports": [],
        "algorithm_reports": [],
        "final_reports": [],
    }
    if not contracts_dir.is_dir():
        return rows

    for path in sorted(contracts_dir.glob("*.json")):
        rel = _workspace_rel(path, workspace_root)
        payload = _load_json(path)
        contract_type = str(payload.get("contract_type") or "").strip()
        row = {"path": rel, "contract_type": contract_type}
        if contract_type == "stage_human_report" or rel.endswith("_stage_report.latest.json"):
            row["stage_key"] = payload.get("stage_key")
            rows["stage_reports"].append(row)
        elif contract_type == "workflow_human_report" or (
            rel.endswith("_report.latest.json")
            and not rel.endswith("_stage_report.latest.json")
            and not rel.endswith("_algorithm_report.latest.json")
            and not rel.endswith("final_report.latest.json")
            and not rel.endswith("workflow_smart_report.latest.json")
        ):
            row["workflow_key"] = payload.get("workflow_key")
            rows["workflow_reports"].append(row)
        elif contract_type == "algorithm_human_report" or rel.endswith("_algorithm_report.latest.json"):
            row["workflow_key"] = payload.get("workflow_key")
            row["algorithm_surface_id"] = payload.get("algorithm_surface_id")
            rows["algorithm_reports"].append(row)
        elif rel.endswith("final_report.latest.json"):
            rows["final_reports"].append(row)
    return rows


def build_report_stack_rollup(case_id: str, workspace_root: str | Path) -> dict[str, Any]:
    workspace = Path(workspace_root).expanduser().resolve()
    rows = _report_rows(case_id, workspace)
    return {
        "case_id": case_id,
        "summary": {
            "stage_report_count": len(rows["stage_reports"]),
            "workflow_report_count": len(rows["workflow_reports"]),
            "algorithm_report_count": len(rows["algorithm_reports"]),
            "final_report_count": len(rows["final_reports"]),
        },
        **rows,
    }


def build_report_stack_artifacts(case_id: str, workspace_root: str | Path) -> list[dict[str, Any]]:
    rollup = build_report_stack_rollup(case_id, workspace_root)
    artifacts: list[dict[str, Any]] = []
    role_map = {
        "stage_reports": "stage_report",
        "workflow_reports": "workflow_report",
        "algorithm_reports": "algorithm_report",
        "final_reports": "final_report",
    }
    for key, role in role_map.items():
        for item in rollup.get(key, []):
            artifacts.append(
                {
                    "artifact_id": f"{case_id}:{role}:{Path(str(item.get('path') or '')).stem}",
                    "artifact_type": "json_report",
                    "path": item.get("path"),
                    "metadata": {"role": role},
                }
            )
    return artifacts
