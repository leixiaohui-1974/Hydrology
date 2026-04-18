#!/usr/bin/env python3
"""Import or synthesize a canonical SourceBundle into cases/<id>/contracts/.

This is the minimal P1 import-chain bridge:
- prefer an existing source_bundle contract from manifest / case contracts / pipedream e2e_reports
- otherwise synthesize a lightweight bundle from case config + product outputs + sqlite paths
- optionally copy/update canonical outlets into cases/<id>/contracts/
- update manifest latest_source_bundle/latest_outlets to point at the case-local contracts
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

WORKSPACE = Path(__file__).resolve().parents[2]
HYDROLOGY = WORKSPACE / "Hydrology"
if str(HYDROLOGY) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY))

from workflows._shared import load_case_config, resolve_workspace_relpath, write_json  # noqa: E402

from control_testing_readiness import build_control_testing_readiness  # noqa: E402
from import_observation_csv_to_sqlite import import_observation_csv_to_sqlite  # noqa: E402
from public_data_inventory import build_public_data_inventory  # noqa: E402
from station_geolocation import build_station_geolocation  # noqa: E402
from station_evidence_search_plan import build_station_evidence_search_plan  # noqa: E402
from station_evidence_findings import build_station_evidence_findings  # noqa: E402
from station_outlet_candidates import build_station_outlet_candidates  # noqa: E402
from station_pre_delineation_review import build_station_pre_delineation_review  # noqa: E402
from station_proxy_outlet_anchors import build_station_proxy_outlet_anchors  # noqa: E402
from station_topology import build_station_topology  # noqa: E402


REAL_OBSERVATION_ROLES = {
    "observed_flow",
    "observed_water_level",
    "observed_velocity",
    "observed_station_meta",
}
REAL_OBSERVATION_VARIABLE_ALIASES = {
    "flow": {"flow", "q"},
    "water_level": {"water_level", "z"},
    "velocity": {"velocity"},
}


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_manifest(case_id: str) -> tuple[Path, dict[str, Any]]:
    manifest_path = WORKSPACE / "cases" / case_id / "manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    return manifest_path, data


def _dump_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _looks_like_source_bundle(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(data, dict) and isinstance(data.get("records"), list)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_absolute(path: Path) -> Path:
    try:
        return path.resolve()
    except RuntimeError:
        return path.absolute()


def _workspace_rel(path: Path) -> str:
    return _safe_absolute(path).relative_to(_safe_absolute(WORKSPACE)).as_posix()


def _workspace_rel_or_none(path: Path | None) -> str | None:
    if path is None:
        return None
    return _workspace_rel(path)


def _is_workspace_local_path(path: Path) -> bool:
    try:
        _safe_absolute(path).relative_to(_safe_absolute(WORKSPACE))
        return True
    except ValueError:
        return False


def _redacted_external_path(path: Path) -> str:
    name = path.name or "unknown"
    return f"[external]/{name}"


def _persisted_path_or_none(path: Path | None) -> str | None:
    if path is None:
        return None
    if _is_workspace_local_path(path):
        return _workspace_rel(path)
    return _redacted_external_path(path)


def _persisted_raw_path_or_none(raw_path: Any) -> str | None:
    text = str(raw_path or "").strip()
    if not text:
        return None
    if text.startswith("[external]/"):
        return text
    try:
        return _persisted_path_or_none(resolve_workspace_relpath(text)) or text
    except Exception:
        return text


def _sanitize_configured_input_paths(raw_paths: list[Any]) -> list[str]:
    sanitized: list[str] = []
    for raw in raw_paths or []:
        persisted = _persisted_raw_path_or_none(raw)
        if persisted:
            sanitized.append(persisted)
    return sanitized


def _canonical_artifact_path(path: Path) -> str:
    return _persisted_path_or_none(_safe_absolute(path)) or str(path)


def _canonical_artifact_key_from_raw(raw_path: Any) -> str:
    raw = str(raw_path or "").strip()
    if not raw:
        return ""
    try:
        return _canonical_artifact_path(resolve_workspace_relpath(raw))
    except Exception:
        return raw


def _normalize_payload_artifact_paths(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records") or []
    if not isinstance(records, list):
        return payload
    for record in records:
        if not isinstance(record, dict):
            continue
        artifact = record.get("artifact") or {}
        if not isinstance(artifact, dict):
            continue
        canonical = _canonical_artifact_key_from_raw(artifact.get("path"))
        if canonical:
            artifact["path"] = canonical
    return payload


def _normalize_payload_metadata_paths(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return payload
    for key in ("raw_root", "source_config"):
        if key not in metadata:
            continue
        metadata[key] = _persisted_raw_path_or_none(metadata.get(key)) or ""
    return payload


def _default_case_scan_dirs(case_id: str) -> list[Path]:
    case_root = WORKSPACE / "cases" / case_id
    candidates = [
        case_root / "ingest" / "raw",
        case_root / "ingest" / "web",
        case_root / "inputs",
        case_root / "artifacts",
        case_root / "raw",
    ]
    return [path.resolve() for path in candidates if path.exists()]


def _effective_scan_dirs(case_id: str, cfg: dict[str, Any]) -> list[Path]:
    seen: set[str] = set()
    ordered: list[Path] = []
    for raw_dir in cfg.get("scan_dirs", []) or []:
        path = resolve_workspace_relpath(raw_dir)
        if not path.exists():
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path.resolve())
    for path in _default_case_scan_dirs(case_id):
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path.resolve())
    return ordered


def _default_case_web_seed_files(case_id: str) -> list[Path]:
    web_root = WORKSPACE / "cases" / case_id / "ingest" / "web"
    if not web_root.exists():
        return []
    return [path.resolve() for path in sorted(web_root.glob("*.json")) if path.is_file()]


def _default_case_web_download_files(case_id: str) -> list[Path]:
    downloads_dir = WORKSPACE / "cases" / case_id / "ingest" / "web" / "downloads"
    if not downloads_dir.exists():
        return []
    return [path.resolve() for path in sorted(downloads_dir.rglob("*")) if path.is_file()]


def _case_web_fetch_report_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "web_fetch_report.latest.json"


def _case_public_data_inventory_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "public_data_inventory.latest.json"


def _case_station_topology_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "station_topology.latest.json"


def _case_station_geolocation_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "station_geolocation.latest.json"


def _case_station_geocode_candidates_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "station_geocode_candidates.latest.json"


def _case_station_proxy_outlet_anchors_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "station_proxy_outlet_anchors.latest.json"


def _case_station_outlet_candidates_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "station_outlet_candidates.latest.json"


def _case_station_pre_delineation_review_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "station_pre_delineation_review.latest.json"


def _case_station_evidence_search_plan_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "station_evidence_search_plan.latest.json"


def _case_station_evidence_findings_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "station_evidence_findings.latest.json"


def _case_control_testing_readiness_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "control_testing_readiness.latest.json"


def _artifact_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".xml":
        return "xml"
    if suffix in {".txt", ".md"}:
        return "text"
    if suffix == ".csv":
        return "csv"
    if suffix == ".xlsx":
        return "xlsx"
    if suffix == ".zip":
        return "zip"
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        return "sqlite3"
    return "file"


def _safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _candidate_bundle_paths(case_id: str, manifest: dict[str, Any], cfg: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    latest = manifest.get("latest_source_bundle") or {}
    if isinstance(latest, dict) and str(latest.get("path") or "").strip():
        candidates.append(resolve_workspace_relpath(str(latest["path"])))
    candidates.append(WORKSPACE / "cases" / case_id / "contracts" / "source_bundle.contract.json")
    candidates.append(WORKSPACE / "cases" / case_id / "contracts" / "source_bundle.json")
    candidates.append(
        WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id / "contracts" / "source_bundle.contract.json"
    )
    if cfg.get("source_bundle_path"):
        candidates.append(resolve_workspace_relpath(cfg["source_bundle_path"]))
    # stable de-dupe
    seen: set[str] = set()
    uniq: list[Path] = []
    for path in candidates:
        raw = str(path)
        if raw in seen:
            continue
        seen.add(raw)
        uniq.append(path)
    return uniq


def _candidate_outlets_paths(case_id: str, manifest: dict[str, Any], cfg: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    latest = manifest.get("latest_outlets") or {}
    if isinstance(latest, dict) and str(latest.get("path") or "").strip():
        candidates.append(resolve_workspace_relpath(str(latest["path"])))
    output_dir = cfg.get("output_dir")
    if output_dir:
        candidates.append(resolve_workspace_relpath(output_dir) / "outlets.delineation_ready.json")
    candidates.append(WORKSPACE / "cases" / case_id / "contracts" / "outlets.normalized.json")
    candidates.append(
        WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id / "contracts" / "outlets.normalized.json"
    )
    seen: set[str] = set()
    uniq: list[Path] = []
    for path in candidates:
        raw = str(path)
        if raw in seen:
            continue
        seen.add(raw)
        uniq.append(path)
    return uniq


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _canonicalize_outlets_payload(case_id: str, source_path: Path, payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        outlets = payload.get("outlets")
        count = payload.get("count")
    else:
        outlets = payload
        count = None
    if not isinstance(outlets, list):
        outlets = []
    outlet_count = int(count) if isinstance(count, int) else len(outlets)
    review_candidates = payload.get("review_candidates") if isinstance(payload, dict) else None
    normalization_inputs = payload.get("normalization_inputs") if isinstance(payload, dict) else None
    notes = payload.get("notes") if isinstance(payload, dict) else None
    if not notes:
        notes = (
            "当前合同直接对齐 source_selection/product_outputs 的真实筛选结果；暂无满足规则的可用 outlet，因此保留空集合而非 bootstrap 占位点。"
            if outlet_count == 0
            else "当前合同直接对齐 source_selection/product_outputs 的真实筛选结果。"
        )
    return {
        "case_id": case_id,
        "workflow": (payload.get("workflow") if isinstance(payload, dict) else None) or "watershed_delineation",
        "generated_from": _workspace_rel(source_path),
        "program_contract_path": "Case -> Source Bundle -> Outlet Contract -> Data Pack -> Outcome",
        "review_required": bool(review_candidates) or outlet_count == 0,
        "_auto_generated": True,
        "filter_rules": list((payload.get("filter_rules") if isinstance(payload, dict) else []) or []),
        "excluded": list((payload.get("excluded") if isinstance(payload, dict) else []) or []),
        "count": outlet_count,
        "notes": notes,
        "outlets": outlets,
        "review_candidates": list(review_candidates or []),
        "normalization_inputs": dict(normalization_inputs or {}),
    }


def _preferred_outlets_source(case_id: str, manifest: dict[str, Any], cfg: dict[str, Any], canonical_outlets: Path) -> Path | None:
    output_dir = cfg.get("output_dir")
    output_candidate = resolve_workspace_relpath(output_dir) / "outlets.delineation_ready.json" if output_dir else None
    latest = manifest.get("latest_outlets") or {}
    latest_candidate = None
    if isinstance(latest, dict) and str(latest.get("path") or "").strip():
        latest_candidate = resolve_workspace_relpath(str(latest.get("path")))
    if output_candidate and output_candidate.exists() and (latest_candidate is None or latest_candidate == canonical_outlets):
        return output_candidate
    return _first_existing(_candidate_outlets_paths(case_id, manifest, cfg))


def _artifact_record(case_id: str, role: str, path: Path, artifact_type: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    artifact_path = _canonical_artifact_path(path)
    return {
        "role": role,
        "confidence": 0.8,
        "artifact": {
            "artifact_id": f"{case_id}:{role}",
            "artifact_type": artifact_type,
            "path": artifact_path,
            "uri": None,
            "checksum": None,
            "metadata": metadata or {},
        },
        "evidence": [],
        "needs_review": False,
    }


def _is_case_local_path(case_id: str, path: Path) -> bool:
    case_root = (WORKSPACE / "cases" / case_id).resolve()
    try:
        path.resolve().relative_to(case_root)
        return True
    except ValueError:
        return False


def _should_include_cfg_sqlite_asset(case_id: str, path: Path) -> bool:
    if not _is_workspace_local_path(path):
        return False
    artifact_type = _artifact_type_for_path(path)
    if artifact_type != "sqlite3":
        return True
    return _is_case_local_path(case_id, path)


def _configured_sqlite_path(case_id: str, cfg: dict[str, Any]) -> Path | None:
    sqlite_paths = cfg.get("sqlite_paths") or []
    for candidate in sqlite_paths:
        raw = str(candidate or "").strip()
        if not raw:
            continue
        path = resolve_workspace_relpath(raw)
        if _artifact_type_for_path(path) != "sqlite3":
            continue
        if not _is_case_local_path(case_id, path):
            continue
        return path
    return None


def _source_bundle_roles(payload: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    for record in payload.get("records") or []:
        if not isinstance(record, dict):
            continue
        role = str(record.get("role") or "").strip()
        if role:
            roles.add(role)
    return roles


def _probe_sqlite_observation_mode(sqlite_path: Path) -> dict[str, Any]:
    probe = {
        "exists": sqlite_path.exists(),
        "mode": "missing",
        "station_count": 0,
        "timeseries_meta_rows": 0,
        "variables": [],
    }
    if not sqlite_path.exists():
        return probe

    try:
        conn = sqlite3.connect(str(sqlite_path))
        try:
            table_names = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "stations" in table_names:
                probe["station_count"] = int(conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0])
            if "timeseries_meta" in table_names:
                variables = sorted(
                    {
                        str(row[0] or "").strip()
                        for row in conn.execute("SELECT DISTINCT variable FROM timeseries_meta")
                    }
                )
                probe["variables"] = variables
                probe["timeseries_meta_rows"] = int(conn.execute("SELECT COUNT(*) FROM timeseries_meta").fetchone()[0])
                normalized_variables = {str(value).strip().lower() for value in variables if str(value).strip()}
                has_required_observation_vars = all(
                    normalized_variables.intersection(aliases)
                    for aliases in REAL_OBSERVATION_VARIABLE_ALIASES.values()
                )
                if has_required_observation_vars:
                    probe["mode"] = "real_observation_bundle"
                elif normalized_variables:
                    probe["mode"] = "canonical_csv"
                else:
                    probe["mode"] = "empty"
            else:
                probe["mode"] = "unknown"
        finally:
            conn.close()
    except sqlite3.Error as error:
        probe["mode"] = "invalid_sqlite"
        probe["error"] = str(error)
    return probe


def _ensure_real_observation_sqlite(case_id: str, cfg: dict[str, Any], canonical_bundle: Path, payload: dict[str, Any]) -> dict[str, Any]:
    roles = _source_bundle_roles(payload)
    if not REAL_OBSERVATION_ROLES.issubset(roles):
        return {
            "status": "skipped",
            "reason": "source_bundle_has_no_complete_real_observation_roles",
            "required_roles": sorted(REAL_OBSERVATION_ROLES),
            "present_roles": sorted(roles),
        }

    sqlite_path = _configured_sqlite_path(case_id, cfg)
    if sqlite_path is None:
        return {
            "status": "skipped",
            "reason": "sqlite_path_not_configured",
            "required_roles": sorted(REAL_OBSERVATION_ROLES),
            "present_roles": sorted(roles),
        }

    before = _probe_sqlite_observation_mode(sqlite_path)
    if before.get("mode") == "real_observation_bundle":
        return {
            "status": "skipped",
            "reason": "valid_real_observation_sqlite_exists",
            "sqlite_path": _workspace_rel(sqlite_path),
            "probe_before": before,
        }

    result = import_observation_csv_to_sqlite(
        case_id,
        sqlite_path=sqlite_path,
        replace=sqlite_path.exists(),
        source_bundle_path=canonical_bundle,
    )
    after = _probe_sqlite_observation_mode(sqlite_path)
    return {
        "status": "imported",
        "reason": "replaced_non_real_sqlite" if before.get("exists") else "created_from_real_observation_bundle",
        "sqlite_path": _workspace_rel(sqlite_path),
        "source_bundle_path": _workspace_rel(canonical_bundle),
        "probe_before": before,
        "probe_after": after,
        "result": result,
    }


def _merge_missing_cfg_sqlite_records(case_id: str, payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    records = payload.setdefault("records", [])
    configured_paths: dict[str, Path] = {}
    for raw in cfg.get("sqlite_paths", []) or []:
        path = resolve_workspace_relpath(raw)
        if not path.exists():
            continue
        if not _should_include_cfg_sqlite_asset(case_id, path):
            continue
        configured_paths[_canonical_artifact_path(path)] = path

    retained_records: list[Any] = []
    existing_paths: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            retained_records.append(record)
            continue
        artifact = record.get("artifact") or {}
        resolved = _canonical_artifact_key_from_raw(artifact.get("path"))
        metadata = artifact.get("metadata") or {}
        if resolved in configured_paths and metadata.get("source_mode") == "case_config_merge":
            continue
        retained_records.append(record)
        if resolved:
            existing_paths.add(resolved)

    records[:] = retained_records
    for resolved, path in configured_paths.items():
        if resolved in existing_paths:
            continue
        artifact_type = _artifact_type_for_path(path)
        role_prefix = "sqlite" if artifact_type == "sqlite3" else artifact_type
        records.append(
            _artifact_record(
                case_id,
                f"{role_prefix}_{path.stem}",
                path,
                artifact_type,
                {"role_in_bundle": "telemetry", "source_mode": "case_config_merge"},
            )
        )
        existing_paths.add(resolved)
    return payload


def _merge_case_local_source_records(case_id: str, payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    records = payload.setdefault("records", [])
    existing_paths = {
        _canonical_artifact_key_from_raw((record.get("artifact") or {}).get("path"))
        for record in records
        if isinstance(record, dict)
    }
    for path in _effective_scan_dirs(case_id, cfg):
        resolved = _canonical_artifact_path(path)
        if resolved in existing_paths:
            continue
        records.append(
            _artifact_record(
                case_id,
                f"scan_dir_{path.name}",
                path,
                "directory",
                {"role_in_bundle": "raw_root", "source_mode": "case_local_default"},
            )
        )
        existing_paths.add(resolved)
    for path in _default_case_web_seed_files(case_id):
        resolved = _canonical_artifact_path(path)
        if resolved in existing_paths:
            continue
        records.append(
            _artifact_record(
                case_id,
                f"web_seed_{path.stem}",
                path,
                "json",
                {"role_in_bundle": "web_seed", "source_mode": "case_local_default"},
            )
        )
        existing_paths.add(resolved)
    for path in _default_case_web_download_files(case_id):
        resolved = _canonical_artifact_path(path)
        if resolved in existing_paths:
            continue
        records.append(
            _artifact_record(
                case_id,
                f"web_download_{path.stem}",
                path,
                _artifact_type_for_path(path),
                {"role_in_bundle": "web_download", "source_mode": "web_fetch"},
            )
        )
        existing_paths.add(resolved)
    fetch_report = _case_web_fetch_report_path(case_id)
    fetch_report_resolved = _canonical_artifact_path(fetch_report)
    if fetch_report.exists() and fetch_report_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "web_fetch_report",
                fetch_report,
                "json",
                {"role_in_bundle": "web_fetch_report", "source_mode": "web_fetch"},
            )
        )
        existing_paths.add(fetch_report_resolved)
    public_data_inventory = _case_public_data_inventory_path(case_id)
    public_data_inventory_resolved = _canonical_artifact_path(public_data_inventory)
    if public_data_inventory.exists() and public_data_inventory_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "public_data_inventory",
                public_data_inventory,
                "json",
                {"role_in_bundle": "public_data_inventory", "source_mode": "web_fetch"},
            )
        )
        existing_paths.add(public_data_inventory_resolved)
    station_topology = _case_station_topology_path(case_id)
    station_topology_resolved = _canonical_artifact_path(station_topology)
    if station_topology.exists() and station_topology_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "station_topology",
                station_topology,
                "json",
                {"role_in_bundle": "station_topology", "source_mode": "structured_config"},
            )
        )
        existing_paths.add(station_topology_resolved)
    station_geolocation = _case_station_geolocation_path(case_id)
    station_geolocation_resolved = _canonical_artifact_path(station_geolocation)
    if station_geolocation.exists() and station_geolocation_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "station_geolocation",
                station_geolocation,
                "json",
                {"role_in_bundle": "station_geolocation", "source_mode": "structured_config"},
            )
        )
        existing_paths.add(station_geolocation_resolved)
    station_geocode_candidates = _case_station_geocode_candidates_path(case_id)
    station_geocode_candidates_resolved = _canonical_artifact_path(station_geocode_candidates)
    if station_geocode_candidates.exists() and station_geocode_candidates_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "station_geocode_candidates",
                station_geocode_candidates,
                "json",
                {"role_in_bundle": "station_geocode_candidates", "source_mode": "geocoding_augmentation"},
            )
        )
        existing_paths.add(station_geocode_candidates_resolved)
    station_proxy_outlet_anchors = _case_station_proxy_outlet_anchors_path(case_id)
    station_proxy_outlet_anchors_resolved = _canonical_artifact_path(station_proxy_outlet_anchors)
    if station_proxy_outlet_anchors.exists() and station_proxy_outlet_anchors_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "station_proxy_outlet_anchors",
                station_proxy_outlet_anchors,
                "json",
                {"role_in_bundle": "station_proxy_outlet_anchors", "source_mode": "geocoding_augmentation"},
            )
        )
        existing_paths.add(station_proxy_outlet_anchors_resolved)
    station_outlet_candidates = _case_station_outlet_candidates_path(case_id)
    station_outlet_candidates_resolved = _canonical_artifact_path(station_outlet_candidates)
    if station_outlet_candidates.exists() and station_outlet_candidates_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "station_outlet_candidates",
                station_outlet_candidates,
                "json",
                {"role_in_bundle": "station_outlet_candidates", "source_mode": "geocoding_augmentation"},
            )
        )
        existing_paths.add(station_outlet_candidates_resolved)
    station_pre_delineation_review = _case_station_pre_delineation_review_path(case_id)
    station_pre_delineation_review_resolved = _canonical_artifact_path(station_pre_delineation_review)
    if station_pre_delineation_review.exists() and station_pre_delineation_review_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "station_pre_delineation_review",
                station_pre_delineation_review,
                "json",
                {"role_in_bundle": "station_pre_delineation_review", "source_mode": "geocoding_augmentation"},
            )
        )
        existing_paths.add(station_pre_delineation_review_resolved)
    station_evidence_search_plan = _case_station_evidence_search_plan_path(case_id)
    station_evidence_search_plan_resolved = _canonical_artifact_path(station_evidence_search_plan)
    if station_evidence_search_plan.exists() and station_evidence_search_plan_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "station_evidence_search_plan",
                station_evidence_search_plan,
                "json",
                {"role_in_bundle": "station_evidence_search_plan", "source_mode": "review_planning"},
            )
        )
        existing_paths.add(station_evidence_search_plan_resolved)
    station_evidence_findings = _case_station_evidence_findings_path(case_id)
    station_evidence_findings_resolved = _canonical_artifact_path(station_evidence_findings)
    if station_evidence_findings.exists() and station_evidence_findings_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "station_evidence_findings",
                station_evidence_findings,
                "json",
                {"role_in_bundle": "station_evidence_findings", "source_mode": "evidence_ingestion"},
            )
        )
        existing_paths.add(station_evidence_findings_resolved)
    control_testing_readiness = _case_control_testing_readiness_path(case_id)
    control_testing_readiness_resolved = _canonical_artifact_path(control_testing_readiness)
    if control_testing_readiness.exists() and control_testing_readiness_resolved not in existing_paths:
        records.append(
            _artifact_record(
                case_id,
                "control_testing_readiness",
                control_testing_readiness,
                "json",
                {"role_in_bundle": "control_testing_readiness", "source_mode": "control_lane_readiness"},
            )
        )
        existing_paths.add(control_testing_readiness_resolved)
    return payload


def _synthesize_bundle(case_id: str, manifest: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    output_dir = resolve_workspace_relpath(cfg["output_dir"]) if cfg.get("output_dir") else None
    scan_dirs = _effective_scan_dirs(case_id, cfg)
    web_seed_files = _default_case_web_seed_files(case_id)
    web_download_files = _default_case_web_download_files(case_id)

    if output_dir:
        for filename, role, artifact_type, metadata in [
            ("outlets.delineation_ready.json", "outlets_ready", "json", {"role_in_bundle": "outlets"}),
            ("control_station_mapping.json", "control_station_mapping", "json", {"role_in_bundle": "topology"}),
            ("source_reliability.json", "source_reliability", "json", {"role_in_bundle": "reliability"}),
            ("coordinate_validation.json", "coordinate_validation", "json", {"role_in_bundle": "gis_validation"}),
        ]:
            path = output_dir / filename
            if path.exists():
                records.append(_artifact_record(case_id, role, path, artifact_type, metadata))

    for raw in cfg.get("sqlite_paths", []) or []:
        path = resolve_workspace_relpath(raw)
        if not path.exists():
            continue
        if not _should_include_cfg_sqlite_asset(case_id, path):
            continue
        artifact_type = _artifact_type_for_path(path)
        role_prefix = "sqlite" if artifact_type == "sqlite3" else artifact_type
        records.append(
            _artifact_record(
                case_id,
                f"{role_prefix}_{path.stem}",
                path,
                artifact_type,
                {"role_in_bundle": "telemetry"},
            )
        )

    for path in scan_dirs:
        records.append(_artifact_record(case_id, f"scan_dir_{path.name}", path, "directory", {"role_in_bundle": "raw_root"}))

    for path in web_seed_files:
        records.append(
            _artifact_record(
                case_id,
                f"web_seed_{path.stem}",
                path,
                "json",
                {"role_in_bundle": "web_seed"},
            )
        )
    for path in web_download_files:
        records.append(
            _artifact_record(
                case_id,
                f"web_download_{path.stem}",
                path,
                _artifact_type_for_path(path),
                {"role_in_bundle": "web_download", "source_mode": "web_fetch"},
            )
        )
    fetch_report = _case_web_fetch_report_path(case_id)
    if fetch_report.exists():
        records.append(
            _artifact_record(
                case_id,
                "web_fetch_report",
                fetch_report,
                "json",
                {"role_in_bundle": "web_fetch_report", "source_mode": "web_fetch"},
            )
        )

    latest_outlets = manifest.get("latest_outlets") or {}
    if isinstance(latest_outlets, dict) and str(latest_outlets.get("path") or "").strip():
        out_path = resolve_workspace_relpath(str(latest_outlets["path"]))
        out_key = _canonical_artifact_path(out_path)
        if out_path.exists() and not any(_canonical_artifact_key_from_raw((r.get("artifact") or {}).get("path")) == out_key for r in records):
            records.append(_artifact_record(case_id, "outlets_latest", out_path, "json", {"role_in_bundle": "outlets"}))

    return {
        "bundle_id": f"{case_id}-source-bundle-imported",
        "case_id": case_id,
        "records": records,
        "gaps": [],
        "review_required": [],
        "metadata": {
            "display_name": cfg.get("display_name") or ((manifest.get("case") or {}).get("display_name")) or case_id,
            "internal_case_code": case_id,
            "raw_root": _persisted_raw_path_or_none((manifest.get("locations") or {}).get("raw_root")) or "",
            "source": "import_case_sourcebundle.py",
        },
        "schema_version": "1.0",
    }


def _build_web_source_session(case_id: str, public_data_inventory: dict[str, Any] | None = None) -> dict[str, Any] | None:
    web_root = WORKSPACE / "cases" / case_id / "ingest" / "web"
    downloads_dir = web_root / "downloads"
    web_files = _default_case_web_seed_files(case_id)
    fetch_report_path = _case_web_fetch_report_path(case_id)
    fetch_report = _safe_load_json(fetch_report_path) if fetch_report_path.exists() else None
    if not web_root.exists() and not web_files and not downloads_dir.exists() and not fetch_report_path.exists():
        return None

    seed_query_count = 0
    seed_url_count = 0
    discovered_source_count = 0
    artifacts: list[dict[str, Any]] = []

    for path in web_files:
        payload = _safe_load_json(path)
        rel = _workspace_rel(path)
        artifacts.append(
            {
                "path": rel,
                "kind": path.stem,
                "present": True,
            }
        )
        if isinstance(payload, dict):
            if isinstance(payload.get("queries"), list):
                seed_query_count += len(payload.get("queries") or [])
            if isinstance(payload.get("urls"), list):
                seed_url_count += len(payload.get("urls") or [])
            if isinstance(payload.get("sources"), list):
                discovered_source_count += len(payload.get("sources") or [])
        elif isinstance(payload, list):
            if path.stem == "seed_queries":
                seed_query_count += len(payload)
            elif path.stem == "seed_urls":
                seed_url_count += len(payload)
            elif path.stem == "discovered_urls":
                discovered_source_count += len(payload)

    download_files = _default_case_web_download_files(case_id)
    for path in download_files:
        artifacts.append(
            {
                "path": _workspace_rel(path),
                "kind": "download",
                "present": True,
            }
        )
    if fetch_report_path.exists():
        artifacts.append(
            {
                "path": _workspace_rel(fetch_report_path),
                "kind": "fetch_report",
                "present": True,
            }
        )
    public_data_inventory_path = _case_public_data_inventory_path(case_id)
    if public_data_inventory_path.exists():
        artifacts.append(
            {
                "path": _workspace_rel(public_data_inventory_path),
                "kind": "public_data_inventory",
                "present": True,
            }
        )

    status = "absent"
    if discovered_source_count > 0 or seed_query_count > 0 or seed_url_count > 0:
        status = "seeded"
    if download_files:
        status = "downloaded"

    return {
        "case_id": case_id,
        "schema_version": "web_source_session.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "web_root": _workspace_rel(web_root) if web_root.exists() else None,
        "downloads_dir": _workspace_rel(downloads_dir) if downloads_dir.exists() else _workspace_rel(downloads_dir),
        "seed_query_count": seed_query_count,
        "seed_url_count": seed_url_count,
        "discovered_source_count": discovered_source_count,
        "download_file_count": len(download_files),
        "downloaded_count": int((fetch_report or {}).get("downloaded_count") or len(download_files)),
        "fetch_report_contract": _workspace_rel(fetch_report_path) if fetch_report_path.exists() else None,
        "public_data_inventory_contract": _workspace_rel(public_data_inventory_path) if public_data_inventory_path.exists() else None,
        "public_data_summary": dict((public_data_inventory or {}).get("summary") or {}),
        "needs_web_fetch": bool((seed_query_count or seed_url_count or discovered_source_count) and not download_files),
        "artifacts": artifacts,
    }


def import_case_sourcebundle(case_id: str, *, update_manifest: bool = True) -> dict[str, Any]:
    manifest_path, manifest = _load_manifest(case_id)
    cfg = load_case_config(case_id)
    effective_scan_dirs = _effective_scan_dirs(case_id, cfg)
    web_seed_files = _default_case_web_seed_files(case_id)
    web_download_files = _default_case_web_download_files(case_id)
    web_fetch_report_path = _case_web_fetch_report_path(case_id)
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    source_bundle_path = _first_existing(_candidate_bundle_paths(case_id, manifest, cfg))
    if source_bundle_path and _looks_like_source_bundle(source_bundle_path):
        payload = _normalize_payload_metadata_paths(_normalize_payload_artifact_paths(deepcopy(_load_json(source_bundle_path))))
        payload = _merge_case_local_source_records(case_id, payload, cfg)
        payload = _merge_missing_cfg_sqlite_records(case_id, payload, cfg)
        source_mode = "copied_contract"
    else:
        payload = _normalize_payload_metadata_paths(_normalize_payload_artifact_paths(_synthesize_bundle(case_id, manifest, cfg)))
        source_mode = "synthesized"

    canonical_bundle = contracts_dir / "source_bundle.contract.json"
    write_json(canonical_bundle, payload)
    import_session_path = contracts_dir / "source_import_session.latest.json"
    web_source_session_path = contracts_dir / "web_source_session.latest.json"
    public_data_inventory_path = _case_public_data_inventory_path(case_id)
    station_topology_path = _case_station_topology_path(case_id)
    station_geolocation_path = _case_station_geolocation_path(case_id)
    station_geocode_candidates_path = _case_station_geocode_candidates_path(case_id)
    station_proxy_outlet_anchors_path = _case_station_proxy_outlet_anchors_path(case_id)
    station_outlet_candidates_path = _case_station_outlet_candidates_path(case_id)
    station_pre_delineation_review_path = _case_station_pre_delineation_review_path(case_id)
    station_evidence_search_plan_path = _case_station_evidence_search_plan_path(case_id)
    station_evidence_findings_path = _case_station_evidence_findings_path(case_id)
    control_testing_readiness_path = _case_control_testing_readiness_path(case_id)
    sqlite_import = _ensure_real_observation_sqlite(case_id, cfg, canonical_bundle, payload)
    payload = _merge_case_local_source_records(case_id, payload, cfg)
    payload = _merge_missing_cfg_sqlite_records(case_id, payload, cfg)
    public_data_inventory = build_public_data_inventory(case_id, WORKSPACE)
    if public_data_inventory:
        write_json(public_data_inventory_path, public_data_inventory)
    station_topology = build_station_topology(case_id, WORKSPACE)
    if station_topology:
        write_json(station_topology_path, station_topology)
    station_geolocation = build_station_geolocation(case_id, WORKSPACE, case_config=cfg)
    if station_geolocation:
        write_json(station_geolocation_path, station_geolocation)
    station_proxy_outlet_anchors = build_station_proxy_outlet_anchors(case_id, WORKSPACE)
    if station_proxy_outlet_anchors:
        write_json(station_proxy_outlet_anchors_path, station_proxy_outlet_anchors)
    station_outlet_candidates = build_station_outlet_candidates(case_id, WORKSPACE)
    if station_outlet_candidates:
        write_json(station_outlet_candidates_path, station_outlet_candidates)
    station_pre_delineation_review = build_station_pre_delineation_review(case_id, WORKSPACE)
    if station_pre_delineation_review:
        write_json(station_pre_delineation_review_path, station_pre_delineation_review)
    station_evidence_search_plan = build_station_evidence_search_plan(case_id, WORKSPACE)
    if station_evidence_search_plan:
        write_json(station_evidence_search_plan_path, station_evidence_search_plan)
    station_evidence_findings = build_station_evidence_findings(case_id, WORKSPACE)
    if station_evidence_findings:
        write_json(station_evidence_findings_path, station_evidence_findings)
    control_testing_readiness = build_control_testing_readiness(case_id, WORKSPACE)
    if control_testing_readiness:
        write_json(control_testing_readiness_path, control_testing_readiness)
    web_source_session = _build_web_source_session(case_id, public_data_inventory)
    payload = _merge_case_local_source_records(case_id, payload, cfg)
    write_json(canonical_bundle, payload)
    if web_source_session:
        write_json(web_source_session_path, web_source_session)

    canonical_outlets = contracts_dir / "outlets.normalized.json"
    outlets_source = _preferred_outlets_source(case_id, manifest, cfg, canonical_outlets)
    if outlets_source and outlets_source.is_file():
        canonical_payload = _canonicalize_outlets_payload(case_id, outlets_source, _load_json(outlets_source))
        write_json(canonical_outlets, canonical_payload)

    if update_manifest:
        latest_source = manifest.setdefault("latest_source_bundle", {})
        latest_source["path"] = _workspace_rel(canonical_bundle)
        latest_source["status"] = "contract_ready"
        latest_source["updated_at"] = _now_date()

        if canonical_outlets.exists():
            latest_outlets = manifest.setdefault("latest_outlets", {})
            latest_outlets["path"] = _workspace_rel(canonical_outlets)
            latest_outlets["status"] = latest_outlets.get("status") or "contract_ready"
            latest_outlets["updated_at"] = _now_date()

        latest_session = manifest.setdefault("latest_source_import_session", {})
        latest_session["path"] = _workspace_rel(import_session_path)
        latest_session["status"] = "contract_ready"
        latest_session["updated_at"] = _now_date()

        if web_source_session:
            latest_web = manifest.setdefault("latest_web_source_session", {})
            latest_web["path"] = _workspace_rel(web_source_session_path)
            latest_web["status"] = web_source_session.get("status") or "contract_ready"
            latest_web["updated_at"] = _now_date()

        if station_topology:
            latest_topology = manifest.setdefault("latest_station_topology", {})
            latest_topology["path"] = _workspace_rel(station_topology_path)
            latest_topology["status"] = station_topology.get("topology_status") or "contract_ready"
            latest_topology["updated_at"] = _now_date()
        if station_geolocation:
            latest_geolocation = manifest.setdefault("latest_station_geolocation", {})
            latest_geolocation["path"] = _workspace_rel(station_geolocation_path)
            latest_geolocation["status"] = station_geolocation.get("geolocation_status") or "contract_ready"
            latest_geolocation["updated_at"] = _now_date()
        if station_geocode_candidates_path.exists():
            latest_geocode = manifest.setdefault("latest_station_geocode_candidates", {})
            latest_geocode["path"] = _workspace_rel(station_geocode_candidates_path)
            latest_geocode["status"] = "contract_ready"
            latest_geocode["updated_at"] = _now_date()
        if station_proxy_outlet_anchors:
            latest_proxy = manifest.setdefault("latest_station_proxy_outlet_anchors", {})
            latest_proxy["path"] = _workspace_rel(station_proxy_outlet_anchors_path)
            latest_proxy["status"] = station_proxy_outlet_anchors.get("anchor_status") or "contract_ready"
            latest_proxy["updated_at"] = _now_date()
        if station_outlet_candidates:
            latest_outlet_candidates = manifest.setdefault("latest_station_outlet_candidates", {})
            latest_outlet_candidates["path"] = _workspace_rel(station_outlet_candidates_path)
            latest_outlet_candidates["status"] = station_outlet_candidates.get("candidate_status") or "contract_ready"
            latest_outlet_candidates["updated_at"] = _now_date()
        if station_pre_delineation_review:
            latest_pre_delineation = manifest.setdefault("latest_station_pre_delineation_review", {})
            latest_pre_delineation["path"] = _workspace_rel(station_pre_delineation_review_path)
            latest_pre_delineation["status"] = station_pre_delineation_review.get("review_status") or "contract_ready"
            latest_pre_delineation["updated_at"] = _now_date()
        if station_evidence_search_plan:
            latest_search_plan = manifest.setdefault("latest_station_evidence_search_plan", {})
            latest_search_plan["path"] = _workspace_rel(station_evidence_search_plan_path)
            latest_search_plan["status"] = station_evidence_search_plan.get("plan_status") or "contract_ready"
            latest_search_plan["updated_at"] = _now_date()
        if station_evidence_findings:
            latest_findings = manifest.setdefault("latest_station_evidence_findings", {})
            latest_findings["path"] = _workspace_rel(station_evidence_findings_path)
            latest_findings["status"] = station_evidence_findings.get("ingest_status") or "contract_ready"
            latest_findings["updated_at"] = _now_date()
        if control_testing_readiness:
            latest_control = manifest.setdefault("latest_control_testing_readiness", {})
            latest_control["path"] = _workspace_rel(control_testing_readiness_path)
            latest_control["status"] = control_testing_readiness.get("status") or "contract_ready"
            latest_control["updated_at"] = _now_date()

        _dump_manifest(manifest_path, manifest)

    imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    import_session = {
        "case_id": case_id,
        "imported_at": imported_at,
        "source_mode": source_mode,
        "record_count": len(payload.get("records") or []),
        "source_bundle_contract": _workspace_rel(canonical_bundle),
        "outlets_contract": _workspace_rel(canonical_outlets) if canonical_outlets.exists() else None,
        "source_bundle_input": _persisted_path_or_none(source_bundle_path),
        "outlets_input": _persisted_path_or_none(outlets_source),
        "manifest_updated": bool(update_manifest),
        "sqlite_import": sqlite_import,
        "station_topology_contract": _workspace_rel_or_none(station_topology_path if station_topology else None),
        "station_topology_summary": dict((station_topology or {}).get("summary") or {}),
        "topology_status": (station_topology or {}).get("topology_status"),
        "station_geolocation_contract": _workspace_rel_or_none(station_geolocation_path if station_geolocation else None),
        "station_geolocation_summary": dict((station_geolocation or {}).get("summary") or {}),
        "geolocation_status": (station_geolocation or {}).get("geolocation_status"),
        "station_geocode_candidates_contract": _workspace_rel_or_none(station_geocode_candidates_path if station_geocode_candidates_path.exists() else None),
        "station_proxy_outlet_anchors_contract": _workspace_rel_or_none(station_proxy_outlet_anchors_path if station_proxy_outlet_anchors else None),
        "station_proxy_outlet_anchors_summary": dict((station_proxy_outlet_anchors or {}).get("summary") or {}),
        "proxy_anchor_status": (station_proxy_outlet_anchors or {}).get("anchor_status"),
        "station_outlet_candidates_contract": _workspace_rel_or_none(station_outlet_candidates_path if station_outlet_candidates else None),
        "station_outlet_candidates_summary": dict((station_outlet_candidates or {}).get("summary") or {}),
        "outlet_candidate_status": (station_outlet_candidates or {}).get("candidate_status"),
        "station_pre_delineation_review_contract": _workspace_rel_or_none(station_pre_delineation_review_path if station_pre_delineation_review else None),
        "station_pre_delineation_review_summary": dict((station_pre_delineation_review or {}).get("summary") or {}),
        "pre_delineation_review_status": (station_pre_delineation_review or {}).get("review_status"),
        "station_evidence_search_plan_contract": _workspace_rel_or_none(station_evidence_search_plan_path if station_evidence_search_plan else None),
        "station_evidence_search_plan_summary": dict((station_evidence_search_plan or {}).get("summary") or {}),
        "evidence_search_plan_status": (station_evidence_search_plan or {}).get("plan_status"),
        "station_evidence_findings_contract": _workspace_rel_or_none(station_evidence_findings_path if station_evidence_findings else None),
        "station_evidence_findings_summary": dict((station_evidence_findings or {}).get("summary") or {}),
        "evidence_findings_status": (station_evidence_findings or {}).get("ingest_status"),
        "control_testing_readiness_contract": _workspace_rel_or_none(control_testing_readiness_path if control_testing_readiness else None),
        "control_testing_readiness_summary": {
            "ready_for": list((control_testing_readiness or {}).get("ready_for") or []),
            "not_ready_for": list((control_testing_readiness or {}).get("not_ready_for") or []),
        },
        "control_testing_readiness_status": (control_testing_readiness or {}).get("status"),
        "inputs": {
            "manifest_path": _workspace_rel(manifest_path),
            "latest_source_bundle_path": str((manifest.get("latest_source_bundle") or {}).get("path") or ""),
            "latest_outlets_path": str((manifest.get("latest_outlets") or {}).get("path") or ""),
            "scan_dirs": [_workspace_rel(path) for path in effective_scan_dirs],
            "web_seed_files": [_workspace_rel(path) for path in web_seed_files],
            "web_download_files": [_workspace_rel(path) for path in web_download_files],
            "web_fetch_report": _workspace_rel_or_none(web_fetch_report_path if web_fetch_report_path.exists() else None),
            "web_source_session": _workspace_rel_or_none(web_source_session_path if web_source_session else None),
            "public_data_inventory": _workspace_rel_or_none(public_data_inventory_path if public_data_inventory else None),
            "station_topology": _workspace_rel_or_none(station_topology_path if station_topology else None),
            "station_geolocation": _workspace_rel_or_none(station_geolocation_path if station_geolocation else None),
            "station_geocode_candidates": _workspace_rel_or_none(station_geocode_candidates_path if station_geocode_candidates_path.exists() else None),
            "station_proxy_outlet_anchors": _workspace_rel_or_none(station_proxy_outlet_anchors_path if station_proxy_outlet_anchors else None),
            "station_outlet_candidates": _workspace_rel_or_none(station_outlet_candidates_path if station_outlet_candidates else None),
            "station_pre_delineation_review": _workspace_rel_or_none(station_pre_delineation_review_path if station_pre_delineation_review else None),
            "station_evidence_search_plan": _workspace_rel_or_none(station_evidence_search_plan_path if station_evidence_search_plan else None),
            "station_evidence_findings": _workspace_rel_or_none(station_evidence_findings_path if station_evidence_findings else None),
            "control_testing_readiness": _workspace_rel_or_none(control_testing_readiness_path if control_testing_readiness else None),
            "sqlite_paths": _sanitize_configured_input_paths(cfg.get("sqlite_paths") or []),
            "output_dir": _persisted_raw_path_or_none(cfg.get("output_dir")) or "",
        },
    }
    write_json(import_session_path, import_session)

    return {
        "ok": True,
        "case_id": case_id,
        "source_mode": source_mode,
        "imported_at": imported_at,
        "source_bundle_contract": _workspace_rel(canonical_bundle),
        "outlets_contract": _workspace_rel(canonical_outlets) if canonical_outlets.exists() else None,
        "import_session_contract": _workspace_rel(import_session_path),
        "web_fetch_report_contract": _workspace_rel_or_none(web_fetch_report_path if web_fetch_report_path.exists() else None),
        "web_source_session_contract": _workspace_rel_or_none(web_source_session_path if web_source_session else None),
        "public_data_inventory_contract": _workspace_rel_or_none(public_data_inventory_path if public_data_inventory else None),
        "station_topology_contract": _workspace_rel_or_none(station_topology_path if station_topology else None),
        "station_geolocation_contract": _workspace_rel_or_none(station_geolocation_path if station_geolocation else None),
        "station_geocode_candidates_contract": _workspace_rel_or_none(station_geocode_candidates_path if station_geocode_candidates_path.exists() else None),
        "station_proxy_outlet_anchors_contract": _workspace_rel_or_none(station_proxy_outlet_anchors_path if station_proxy_outlet_anchors else None),
        "station_outlet_candidates_contract": _workspace_rel_or_none(station_outlet_candidates_path if station_outlet_candidates else None),
        "station_pre_delineation_review_contract": _workspace_rel_or_none(station_pre_delineation_review_path if station_pre_delineation_review else None),
        "station_evidence_search_plan_contract": _workspace_rel_or_none(station_evidence_search_plan_path if station_evidence_search_plan else None),
        "station_evidence_findings_contract": _workspace_rel_or_none(station_evidence_findings_path if station_evidence_findings else None),
        "control_testing_readiness_contract": _workspace_rel_or_none(control_testing_readiness_path if control_testing_readiness else None),
        "source_bundle_input": _persisted_path_or_none(source_bundle_path),
        "outlets_input": _persisted_path_or_none(outlets_source),
        "record_count": len(payload.get("records") or []),
        "manifest_updated": bool(update_manifest),
        "sqlite_import": sqlite_import,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a canonical SourceBundle into case-local contracts")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--no-manifest-update", action="store_true")
    args = parser.parse_args()
    payload = import_case_sourcebundle(args.case_id.strip(), update_manifest=not args.no_manifest_update)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
