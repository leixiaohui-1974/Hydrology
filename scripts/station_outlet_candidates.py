#!/usr/bin/env python3
"""探源 (TanYuan) — Build review-only outlet candidates from proxy outlet anchors."""
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


def _load_naming_evidence(case_id: str, workspace: Path) -> dict[str, Any]:
    path = workspace / "cases" / case_id / "ingest" / "raw" / "station_naming_evidence.json"
    payload = _safe_load_json(path)
    return payload if isinstance(payload, dict) else {}


def _role_hypothesis_map(naming_evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    for hint in naming_evidence.get("mainstem_planning_hints") or []:
        if not isinstance(hint, dict) or hint.get("kind") != "role_hypothesis":
            continue
        mapping: dict[str, dict[str, Any]] = {}
        for row in hint.get("stations") or []:
            if not isinstance(row, dict):
                continue
            key = str(row.get("name") or "").strip()
            if key:
                mapping[key] = row
        return mapping
    return {}


def _match_role_hypothesis(station_name: str, role_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for key, payload in role_map.items():
        if key and key in station_name:
            return payload
    return {}


def _validation_priority(candidate_confidence: str, role_alignment_status: str) -> str:
    if role_alignment_status == "aligned_with_role_prior":
        return "high"
    if candidate_confidence in {"medium", "high"}:
        return "medium"
    return "low"


def _pre_delineation_review_status(candidate_confidence: str, role_alignment_status: str) -> str:
    if role_alignment_status == "aligned_with_role_prior":
        return "manual_validation_priority"
    if candidate_confidence in {"medium", "high"}:
        return "manual_validation_secondary"
    return "hold"


def _recommended_next_step(review_status: str) -> str:
    if review_status == "manual_validation_priority":
        return "优先补充高分辨率地理证据或水系/坝址坐标后，进入 pre-delineation 人工复核。"
    if review_status == "manual_validation_secondary":
        return "补充更强地理证据后再考虑进入 pre-delineation 复核。"
    return "暂不升格，继续保留为 review-only candidate。"


def build_station_outlet_candidates(case_id: str, workspace: Path) -> dict[str, Any] | None:
    contracts_dir = workspace / "cases" / case_id / "contracts"
    proxy_path = contracts_dir / "station_proxy_outlet_anchors.latest.json"
    payload = _safe_load_json(proxy_path)
    if not isinstance(payload, dict):
        return None

    station_proxy_anchors = [
        row for row in (payload.get("station_proxy_anchors") or []) if isinstance(row, dict)
    ]
    unassigned_case_proxy_anchors = [
        row for row in (payload.get("unassigned_case_proxy_anchors") or []) if isinstance(row, dict)
    ]
    if not station_proxy_anchors and not unassigned_case_proxy_anchors:
        return None
    role_map = _role_hypothesis_map(_load_naming_evidence(case_id, workspace))

    candidates: list[dict[str, Any]] = []
    for index, anchor in enumerate(station_proxy_anchors, start=1):
        role_prior = _match_role_hypothesis(str(anchor.get("station_name") or ""), role_map)
        role_alignment_status = (
            "aligned_with_role_prior"
            if role_prior.get("role_hypothesis") in {"tunnel-system", "mainstem"}
            else "role_prior_missing"
        )
        candidate_confidence = anchor.get("confidence")
        review_status = _pre_delineation_review_status(str(candidate_confidence or ""), role_alignment_status)
        candidates.append(
            {
                "candidate_id": f"{case_id}-outlet-candidate-{index:02d}",
                "station_id": anchor.get("station_id"),
                "station_name": anchor.get("station_name"),
                "candidate_status": "proxy_candidate_review_ready",
                "candidate_kind": "proxy_outlet_candidate",
                "candidate_ref": anchor.get("anchor_id"),
                "candidate_confidence": anchor.get("confidence"),
                "lat": anchor.get("lat"),
                "lon": anchor.get("lon"),
                "display_name": anchor.get("display_name"),
                "source_name": anchor.get("source_name"),
                "source_type": anchor.get("source_type"),
                "source_category": anchor.get("source_category"),
                "mapping_basis": anchor.get("mapping_basis"),
                "system_layout_role_hypothesis": role_prior.get("role_hypothesis"),
                "system_layout_role_confidence": role_prior.get("confidence"),
                "role_alignment_status": role_alignment_status,
                "validation_priority": _validation_priority(str(candidate_confidence or ""), role_alignment_status),
                "pre_delineation_review_status": review_status,
                "recommended_next_step": _recommended_next_step(review_status),
                "authoritative": False,
                "eligible_for_delineation": False,
                "limitations": list(anchor.get("limitations") or []),
            }
        )

    return {
        "case_id": case_id,
        "schema_version": "station_outlet_candidates.v1",
        "generated_at": _now_iso(),
        "candidate_status": "proxy_candidate_review_ready" if candidates else "unassigned_only",
        "source_contracts": {
            "station_proxy_outlet_anchors": _workspace_rel(proxy_path, workspace),
        },
        "summary": {
            "candidate_count": len(candidates),
            "unassigned_case_proxy_anchor_count": len(unassigned_case_proxy_anchors),
            "eligible_for_delineation_count": 0,
            "role_aligned_candidate_count": sum(1 for item in candidates if item.get("role_alignment_status") == "aligned_with_role_prior"),
            "manual_validation_priority_count": sum(1 for item in candidates if item.get("pre_delineation_review_status") == "manual_validation_priority"),
            "held_candidate_count": sum(1 for item in candidates if item.get("pre_delineation_review_status") == "hold"),
        },
        "candidates": candidates,
        "unassigned_case_proxy_anchors": unassigned_case_proxy_anchors,
        "notes": [
            "Outlet candidates are review-only and derived from proxy anchors.",
            "They must not be treated as authoritative or delineation-ready without stronger geographic evidence.",
        ],
    }
