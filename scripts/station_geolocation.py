#!/usr/bin/env python3
"""探源 (TanYuan) — Derive a generic station-geolocation contract from topology and public-data evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENERATOR_REF = "Hydrology/scripts/station_geolocation.py:build_station_geolocation"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _workspace_rel(path: Path, workspace: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def _persisted_path_or_none(raw: Any, workspace: Path) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.startswith("[external]/"):
        return text
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    try:
        return resolved.relative_to(workspace.resolve()).as_posix()
    except ValueError:
        name = resolved.name or candidate.name or "artifact"
        return f"[external]/{name}"


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        candidate = str(value or "").strip()
        if not candidate:
            continue
        lowered = candidate.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(candidate)
    return ordered


def _project_context_records(public_data_inventory: dict[str, Any]) -> list[dict[str, Any]]:
    records = public_data_inventory.get("records") or []
    return [
        record
        for record in records
        if isinstance(record, dict)
        and str(record.get("public_data_kind") or "").strip() == "project_context"
    ]


def _load_case_naming_evidence(case_id: str, workspace: Path) -> tuple[dict[str, Any], Path | None]:
    path = workspace / "cases" / case_id / "ingest" / "raw" / "station_naming_evidence.json"
    payload = _safe_load_json(path)
    if not isinstance(payload, dict):
        return {}, (path if path.exists() else None)
    return payload, path


def _load_station_geocode_candidates(case_id: str, workspace: Path) -> tuple[dict[str, Any], Path | None]:
    path = workspace / "cases" / case_id / "contracts" / "station_geocode_candidates.latest.json"
    payload = _safe_load_json(path)
    if not isinstance(payload, dict):
        return {}, (path if path.exists() else None)
    return payload, path


def _context_evidence(record: dict[str, Any], workspace: Path) -> dict[str, Any]:
    return {
        "source_id": record.get("source_id"),
        "title": record.get("title"),
        "url": record.get("url"),
        "path": _persisted_path_or_none(record.get("path"), workspace),
        "provider": record.get("provider"),
        "public_data_kind": record.get("public_data_kind"),
        "source_kind": record.get("source_kind"),
    }


def _resolve_evidence_path(raw: Any, workspace: Path) -> Path | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path if path.is_file() else None
    candidate = (workspace / path).resolve()
    return candidate if candidate.is_file() else None


def _evidence_paths_from_config(case_config: dict[str, Any] | None, workspace: Path) -> tuple[Path | None, Path | None]:
    if not case_config:
        return None, None
    block = case_config.get("station_geolocation_inputs") or {}
    if not isinstance(block, dict):
        return None, None
    auth = _resolve_evidence_path(block.get("authoritative_coordinates_path"), workspace)
    hydro = _resolve_evidence_path(block.get("hydrography_alignment_evidence_path"), workspace)
    return auth, hydro


def _load_geojson_authoritative(path: Path) -> dict[str, dict[str, Any]]:
    """Load station_id -> resolved_coordinate payload from GeoJSON FeatureCollection."""
    raw = _safe_load_json(path)
    if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection":
        return {}
    out: dict[str, dict[str, Any]] = {}
    for feat in raw.get("features") or []:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") if isinstance(feat.get("properties"), dict) else {}
        sid = str(props.get("station_id") or props.get("id") or "").strip()
        if not sid:
            continue
        geom = feat.get("geometry")
        if not isinstance(geom, dict) or geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates")
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            continue
        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except (TypeError, ValueError):
            continue
        out[sid] = {
            "lon": lon,
            "lat": lat,
            "source": "authoritative_geojson",
            "source_path": path,
        }
    return out


def _load_hydro_alignment_flag(path: Path) -> bool:
    raw = _safe_load_json(path)
    if not isinstance(raw, dict):
        return False
    if raw.get("hydrography_alignment") is True:
        return True
    if raw.get("aligned") is True:
        return True
    status = str(raw.get("status") or "").strip().lower()
    return status in {"aligned", "ready", "verified"}


def _hydrography_satisfied_from_inventory(public_data_inventory: dict[str, Any]) -> bool:
    summary = public_data_inventory.get("summary") if isinstance(public_data_inventory, dict) else {}
    if not isinstance(summary, dict):
        return False
    avail = [str(x).casefold() for x in (summary.get("available_public_data_kinds") or []) if str(x).strip()]
    blocked = [str(x).casefold() for x in (summary.get("blocked_public_data_kinds") or []) if str(x).strip()]
    return "hydrography" in avail and "hydrography" not in blocked


def _station_queries(station: dict[str, Any], context_titles: list[str]) -> list[str]:
    canonical_name = str(station.get("canonical_name") or station.get("station_id") or "").strip()
    aliases = [str(alias or "").strip() for alias in (station.get("aliases") or []) if str(alias or "").strip()]
    queries = [
        f"{canonical_name} 经纬度",
        f"{canonical_name} 坐标",
        f"{canonical_name} latitude longitude",
    ]
    for alias in aliases:
        queries.append(f"{alias} latitude longitude")
    for title in context_titles[:2]:
        queries.append(f"{canonical_name} {title} 经纬度")
    return _ordered_unique(queries)


def build_station_geolocation(
    case_id: str,
    workspace: Path,
    *,
    case_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    contracts_dir = workspace / "cases" / case_id / "contracts"
    station_topology_path = contracts_dir / "station_topology.latest.json"
    station_topology = _safe_load_json(station_topology_path)
    if not isinstance(station_topology, dict):
        return None

    stations = [station for station in (station_topology.get("stations") or []) if isinstance(station, dict)]
    if not stations:
        return None

    public_data_inventory_path = contracts_dir / "public_data_inventory.latest.json"
    public_data_inventory = _safe_load_json(public_data_inventory_path)
    if not isinstance(public_data_inventory, dict):
        public_data_inventory = {}

    context_records = _project_context_records(public_data_inventory)
    context_titles = _ordered_unique([str(record.get("title") or "").strip() for record in context_records])
    context_evidence = [_context_evidence(record, workspace) for record in context_records]
    blocked_public_data = list(
        ((public_data_inventory.get("summary") or {}).get("blocked_public_data_kinds")) or []
    )
    naming_evidence, naming_evidence_path = _load_case_naming_evidence(case_id, workspace)
    planning_hints = [
        hint
        for hint in (naming_evidence.get("mainstem_planning_hints") or [])
        if isinstance(hint, dict)
    ]
    geocode_candidates, geocode_candidates_path = _load_station_geocode_candidates(case_id, workspace)
    geocode_results = geocode_candidates.get("results") or []
    geocode_by_owner: dict[str, list[dict[str, Any]]] = {}
    for row in geocode_results:
        if not isinstance(row, dict):
            continue
        owner_id = str(row.get("owner_id") or "").strip()
        if not owner_id:
            continue
        geocode_by_owner.setdefault(owner_id, []).append(row)

    auth_path, hydro_path = _evidence_paths_from_config(case_config, workspace)
    authoritative_by_station = _load_geojson_authoritative(auth_path) if auth_path else {}

    geocode_summary = dict(geocode_candidates.get("summary") or {})
    review_anchor_candidates = list(geocode_candidates.get("review_anchor_candidates") or [])
    review_anchor_by_owner: dict[str, list[dict[str, Any]]] = {}
    for row in review_anchor_candidates:
        if not isinstance(row, dict):
            continue
        owner_id = str(row.get("owner_id") or "").strip()
        if not owner_id:
            continue
        review_anchor_by_owner.setdefault(owner_id, []).append(row)
    hydro_ok = bool(hydro_path and _load_hydro_alignment_flag(hydro_path))
    if not hydro_ok:
        hydro_ok = _hydrography_satisfied_from_inventory(public_data_inventory)

    geolocated_count = 0
    station_rows: list[dict[str, Any]] = []
    for station in stations:
        sid = str(station.get("station_id") or "").strip()
        auth_coord = authoritative_by_station.get(sid)
        base_geo_status = "context_linked" if context_evidence else "query_ready"
        resolved_coordinate = dict(auth_coord) if isinstance(auth_coord, dict) else auth_coord
        if isinstance(resolved_coordinate, dict) and resolved_coordinate.get("source_path"):
            resolved_coordinate["source_path"] = _persisted_path_or_none(
                resolved_coordinate.get("source_path"), workspace
            )
        if auth_coord:
            base_geo_status = "authoritative_resolved"
            geolocated_count += 1
        station_rows.append(
            {
                "station_id": station.get("station_id"),
                "canonical_name": station.get("canonical_name"),
                "aliases": list(station.get("aliases") or []),
                "cascade_position": station.get("cascade_position"),
                "geolocation_status": base_geo_status,
                "resolved_coordinate": resolved_coordinate,
                "query_candidates": _station_queries(station, context_titles),
                "geocode_candidates": list(geocode_by_owner.get(sid, [])),
                "review_anchor_candidates": list(review_anchor_by_owner.get(sid, [])),
                "topology_source_refs": list(station.get("source_refs") or []),
                "context_evidence_refs": [
                    {
                        "source_id": item.get("source_id"),
                        "url": item.get("url"),
                        "path": item.get("path"),
                    }
                    for item in context_evidence
                ],
                "blocked_public_data_kinds": blocked_public_data,
                "fit_for_outlet_normalization": bool(auth_coord) and hydro_ok,
            }
        )

    authoritative_coordinate_count = sum(1 for row in station_rows if row.get("resolved_coordinate"))
    fit_for_outlet_normalization_count = sum(1 for row in station_rows if row.get("fit_for_outlet_normalization"))
    candidate_only_count = len(station_rows) - authoritative_coordinate_count
    blocked_by: list[str] = []
    if authoritative_coordinate_count < len(station_rows):
        blocked_by.append("station_specific_coordinates_missing")
    if not hydro_ok:
        blocked_by.append("hydrography_alignment_missing")

    if fit_for_outlet_normalization_count >= len(station_rows) and station_rows:
        pipeline_status = "ready_for_outlet_normalization"
    elif authoritative_coordinate_count >= len(station_rows) and station_rows:
        pipeline_status = "needs_hydrography_alignment"
    else:
        pipeline_status = "needs_station_coordinate_sources"

    status = "context_linked" if context_evidence else "query_ready"
    if int(geocode_summary.get("owners_with_candidates") or 0) > 0 or int(geocode_summary.get("candidate_count") or 0) > 0:
        status = "candidate_augmented"
    if geolocated_count:
        status = "partially_resolved"
    if authoritative_coordinate_count >= len(station_rows) and station_rows:
        status = "authoritative_complete"

    return {
        "case_id": case_id,
        "schema_version": "station_geolocation.v1",
        "generated_at": _now_iso(),
        "generator": GENERATOR_REF,
        "status": pipeline_status,
        "geolocation_status": status,
        "source_contracts": {
            "station_topology": _workspace_rel(station_topology_path, workspace),
            "public_data_inventory": (
                _workspace_rel(public_data_inventory_path, workspace)
                if public_data_inventory_path.exists()
                else None
            ),
            "authoritative_coordinates": _persisted_path_or_none(auth_path, workspace),
            "hydrography_alignment_evidence": _persisted_path_or_none(hydro_path, workspace),
        },
        "summary": {
            "station_count": len(station_rows),
            "context_evidence_count": len(context_evidence),
            "query_ready_station_count": len(station_rows),
            "geo_located_station_count": geolocated_count,
            "blocked_public_data_kinds": blocked_public_data,
            "review_anchor_candidate_count": len(review_anchor_candidates),
            "authoritative_coordinate_count": authoritative_coordinate_count,
            "candidate_only_count": candidate_only_count,
            "fit_for_outlet_normalization_count": fit_for_outlet_normalization_count,
            "blocked_by": blocked_by,
        },
        "case_context": {
            "project_context_titles": context_titles,
            "project_context_evidence": context_evidence,
            "available_public_data_kinds": list(
                ((public_data_inventory.get("summary") or {}).get("available_public_data_kinds")) or []
            ),
            "blocked_public_data_kinds": blocked_public_data,
            "naming_evidence_contract": (
                _workspace_rel(naming_evidence_path, workspace)
                if naming_evidence_path and naming_evidence_path.exists()
                else None
            ),
            "mainstem_planning_hints": planning_hints,
            "station_geocode_candidates_contract": (
                _workspace_rel(geocode_candidates_path, workspace)
                if geocode_candidates_path and geocode_candidates_path.exists()
                else None
            ),
            "station_geocode_summary": geocode_summary,
            "review_anchor_candidates": review_anchor_candidates,
        },
        "stations": station_rows,
        "warnings": ([] if context_evidence else ["project_context_evidence_missing"]),
    }
