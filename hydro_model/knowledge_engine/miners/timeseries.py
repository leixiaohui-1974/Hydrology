"""Miners for the Time Series domain (F1-F5).

Handles rainfall, water level, discharge, evaporation, and meteorological
time series.  Extracts from CSV, SQLite, and TXT.
"""
from __future__ import annotations

import csv
import fnmatch
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..registry import MineResult
from ..taxonomy import TYPE_CATALOG, DataType

log = logging.getLogger(__name__)

_TS_TYPES = [
    DataType.TS_RAINFALL,
    DataType.TS_WATER_LEVEL,
    DataType.TS_DISCHARGE,
    DataType.TS_EVAPORATION,
    DataType.TS_METEOROLOGICAL,
]

_DATETIME_PATTERNS = [
    r"\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}",
    r"\d{4}[-/]\d{2}[-/]\d{2}",
]


def _detect_timestep(timestamps: list[str]) -> str | None:
    """Infer time step from the first few timestamps."""
    if len(timestamps) < 2:
        return None
    try:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
                     "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                t1 = datetime.strptime(timestamps[0].strip(), fmt)
                t2 = datetime.strptime(timestamps[1].strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return None
        delta = t2 - t1
        secs = int(delta.total_seconds())
        if secs <= 0:
            return None
        if secs <= 360:
            return "5min"
        if secs <= 1800:
            return "15min"
        if secs <= 5400:
            return "1h"
        if secs <= 21600:
            return "3h"
        if secs <= 43200:
            return "6h"
        if secs <= 86400:
            return "daily"
        return "monthly"
    except Exception:
        return None


class TimeseriesMiner:
    @property
    def handled_types(self) -> list[DataType]:
        return list(_TS_TYPES)

    def probe(self, path: Path, cfg: dict[str, Any]) -> list[DataType]:
        matched: list[DataType] = []
        name_lower = path.name.lower()
        ext = path.suffix.lower()
        for dt in _TS_TYPES:
            meta = TYPE_CATALOG[dt]
            if ext not in meta.extensions:
                continue
            if meta.filename_patterns and not any(
                fnmatch.fnmatch(name_lower, p) for p in meta.filename_patterns
            ):
                if ext in (".sqlite3", ".db", ".xlsx", ".xls"):
                    matched.append(dt)
                    continue
                continue
            matched.append(dt)
        return matched

    def extract(
        self, path: Path, data_type: DataType, cfg: dict[str, Any],
    ) -> list[MineResult]:
        ext = path.suffix.lower()
        if ext == ".csv":
            return self._extract_csv(path, data_type, cfg)
        if ext in (".sqlite3", ".db"):
            return self._extract_sqlite(path, data_type, cfg)
        if ext == ".txt":
            return self._extract_txt(path, data_type)
        if ext in (".xlsx", ".xls"):
            return self._extract_excel(path, data_type, cfg)
        return []

    # ── Excel extraction ──────────────────────────────────────────────────

    def _extract_excel(
        self, path: Path, data_type: DataType, cfg: dict[str, Any],
    ) -> list[MineResult]:
        try:
            import pandas as pd
        except ImportError:
            log.warning("pandas not installed, cannot extract excel timeseries")
            return []
            
        results: list[MineResult] = []
        ext = path.suffix.lower()
        engine = 'xlrd' if ext == '.xls' else 'openpyxl'
        try:
            xl = pd.ExcelFile(path, engine=engine)
        except Exception as e:
            # Fallback if extension lies
            try:
                fallback_engine = 'openpyxl' if engine == 'xlrd' else 'xlrd'
                xl = pd.ExcelFile(path, engine=fallback_engine)
            except Exception as fallback_e:
                log.warning(f"Failed to read excel file {path} with both engines: {e} | {fallback_e}")
                # We can't return an error here easily since it's not throwing out of the miner,
                # but we can raise an exception to be caught by discovery.py so it's logged in errors.
                raise RuntimeError(f"Excel parsing failed: {e}")

        station = self._infer_station(path, cfg)
        var_map = {
            DataType.TS_RAINFALL: ["rainfall", "precip", "rain", "降雨", "雨量"],
            DataType.TS_WATER_LEVEL: ["water_level", "waterlevel", "h_up", "h_down", "水位", "监测数据"],
            DataType.TS_DISCHARGE: ["discharge", "q_out", "q_in", "streamflow", "流量", "监测数据"],
            DataType.TS_EVAPORATION: ["evap", "蒸发"],
            DataType.TS_METEOROLOGICAL: ["temperature", "wind", "humidity", "气温", "风速"],
        }
        target_keywords = var_map.get(data_type, [])
        time_keywords = ["time", "date", "datetime", "时间", "日期"]

        for sheet_name in xl.sheet_names:
            try:
                df = xl.parse(sheet_name)
            except Exception:
                continue

            if df.empty:
                continue

            cols = [str(c).lower() for c in df.columns]
            time_col = None
            for c, raw_c in zip(cols, df.columns):
                if any(tk in c for tk in time_keywords):
                    time_col = raw_c
                    break

            if not time_col:
                continue

            matched_cols = []
            for c, raw_c in zip(cols, df.columns):
                if raw_c == time_col:
                    continue
                if any(kw in c for kw in target_keywords):
                    matched_cols.append(raw_c)

            if not matched_cols:
                if any(kw in sheet_name.lower() for kw in target_keywords):
                    for c, raw_c in zip(cols, df.columns):
                        if raw_c == time_col:
                            continue
                        if pd.api.types.is_numeric_dtype(df[raw_c]):
                            matched_cols.append(raw_c)
            
            if not matched_cols:
                continue

            df = df.dropna(subset=[time_col])
            n_records = len(df)
            if n_records < 2:
                continue

            timestamps = df[time_col].astype(str).tolist()
            time_step = _detect_timestep(timestamps[:5])

            for mc in matched_cols:
                non_empty = df[mc].notna().sum()
                if non_empty < 2:
                    continue
                
                results.append(MineResult(
                    data_type=data_type,
                    source_path=str(path),
                    source_kind="excel",
                    payload={
                        "sheet_name": sheet_name,
                        "variable": str(mc),
                        "station": station,
                        "n_records": int(n_records),
                        "non_empty": int(non_empty),
                        "time_step": time_step,
                        "start": timestamps[0],
                        "end": timestamps[-1],
                        "modified": datetime.fromtimestamp(
                            path.stat().st_mtime
                        ).isoformat(timespec="seconds"),
                    },
                    confidence=0.8,
                    label=f"{TYPE_CATALOG[data_type].label_cn}: {mc} @ {station or sheet_name} ({n_records} records)",
                ))
        return results

    # ── CSV extraction ────────────────────────────────────────────────────

    def _extract_csv(
        self, path: Path, data_type: DataType, cfg: dict[str, Any],
    ) -> list[MineResult]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            reader = csv.DictReader(lines)
            fields = reader.fieldnames or []
        except Exception:
            return []

        time_keys = [
            k for k in fields
            if any(w in k.lower() for w in ["time", "date", "datetime", "时间", "日期"])
        ]
        value_keys = [
            k for k in fields
            if k not in time_keys and k.strip()
        ]
        if not time_keys or not value_keys:
            return []

        rows = list(reader)
        n_records = len(rows)
        if n_records == 0:
            return []

        timestamps = [r.get(time_keys[0], "") for r in rows if r.get(time_keys[0])]
        start = timestamps[0] if timestamps else None
        end = timestamps[-1] if timestamps else None
        time_step = _detect_timestep(timestamps[:5])

        station = self._infer_station(path, cfg)

        results: list[MineResult] = []
        for vk in value_keys:
            non_empty = sum(1 for r in rows if r.get(vk, "").strip())
            if non_empty < 2:
                continue
            results.append(MineResult(
                data_type=data_type,
                source_path=str(path),
                source_kind="csv",
                payload={
                    "variable": vk,
                    "station": station,
                    "n_records": n_records,
                    "non_empty": non_empty,
                    "time_step": time_step,
                    "start": start,
                    "end": end,
                    "modified": datetime.fromtimestamp(
                        path.stat().st_mtime
                    ).isoformat(timespec="seconds"),
                },
                confidence=0.7 if n_records >= 10 else 0.4,
                label=f"{TYPE_CATALOG[data_type].label_cn}: {vk} ({n_records} records)",
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

        if "timeseries_meta" in tables:
            results.extend(self._from_ts_meta(conn, path, data_type))
        else:
            results.extend(self._from_generic_tables(conn, tables, path, data_type))

        conn.close()
        return results

    def _from_ts_meta(
        self, conn: sqlite3.Connection, path: Path, data_type: DataType,
    ) -> list[MineResult]:
        results: list[MineResult] = []
        var_map = {
            DataType.TS_RAINFALL: ["rainfall", "precip", "rain", "P_total", "降雨"],
            DataType.TS_WATER_LEVEL: ["water_level", "waterLevel", "H_up", "H_down", "水位"],
            DataType.TS_DISCHARGE: ["discharge", "Q_out", "Q_in", "streamflow", "流量"],
            DataType.TS_EVAPORATION: ["evap", "E_pan", "蒸发"],
            DataType.TS_METEOROLOGICAL: ["temperature", "wind", "humidity", "气温", "风速"],
        }
        keywords = var_map.get(data_type, [])

        try:
            for row in conn.execute(
                "SELECT station_id, variable, time_step, n_records FROM timeseries_meta"
            ).fetchall():
                variable = str(row[1])
                if keywords and not any(kw in variable.lower() for kw in keywords):
                    continue
                results.append(MineResult(
                    data_type=data_type,
                    source_path=str(path),
                    source_kind="sqlite",
                    payload={
                        "station": row[0],
                        "variable": variable,
                        "time_step": row[2],
                        "n_records": row[3],
                    },
                    confidence=0.8,
                    label=f"{TYPE_CATALOG[data_type].label_cn}: {variable} @ {row[0]}",
                ))
        except Exception:
            pass
        return results

    def _from_generic_tables(
        self, conn: sqlite3.Connection, tables: list[str],
        path: Path, data_type: DataType,
    ) -> list[MineResult]:
        results: list[MineResult] = []
        for table in tables:
            try:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{table}])").fetchall()]
                cols_lower = [c.lower() for c in cols]
            except Exception:
                continue

            has_time = any(
                any(w in c for w in ["time", "date", "datetime", "时间"])
                for c in cols_lower
            )
            if not has_time:
                continue

            try:
                n_rows = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            except Exception:
                continue

            if n_rows < 2:
                continue

            numeric_cols = [
                c for c in cols
                if c.lower() not in ("time", "date", "datetime", "时间", "日期")
            ]
            results.append(MineResult(
                data_type=data_type,
                source_path=str(path),
                source_kind="sqlite",
                payload={
                    "table": table,
                    "n_records": n_rows,
                    "columns": numeric_cols,
                    "variable": table,
                },
                confidence=0.5,
                label=f"时序表: {table} ({n_rows} rows)",
            ))
        return results

    # ── TXT extraction ────────────────────────────────────────────────────

    def _extract_txt(self, path: Path, data_type: DataType) -> list[MineResult]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        lines = text.splitlines()
        has_datetime = False
        numeric_lines = 0
        for line in lines[:50]:
            for pat in _DATETIME_PATTERNS:
                if re.search(pat, line):
                    has_datetime = True
                    break
            nums = re.findall(r"[-+]?\d*\.?\d+", line)
            if len(nums) >= 2:
                numeric_lines += 1

        if not has_datetime or numeric_lines < 3:
            return []

        return [MineResult(
            data_type=data_type,
            source_path=str(path),
            source_kind="text",
            payload={
                "variable": path.stem,
                "n_records": numeric_lines,
                "modified": datetime.fromtimestamp(
                    path.stat().st_mtime
                ).isoformat(timespec="seconds"),
            },
            confidence=0.4,
            label=f"{TYPE_CATALOG[data_type].label_cn}: {path.name}",
        )]

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _infer_station(path: Path, cfg: dict[str, Any]) -> str | None:
        targets = cfg.get("target_stations", [])
        name = path.stem
        for t in targets:
            if t in name:
                return t
        return path.stem
