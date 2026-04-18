"""Miners for the Topology domain (D1-D4).

Handles river topology, basin topology, station-basin relationships,
and cascade arrangements.  Primary source: wxq topology JSON and SQLite.
"""
from __future__ import annotations

import fnmatch
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from ..registry import MineResult
from ..taxonomy import TYPE_CATALOG, DataType

log = logging.getLogger(__name__)

_TOPO_TYPES = [
    DataType.RIVER_TOPO,
    DataType.BASIN_TOPO,
    DataType.STATION_BASIN_REL,
    DataType.CASCADE_ARRANGEMENT,
]


def _find_at(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find_at(v, key)
            if r is not None:
                return r
    return None


class TopologyMiner:
    @property
    def handled_types(self) -> list[DataType]:
        return list(_TOPO_TYPES)

    def probe(self, path: Path, cfg: dict[str, Any]) -> list[DataType]:
        matched: list[DataType] = []
        name_lower = path.name.lower()
        ext = path.suffix.lower()
        for dt in _TOPO_TYPES:
            meta = TYPE_CATALOG[dt]
            if ext not in meta.extensions:
                continue
            if meta.filename_patterns and not any(
                fnmatch.fnmatch(name_lower, p) for p in meta.filename_patterns
            ):
                if ext == ".json":
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
            return self._extract_sqlite(path, data_type)
        if ext in (".yaml", ".yml"):
            return self._extract_yaml(path, data_type)
        return []

    # ── JSON extraction ──────────────────────────────────────────────────

    def _extract_json(self, path: Path, data_type: DataType) -> list[MineResult]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

        if data_type == DataType.RIVER_TOPO:
            return self._river_topo_from_json(path, data)
        if data_type == DataType.CASCADE_ARRANGEMENT:
            return self._cascade_from_json(path, data)
        if data_type == DataType.STATION_BASIN_REL:
            return self._station_basin_from_json(path, data)
        if data_type == DataType.BASIN_TOPO:
            return self._basin_topo_from_json(path, data)
        return []

    def _river_topo_from_json(self, path: Path, data: Any) -> list[MineResult]:
        base = _find_at(data, "baseData") or {}
        nodes = base.get("nodes") or _find_at(data, "nodes") or {}
        channels = base.get("channels") or _find_at(data, "channels") or {}
        if not isinstance(nodes, dict):
            nodes = {}
        if not isinstance(channels, dict):
            channels = {}
        if not nodes and not channels:
            return []

        node_list = []
        for name, node in nodes.items():
            node_type = node.get("nodeType")
            if "水库" in name or "reservoir" in name.lower() or "调蓄" in name:
                node_type = "reservoir"
            elif "闸" in name or "gate" in name.lower():
                node_type = "gate"
                
            node_list.append({
                "name": name,
                "nodeType": node_type,
                "x": node.get("x"),
                "y": node.get("y"),
                "zb": node.get("zb"),
            })

        channel_list = []
        for name, ch in channels.items():
            channel_list.append({
                "name": name,
                "node1": ch.get("node1"),
                "node2": ch.get("node2"),
                "manning_n": ch.get("nc"),
                "section_count": len(ch.get("sec_names", [])),
            })
            
        # Determine network_type based on project_type from cfg or heuristic
        network_type = cfg.get("project_type", "natural_river")
        if "canal" in network_type or "transfer" in network_type:
            network_type = "open_channel_transfer"

        return [MineResult(
            data_type=DataType.RIVER_TOPO,
            source_path=str(path),
            source_kind="json_topology",
            payload={
                "network_type": network_type,
                "nodes": node_list,
                "channels": channel_list,
                "node_count": len(node_list),
                "channel_count": len(channel_list),
                "data_points": len(node_list) + len(channel_list),
            },
            confidence=0.9 if channel_list else 0.5,
            label=f"河网拓扑: {len(node_list)} nodes, {len(channel_list)} channels",
        )]

    def _cascade_from_json(self, path: Path, data: Any) -> list[MineResult]:
        base = _find_at(data, "baseData") or {}
        channels = base.get("channels") or _find_at(data, "channels") or {}
        if not isinstance(channels, dict) or not channels:
            return []

        cascade: list[dict] = []
        for name, ch in channels.items():
            cascade.append({
                "channel": name,
                "upstream": ch.get("node1"),
                "downstream": ch.get("node2"),
            })

        if not cascade:
            return []

        return [MineResult(
            data_type=DataType.CASCADE_ARRANGEMENT,
            source_path=str(path),
            source_kind="json_topology",
            payload={
                "arrangement": cascade,
                "count": len(cascade),
                "data_points": len(cascade),
            },
            confidence=0.8,
            label=f"梯级排列: {len(cascade)} reaches",
        )]

    def _station_basin_from_json(self, path: Path, data: Any) -> list[MineResult]:
        nodes = _find_at(data, "nodes") or {}
        if not isinstance(nodes, dict):
            return []
        rels: list[dict] = []
        for name, node in nodes.items():
            amin = node.get("Amin")
            if amin is not None:
                rels.append({
                    "station": name,
                    "control_area_km2": amin,
                    "nodeType": node.get("nodeType"),
                })
        if not rels:
            return []
        return [MineResult(
            data_type=DataType.STATION_BASIN_REL,
            source_path=str(path),
            source_kind="json_topology",
            payload={
                "relationships": rels,
                "count": len(rels),
                "data_points": len(rels),
            },
            confidence=0.7,
            label=f"站点-流域关系: {len(rels)} entries",
        )]

    def _basin_topo_from_json(self, path: Path, data: Any) -> list[MineResult]:
        base = _find_at(data, "baseData") or {}
        channels = base.get("channels") or {}
        nodes = base.get("nodes") or _find_at(data, "nodes") or {}
        if not isinstance(channels, dict) or not channels:
            return []
        if not isinstance(nodes, dict):
            nodes = {}
        if not channels:
            return []

        basins: list[dict] = []
        for ch_name, ch in channels.items():
            n1, n2 = ch.get("node1"), ch.get("node2")
            n1_data = nodes.get(n1, {}) if n1 else {}
            n2_data = nodes.get(n2, {}) if n2 else {}
            basins.append({
                "name": ch_name,
                "upstream_node": n1,
                "downstream_node": n2,
                "upstream_area": n1_data.get("Amin"),
                "downstream_area": n2_data.get("Amin"),
            })
        return [MineResult(
            data_type=DataType.BASIN_TOPO,
            source_path=str(path),
            source_kind="json_topology",
            payload={
                "basins": basins,
                "count": len(basins),
                "data_points": len(basins),
            },
            confidence=0.7,
            label=f"流域拓扑: {len(basins)} basins",
        )]

    # ── SQLite extraction ─────────────────────────────────────────────────

    def _extract_sqlite(self, path: Path, data_type: DataType) -> list[MineResult]:
        try:
            conn = sqlite3.connect(str(path))
            tables = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        except Exception:
            return []

        results: list[MineResult] = []
        if data_type == DataType.BASIN_TOPO and "basins" in tables:
            results.extend(self._basins_from_sqlite(conn, path))
        if data_type == DataType.STATION_BASIN_REL and "basins" in tables:
            results.extend(self._rels_from_sqlite(conn, path))
        conn.close()
        return results

    def _basins_from_sqlite(
        self, conn: sqlite3.Connection, path: Path,
    ) -> list[MineResult]:
        try:
            rows = conn.execute(
                "SELECT id, name, area_km2, upstream, downstream FROM basins"
            ).fetchall()
        except Exception:
            return []
        if not rows:
            return []
        basins = [
            {"id": r[0], "name": r[1], "area_km2": r[2],
             "upstream": r[3], "downstream": r[4]}
            for r in rows
        ]
        return [MineResult(
            data_type=DataType.BASIN_TOPO,
            source_path=str(path),
            source_kind="sqlite",
            payload={
                "basins": basins,
                "count": len(basins),
                "data_points": len(basins),
            },
            confidence=0.8,
            label=f"流域拓扑(SQLite): {len(basins)} basins",
        )]

    def _rels_from_sqlite(
        self, conn: sqlite3.Connection, path: Path,
    ) -> list[MineResult]:
        try:
            rows = conn.execute(
                "SELECT id, name, area_km2, upstream, downstream FROM basins"
            ).fetchall()
        except Exception:
            return []
        if not rows:
            return []
        rels = [
            {"station": r[1], "control_area_km2": r[2],
             "upstream": r[3], "downstream": r[4]}
            for r in rows
        ]
        return [MineResult(
            data_type=DataType.STATION_BASIN_REL,
            source_path=str(path),
            source_kind="sqlite",
            payload={
                "relationships": rels,
                "count": len(rels),
                "data_points": len(rels),
            },
            confidence=0.7,
            label=f"站点-流域关系(SQLite): {len(rels)} entries",
        )]

    # ── YAML extraction ───────────────────────────────────────────────────

    def _extract_yaml(self, path: Path, data_type: DataType) -> list[MineResult]:
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        return [MineResult(
            data_type=data_type,
            source_path=str(path),
            source_kind="yaml",
            payload={**data, "data_points": len(data)},
            confidence=0.6,
            label=f"{TYPE_CATALOG[data_type].label_cn}: {path.name}",
        )]
