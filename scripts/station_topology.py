#!/usr/bin/env python3
"""探源 (TanYuan) — Extract a generic station-topology contract from source bundle evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _workspace_rel(path: Path, workspace: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def _resolve_artifact_path(record: dict[str, Any], workspace: Path) -> Path | None:
    artifact = record.get("artifact") or {}
    raw_path = str(artifact.get("path") or "").strip()
    if not raw_path:
        return None
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else (workspace / candidate)


def _record_summary(record: dict[str, Any], workspace: Path) -> dict[str, Any]:
    path = _resolve_artifact_path(record, workspace)
    artifact = record.get("artifact") or {}
    return {
        "role": record.get("role"),
        "artifact_type": artifact.get("artifact_type"),
        "path": _workspace_rel(path, workspace) if path and path.exists() else str(artifact.get("path") or ""),
        "evidence": list(record.get("evidence") or []),
    }


def _discovered_record(path: Path, role: str, via_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": role,
        "artifact": {
            "artifact_type": "yaml",
            "path": str(path),
            "metadata": {"role_in_bundle": "structured_config_discovery"},
        },
        "evidence": [
            f"discovered_from:{via_record.get('role')}",
        ],
    }


def _source_ref(path: Path, key: str, workspace: Path) -> str:
    return f"{_workspace_rel(path, workspace)}#{key}"


def _normalize_aliases(*values: Any) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        candidate = str(value).strip()
        if not candidate:
            continue
        lowered = candidate.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        aliases.append(candidate)
    return aliases


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _station_index(stations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for station in stations:
        station_id = str(station.get("id") or "").strip()
        if station_id:
            indexed[station_id] = station
    return indexed


def _discover_yaml_records(records: list[dict[str, Any]], workspace: Path) -> dict[str, dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    for record in records:
        artifact = record.get("artifact") or {}
        if str(artifact.get("artifact_type") or "").strip().lower() != "directory":
            continue
        directory = _resolve_artifact_path(record, workspace)
        if directory is None or not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".yaml", ".yml"}:
                continue
            payload = _safe_load_yaml(path)
            if not isinstance(payload, dict):
                continue
            if "engine" not in discovered and isinstance(payload.get("cascade_stations"), list):
                discovered["engine"] = _discovered_record(path, "discovered_engine_params", record)
            if (
                "scheme" not in discovered
                and isinstance((payload.get("cascade_config") or {}).get("stations"), list)
            ):
                discovered["scheme"] = _discovered_record(path, "discovered_scheme_params", record)
            topology = payload.get("topology") or {}
            if "bridge" not in discovered and isinstance(topology, dict) and (
                isinstance(topology.get("station_names"), dict) or isinstance(payload.get("target_stations"), list)
            ):
                discovered["bridge"] = _discovered_record(path, "discovered_bridge_config", record)
            if {"engine", "scheme", "bridge"}.issubset(discovered.keys()):
                return discovered
    return discovered


def build_station_topology(case_id: str, workspace: Path) -> dict[str, Any] | None:
    contracts_dir = workspace / "cases" / case_id / "contracts"
    source_bundle_path = contracts_dir / "source_bundle.contract.json"
    payload = _safe_load_json(source_bundle_path)
    if not isinstance(payload, dict):
        return None

    records = [record for record in (payload.get("records") or []) if isinstance(record, dict)]
    selected_records: dict[str, dict[str, Any]] = {}
    for record in records:
        role = str(record.get("role") or "").strip()
        metadata = (record.get("artifact") or {}).get("metadata") or {}
        bundle_role = str(metadata.get("role_in_bundle") or "").strip()
        artifact_type = str((record.get("artifact") or {}).get("artifact_type") or "").strip().lower()
        if artifact_type != "yaml":
            continue
        if bundle_role == "external_model_params" and "engine" not in selected_records:
            selected_records["engine"] = record
        elif bundle_role == "external_model_scheme" and "scheme" not in selected_records:
            selected_records["scheme"] = record
        elif bundle_role == "lab_bridge_config" and "bridge" not in selected_records:
            selected_records["bridge"] = record
        elif role.endswith("_engine_params") and "engine" not in selected_records:
            selected_records["engine"] = record
        elif role.endswith("_scheme_params") and "scheme" not in selected_records:
            selected_records["scheme"] = record

    if "engine" not in selected_records or "scheme" not in selected_records:
        selected_records.update({key: value for key, value in _discover_yaml_records(records, workspace).items() if key not in selected_records})

    warnings: list[str] = []
    engine_path = _resolve_artifact_path(selected_records.get("engine") or {}, workspace)
    scheme_path = _resolve_artifact_path(selected_records.get("scheme") or {}, workspace)
    bridge_path = _resolve_artifact_path(selected_records.get("bridge") or {}, workspace)
    engine = _safe_load_yaml(engine_path) if engine_path and engine_path.exists() else None
    scheme = _safe_load_yaml(scheme_path) if scheme_path and scheme_path.exists() else None
    bridge = _safe_load_yaml(bridge_path) if bridge_path and bridge_path.exists() else None

    if not isinstance(engine, dict) and not isinstance(scheme, dict):
        return None

    engine_stations = engine.get("cascade_stations") if isinstance(engine, dict) else None
    scheme_stations = _first_dict(scheme).get("cascade_config", {}).get("stations") if isinstance(scheme, dict) else None
    bridge_topology = _first_dict(bridge).get("topology", {}) if isinstance(bridge, dict) else {}

    if not isinstance(engine_stations, list):
        engine_stations = []
    if not isinstance(scheme_stations, list):
        scheme_stations = []

    primary_stations = sorted(
        [station for station in engine_stations if isinstance(station, dict)],
        key=lambda item: int(item.get("position", 0) or 0),
    )
    if not primary_stations:
        primary_stations = sorted(
            [station for station in scheme_stations if isinstance(station, dict)],
            key=lambda item: int(item.get("position", 0) or 0),
        )
        warnings.append("engine_primary_missing_using_scheme_fallback")

    if not primary_stations:
        return None

    scheme_by_id = _station_index([station for station in scheme_stations if isinstance(station, dict)])
    bridge_station_names = bridge_topology.get("station_names") if isinstance(bridge_topology, dict) else {}
    if not isinstance(bridge_station_names, dict):
        bridge_station_names = {}

    stations: list[dict[str, Any]] = []
    total_aliases = 0
    for index, station in enumerate(primary_stations):
        station_id = str(station.get("id") or "").strip()
        if not station_id:
            warnings.append(f"station_missing_id_at_index_{index}")
            continue
        scheme_station = scheme_by_id.get(station_id, {})
        hydraulic = _first_dict(station.get("hydraulic"))
        turbine = _first_dict(station.get("turbine"))
        generator = _first_dict(station.get("generator"))
        governor = _first_dict(station.get("governor"))
        canonical_name = station.get("name") or scheme_station.get("name") or bridge_station_names.get(station_id) or station_id
        aliases = _normalize_aliases(
            station.get("name_en"),
            scheme_station.get("name"),
            bridge_station_names.get(station_id),
        )
        aliases = [alias for alias in aliases if alias != canonical_name]
        total_aliases += len(aliases)
        installed_capacity = scheme_station.get("installed_capacity")
        if installed_capacity is None and turbine.get("rated_power") is not None and turbine.get("num_units") is not None:
            try:
                installed_capacity = float(turbine["rated_power"]) * int(turbine["num_units"])
            except Exception:
                installed_capacity = None
        position = station.get("position") or scheme_station.get("position") or index + 1
        upstream_station_id = primary_stations[index - 1].get("id") if index > 0 else None
        downstream_station_id = primary_stations[index + 1].get("id") if index + 1 < len(primary_stations) else None
        stations.append(
            {
                "station_id": station_id,
                "canonical_name": canonical_name,
                "aliases": aliases,
                "cascade_position": int(position),
                "upstream_station_id": upstream_station_id,
                "downstream_station_id": downstream_station_id,
                "installed_capacity_mw": installed_capacity,
                "num_units": turbine.get("num_units", scheme_station.get("num_units")),
                "scheme_ref": scheme_station.get("scheme"),
                "hydraulic": {
                    "rated_head_m": hydraulic.get("rated_head"),
                    "min_head_m": hydraulic.get("min_head"),
                    "max_head_m": hydraulic.get("max_head"),
                    "rated_flow_per_unit_m3s": hydraulic.get("rated_flow"),
                    "tunnel_length_m": hydraulic.get("tunnel_length"),
                    "tunnel_diameter_m": hydraulic.get("tunnel_diameter"),
                    "water_inertia_time_s": hydraulic.get("water_inertia_time"),
                    "wave_speed_mps": hydraulic.get("wave_speed"),
                    "friction_factor": hydraulic.get("friction_factor"),
                },
                "turbine": {
                    "type": turbine.get("type"),
                    "rated_power_per_unit_mw": turbine.get("rated_power"),
                    "rated_speed_rpm": turbine.get("rated_speed"),
                    "efficiency": turbine.get("efficiency"),
                },
                "generator": {
                    "type": generator.get("type"),
                    "rated_power_mva": generator.get("rated_power"),
                    "rated_voltage_kv": generator.get("rated_voltage"),
                    "power_factor": generator.get("power_factor"),
                    "inertia_constant_s": generator.get("inertia_constant"),
                },
                "governor": {
                    "type": governor.get("type"),
                    "kp": governor.get("kp"),
                    "ki": governor.get("ki"),
                    "kd": governor.get("kd"),
                    "rate_limit": governor.get("rate_limit"),
                    "servo_time": governor.get("servo_time"),
                    "dead_band": governor.get("dead_band"),
                },
                "geometry_status": "missing",
                "geometry_hints": [],
                "source_refs": [
                    _source_ref(engine_path, f"cascade_stations[{index}]", workspace)
                    if engine_path and engine_path.exists()
                    else None,
                    _source_ref(scheme_path, f"cascade_config.stations[{index}]", workspace)
                    if scheme_path and scheme_path.exists() and scheme_station
                    else None,
                ],
            }
        )

    for station in stations:
        station["source_refs"] = [item for item in station.get("source_refs", []) if item]

    odd_config = _first_dict(engine).get("odd_config", {}) if isinstance(engine, dict) else {}
    boundary_hints = {
        "system_boundaries": _first_dict(odd_config.get("system_boundaries")),
        "transient_boundaries": _first_dict(odd_config.get("transient_boundaries")),
        "cascade_boundaries": _first_dict(odd_config.get("cascade_boundaries")),
    }
    if not any(boundary_hints.values()):
        warnings.append("boundary_hints_missing")

    return {
        "case_id": case_id,
        "schema_version": "station_topology.v1",
        "generated_at": _now_iso(),
        "topology_kind": "cascade_station_registry",
        "topology_status": "named_only",
        "source_bundle_contract": _workspace_rel(source_bundle_path, workspace),
        "source_records": [
            _record_summary(selected_records[key], workspace)
            for key in ("engine", "scheme", "bridge")
            if key in selected_records
        ],
        "summary": {
            "station_count": len(stations),
            "geo_located_station_count": 0,
            "alias_count": total_aliases,
            "boundary_hints_present": any(boundary_hints.values()),
        },
        "stations": stations,
        "boundary_hints": boundary_hints,
        "warnings": sorted(set(warnings)),
    }
