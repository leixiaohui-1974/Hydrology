#!/usr/bin/env python3
"""探源 (TanYuan) — Fetch review-only geocode candidates for case stations."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import load_case_config, write_json  # noqa: E402

WORKSPACE = BASE_DIR.parent
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "CodexHydroMind/1.0 (research geocode candidate fetch)"


@dataclass
class QuerySpec:
    owner_kind: str
    owner_id: str
    label: str
    query: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _workspace_rel(path: Path) -> str:
    return path.resolve().relative_to(WORKSPACE.resolve()).as_posix()


def _ordered_unique_queries(specs: list[QuerySpec]) -> list[QuerySpec]:
    seen: set[tuple[str, str]] = set()
    ordered: list[QuerySpec] = []
    for spec in specs:
        key = (spec.owner_id, spec.query.casefold())
        if key in seen:
            continue
        seen.add(key)
        ordered.append(spec)
    return ordered


def _norm_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _query_specs(station_geolocation: dict[str, Any]) -> list[QuerySpec]:
    specs: list[QuerySpec] = []
    for station in station_geolocation.get("stations") or []:
        if not isinstance(station, dict):
            continue
        owner_id = str(station.get("station_id") or station.get("canonical_name") or "").strip()
        label = str(station.get("canonical_name") or owner_id).strip()
        for query in station.get("query_candidates") or []:
            specs.append(QuerySpec("station", owner_id, label, str(query)))
    for hint in ((station_geolocation.get("case_context") or {}).get("mainstem_planning_hints") or []):
        if not isinstance(hint, dict):
            continue
        owner_id = str(hint.get("hint_id") or hint.get("label") or "").strip()
        label = str(hint.get("label") or owner_id).strip()
        raw_queries = hint.get("query_candidates") or [label]
        for query in raw_queries:
            specs.append(QuerySpec("hint", owner_id, label, str(query)))
    return _ordered_unique_queries(specs)


def _candidate_anchor_score(spec: QuerySpec, candidate: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    query_norm = _norm_text(spec.query)
    label_norm = _norm_text(spec.label)
    name_norm = _norm_text(candidate.get("name"))
    display_norm = _norm_text(candidate.get("display_name"))
    candidate_type = str(candidate.get("type") or "").strip().lower()
    candidate_category = str(candidate.get("category") or "").strip().lower()
    importance = float(candidate.get("importance") or 0.0)

    query_name_exact = bool(query_norm and query_norm == name_norm)
    label_name_exact = bool(label_norm and label_norm == name_norm)
    label_display_partial = bool(label_norm and label_norm in display_norm)
    query_display_partial = bool(query_norm and query_norm in display_norm)

    type_weight = {
        ("place", "village"): 2.4,
        ("place", "town"): 2.2,
        ("place", "city"): 1.8,
        ("boundary", "administrative"): 1.6,
        ("place", "locality"): 1.0,
    }.get((candidate_category, candidate_type), 0.5)

    score = type_weight + importance
    if spec.owner_kind == "hint":
        score += 0.5
    if query_name_exact:
        score += 1.5
    if label_name_exact:
        score += 1.0
    if query_display_partial:
        score += 0.4
    if label_display_partial:
        score += 0.4

    proxy_class = "weak_proxy"
    if candidate_category == "boundary" and candidate_type == "administrative":
        proxy_class = "admin_area_proxy"
    elif candidate_type in {"village", "town", "city"}:
        proxy_class = "locality_proxy"

    return round(score, 4), {
        "query_name_exact": query_name_exact,
        "label_name_exact": label_name_exact,
        "query_display_partial": query_display_partial,
        "label_display_partial": label_display_partial,
        "proxy_class": proxy_class,
    }


def _select_review_anchor_candidates(spec: QuerySpec, formatted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in formatted:
        score, signals = _candidate_anchor_score(spec, candidate)
        ranked.append(
            {
                **candidate,
                "anchor_score": score,
                "anchor_signals": signals,
            }
        )
    ranked.sort(key=lambda item: (-float(item["anchor_score"]), -float(item.get("importance") or 0.0), item.get("display_name") or ""))
    selected: list[dict[str, Any]] = []
    for candidate in ranked:
        if candidate["anchor_signals"]["proxy_class"] == "weak_proxy":
            continue
        if float(candidate["anchor_score"]) < 1.8:
            continue
        selected.append(candidate)
    return selected[:2]


def _bounded_result(item: dict[str, Any], cfg: dict[str, Any]) -> bool:
    validation = cfg.get("validation") or {}
    lat_range = validation.get("lat_range") or [15.0, 55.0]
    lon_range = validation.get("lon_range") or [70.0, 140.0]
    try:
        lat = float(item.get("lat"))
        lon = float(item.get("lon"))
    except (TypeError, ValueError):
        return False
    return lat_range[0] <= lat <= lat_range[1] and lon_range[0] <= lon <= lon_range[1]


def _search_nominatim(query: str, cfg: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    validation = cfg.get("validation") or {}
    lat_range = validation.get("lat_range") or [15.0, 55.0]
    lon_range = validation.get("lon_range") or [70.0, 140.0]
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": str(limit),
        "addressdetails": "1",
        "accept-language": "zh-CN,en",
        "countrycodes": "cn",
        "viewbox": f"{lon_range[0]},{lat_range[1]},{lon_range[1]},{lat_range[0]}",
        "bounded": "1",
    }
    request = Request(f"{NOMINATIM_SEARCH_URL}?{urlencode(params)}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict) and _bounded_result(item, cfg)]


def fetch_case_station_geocode_candidates(case_id: str, *, limit: int = 3) -> dict[str, Any]:
    station_geolocation_path = WORKSPACE / "cases" / case_id / "contracts" / "station_geolocation.latest.json"
    station_geolocation = _load_json(station_geolocation_path)
    if not station_geolocation:
        raise FileNotFoundError(f"station geolocation contract not found: {station_geolocation_path}")

    cfg = load_case_config(case_id)
    queries = _query_specs(station_geolocation)
    results: list[dict[str, Any]] = []
    owner_summary: dict[str, dict[str, Any]] = {}
    review_anchor_candidates: list[dict[str, Any]] = []
    for spec in queries:
        error: str | None = None
        try:
            matches = _search_nominatim(spec.query, cfg, limit)
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            matches = []
            error = str(exc)
        formatted = [
            {
                "query": spec.query,
                "place_id": item.get("place_id"),
                "osm_type": item.get("osm_type"),
                "osm_id": item.get("osm_id"),
                "name": item.get("name"),
                "display_name": item.get("display_name"),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "category": item.get("category"),
                "type": item.get("type"),
                "importance": item.get("importance"),
            }
            for item in matches
        ]
        selected_anchors = _select_review_anchor_candidates(spec, formatted)
        results.append(
            {
                "owner_kind": spec.owner_kind,
                "owner_id": spec.owner_id,
                "label": spec.label,
                "query": spec.query,
                "candidate_count": len(formatted),
                "candidates": formatted,
                "selected_anchor_candidates": selected_anchors,
                "error": error,
            }
        )
        summary = owner_summary.setdefault(
            spec.owner_id,
            {
                "owner_kind": spec.owner_kind,
                "owner_id": spec.owner_id,
                "label": spec.label,
                "query_count": 0,
                "candidate_count": 0,
            },
        )
        summary["query_count"] += 1
        summary["candidate_count"] += len(formatted)
        summary["selected_anchor_candidate_count"] = int(summary.get("selected_anchor_candidate_count") or 0) + len(selected_anchors)
        for anchor in selected_anchors:
            review_anchor_candidates.append(
                {
                    "owner_kind": spec.owner_kind,
                    "owner_id": spec.owner_id,
                    "label": spec.label,
                    "query": spec.query,
                    "candidate": anchor,
                }
            )

    payload = {
        "case_id": case_id,
        "schema_version": "station_geocode_candidates.v1",
        "generated_at": _now_iso(),
        "geocoder": {
            "provider": "nominatim",
            "search_url": NOMINATIM_SEARCH_URL,
            "countrycodes": ["cn"],
        },
        "source_contracts": {
            "station_geolocation": _workspace_rel(station_geolocation_path),
        },
        "summary": {
            "query_count": len(queries),
            "result_row_count": len(results),
            "owner_count": len(owner_summary),
            "candidate_count": sum(item["candidate_count"] for item in results),
            "owners_with_candidates": sum(1 for item in owner_summary.values() if item["candidate_count"] > 0),
            "review_anchor_candidate_count": len(review_anchor_candidates),
            "owners_with_review_anchors": sum(1 for item in owner_summary.values() if item.get("selected_anchor_candidate_count")),
        },
        "owners": list(owner_summary.values()),
        "review_anchor_candidates": review_anchor_candidates,
        "results": results,
    }
    output_path = WORKSPACE / "cases" / case_id / "contracts" / "station_geocode_candidates.latest.json"
    write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch review-only station geocode candidates for a case")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    payload = fetch_case_station_geocode_candidates(args.case_id.strip(), limit=args.limit)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
