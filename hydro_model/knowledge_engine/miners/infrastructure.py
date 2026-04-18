"""Miners for the Infrastructure domain (B1-B5).

Handles reservoirs, hydropower stations, turbines, gates, pump/valves.
Extracts from wxq topology JSON, SQLite databases, CSV, and YAML/JSON configs.
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

_INFRA_TYPES = [
    DataType.RESERVOIR,
    DataType.HYDROPOWER_STATION,
    DataType.TURBINE,
    DataType.GATE,
    DataType.PUMP_VALVE,
]


def _find_at(obj: Any, key: str) -> Any:
    """Recursively find first dict value at *key*."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find_at(v, key)
            if r is not None:
                return r
    return None


class InfrastructureMiner:
    @property
    def handled_types(self) -> list[DataType]:
        return list(_INFRA_TYPES)

    def probe(self, path: Path, cfg: dict[str, Any]) -> list[DataType]:
        matched: list[DataType] = []
        name_lower = path.name.lower()
        ext = path.suffix.lower()
        for dt in _INFRA_TYPES:
            meta = TYPE_CATALOG[dt]
            if ext not in meta.extensions:
                continue
            if meta.filename_patterns and not any(
                fnmatch.fnmatch(name_lower, p) for p in meta.filename_patterns
            ):
                if ext == ".json" and dt in (
                    DataType.TURBINE, DataType.GATE, DataType.RESERVOIR,
                ):
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
            return self._extract_json(path, data_type)
        if ext in (".sqlite3", ".db"):
            return self._extract_sqlite(path, data_type, cfg)
        if ext in (".csv", ".xlsx"):
            return self._extract_tabular(path, data_type)
        if ext in (".yaml", ".yml"):
            return self._extract_yaml(path, data_type)
        return []

    # ── JSON extraction (wxq topology format) ────────────────────────────

    def _extract_json(self, path: Path, data_type: DataType) -> list[MineResult]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

        results: list[MineResult] = []
        if data_type == DataType.RESERVOIR:
            results.extend(self._reservoirs_from_json(path, data))
        elif data_type == DataType.HYDROPOWER_STATION:
            results.extend(self._stations_from_json(path, data))
        elif data_type == DataType.TURBINE:
            results.extend(self._turbines_from_json(path, data))
        elif data_type == DataType.GATE:
            results.extend(self._gates_from_json(path, data))
        return results

    def _reservoirs_from_json(self, path: Path, data: Any) -> list[MineResult]:
        results: list[MineResult] = []
        nodes = _find_at(data, "nodes") or {}
        if not isinstance(nodes, dict):
            return results
        for name, node in nodes.items():
            ntype = str(node.get("nodeType", "")).lower()
            if "水库" not in ntype and "reservoir" not in ntype:
                zb = node.get("zb")
                amin = node.get("Amin")
                if zb is None and amin is None:
                    continue
            results.append(MineResult(
                data_type=DataType.RESERVOIR,
                source_path=str(path),
                source_kind="json_topology",
                payload={
                    "name": name,
                    "zb": node.get("zb"),
                    "Amin": node.get("Amin"),
                    "nodeType": node.get("nodeType"),
                    "lon": node.get("x"),
                    "lat": node.get("y"),
                },
                confidence=0.7,
                label=f"水库: {name}",
            ))
        return results

    def _stations_from_json(self, path: Path, data: Any) -> list[MineResult]:
        results: list[MineResult] = []
        nodes = _find_at(data, "nodes") or {}
        if not isinstance(nodes, dict):
            return results
        for name, node in nodes.items():
            ntype = str(node.get("nodeType", ""))
            if "电站" not in ntype and "hydropower" not in ntype.lower():
                continue
            results.append(MineResult(
                data_type=DataType.HYDROPOWER_STATION,
                source_path=str(path),
                source_kind="json_topology",
                payload={
                    "name": name,
                    "nodeType": ntype,
                    "lon": node.get("x"),
                    "lat": node.get("y"),
                    "zb": node.get("zb"),
                },
                confidence=0.7,
                label=f"水电站: {name}",
            ))
        return results

    def _turbines_from_json(self, path: Path, data: Any) -> list[MineResult]:
        results: list[MineResult] = []
        ini = _find_at(data, "initialData") or {}
        turbines = ini.get("turbines") or {}
        if not isinstance(turbines, dict):
            turbines = {}
        for name, value in turbines.items():
            station = name.replace("水轮机", "").rstrip("0123456789")
            results.append(MineResult(
                data_type=DataType.TURBINE,
                source_path=str(path),
                source_kind="json_topology",
                payload={
                    "name": name,
                    "station": station,
                    "initial_value": value,
                },
                confidence=0.8,
                label=f"水轮机: {name}",
            ))
        base = _find_at(data, "baseData") or {}
        base_turbines = base.get("turbines") or {}
        if not isinstance(base_turbines, dict):
            base_turbines = {}
        for name, tdata in base_turbines.items():
            station = name.replace("水轮机", "").rstrip("0123456789")
            payload: dict[str, Any] = {"name": name, "station": station}
            if isinstance(tdata, dict):
                payload.update({
                    "qh_surface": tdata.get("QH"),
                    "power_curve": tdata.get("power"),
                    "rated_head": tdata.get("ratedHead"),
                    "rated_flow": tdata.get("ratedQ"),
                })
            results.append(MineResult(
                data_type=DataType.TURBINE,
                source_path=str(path),
                source_kind="json_topology",
                payload=payload,
                confidence=0.9 if payload.get("qh_surface") else 0.6,
                label=f"水轮机参数: {name}",
            ))
        return results

    def _gates_from_json(self, path: Path, data: Any) -> list[MineResult]:
        results: list[MineResult] = []
        ini = _find_at(data, "initialData") or {}
        ini_gates = ini.get("gates") or {}
        if not isinstance(ini_gates, dict):
            ini_gates = {}
        for name, opening in ini_gates.items():
            station = name.replace("闸", "").rstrip("0123456789")
            is_maintenance = "检修" in str(name)
            results.append(MineResult(
                data_type=DataType.GATE,
                source_path=str(path),
                source_kind="json_topology",
                payload={"name": name, "station": station, "initial_opening": opening, "is_maintenance": is_maintenance},
                confidence=0.7,
                label=f"闸门: {name}",
            ))
        base = _find_at(data, "baseData") or {}
        base_gates = base.get("gates") or {}
        if not isinstance(base_gates, dict):
            base_gates = {}
        for name, gdata in base_gates.items():
            station = name.replace("闸", "").rstrip("0123456789")
            is_maintenance = "检修" in str(name) or "检修" in str(gdata.get("name", "")) if isinstance(gdata, dict) else False
            payload: dict[str, Any] = {"name": name, "station": station, "is_maintenance": is_maintenance}
            if isinstance(gdata, dict):
                payload.update({
                    "zb": gdata.get("zb"),
                    "width_b": gdata.get("b"),
                    "c1": gdata.get("c1"), "c2": gdata.get("c2"),
                    "c3": gdata.get("c3"), "c4": gdata.get("c4"),
                    "down_zb": gdata.get("down_zb"),
                    "down_b": gdata.get("down_b"),
                    "down_m": gdata.get("down_m"),
                    "data_points": sum(1 for v in gdata.values() if v is not None),
                })
            results.append(MineResult(
                data_type=DataType.GATE,
                source_path=str(path),
                source_kind="json_topology",
                payload=payload,
                confidence=0.9 if payload.get("zb") is not None else 0.5,
                label=f"闸门参数: {name}",
            ))
        return results

    # ── SQLite extraction ─────────────────────────────────────────────────

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

        if data_type == DataType.RESERVOIR:
            results.extend(self._reservoirs_from_sqlite(conn, tables, path))
        conn.close()
        return results

    def _reservoirs_from_sqlite(
        self, conn: sqlite3.Connection, tables: list[str], path: Path,
    ) -> list[MineResult]:
        results: list[MineResult] = []
        if "stations" not in tables:
            return results
        try:
            for r in conn.execute(
                "SELECT id, name, elevation, basin_area_km2, metadata_json FROM stations"
            ).fetchall():
                meta = json.loads(r[4]) if r[4] else {}
                results.append(MineResult(
                    data_type=DataType.RESERVOIR,
                    source_path=str(path),
                    source_kind="sqlite",
                    payload={
                        "name": r[1],
                        "id": r[0],
                        "elevation": r[2],
                        "basin_area_km2": r[3],
                        "normal_pool": meta.get("normal_pool"),
                        "dead_pool": meta.get("dead_pool"),
                        "installed_capacity_mw": meta.get("installed_capacity_mw"),
                    },
                    confidence=0.8,
                    label=f"水库(SQLite): {r[1]}",
                ))
        except Exception:
            pass
        return results

    # ── Tabular extraction (CSV/XLSX) ─────────────────────────────────────

    def _extract_tabular(self, path: Path, data_type: DataType) -> list[MineResult]:
        if path.suffix.lower() != ".csv":
            return []
        results: list[MineResult] = []
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            reader = csv.DictReader(text.splitlines())
            fields = reader.fieldnames or []
        except Exception:
            return results

        name_keys = [k for k in fields if any(w in k.lower() for w in ["name", "名", "站"])]
        if not name_keys:
            return results

        for row_idx, row in enumerate(reader, start=2):
            name = row.get(name_keys[0], "").strip()
            if not name:
                continue
            payload: dict[str, Any] = {"name": name}
            if data_type == DataType.GATE:
                payload["is_maintenance"] = "检修" in str(name)
            for k, v in row.items():
                if v and v.strip():
                    payload[k] = v.strip()
            results.append(MineResult(
                data_type=data_type,
                source_path=str(path),
                source_kind="csv",
                payload=payload,
                confidence=0.5,
                label=f"{TYPE_CATALOG[data_type].label_cn}: {name}",
            ))
        return results

    # ── YAML extraction ───────────────────────────────────────────────────

    def _extract_yaml(self, path: Path, data_type: DataType) -> list[MineResult]:
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        results: list[MineResult] = []
        items = data if isinstance(next(iter(data.values()), None), dict) else {"_root": data}
        for key, val in items.items():
            if not isinstance(val, dict):
                continue
            name = val.get("name", key)
            payload = {**val, "name": name}
            if data_type == DataType.GATE:
                payload.setdefault("is_maintenance", "检修" in str(name))
            results.append(MineResult(
                data_type=data_type,
                source_path=str(path),
                source_kind="yaml",
                payload=payload,
                confidence=0.7,
                label=f"{TYPE_CATALOG[data_type].label_cn}: {name}",
            ))
        return results
