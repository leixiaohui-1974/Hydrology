#!/usr/bin/env python3
"""Generate a small synthetic observation CSV for bootstrap validation."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
HYDROLOGY = WORKSPACE / "Hydrology"

if str(HYDROLOGY) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY))

from workflows._shared import load_case_config  # noqa: E402


def _resolve_station(case_id: str, station_id: str) -> dict[str, Any]:
    cfg = load_case_config(case_id)
    reservoir = ((cfg.get("knowledge") or {}).get("reservoirs") or {}).get(station_id) or {}
    if not reservoir:
        raise KeyError(f"station_id not found in knowledge.reservoirs: {station_id}")
    name = str(reservoir.get("name") or station_id)
    node = (((cfg.get("knowledge") or {}).get("topology") or {}).get("nodes") or {}).get(name) or {}
    return {
        "station_id": station_id,
        "station_name": name,
        "lat": node.get("y"),
        "lon": node.get("x"),
        "elevation": node.get("zb"),
        "station_type": str(reservoir.get("station_type") or "reservoir"),
        "normal_pool_m": float(reservoir.get("normal_pool_m") or reservoir.get("dead_pool_m") or 100.0),
    }


def _default_output(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "ingest" / "raw" / f"{case_id}_observation_timeseries.csv"


def generate_bootstrap_observation_csv(
    case_id: str,
    station_id: str,
    *,
    output_path: str | Path | None = None,
    periods: int = 720,
    start_time: str = "2024-01-01 00:00:00",
) -> Path:
    station = _resolve_station(case_id, station_id)
    out = Path(output_path) if output_path else _default_output(case_id)
    if not out.is_absolute():
        out = (WORKSPACE / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    source = out.relative_to(WORKSPACE).as_posix() if out.is_relative_to(WORKSPACE) else str(out)
    area = 1.2e6
    level = station["normal_pool_m"]

    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "time",
                "station_id",
                "station_name",
                "variable",
                "value",
                "unit",
                "time_step",
                "quality",
                "lat",
                "lon",
                "elevation",
                "station_type",
                "source",
            ]
        )
        for i in range(periods):
            current = start + timedelta(hours=i)
            q_in = 15.4 + 1.2 * math.sin(i / 18.0) + 0.35 * math.cos(i / 7.0)
            q_out = 15.0 + 0.9 * math.sin((i - 3) / 18.0) + 0.25 * math.cos(i / 9.0)
            level += (q_in - q_out) * 3600.0 / area
            level_obs = level + 0.03 * math.sin(i / 11.0)
            time_text = current.strftime("%Y-%m-%d %H:%M:%S")
            common = [
                time_text,
                station["station_id"],
                station["station_name"],
                None,
                None,
                None,
                "1H",
                1,
                station["lat"],
                station["lon"],
                station["elevation"],
                station["station_type"],
                source,
            ]
            for variable, value, unit in (
                ("H_up", level_obs, "m"),
                ("Q_in", q_in, "m3/s"),
                ("Q_out", q_out, "m3/s"),
            ):
                row = list(common)
                row[3] = variable
                row[4] = f"{value:.4f}"
                row[5] = unit
                writer.writerow(row)

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate bootstrap observation CSV for SQLite ingestion tests")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--station-id", required=True)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--periods", type=int, default=720)
    parser.add_argument("--start-time", default="2024-01-01 00:00:00")
    args = parser.parse_args()
    out = generate_bootstrap_observation_csv(
        args.case_id.strip(),
        args.station_id.strip(),
        output_path=args.output_path,
        periods=args.periods,
        start_time=args.start_time,
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
