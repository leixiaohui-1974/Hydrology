#!/usr/bin/env python3
"""Lightweight SCADA replay engine with unified message contract."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]


def _station_operation_column_set(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute("PRAGMA table_info(station_operation)")
    return {str(r[1]) for r in cur.fetchall()}


def _station_operation_metric_exprs(cols: set[str]) -> tuple[str, str, str, str]:
    """Build SELECT fragments for hydrology vs hydromind station_operation layouts."""
    h_up = "so.H_up" if "H_up" in cols else ("so.actual_level" if "actual_level" in cols else "NULL")
    h_down = "so.H_down" if "H_down" in cols else ("so.target_level" if "target_level" in cols else "NULL")
    q_in = "so.Q_in" if "Q_in" in cols else ("so.unit_output" if "unit_output" in cols else "NULL")
    q_out = "so.Q_out" if "Q_out" in cols else ("so.discharge" if "discharge" in cols else "NULL")
    return h_up, h_down, q_in, q_out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReplayConfig:
    case_id: str
    sqlite_path: Path
    scenario_id: str
    replay_speed: float
    quality_code: str
    max_events: int
    query_start: str | None = None
    query_end: str | None = None
    replay_dt_seconds: float | None = None


class ScadaReplayEngine:
    """Replay historical station_operation records into SCADA message contract."""

    def __init__(self, cfg: ReplayConfig) -> None:
        self.cfg = cfg
        self.run_id = f"{cfg.case_id}-replay-{uuid.uuid4().hex[:8]}"

    def _query_rows(self) -> list[dict[str, Any]]:
        if not self.cfg.sqlite_path.exists():
            raise FileNotFoundError(f"sqlite not found: {self.cfg.sqlite_path}")

        with sqlite3.connect(self.cfg.sqlite_path) as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {str(r[0]) for r in cur.fetchall()}

            if "observations" in tables:
                rows = self._query_observations_table(conn)
                if rows:
                    return rows
            if "station_operation" in tables:
                rows = self._query_station_operation_table(conn)
                if rows:
                    return rows
            if "timeseries" in tables:
                rows = self._query_timeseries_table(conn)
                if rows:
                    return rows

        raise RuntimeError(
            "no replayable rows: tried observations (if present), station_operation, then timeseries"
        )

    def _query_observations_table(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        where = ["time IS NOT NULL"]
        params: list[Any] = []
        if self.cfg.query_start:
            where.append("CASE WHEN typeof(time)='real' THEN datetime(time, 'unixepoch') ELSE datetime(time) END >= datetime(?)")
            params.append(self.cfg.query_start)
        if self.cfg.query_end:
            where.append("CASE WHEN typeof(time)='real' THEN datetime(time, 'unixepoch') ELSE datetime(time) END < datetime(?)")
            params.append(self.cfg.query_end)
        where_sql = " AND ".join(where)
        sql_text = f"""
            SELECT
                CASE WHEN typeof(time)='real' THEN datetime(time, 'unixepoch') ELSE datetime(time) END AS ts_event,
                station AS station_id,
                COALESCE(name, station) AS station_name,
                Z,
                Q
            FROM observations
            WHERE {where_sql}
            ORDER BY ts_event, station
            LIMIT ?
        """
        params.append(int(self.cfg.max_events))
        cur = conn.execute(sql_text, params)
        frame = cur.fetchall()
        cols = [col[0] for col in cur.description]
        rows = [dict(zip(cols, row)) for row in frame]
        return rows

    def _query_station_operation_table(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        where = ["so.time IS NOT NULL"]
        params: list[Any] = []
        if self.cfg.query_start:
            where.append("datetime(so.time) >= datetime(?)")
            params.append(self.cfg.query_start)
        if self.cfg.query_end:
            where.append("datetime(so.time) < datetime(?)")
            params.append(self.cfg.query_end)
        where_sql = " AND ".join(where)
        colset = _station_operation_column_set(conn)
        ex_h_up, ex_h_down, ex_q_in, ex_q_out = _station_operation_metric_exprs(colset)
        sql_text = f"""
            SELECT
                so.time AS ts_event,
                so.station_id,
                COALESCE(st.name, so.station_id) AS station_name,
                {ex_h_up} AS H_up,
                {ex_h_down} AS H_down,
                {ex_q_in} AS Q_in,
                {ex_q_out} AS Q_out
            FROM station_operation AS so
            LEFT JOIN stations AS st
              ON st.id = so.station_id
            WHERE {where_sql}
            ORDER BY datetime(so.time), so.station_id
            LIMIT ?
        """
        params.append(int(self.cfg.max_events))
        cur = conn.execute(sql_text, params)
        frame = cur.fetchall()
        cols = [col[0] for col in cur.description]
        rows = [dict(zip(cols, row)) for row in frame]
        return rows

    def _query_timeseries_table(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        where = ["ts.time IS NOT NULL", "ts.value IS NOT NULL"]
        params: list[Any] = []
        if self.cfg.query_start:
            where.append("datetime(ts.time) >= datetime(?)")
            params.append(self.cfg.query_start)
        if self.cfg.query_end:
            where.append("datetime(ts.time) < datetime(?)")
            params.append(self.cfg.query_end)
        where_sql = " AND ".join(where)
        sql_text = f"""
            SELECT
                ts.time AS ts_event,
                ts.station_id,
                COALESCE(st.name, ts.station_id) AS station_name,
                ts.variable AS replay_var,
                ts.value AS replay_value
            FROM timeseries AS ts
            LEFT JOIN stations AS st
              ON st.id = ts.station_id
            WHERE {where_sql}
            ORDER BY datetime(ts.time), ts.station_id, ts.variable
            LIMIT ?
        """
        params.append(int(self.cfg.max_events))
        cur = conn.execute(sql_text, params)
        frame = cur.fetchall()
        cols = [col[0] for col in cur.description]
        return [dict(zip(cols, row)) for row in frame]

    def _build_messages(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for row in rows:
            rv = row.get("replay_var")
            rvl = row.get("replay_value")
            if rv is not None and rvl is not None:
                try:
                    fv = float(rvl)
                except (TypeError, ValueError):
                    continue
                messages.append(
                    {
                        "ts_event": str(row.get("ts_event")),
                        "ts_ingest": _now_iso(),
                        "station_id": str(row.get("station_id")),
                        "station_name": str(row.get("station_name")),
                        "tag": str(rv),
                        "value": fv,
                        "quality_code": self.cfg.quality_code,
                        "source_type": "historical_replay",
                        "scenario_id": self.cfg.scenario_id,
                        "run_id": self.run_id,
                        "case_id": self.cfg.case_id,
                        "replay_speed": float(self.cfg.replay_speed),
                        "_auto_generated": True,
                    }
                )
                continue
            # Check if this is an observations table row (Z, Q) or station_operation row (H_up, H_down, Q_in, Q_out)
            tags_to_check = ["Z", "Q"] if "Z" in row or "Q" in row else ["H_up", "H_down", "Q_in", "Q_out"]
            for tag in tags_to_check:
                value = row.get(tag)
                if value is None:
                    continue
                messages.append(
                    {
                        "ts_event": str(row.get("ts_event")),
                        "ts_ingest": _now_iso(),
                        "station_id": str(row.get("station_id")),
                        "station_name": str(row.get("station_name")),
                        "tag": tag,
                        "value": float(value),
                        "quality_code": self.cfg.quality_code,
                        "source_type": "historical_replay",
                        "scenario_id": self.cfg.scenario_id,
                        "run_id": self.run_id,
                        "case_id": self.cfg.case_id,
                        "replay_speed": float(self.cfg.replay_speed),
                        "_auto_generated": True,
                    }
                )
        return messages

    def _interpolate_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.cfg.replay_dt_seconds or not self.cfg.query_start or not self.cfg.query_end:
            return messages

        dt = float(self.cfg.replay_dt_seconds)
        start_dt = datetime.fromisoformat(self.cfg.query_start.replace(" ", "T"))
        end_dt = datetime.fromisoformat(self.cfg.query_end.replace(" ", "T"))
        
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
            
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()

        series_data: dict[tuple[str, str, str], list[tuple[float, float]]] = {}
        for m in messages:
            ts_str = m["ts_event"]
            if "T" not in ts_str:
                ts_str = ts_str.replace(" ", "T")
            event_dt = datetime.fromisoformat(ts_str)
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)
            t = event_dt.timestamp()
            
            key = (m["station_id"], m["station_name"], m["tag"])
            if key not in series_data:
                series_data[key] = []
            series_data[key].append((t, float(m["value"])))

        interpolated_messages = []
        
        current_ts = start_ts
        while current_ts < end_ts:
            for (st_id, st_name, tag), pts in series_data.items():
                pts.sort(key=lambda x: x[0])
                times = [p[0] for p in pts]
                vals = [p[1] for p in pts]
                
                if not times:
                    continue
                
                if current_ts <= times[0]:
                    val = vals[0]
                elif current_ts >= times[-1]:
                    val = vals[-1]
                else:
                    import bisect
                    idx = bisect.bisect_right(times, current_ts)
                    t0, v0 = times[idx-1], vals[idx-1]
                    t1, v1 = times[idx], vals[idx]
                    ratio = (current_ts - t0) / (t1 - t0) if t1 > t0 else 0
                    val = v0 + ratio * (v1 - v0)
                
                ts_event_iso = datetime.fromtimestamp(current_ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                
                interpolated_messages.append({
                    "ts_event": ts_event_iso,
                    "ts_ingest": _now_iso(),
                    "station_id": st_id,
                    "station_name": st_name,
                    "tag": tag,
                    "value": round(val, 4),
                    "quality_code": self.cfg.quality_code,
                    "source_type": "historical_replay_interpolated",
                    "scenario_id": self.cfg.scenario_id,
                    "run_id": self.run_id,
                    "case_id": self.cfg.case_id,
                    "replay_speed": float(self.cfg.replay_speed),
                    "_auto_generated": True,
                })
            current_ts += dt
            
        interpolated_messages.sort(key=lambda m: m["ts_event"])
        return interpolated_messages

    def run(self, summary_path: Path, stream_path: Path) -> dict[str, Any]:
        rows = self._query_rows()
        messages = self._build_messages(rows)
        messages = self._interpolate_messages(messages)
        stream_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        stream_path.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in messages) + "\n",
            encoding="utf-8",
        )
        summary = {
            "case_id": self.cfg.case_id,
            "run_id": self.run_id,
            "scenario_id": self.cfg.scenario_id,
            "source_type": "historical_replay",
            "sqlite_path": str(self.cfg.sqlite_path),
            "query_window": {
                "start": self.cfg.query_start,
                "end": self.cfg.query_end,
            },
            "replay_speed": float(self.cfg.replay_speed),
            "quality_code": self.cfg.quality_code,
            "records_loaded": len(rows),
            "messages_emitted": len(messages),
            "stream_path": str(stream_path),
            "generated_at": _now_iso(),
            "_auto_generated": True,
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary
