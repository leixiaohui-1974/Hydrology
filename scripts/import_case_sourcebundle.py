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

from import_observation_csv_to_sqlite import import_observation_csv_to_sqlite  # noqa: E402


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


def _workspace_rel(path: Path) -> str:
    return path.resolve().relative_to(WORKSPACE.resolve()).as_posix()


def _workspace_rel_or_none(path: Path | None) -> str | None:
    if path is None:
        return None
    return _workspace_rel(path)


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


def _artifact_record(case_id: str, role: str, path: Path, artifact_type: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "role": role,
        "confidence": 0.8,
        "artifact": {
            "artifact_id": f"{case_id}:{role}",
            "artifact_type": artifact_type,
            "path": str(path.resolve()),
            "uri": None,
            "checksum": None,
            "metadata": metadata or {},
        },
        "evidence": [],
        "needs_review": False,
    }


def _configured_sqlite_path(cfg: dict[str, Any]) -> Path | None:
    sqlite_paths = cfg.get("sqlite_paths") or []
    if not sqlite_paths:
        return None
    raw = str(sqlite_paths[0] or "").strip()
    if not raw:
        return None
    return resolve_workspace_relpath(raw)


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

    sqlite_path = _configured_sqlite_path(cfg)
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
    existing_paths = {
        str(((record.get("artifact") or {}).get("path") or "")).strip()
        for record in records
        if isinstance(record, dict)
    }
    for raw in cfg.get("sqlite_paths", []) or []:
        path = resolve_workspace_relpath(raw)
        resolved = str(path.resolve())
        if not path.exists() or resolved in existing_paths:
            continue
        records.append(
            _artifact_record(
                case_id,
                f"sqlite_{path.stem}",
                path,
                "sqlite3",
                {"role_in_bundle": "telemetry", "source_mode": "case_config_merge"},
            )
        )
        existing_paths.add(resolved)
    return payload


def _merge_case_local_source_records(case_id: str, payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    records = payload.setdefault("records", [])
    existing_paths = {
        str(((record.get("artifact") or {}).get("path") or "")).strip()
        for record in records
        if isinstance(record, dict)
    }
    for path in _effective_scan_dirs(case_id, cfg):
        resolved = str(path.resolve())
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
        resolved = str(path.resolve())
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
        resolved = str(path.resolve())
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
    fetch_report_resolved = str(fetch_report.resolve())
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
        if path.exists():
            records.append(_artifact_record(case_id, f"sqlite_{path.stem}", path, "sqlite3", {"role_in_bundle": "telemetry"}))

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
        if out_path.exists() and not any(r.get("artifact", {}).get("path") == str(out_path.resolve()) for r in records):
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
            "raw_root": str((manifest.get("locations") or {}).get("raw_root") or ""),
            "source": "import_case_sourcebundle.py",
        },
        "schema_version": "1.0",
    }


def _build_web_source_session(case_id: str) -> dict[str, Any] | None:
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
        payload = deepcopy(_load_json(source_bundle_path))
        payload = _merge_case_local_source_records(case_id, payload, cfg)
        payload = _merge_missing_cfg_sqlite_records(case_id, payload, cfg)
        source_mode = "copied_contract"
    else:
        payload = _synthesize_bundle(case_id, manifest, cfg)
        source_mode = "synthesized"

    canonical_bundle = contracts_dir / "source_bundle.contract.json"
    write_json(canonical_bundle, payload)
    import_session_path = contracts_dir / "source_import_session.latest.json"
    web_source_session_path = contracts_dir / "web_source_session.latest.json"
    sqlite_import = _ensure_real_observation_sqlite(case_id, cfg, canonical_bundle, payload)
    payload = _merge_case_local_source_records(case_id, payload, cfg)
    payload = _merge_missing_cfg_sqlite_records(case_id, payload, cfg)
    write_json(canonical_bundle, payload)
    web_source_session = _build_web_source_session(case_id)
    if web_source_session:
        write_json(web_source_session_path, web_source_session)

    outlets_source = _first_existing(_candidate_outlets_paths(case_id, manifest, cfg))
    canonical_outlets = contracts_dir / "outlets.normalized.json"
    if outlets_source and outlets_source.is_file() and outlets_source != canonical_outlets:
        canonical_outlets.write_text(outlets_source.read_text(encoding="utf-8"), encoding="utf-8")
    elif outlets_source == canonical_outlets and canonical_outlets.exists():
        pass

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

        _dump_manifest(manifest_path, manifest)

    imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    import_session = {
        "case_id": case_id,
        "imported_at": imported_at,
        "source_mode": source_mode,
        "record_count": len(payload.get("records") or []),
        "source_bundle_contract": _workspace_rel(canonical_bundle),
        "outlets_contract": _workspace_rel(canonical_outlets) if canonical_outlets.exists() else None,
        "source_bundle_input": _workspace_rel_or_none(source_bundle_path),
        "outlets_input": _workspace_rel_or_none(outlets_source),
        "manifest_updated": bool(update_manifest),
        "sqlite_import": sqlite_import,
        "inputs": {
            "manifest_path": _workspace_rel(manifest_path),
            "latest_source_bundle_path": str((manifest.get("latest_source_bundle") or {}).get("path") or ""),
            "latest_outlets_path": str((manifest.get("latest_outlets") or {}).get("path") or ""),
            "scan_dirs": [_workspace_rel(path) for path in effective_scan_dirs],
            "web_seed_files": [_workspace_rel(path) for path in web_seed_files],
            "web_download_files": [_workspace_rel(path) for path in web_download_files],
            "web_fetch_report": _workspace_rel_or_none(web_fetch_report_path if web_fetch_report_path.exists() else None),
            "web_source_session": _workspace_rel_or_none(web_source_session_path if web_source_session else None),
            "sqlite_paths": cfg.get("sqlite_paths") or [],
            "output_dir": cfg.get("output_dir") or "",
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
        "source_bundle_input": _workspace_rel_or_none(source_bundle_path),
        "outlets_input": _workspace_rel_or_none(outlets_source),
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
