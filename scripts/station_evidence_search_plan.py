#!/usr/bin/env python3
"""探源 (TanYuan) — Build a search-plan contract from pre-delineation review candidates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _workspace_rel(path: Path, workspace: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def build_station_evidence_search_plan(case_id: str, workspace: Path) -> dict[str, Any] | None:
    contracts_dir = workspace / "cases" / case_id / "contracts"
    review_path = contracts_dir / "station_pre_delineation_review.latest.json"
    payload = _safe_load_json(review_path)
    if not isinstance(payload, dict):
        return None

    review_candidates = [row for row in (payload.get("review_candidates") or []) if isinstance(row, dict)]
    if not review_candidates:
        return None

    plans: list[dict[str, Any]] = []
    for index, row in enumerate(review_candidates, start=1):
        plans.append(
            {
                "plan_id": f"{case_id}-search-plan-{index:02d}",
                "station_id": row.get("station_id"),
                "station_name": row.get("station_name"),
                "review_status": row.get("review_status"),
                "validation_priority": row.get("validation_priority"),
                "evidence_gate_status": row.get("evidence_gate_status"),
                "required_evidence": list(row.get("required_evidence") or []),
                "recommended_public_source_types": list(row.get("recommended_public_source_types") or []),
                "recommended_query_patterns": list(row.get("recommended_query_patterns") or []),
                "search_goal": "collect_coordinate_grade_or_hydrography_adjacent_evidence",
                "next_action": row.get("recommended_next_step"),
            }
        )

    return {
        "case_id": case_id,
        "schema_version": "station_evidence_search_plan.v1",
        "generated_at": _now_iso(),
        "plan_status": "ready_to_search",
        "source_contracts": {
            "station_pre_delineation_review": _workspace_rel(review_path, workspace),
        },
        "summary": {
            "plan_count": len(plans),
            "manual_validation_priority_count": sum(1 for row in plans if row.get("review_status") == "manual_validation_priority"),
            "needs_corroboration_count": sum(1 for row in plans if row.get("evidence_gate_status") == "needs_corroboration"),
        },
        "plans": plans,
    }
