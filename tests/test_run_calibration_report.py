import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

import workflows.run_calibration_report as target


class _FakeEval:
    def __init__(self, label: str) -> None:
        self.metrics = {
            "nse": 0.81 if label == "calibration" else 0.76,
            "rmse": 0.12,
            "kge": 0.73,
            "r2": 0.84,
            "pbias": 1.5,
        }
        self.grade = "A" if label == "calibration" else "B"
        self.peak_error = 0.08


class _FakePrecisionReport:
    def __init__(self, case_id, delineation, hydrology) -> None:
        self.case_id = case_id
        self.delineation = delineation
        self.hydrology = hydrology

    def compute_overall(self) -> str:
        return "B"


def _write_station_catalog_db(path: Path, *, stations: list[dict], rows: list[tuple]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE stations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                station_type TEXT,
                basin_area_km2 REAL,
                metadata_json TEXT
            );
            CREATE TABLE timeseries (
                station_id TEXT NOT NULL,
                variable TEXT NOT NULL,
                time_step TEXT NOT NULL,
                time TEXT NOT NULL,
                value REAL,
                quality INTEGER,
                PRIMARY KEY (station_id, variable, time_step, time)
            );
            CREATE TABLE timeseries_meta (
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
            """
        )
        conn.executemany(
            """
            INSERT INTO stations (id, name, station_type, basin_area_km2, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    station["id"],
                    station["name"],
                    station.get("station_type", "open_channel"),
                    station.get("basin_area_km2"),
                    json.dumps({"station_name": station["name"]}, ensure_ascii=False),
                )
                for station in stations
            ],
        )
        meta_rows = []
        grouped: dict[tuple[str, str, str], int] = {}
        for station_id, variable, time_step, *_rest in rows:
            key = (station_id, variable, time_step)
            grouped[key] = grouped.get(key, 0) + 1
        for (station_id, variable, time_step), count in grouped.items():
            meta_rows.append(
                (
                    station_id,
                    variable,
                    "m3/s" if "flow" in variable or variable.startswith("Q_") else "m",
                    time_step,
                    "2025-07-01 00:00:00",
                    "2025-07-01 01:59:00" if time_step == "1min" else "2025-10-28 00:00:00",
                    count,
                    "observed.csv",
                )
            )
        conn.executemany(
            """
            INSERT INTO timeseries_meta
            (station_id, variable, unit, time_step, start_time, end_time, n_records, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            meta_rows,
        )
        conn.executemany(
            """
            INSERT INTO timeseries (station_id, variable, time_step, time, value, quality)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _series_rows(
    station_id: str,
    variable: str,
    time_step: str,
    values: list[float],
) -> list[tuple]:
    rows = []
    start = datetime(2025, 7, 1, 0, 0, 0)
    delta = timedelta(minutes=1) if time_step == "1min" else timedelta(days=1)
    for index, value in enumerate(values):
        ts = (start + index * delta).strftime("%Y-%m-%d %H:%M:%S")
        rows.append((station_id, variable, time_step, ts, float(value), 1))
    return rows


def _write_observations_db(path: Path, *, station: str, rows) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE observations (
                station TEXT NOT NULL,
                time TEXT NOT NULL,
                Z REAL,
                Q REAL
            );
            """
        )
        conn.executemany(
            "INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)",
            [(station, ts, z, q) for ts, z, q in rows],
        )
        conn.commit()
    finally:
        conn.close()



def _patch_scoring(monkeypatch) -> None:
    monkeypatch.setattr(
        target,
        "run_full_cv",
        lambda **kwargs: {
            "best_params": {"K": 1.2, "x": 0.15},
            "assessment": {"consistency": "稳定"},
        },
    )
    monkeypatch.setattr(target, "evaluate_timeseries", lambda *args: _FakeEval(args[-1]))
    monkeypatch.setattr(target, "PrecisionReport", _FakePrecisionReport)


def test_run_report_discovers_open_channel_station_without_hydropower_filter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "demo_hydromind.sqlite3"
    values_in = [10.0 + i * 0.1 for i in range(120)]
    values_out = [9.0 + i * 0.08 for i in range(120)]
    _write_station_catalog_db(
        db_path,
        stations=[{"id": "oc-01", "name": "开放渠站", "station_type": "open_channel"}],
        rows=_series_rows("oc-01", "Q_in", "1D", values_in) + _series_rows("oc-01", "Q_out", "1D", values_out),
    )
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        json.dumps({"case_id": "demo_case", "sqlite_paths": [str(db_path)]}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    _patch_scoring(monkeypatch)

    report = target.run_report("demo_case", str(config_path))

    assert report["overall_grade"] == "B"
    assert len(report["stations"]) == 1
    station = report["stations"][0]
    assert station["status"] == "completed"
    assert station["station_id"] == "oc-01"
    assert station["data_count"] == 120
    assert station["data_binding"]["input_variable"] == "Q_in"
    assert station["data_binding"]["observed_variable"] == "Q_out"
    assert station["data_binding"]["time_step"] == "1D"


def test_run_report_uses_explicit_case_closure_binding_for_yinchuojiliao(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "yinchuojiliao_hydromind.sqlite3"
    input_values = [3.0 + np.sin(i / 10.0) for i in range(120)]
    _write_station_catalog_db(
        db_path,
        stations=[
            {"id": "24001207", "name": "归流河进口", "station_type": "open_channel"},
        ],
        rows=_series_rows("24001207", "flow", "1min", input_values),
    )
    config_path = tmp_path / "yinchuojiliao.yaml"
    config_path.write_text(
        json.dumps(
            {
                "case_id": "yinchuojiliao",
                "sqlite_paths": [str(db_path)],
                "modeling": {
                    "hydrology": {
                        "closure_binding": {
                            "time_step": "1min",
                            "input": {
                                "station_id": "24001207",
                                "station_name": "归流河进口",
                                "variable": "flow",
                            },
                            "observed": {
                                "station_id": "24001207",
                                "station_name": "归流河进口",
                                "variable": "flow",
                            },
                        }
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    _patch_scoring(monkeypatch)

    report = target.run_report("yinchuojiliao", str(config_path))

    assert len(report["stations"]) == 1
    station = report["stations"][0]
    assert station["status"] == "completed"
    assert station["station_id"] == "24001207"
    assert station["station_name"] == "归流河进口"
    assert station["data_count"] == 120
    assert station["data_binding"]["selection_mode"] == "explicit_case_binding"
    assert station["data_binding"]["input_station_id"] == "24001207"
    assert station["data_binding"]["observed_station_id"] == "24001207"
    assert station["data_binding"]["input_variable"] == "flow"
    assert station["data_binding"]["observed_variable"] == "flow"
    assert station["data_binding"]["time_step"] == "1min"

    report_path = tmp_path / "cases" / "yinchuojiliao" / "contracts" / "calibration_report.latest.json"
    assert report_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["stations"][0]["data_binding"]["time_step"] == "1min"

    evidence_path = tmp_path / "cases" / "yinchuojiliao" / "contracts" / "hydrology_nse_evidence.latest.json"
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["case_id"] == "yinchuojiliao"
    assert evidence["source_workflow"] == "calibration_report"
    assert evidence["comparable_nse"] == 0.76
    assert evidence["mean_validation_nse"] == 0.76
    assert evidence["min_validation_nse"] == 0.76
    assert evidence["stations"][0]["station_id"] == "24001207"
    assert evidence["stations"][0]["validation_nse"] == 0.76



def test_run_report_accepts_observations_db_without_hydromind_in_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "xuhonghe_observations.sqlite"
    rows = [
        (f"2025-07-{day:02d} 00:00:00", 23.0 + day * 0.01, 10.0 + day * 0.1)
        for day in range(1, 121)
    ]
    _write_observations_db(db_path, station="0-洪泽湖", rows=rows)
    config_path = tmp_path / "xuhonghe.yaml"
    config_path.write_text(
        json.dumps({"case_id": "xuhonghe", "sqlite_paths": [str(db_path)]}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    _patch_scoring(monkeypatch)

    report = target.run_report("xuhonghe", str(config_path))

    assert report["overall_grade"] == "B"
    assert len(report["stations"]) == 1
    station = report["stations"][0]
    assert station["status"] == "completed"
    assert station["station_id"] == "0-洪泽湖"
    assert station["data_count"] == 120



def test_run_report_reads_observations_schema_via_explicit_binding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "observations_only.db"
    rows = [
        (f"2025-07-{day:02d} 00:00:00", 23.0 + day * 0.01, 10.0 + day * 0.1)
        for day in range(1, 121)
    ]
    _write_observations_db(db_path, station="0-洪泽湖", rows=rows)
    config_path = tmp_path / "xuhonghe.yaml"
    config_path.write_text(
        json.dumps(
            {
                "case_id": "xuhonghe",
                "sqlite_paths": [str(db_path)],
                "modeling": {
                    "hydrology": {
                        "closure_binding": {
                            "time_step": "1D",
                            "input": {
                                "station_id": "0-洪泽湖",
                                "station_name": "0-洪泽湖",
                                "variable": "flow",
                            },
                            "observed": {
                                "station_id": "0-洪泽湖",
                                "station_name": "0-洪泽湖",
                                "variable": "flow",
                            },
                        }
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    _patch_scoring(monkeypatch)

    report = target.run_report("xuhonghe", str(config_path))

    assert len(report["stations"]) == 1
    station = report["stations"][0]
    assert station["status"] == "completed"
    assert station["data_binding"]["selection_mode"] == "explicit_case_binding"
    assert station["data_binding"]["input_variable"] == "flow"
    assert station["data_binding"]["observed_variable"] == "flow"
    assert station["data_count"] == 120
