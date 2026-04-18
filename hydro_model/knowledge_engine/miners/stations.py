"""Miners for the Stations domain (C1-C4).

Handles hydro stations, rainfall stations, evaporation stations,
and station control areas.  Extracts from JSON topology, SQLite, CSV.
"""
from __future__ import annotations

import csv
import fnmatch
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from ..registry import MineResult
from ..taxonomy import TYPE_CATALOG, DataType

log = logging.getLogger(__name__)

_STATION_TYPES = [
    DataType.HYDRO_STATION,
    DataType.RAINFALL_STATION,
    DataType.EVAP_STATION,
    DataType.STATION_CONTROL_AREA,
]


def _decimal_digits(value: float) -> int:
    s = f"{value:.15f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def _find_at(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find_at(v, key)
            if r is not None:
                return r
    return None


class StationsMiner:
    @property
    def handled_types(self) -> list[DataType]:
        return list(_STATION_TYPES)

    def probe(self, path: Path, cfg: dict[str, Any]) -> list[DataType]:
        matched: list[DataType] = []
        name_lower = path.name.lower()
        ext = path.suffix.lower()
        for dt in _STATION_TYPES:
            meta = TYPE_CATALOG[dt]
            if ext not in meta.extensions:
                continue
            if meta.filename_patterns and not any(
                fnmatch.fnmatch(name_lower, p) for p in meta.filename_patterns
            ):
                if ext == ".json":
                    matched.append(dt)
                    continue
                if ext in (".sqlite3", ".db"):
                    matched.append(dt)
                    continue
                continue
            matched.append(dt)
        return matched

    def extract(
        self, path: Path, data_type: DataType, cfg: dict[str, Any],
    ) -> list[MineResult]:
        ext = path.suffix.lower()
        if ext == ".json":
            return self._extract_json(path, data_type, cfg)
        if ext in (".sqlite3", ".db"):
            return self._extract_sqlite(path, data_type, cfg)
        if ext == ".csv":
            return self._extract_csv(path, data_type, cfg)
        return []

    # ── JSON (wxq topology) ──────────────────────────────────────────────

    def _extract_json(
        self, path: Path, data_type: DataType, cfg: dict[str, Any],
    ) -> list[MineResult]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

        nodes = _find_at(data, "nodes") or {}
        if not isinstance(nodes, dict):
            return []
        targets = cfg.get("target_stations", [])
        results: list[MineResult] = []

        for name, node in nodes.items():
            x, y = node.get("x"), node.get("y")
            if x is None or y is None:
                continue
            lat, lon = float(y), float(x)

            if data_type == DataType.HYDRO_STATION:
                precision = min(_decimal_digits(lat), _decimal_digits(lon))
                results.append(MineResult(
                    data_type=DataType.HYDRO_STATION,
                    source_path=str(path),
                    source_kind="json_topology",
                    payload={
                        "name": name,
                        "lat": lat, "lon": lon,
                        "precision": precision,
                        "zb": node.get("zb"),
                        "Amin": node.get("Amin"),
                        "nodeType": node.get("nodeType"),
                    },
                    confidence=0.8 if name in targets else 0.5,
                    label=f"水文站: {name}",
                ))
            elif data_type == DataType.STATION_CONTROL_AREA:
                amin = node.get("Amin")
                if amin is not None:
                    results.append(MineResult(
                        data_type=DataType.STATION_CONTROL_AREA,
                        source_path=str(path),
                        source_kind="json_topology",
                        payload={
                            "name": name,
                            "control_area_km2": amin,
                            "lon": lon, "lat": lat,
                        },
                        confidence=0.8,
                        label=f"控制面积: {name} = {amin} km²",
                    ))
        return results

    # ── SQLite ───────────────────────────────────────────────────────────

    def _extract_sqlite(
        self, path: Path, data_type: DataType, cfg: dict[str, Any],
    ) -> list[MineResult]:
        results: list[MineResult] = []
        try:
            conn = sqlite3.connect(str(path))
            tables = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        except Exception:
            return results

        if data_type in (DataType.HYDRO_STATION, DataType.RAINFALL_STATION):
            results.extend(self._stations_from_sqlite(conn, tables, path, data_type))
        if data_type == DataType.STATION_CONTROL_AREA:
            results.extend(self._areas_from_sqlite(conn, tables, path))
        conn.close()
        return results

    def _stations_from_sqlite(
        self, conn: sqlite3.Connection, tables: list[str],
        path: Path, data_type: DataType,
    ) -> list[MineResult]:
        results: list[MineResult] = []
        if "stations" not in tables:
            return results
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(stations)").fetchall()]
            rows = conn.execute("SELECT * FROM stations").fetchall()
        except Exception:
            return results

        cols_lower = [c.lower() for c in cols]
        name_idx = next((i for i, c in enumerate(cols_lower)
                         if any(w in c for w in ["name", "名"])), None)
        lat_idx = next((i for i, c in enumerate(cols_lower)
                        if "lat" in c or "纬" in c), None)
        lon_idx = next((i for i, c in enumerate(cols_lower)
                        if "lon" in c or "经" in c), None)

        for row in rows:
            name = str(row[name_idx]).strip() if name_idx is not None else None
            if not name:
                continue
            payload: dict[str, Any] = {"name": name}
            if lat_idx is not None and lon_idx is not None:
                try:
                    payload["lat"] = float(row[lat_idx])
                    payload["lon"] = float(row[lon_idx])
                    payload["precision"] = min(
                        _decimal_digits(payload["lat"]),
                        _decimal_digits(payload["lon"]),
                    )
                except (ValueError, TypeError):
                    pass
            for i, col in enumerate(cols):
                if i not in (name_idx, lat_idx, lon_idx) and row[i] is not None:
                    payload[col] = row[i]
            results.append(MineResult(
                data_type=data_type,
                source_path=str(path),
                source_kind="sqlite",
                payload=payload,
                confidence=0.8 if payload.get("lat") else 0.5,
                label=f"{TYPE_CATALOG[data_type].label_cn}: {name}",
            ))
        return results

    def _areas_from_sqlite(
        self, conn: sqlite3.Connection, tables: list[str], path: Path,
    ) -> list[MineResult]:
        results: list[MineResult] = []
        if "basins" not in tables:
            return results
        try:
            for row in conn.execute(
                "SELECT id, name, area_km2, upstream, downstream FROM basins"
            ).fetchall():
                results.append(MineResult(
                    data_type=DataType.STATION_CONTROL_AREA,
                    source_path=str(path),
                    source_kind="sqlite",
                    payload={
                        "name": row[1],
                        "id": row[0],
                        "control_area_km2": row[2],
                        "upstream": row[3],
                        "downstream": row[4],
                    },
                    confidence=0.8,
                    label=f"控制面积: {row[1]}",
                ))
        except Exception:
            pass
        return results

    # ── CSV ───────────────────────────────────────────────────────────────

    def _extract_csv(
        self, path: Path, data_type: DataType, cfg: dict[str, Any],
    ) -> list[MineResult]:
        results: list[MineResult] = []
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            reader = csv.DictReader(text.splitlines())
            fields = reader.fieldnames or []
        except Exception:
            return results

        name_keys = [k for k in fields if any(w in k.lower() for w in ["name", "名", "站"])]
        lat_keys = [k for k in fields if any(w in k.lower() for w in ["lat", "纬"])]
        lon_keys = [k for k in fields if any(w in k.lower() for w in ["lon", "经"])]
        if not name_keys:
            return results

        for row_idx, row in enumerate(reader, start=2):
            name = row.get(name_keys[0], "").strip()
            if not name:
                continue
            payload: dict[str, Any] = {"name": name}
            if lat_keys and lon_keys:
                try:
                    payload["lat"] = float(row[lat_keys[0]])
                    payload["lon"] = float(row[lon_keys[0]])
                    payload["precision"] = min(
                        _decimal_digits(payload["lat"]),
                        _decimal_digits(payload["lon"]),
                    )
                except (ValueError, KeyError):
                    pass
            for k, v in row.items():
                if k not in (name_keys[0],) and v and v.strip():
                    payload[k] = v.strip()
            results.append(MineResult(
                data_type=data_type,
                source_path=str(path),
                source_kind="csv",
                payload=payload,
                confidence=0.6 if payload.get("lat") else 0.4,
                label=f"{TYPE_CATALOG[data_type].label_cn}: {name}",
            ))
        return results
