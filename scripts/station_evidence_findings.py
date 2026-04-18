#!/usr/bin/env python3
"""探源 (TanYuan) — Build structured station evidence findings from raw review inputs."""
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


def _count_claims(rows: list[dict[str, Any]], claim_type: str) -> int:
    total = 0
    for row in rows:
        for claim in row.get("claims") or []:
            if isinstance(claim, dict) and claim.get("claim_type") == claim_type:
                total += 1
    return total


def _tier_count(rows: list[dict[str, Any]], publisher_tier: str) -> int:
    total = 0
    for row in rows:
        source = row.get("source_attribution") or {}
        if source.get("publisher_tier") == publisher_tier:
            total += 1
    return total


def _normalize_findings(entries: list[Any], *, workspace: Path) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        source = dict(item.get("source_attribution") or {})
        if source.get("source_path"):
            source["source_path"] = _workspace_rel(workspace / str(source["source_path"]), workspace)
        item["source_attribution"] = source
        item["claims"] = [claim for claim in (item.get("claims") or []) if isinstance(claim, dict)]
        item["promotion_guardrails"] = dict(item.get("promotion_guardrails") or {})
        normalized.append(item)
    return normalized


def build_station_evidence_findings(case_id: str, workspace: Path) -> dict[str, Any] | None:
    contracts_dir = workspace / "cases" / case_id / "contracts"
    search_plan_path = contracts_dir / "station_evidence_search_plan.latest.json"
    review_path = contracts_dir / "station_pre_delineation_review.latest.json"
    raw_input_path = workspace / "cases" / case_id / "ingest" / "raw" / "station_evidence_findings.json"
    search_plan = _safe_load_json(search_plan_path)
    review = _safe_load_json(review_path)
    raw_input = _safe_load_json(raw_input_path)
    if not isinstance(search_plan, dict) or not isinstance(review, dict) or not isinstance(raw_input, dict):
        return None

    station_findings = _normalize_findings(list(raw_input.get("station_findings") or []), workspace=workspace)
    unassigned_findings = _normalize_findings(list(raw_input.get("unassigned_findings") or []), workspace=workspace)
    if not station_findings and not unassigned_findings:
        return None

    all_rows = [*station_findings, *unassigned_findings]
    return {
        "case_id": case_id,
        "schema_version": "station_evidence_findings.v1",
        "generated_at": _now_iso(),
        "ingest_status": "review_only_findings_ready",
        "source_contracts": {
            "station_evidence_search_plan": _workspace_rel(search_plan_path, workspace),
            "station_pre_delineation_review": _workspace_rel(review_path, workspace),
            "raw_input": _workspace_rel(raw_input_path, workspace),
        },
        "summary": {
            "finding_count": len(all_rows),
            "station_count_with_findings": len({row.get("station_id") for row in station_findings if row.get("station_id")}),
            "coordinate_claim_count": _count_claims(all_rows, "coordinate"),
            "hydrography_claim_count": _count_claims(all_rows, "hydrography_alignment"),
            "official_source_count": _tier_count(all_rows, "official"),
            "quasi_official_source_count": _tier_count(all_rows, "quasi_official"),
            "blocked_promotion_count": sum(
                1
                for row in all_rows
                if list(((row.get("promotion_guardrails") or {}).get("promotion_blockers")) or [])
            ),
        },
        "station_findings": station_findings,
        "unassigned_findings": unassigned_findings,
        "warnings": [
            "All findings remain review-only until corroborated by stronger coordinate or hydrography evidence."
        ],
    }
