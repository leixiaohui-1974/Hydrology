#!/usr/bin/env python3
"""Import canonical observation CSV into a minimal HydroMind SQLite database."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
HYDROLOGY = WORKSPACE / "Hydrology"

if str(HYDROLOGY) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY))

from workflows._shared import load_case_config  # noqa: E402

LONG_CSV_REQUIRED_ANY = [("time", "timestamp"), ("station_id", "station_name", "name"), ("variable",), ("value",)]
TIME_COLUMN_ALIASES = ("time", "timestamp", "datetime", "date")
STATION_META_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "station_id": ("station_id", "测站编码", "站点编码", "station_code", "code"),
    "station_name": ("station_name", "测站名称", "站点名称", "name"),
    "station_type": ("station_type", "测站类型", "站点类型", "type"),
    "lat": ("lat", "latitude", "纬度"),
    "lon": ("lon", "longitude", "经度"),
    "elevation": ("elevation", "elev", "高程"),
    "basin_area_km2": ("basin_area_km2", "流域面积_km2", "流域面积", "basin_area"),
}
STATION_HEADER_PATTERN = re.compile(r"^(?P<station_name>.*?)(?:\((?P<station_id>[^()]+)\))?$")
BATCH_SIZE = 10_000


@dataclass
class StationRecord:
    station_id: str
    name: str
    station_type: str
    lat: float | None
    lon: float | None
    elevation: float | None
    basin_area_km2: float | None
    source: str
    metadata_json: str


@dataclass
class ImportStats:
    stations: dict[str, StationRecord]
    grouped: dict[tuple[str, str, str], dict[str, Any]]
    timeseries_rows: int
    source_paths: list[str]
    mode: str
    source_bundle_path: str | None = None
    station_meta_path: str | None = None


def _parse_float(raw: str | None) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(raw: str | None, default: int = 1) -> int:
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def _infer_unit(variable: str) -> str:
    upper = variable.upper()
    if upper.startswith("Q"):
        return "m3/s"
    if upper.startswith("H") or upper == "Z":
        return "m"
    return ""


def _source_text(path: Path) -> str:
    return path.relative_to(WORKSPACE).as_posix() if path.is_relative_to(WORKSPACE) else str(path)


def _pick_first(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    for key in aliases:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _parse_station_header(header: str) -> tuple[str, str]:
    text = str(header or "").strip()
    if not text:
        return "", ""
    match = STATION_HEADER_PATTERN.match(text)
    if not match:
        return text, text
    station_name = str(match.group("station_name") or "").strip()
    station_id = str(match.group("station_id") or "").strip()
    if not station_name and station_id:
        station_name = station_id
    if not station_id:
        station_id = station_name
    return station_id, station_name


def _looks_like_long_csv(headers: list[str] | None) -> bool:
    header_set = set(headers or [])
    return all(any(key in header_set for key in group) for group in LONG_CSV_REQUIRED_ANY)


def _flush_timeseries_batch(conn: sqlite3.Connection, batch: list[tuple[Any, ...]]) -> None:
    if not batch:
        return
    for row in batch:
        station_id, station_name, variable, time_value, value = row
        normalized_variable = str(variable).strip().lower()
        z_val = value if normalized_variable in {"z", "water_level"} else None
        q_val = value if normalized_variable in {"q", "flow"} else None
        conn.execute(
            """
            INSERT INTO observations (name, station, time, Z, Q)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(station, time) DO UPDATE SET
                Z = COALESCE(EXCLUDED.Z, observations.Z),
                Q = COALESCE(EXCLUDED.Q, observations.Q),
                name = COALESCE(EXCLUDED.name, observations.name)
            """,
            (station_name, station_id, time_value, z_val, q_val)
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO timeseries (station_id, variable, time, value)
            VALUES (?, ?, ?, ?)
            """,
            (station_id, variable, time_value, value),
        )
    batch.clear()


def _update_grouped_meta(
    grouped: dict[tuple[str, str, str], dict[str, Any]],
    *,
    station_id: str,
    variable: str,
    time_step: str,
    unit: str,
    source: str,
    time_value: str,
) -> None:
    meta = grouped[(station_id, variable, time_step)]
    meta.setdefault("unit", unit)
    meta.setdefault("source", source)
    meta["count"] = meta.get("count", 0) + 1
    meta["start_time"] = min(meta.get("start_time", time_value), time_value)
    meta["end_time"] = max(meta.get("end_time", time_value), time_value)


def _case_station_context(cfg: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    reservoirs = cfg.get("knowledge", {}).get("reservoirs", {})
    if isinstance(reservoirs, dict):
        for station_id, payload in reservoirs.items():
            if not isinstance(payload, dict):
                continue
            entry = dict(payload)
            entry["station_id"] = station_id
            by_id[station_id] = entry
            name = str(payload.get("name") or "").strip()
            if name:
                by_name[name] = entry
    nodes = cfg.get("knowledge", {}).get("topology", {}).get("nodes", {})
    if isinstance(nodes, dict):
        for name, payload in nodes.items():
            if not isinstance(payload, dict):
                continue
            node_entry = {
                "name": name,
                "lat": payload.get("y"),
                "lon": payload.get("x"),
                "elevation": payload.get("zb"),
                "node_type": payload.get("type_label"),
            }
            by_name.setdefault(name, {}).update({k: v for k, v in node_entry.items() if v is not None})
    return by_id, by_name


def _default_sqlite_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "ingest" / f"{case_id}_hydromind.sqlite3"


def _default_source_bundle_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / "source_bundle.contract.json"


def _resolve_bundle_observation_files(case_id: str, source_bundle_path: str | Path | None, roles_spec: dict) -> tuple[Path, dict[str, Path]]:
    bundle_file = Path(source_bundle_path) if source_bundle_path else _default_source_bundle_path(case_id)
    if not bundle_file.is_absolute():
        bundle_file = (WORKSPACE / bundle_file).resolve()
    if not bundle_file.exists():
        raise FileNotFoundError(f"source bundle not found: {bundle_file}")

    payload = json.loads(bundle_file.read_text(encoding="utf-8"))
    observation_files: dict[str, Path] = {}
    for record in payload.get("records", []) or []:
        if not isinstance(record, dict):
            continue
        role = str(record.get("role") or "").strip()
        artifact = record.get("artifact") or {}
        raw_path = artifact.get("path")
        if not role or not raw_path:
            continue
        if role not in roles_spec and role != "observed_station_meta":
            continue
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = (WORKSPACE / path).resolve()
        observation_files[role] = path

    required_roles = set(roles_spec) | {"observed_station_meta"}
    missing = sorted(role for role in required_roles if role not in observation_files)
    if missing:
        raise ValueError(f"source bundle missing required observation roles: {', '.join(missing)}")
    for role in sorted(required_roles):
        if not observation_files[role].exists():
            raise FileNotFoundError(f"{role} csv not found: {observation_files[role]}")
    return bundle_file, observation_files


def _resolve_station_row(
    row: dict[str, str],
    by_id: dict[str, dict[str, Any]],
    by_name: dict[str, dict[str, Any]],
    csv_source: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    station_id = str(row.get("station_id") or "").strip()
    station_name = str(row.get("station_name") or row.get("name") or "").strip()
    ctx = by_id.get(station_id, {}) if station_id else {}
    if not station_id and station_name and station_name in by_name:
        station_id = str(by_name[station_name].get("station_id") or "").strip()
        ctx = by_name[station_name]
    if not station_id:
        station_id = station_name
    if not station_name:
        station_name = str(ctx.get("name") or station_id)
    if not station_id:
        raise ValueError("row missing station_id/station_name")

    station_type = str(
        row.get("station_type")
        or ctx.get("station_type")
        or ctx.get("node_type")
        or "observation_station"
    ).strip()
    lat = _parse_float(row.get("lat")) or _parse_float(str(ctx.get("lat") or ""))
    lon = _parse_float(row.get("lon")) or _parse_float(str(ctx.get("lon") or ""))
    elevation = _parse_float(row.get("elevation")) or _parse_float(str(ctx.get("elevation") or ""))
    basin_area = _parse_float(row.get("basin_area_km2")) or _parse_float(str(ctx.get("basin_area_km2") or ""))

    metadata = {
        "csv_source": csv_source,
        "station_name": station_name,
    }
    for key in ("normal_pool_m", "dead_pool_m", "installed_capacity_mw", "node_type"):
        if ctx.get(key) is not None:
            metadata[key] = ctx.get(key)

    station = {
        "station_id": station_id,
        "name": station_name,
        "station_type": station_type,
        "lat": lat,
        "lon": lon,
        "elevation": elevation,
        "basin_area_km2": basin_area,
        "source": csv_source,
        "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    }
    return station, metadata


def _load_station_meta_records(
    case_id: str,
    station_meta_path: Path,
    by_id: dict[str, dict[str, Any]],
    by_name: dict[str, dict[str, Any]],
) -> tuple[dict[str, StationRecord], dict[str, StationRecord]]:
    csv_source = _source_text(station_meta_path)
    stations_by_id: dict[str, StationRecord] = {}
    stations_by_name: dict[str, StationRecord] = {}

    with station_meta_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            station_id = _pick_first(raw, STATION_META_FIELD_ALIASES["station_id"])
            station_name = _pick_first(raw, STATION_META_FIELD_ALIASES["station_name"])
            if not station_id and not station_name:
                continue

            station_row, metadata = _resolve_station_row(
                {
                    "station_id": station_id,
                    "station_name": station_name,
                    "station_type": _pick_first(raw, STATION_META_FIELD_ALIASES["station_type"]),
                    "lat": _pick_first(raw, STATION_META_FIELD_ALIASES["lat"]),
                    "lon": _pick_first(raw, STATION_META_FIELD_ALIASES["lon"]),
                    "elevation": _pick_first(raw, STATION_META_FIELD_ALIASES["elevation"]),
                    "basin_area_km2": _pick_first(raw, STATION_META_FIELD_ALIASES["basin_area_km2"]),
                },
                by_id,
                by_name,
                csv_source,
            )
            extras = {str(key): value for key, value in raw.items() if str(value or "").strip()}
            metadata["station_meta"] = extras
            station_row["metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            station = StationRecord(**station_row)
            stations_by_id[station.station_id] = station
            if station.name:
                stations_by_name[station.name] = station
    return stations_by_id, stations_by_name


def _import_long_csv(conn: sqlite3.Connection, case_id: str, csv_path: Path, roles_spec: dict) -> ImportStats:
    cfg = load_case_config(case_id)
    by_id, by_name = _case_station_context(cfg)
    csv_source = _source_text(csv_path)
    grouped: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(dict)
    stations: dict[str, StationRecord] = {}
    batch: list[tuple[Any, ...]] = []
    row_count = 0

    var_map = {}
    for role, spec in roles_spec.items():
        var = spec.get("variable")
        if var:
            var_map[role] = var
            var_map[var] = var

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        if not _looks_like_long_csv(headers):
            raise ValueError(f"CSV format unsupported for canonical long import: {csv_path}")
        header_set = set(headers)
        for group in LONG_CSV_REQUIRED_ANY:
            if not any(key in header_set for key in group):
                raise ValueError(f"CSV missing required columns from {group}")

        for raw in reader:
            time_value = str(raw.get("time") or raw.get("timestamp") or "").strip()
            raw_var = str(raw.get("variable") or "").strip()
            variable = var_map.get(raw_var, raw_var)
            value = _parse_float(raw.get("value"))
            if not time_value or not variable or value is None:
                continue

            station_row, _metadata = _resolve_station_row(raw, by_id, by_name, csv_source)
            unit = str(raw.get("unit") or _infer_unit(variable)).strip()
            time_step = str(raw.get("time_step") or "1H").strip()
            quality = _parse_int(raw.get("quality"), default=1)

            source = str(raw.get("source") or csv_source).strip()
            batch.append((station_row["station_id"], station_row["name"], variable, time_value, value))
            row_count += 1
            _update_grouped_meta(
                grouped,
                station_id=station_row["station_id"],
                variable=variable,
                time_step=time_step,
                unit=unit,
                source=source,
                time_value=time_value,
            )
            stations[station_row["station_id"]] = StationRecord(**station_row)
            if len(batch) >= BATCH_SIZE:
                _flush_timeseries_batch(conn, batch)

    _flush_timeseries_batch(conn, batch)
    if not row_count:
        raise ValueError(f"no usable observation rows found in {csv_path}")
    return ImportStats(
        stations=stations,
        grouped=grouped,
        timeseries_rows=row_count,
        source_paths=[csv_source],
        mode="canonical_csv",
    )


def _import_real_observation_bundle(
    conn: sqlite3.Connection,
    case_id: str,
    bundle_file: Path,
    observation_files: dict[str, Path],
    roles_spec: dict
) -> ImportStats:
    cfg = load_case_config(case_id)
    by_id, by_name = _case_station_context(cfg)
    station_meta_file = observation_files["observed_station_meta"]
    stations_by_id, stations_by_name = _load_station_meta_records(case_id, station_meta_file, by_id, by_name)
    stations: dict[str, StationRecord] = dict(stations_by_id)
    grouped: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(dict)
    batch: list[tuple[Any, ...]] = []
    row_count = 0
    source_paths = [_source_text(observation_files[role]) for role in sorted(roles_spec)]

    for role, spec in roles_spec.items():
        csv_path = observation_files[role]
        csv_source = _source_text(csv_path)
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = list(reader.fieldnames or [])
            time_key = next((key for key in TIME_COLUMN_ALIASES if key in headers), "")
            if not time_key:
                raise ValueError(f"wide observation csv missing time column: {csv_path}")

            column_station_ids: list[tuple[str, str]] = []
            for header in headers:
                if header == time_key:
                    continue
                station_id, station_name = _parse_station_header(header)
                if not station_id and not station_name:
                    continue
                station = stations_by_id.get(station_id) or stations_by_name.get(station_name)
                if station is None:
                    station_row, metadata = _resolve_station_row(
                        {"station_id": station_id, "station_name": station_name},
                        by_id,
                        by_name,
                        _source_text(station_meta_file),
                    )
                    metadata["station_meta_missing"] = True
                    metadata["header_name"] = header
                    station_row["metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                    station = StationRecord(**station_row)
                stations[station.station_id] = station
                if station.name:
                    stations_by_name[station.name] = station
                stations_by_id[station.station_id] = station
                column_station_ids.append((header, station.station_id))

            for raw in reader:
                time_value = str(raw.get(time_key) or "").strip()
                if not time_value:
                    continue
                for header, station_id in column_station_ids:
                    value = _parse_float(raw.get(header))
                    if value is None:
                        continue
                    batch.append(
                        (
                            station_id,
                            stations_by_id[station_id].name,
                            spec.get("variable", role),
                            time_value,
                            value,
                        )
                    )
                    row_count += 1
                    _update_grouped_meta(
                        grouped,
                        station_id=station_id,
                        variable=spec.get("variable", role),
                        time_step=spec.get("time_step", "1min"),
                        unit=spec.get("unit", ""),
                        source=csv_source,
                        time_value=time_value,
                    )
                    if len(batch) >= BATCH_SIZE:
                        _flush_timeseries_batch(conn, batch)

    _flush_timeseries_batch(conn, batch)
    if not row_count:
        raise ValueError(f"no usable observation rows found in bundle: {bundle_file}")
    return ImportStats(
        stations=stations,
        grouped=grouped,
        timeseries_rows=row_count,
        source_paths=source_paths,
        mode="real_observation_bundle",
        source_bundle_path=_source_text(bundle_file),
        station_meta_path=_source_text(station_meta_file),
    )


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS stations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            station_type TEXT,
            lat REAL,
            lon REAL,
            elevation REAL,
            basin_area_km2 REAL,
            source TEXT,
            metadata_json TEXT
        );
        CREATE TABLE IF NOT EXISTS observations (
            name TEXT,
            station TEXT NOT NULL,
            time TEXT NOT NULL,
            Z REAL,
            Q REAL,
            PRIMARY KEY (station, time)
        );
        CREATE INDEX IF NOT EXISTS idx_observations_time ON observations(time);
        CREATE TABLE IF NOT EXISTS timeseries (
            station_id TEXT NOT NULL,
            variable TEXT NOT NULL,
            time TEXT NOT NULL,
            value REAL,
            PRIMARY KEY (station_id, variable, time)
        );
        CREATE INDEX IF NOT EXISTS idx_timeseries_time ON timeseries(time);
        CREATE TABLE IF NOT EXISTS timeseries_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id TEXT NOT NULL,
            variable TEXT NOT NULL,
            unit TEXT,
            time_step TEXT,
            start_time TEXT,
            end_time TEXT,
            n_records INTEGER,
            source TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_timeseries_meta_unique
            ON timeseries_meta(station_id, variable, time_step);
        CREATE TABLE IF NOT EXISTS basins (
            id TEXT PRIMARY KEY,
            name TEXT,
            area_km2 REAL,
            outlet_station_id TEXT,
            source TEXT,
            metadata_json TEXT
        );
        CREATE TABLE IF NOT EXISTS curves (
            station_id TEXT NOT NULL,
            curve_type TEXT NOT NULL,
            x REAL,
            y REAL,
            PRIMARY KEY (station_id, curve_type, x)
        );
        CREATE TABLE IF NOT EXISTS station_operation (
            station_id TEXT NOT NULL,
            time TEXT NOT NULL,
            gate_opening REAL,
            unit_output REAL,
            discharge REAL,
            mode TEXT,
            target_level REAL,
            actual_level REAL,
            notes TEXT,
            quality INTEGER,
            PRIMARY KEY (station_id, time)
        );
        """
    )


def import_observation_csv_to_sqlite(
    case_id: str,
    csv_path: str | Path | None = None,
    sqlite_path: str | Path | None = None,
    *,
    replace: bool = False,
    source_bundle_path: str | Path | None = None,
) -> dict[str, Any]:
    cfg = load_case_config(case_id)
    scada_cfg = cfg.get("knowledge", {}).get("scada_timeseries", {})
    roles_spec = scada_cfg.get("csv_extraction_rules", {
        "observed_flow": {"variable": "flow", "unit": "m3/s", "time_step": "1min"},
        "observed_water_level": {"variable": "water_level", "unit": "m", "time_step": "1min"},
        "observed_velocity": {"variable": "velocity", "unit": "m/s", "time_step": "1min"},
    })

    db_file = Path(sqlite_path) if sqlite_path else _default_sqlite_path(case_id)
    if not db_file.is_absolute():
        db_file = (WORKSPACE / db_file).resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if replace and db_file.exists():
        db_file.unlink()

    conn = sqlite3.connect(str(db_file))
    try:
        _init_db(conn)
        if csv_path:
            csv_file = Path(csv_path)
            if not csv_file.is_absolute():
                csv_file = (WORKSPACE / csv_file).resolve()
            if not csv_file.exists():
                raise FileNotFoundError(f"csv not found: {csv_file}")
            stats = _import_long_csv(conn, case_id, csv_file, roles_spec)
        else:
            bundle_file, observation_files = _resolve_bundle_observation_files(case_id, source_bundle_path, roles_spec)
            stats = _import_real_observation_bundle(conn, case_id, bundle_file, observation_files, roles_spec)

        conn.executemany(
            """
            INSERT OR REPLACE INTO stations
            (id, name, station_type, lat, lon, elevation, basin_area_km2, source, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    station.station_id,
                    station.name,
                    station.station_type,
                    station.lat,
                    station.lon,
                    station.elevation,
                    station.basin_area_km2,
                    station.source,
                    station.metadata_json,
                )
                for station in stats.stations.values()
            ],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO timeseries_meta
            (station_id, variable, unit, time_step, start_time, end_time, n_records, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    station_id,
                    variable,
                    payload.get("unit"),
                    time_step,
                    payload.get("start_time"),
                    payload.get("end_time"),
                    payload.get("count"),
                    payload.get("source"),
                )
                for (station_id, variable, time_step), payload in sorted(stats.grouped.items())
            ],
        )
        conn.commit()
    finally:
        conn.close()

    rel_db = _source_text(db_file)
    result = {
        "ok": True,
        "case_id": case_id,
        "mode": stats.mode,
        "sqlite_path": rel_db,
        "station_count": len(stats.stations),
        "timeseries_rows": stats.timeseries_rows,
        "timeseries_meta_rows": len(stats.grouped),
        "source_paths": stats.source_paths,
    }
    if csv_path:
        result["csv_path"] = stats.source_paths[0]
    else:
        result["source_bundle_path"] = stats.source_bundle_path
        result["station_meta_path"] = stats.station_meta_path
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Import observation CSV into a minimal HydroMind SQLite")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--csv-path", default=None)
    parser.add_argument("--source-bundle-path", default=None)
    parser.add_argument("--sqlite-path", default=None)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    result = import_observation_csv_to_sqlite(
        args.case_id.strip(),
        args.csv_path,
        sqlite_path=args.sqlite_path,
        replace=args.replace,
        source_bundle_path=args.source_bundle_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
