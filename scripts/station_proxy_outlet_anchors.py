#!/usr/bin/env python3
"""探源 (TanYuan) — Build proxy outlet anchors from review geocode candidates."""
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


def _norm_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _anchor_kind(candidate: dict[str, Any]) -> str:
    signals = candidate.get("anchor_signals") or {}
    proxy_class = str(signals.get("proxy_class") or "").strip()
    if proxy_class == "admin_area_proxy":
        return "proxy_admin_area"
    if proxy_class == "locality_proxy":
        return "proxy_locality"
    return "proxy_unknown"


def _anchor_confidence(candidate: dict[str, Any]) -> str:
    score = float(candidate.get("anchor_score") or 0.0)
    if score >= 4.0:
        return "medium"
    if score >= 2.5:
        return "low"
    return "very_low"


def _load_station_topology(case_id: str, workspace: Path) -> dict[str, Any]:
    path = workspace / "cases" / case_id / "contracts" / "station_topology.latest.json"
    payload = _safe_load_json(path)
    return payload if isinstance(payload, dict) else {}


def _station_query_assignment(query: str, station_topology: dict[str, Any]) -> dict[str, Any] | None:
    query_norm = _norm_text(query)
    if not query_norm:
        return None
    for station in station_topology.get("stations") or []:
        if not isinstance(station, dict):
            continue
        station_id = str(station.get("station_id") or "").strip()
        canonical_name = str(station.get("canonical_name") or "").strip()
        if not station_id or not canonical_name:
            continue
        if query_norm in _norm_text(canonical_name):
            return {
                "station_id": station_id,
                "station_name": canonical_name,
            }
    return None


def _candidate_name_supports_query(query: str, candidate: dict[str, Any]) -> bool:
    query_norm = _norm_text(query)
    if not query_norm:
        return False
    name_norm = _norm_text(candidate.get("name"))
    display_norm = _norm_text(candidate.get("display_name"))
    return query_norm in name_norm or query_norm in display_norm


def _proxy_anchor_payload(case_id: str, index: int, row: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    signals = candidate.get("anchor_signals") or {}
    return {
        "anchor_id": f"{case_id}-proxy-anchor-{index:02d}",
        "owner_kind": row.get("owner_kind"),
        "owner_id": row.get("owner_id"),
        "label": row.get("label"),
        "query": row.get("query"),
        "proxy_anchor_status": "proxy_review_ready",
        "anchor_kind": _anchor_kind(candidate),
        "confidence": _anchor_confidence(candidate),
        "lat": candidate.get("lat"),
        "lon": candidate.get("lon"),
        "display_name": candidate.get("display_name"),
        "source_name": candidate.get("name"),
        "source_type": candidate.get("type"),
        "source_category": candidate.get("category"),
        "anchor_score": candidate.get("anchor_score"),
        "anchor_signals": signals,
        "mapping_basis": "query_token_matches_engineering_station_name",
        "authoritative": False,
        "eligible_for_delineation": False,
        "limitations": [
            "proxy_only_not_authoritative_outlet",
            "requires_downstream_coordinate_or_hydrography_confirmation",
        ],
    }


def build_station_proxy_outlet_anchors(case_id: str, workspace: Path) -> dict[str, Any] | None:
    contracts_dir = workspace / "cases" / case_id / "contracts"
    station_geocode_candidates_path = contracts_dir / "station_geocode_candidates.latest.json"
    station_geocode_candidates = _safe_load_json(station_geocode_candidates_path)
    if not isinstance(station_geocode_candidates, dict):
        return None

    review_candidates = [
        row
        for row in (station_geocode_candidates.get("review_anchor_candidates") or [])
        if isinstance(row, dict) and isinstance(row.get("candidate"), dict)
    ]
    if not review_candidates:
        return None
    station_topology = _load_station_topology(case_id, workspace)
    assigned_candidates: dict[str, list[dict[str, Any]]] = {}
    unassigned: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for index, row in enumerate(review_candidates, start=1):
        candidate = row["candidate"]
        proxy_anchor = _proxy_anchor_payload(case_id, index, row, candidate)
        assignment = _station_query_assignment(str(row.get("query") or ""), station_topology)
        if assignment and _candidate_name_supports_query(str(row.get("query") or ""), candidate):
            assigned = {
                **proxy_anchor,
                "station_id": assignment["station_id"],
                "station_name": assignment["station_name"],
                "source_owner_id": row.get("owner_id"),
                "source_query": row.get("query"),
                "source_candidate": candidate,
                "evidence_refs": [{"owner_id": row.get("owner_id"), "query": row.get("query")}],
            }
            assigned_candidates.setdefault(assignment["station_id"], []).append(assigned)
            continue
        if assignment and not _candidate_name_supports_query(str(row.get("query") or ""), candidate):
            rejected.append(
                {
                    "owner_id": row.get("owner_id"),
                    "query": row.get("query"),
                    "candidate_name": candidate.get("name"),
                    "reject_reason": "candidate_name_does_not_support_query_token",
                }
            )
            continue
        unassigned.append(
            {
                **proxy_anchor,
                "reason_unassigned": "no_safe_engineering_station_mapping",
                "evidence_refs": [{"owner_id": row.get("owner_id"), "query": row.get("query")}],
            }
        )

    station_proxy_anchors: list[dict[str, Any]] = []
    for station_id, candidates in assigned_candidates.items():
        candidates.sort(key=lambda item: (-float(item.get("anchor_score") or 0.0), item.get("display_name") or ""))
        station_proxy_anchors.append(candidates[0])

    return {
        "case_id": case_id,
        "schema_version": "station_proxy_outlet_anchors.v1",
        "generated_at": _now_iso(),
        "anchor_status": "proxy_review_ready",
        "source_contracts": {
            "station_geocode_candidates": _workspace_rel(station_geocode_candidates_path, workspace),
        },
        "summary": {
            "anchor_count": len(station_proxy_anchors) + len(unassigned),
            "station_proxy_anchor_count": len(station_proxy_anchors),
            "unassigned_case_proxy_anchor_count": len(unassigned),
            "rejected_candidate_count": len(rejected),
            "owner_count": len({str(anchor.get("owner_id") or "") for anchor in [*station_proxy_anchors, *unassigned]}),
            "admin_area_anchor_count": sum(1 for anchor in [*station_proxy_anchors, *unassigned] if anchor.get("anchor_kind") == "proxy_admin_area"),
            "locality_anchor_count": sum(1 for anchor in [*station_proxy_anchors, *unassigned] if anchor.get("anchor_kind") == "proxy_locality"),
        },
        "station_proxy_anchors": station_proxy_anchors,
        "unassigned_case_proxy_anchors": unassigned,
        "rejected_candidates": rejected,
        "notes": [
            "Proxy anchors are review-only spatial hints derived from public geocoder results.",
            "Do not promote to delineation-ready outlets without additional coordinate or hydrography confirmation.",
        ],
    }
