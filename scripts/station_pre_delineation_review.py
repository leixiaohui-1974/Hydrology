#!/usr/bin/env python3
"""探源 (TanYuan) — Build a pre-delineation review contract from outlet candidates."""
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


def _load_station_findings(case_id: str, workspace: Path) -> list[dict[str, Any]]:
    path = workspace / "cases" / case_id / "contracts" / "station_evidence_findings.latest.json"
    payload = _safe_load_json(path)
    if not isinstance(payload, dict):
        return []
    return [row for row in (payload.get("station_findings") or []) if isinstance(row, dict)]


def _findings_by_station(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        station_id = str(row.get("station_id") or "").strip()
        if station_id:
            grouped.setdefault(station_id, []).append(row)
    return grouped


def _evidence_gaps(row: dict[str, Any]) -> list[str]:
    gaps = ["needs_hydrography_alignment"]
    display_name = str(row.get("display_name") or "")
    if display_name:
        gaps.append("needs_dam_or_powerhouse_coordinate")
    if str(row.get("source_type") or "").strip().lower() in {"city", "town", "village", "administrative"}:
        gaps.append("current_candidate_is_place_proxy_not_engineering_asset")
    return gaps


def _review_checklist(gaps: list[str]) -> list[str]:
    checklist = ["核对候选点是否位于目标河段/支流附近"]
    if "needs_dam_or_powerhouse_coordinate" in gaps:
        checklist.append("补充坝址、厂房或控制断面的更强坐标证据")
    if "needs_hydrography_alignment" in gaps:
        checklist.append("补充水系或主河道吸附证据，验证候选点与河网关系")
    return checklist


def _recommended_public_source_types() -> list[dict[str, str]]:
    return [
        {
            "source_type": "环评公示稿/环评批复",
            "why": "最可能给出坝址地理坐标、中心地理坐标、取排水与河段影响信息。",
        },
        {
            "source_type": "取水许可/水资源论证/行政许可决定书",
            "why": "最可能给出取水口、坝址、受影响河段和水资源边界。",
        },
        {
            "source_type": "选址意见书/红线图/边界拐点坐标",
            "why": "适合补项目边界、坐标拐点和空间锚点。",
        },
        {
            "source_type": "征地公告/用地批复/勘测定界",
            "why": "适合辅助校核项目实际落地区域与乡镇范围。",
        },
        {
            "source_type": "可研/初设/勘测设计/招标公告",
            "why": "适合补充站名、隧洞、厂房、交通与附属设施的关联地理线索。",
        },
    ]


def _recommended_query_patterns(station_name: str) -> list[str]:
    patterns = [
        f"{station_name} 坐标",
        f"{station_name} 坝址",
        f"{station_name} 地理坐标",
        f"{station_name} 中心地理坐标",
        f"{station_name} 环评公示稿",
        f"{station_name} 取水许可",
        f"{station_name} 选址意见书",
        f"{station_name} 红线图",
        f"{station_name} 拐点坐标",
    ]
    if station_name == "墨脱水电站":
        patterns.extend(["墨脱四级水电站", "米林水库", "帮辛乡", "加热萨乡"])
    if station_name == "达木水电站":
        patterns.extend(["达木乡", "帮辛乡", "加热萨乡"])
    return patterns


def _evidence_families(row: dict[str, Any]) -> list[str]:
    families = ["proxy_geocode_candidate"]
    if row.get("role_alignment_status") == "aligned_with_role_prior":
        families.append("system_layout_role_prior")
    return families


def _required_evidence(gaps: list[str]) -> list[str]:
    required: list[str] = []
    if "needs_hydrography_alignment" in gaps:
        required.append("hydrography")
    if "needs_dam_or_powerhouse_coordinate" in gaps:
        required.append("dam_site_coordinate")
    required.append("second_independent_geo_source")
    return required


def _promotion_blockers(row: dict[str, Any], gaps: list[str]) -> list[str]:
    blockers = list(gaps)
    blockers.append("second_independent_geo_source")
    if row.get("authoritative") is False:
        blockers.append("candidate_is_not_authoritative")
    if row.get("eligible_for_delineation") is False:
        blockers.append("candidate_not_eligible_for_delineation")
    return blockers


def _evidence_gate_status(row: dict[str, Any], blockers: list[str], family_count: int) -> str:
    if row.get("role_alignment_status") == "conflicts_with_role_prior":
        return "blocked_by_conflict"
    if blockers:
        return "needs_corroboration"
    if family_count >= 2:
        return "ready_for_manual_geo_review"
    return "needs_corroboration"


def _resolved_blockers_from_findings(rows: list[dict[str, Any]]) -> list[str]:
    resolved: set[str] = set()
    for row in rows:
        for claim in row.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            claim_type = str(claim.get("claim_type") or "").strip()
            if claim_type in {"hydrography_alignment", "hydrography_context"}:
                resolved.add("needs_hydrography_alignment")
            if claim_type in {"coordinate", "dam_site_coordinate", "dam_site_text"}:
                resolved.add("needs_dam_or_powerhouse_coordinate")
            if claim_type in {"energy_network_relation", "route_access_context", "project_boundary"}:
                resolved.add("second_independent_geo_source")
    return sorted(resolved)


def build_station_pre_delineation_review(case_id: str, workspace: Path) -> dict[str, Any] | None:
    contracts_dir = workspace / "cases" / case_id / "contracts"
    candidates_path = contracts_dir / "station_outlet_candidates.latest.json"
    payload = _safe_load_json(candidates_path)
    if not isinstance(payload, dict):
        return None

    candidates = [row for row in (payload.get("candidates") or []) if isinstance(row, dict)]
    if not candidates:
        return None
    findings_by_station = _findings_by_station(_load_station_findings(case_id, workspace))

    review_rows: list[dict[str, Any]] = []
    for row in candidates:
        gaps = _evidence_gaps(row)
        families = _evidence_families(row)
        blockers = _promotion_blockers(row, gaps)
        matched_findings = findings_by_station.get(str(row.get("station_id") or "").strip(), [])
        resolved_blockers = _resolved_blockers_from_findings(matched_findings)
        remaining_blockers = [item for item in blockers if item not in resolved_blockers]
        gate_status = _evidence_gate_status(row, remaining_blockers, len(families))
        review_rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "station_id": row.get("station_id"),
                "station_name": row.get("station_name"),
                "review_status": row.get("pre_delineation_review_status") or "hold",
                "validation_priority": row.get("validation_priority") or "low",
                "system_layout_role_hypothesis": row.get("system_layout_role_hypothesis"),
                "role_alignment_status": row.get("role_alignment_status"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "display_name": row.get("display_name"),
                "authoritative": row.get("authoritative"),
                "eligible_for_delineation": row.get("eligible_for_delineation"),
                "blocking_reasons": list(row.get("limitations") or []),
                "evidence_gaps": gaps,
                "independent_evidence_families": families,
                "independent_evidence_family_count": len(families),
                "required_evidence": _required_evidence(gaps),
                "promotion_blockers": blockers,
                "blocker_accounting": {
                    "matched_finding_count": len(matched_findings),
                    "resolved_blockers": resolved_blockers,
                    "remaining_blockers": remaining_blockers,
                    "resolution_status": "partially_resolved" if resolved_blockers else "unresolved",
                },
                "evidence_gate_status": gate_status,
                "review_checklist": _review_checklist(gaps),
                "recommended_public_source_types": _recommended_public_source_types(),
                "recommended_query_patterns": _recommended_query_patterns(str(row.get("station_name") or "")),
                "recommended_next_step": row.get("recommended_next_step"),
            }
        )

    return {
        "case_id": case_id,
        "schema_version": "station_pre_delineation_review.v1",
        "generated_at": _now_iso(),
        "review_status": "manual_validation_priority" if any(row.get("review_status") == "manual_validation_priority" for row in review_rows) else "hold",
        "source_contracts": {
            "station_outlet_candidates": _workspace_rel(candidates_path, workspace),
        },
        "summary": {
            "review_candidate_count": len(review_rows),
            "manual_validation_priority_count": sum(1 for row in review_rows if row.get("review_status") == "manual_validation_priority"),
            "hold_count": sum(1 for row in review_rows if row.get("review_status") == "hold"),
            "needs_corroboration_count": sum(1 for row in review_rows if row.get("evidence_gate_status") == "needs_corroboration"),
            "ready_for_manual_geo_review_count": sum(1 for row in review_rows if row.get("evidence_gate_status") == "ready_for_manual_geo_review"),
            "partially_resolved_count": sum(1 for row in review_rows if (row.get("blocker_accounting") or {}).get("resolution_status") == "partially_resolved"),
            "unresolved_count": sum(1 for row in review_rows if (row.get("blocker_accounting") or {}).get("resolution_status") == "unresolved"),
        },
        "review_candidates": review_rows,
        "notes": [
            "Pre-delineation review remains non-authoritative and does not promote candidates into delineation-ready outlets.",
            "Candidates in manual_validation_priority should be the next focus for stronger geographic evidence collection.",
        ],
    }
