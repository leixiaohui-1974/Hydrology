from __future__ import annotations

import sqlite3
from pathlib import Path

import workflows.run_hydraulic_calibration as target


def _write_observations_db(
    path: Path,
    *,
    station: str,
    rows: int,
    include_q: bool = True,
) -> None:
    conn = sqlite3.connect(path)
    try:
        value_columns = "Z REAL, Q REAL" if include_q else "Z REAL"
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS observations (station TEXT, time TEXT, {value_columns})"
        )
        if include_q:
            payload = [
                (
                    station,
                    f"2026-01-{(index % 28) + 1:02d}T{index % 24:02d}:00:00",
                    100.0 + index * 0.01,
                    50.0 + index * 0.02,
                )
                for index in range(rows)
            ]
            conn.executemany(
                "INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)",
                payload,
            )
        else:
            payload = [
                (
                    station,
                    f"2026-01-{(index % 28) + 1:02d}T{index % 24:02d}:00:00",
                    100.0 + index * 0.01,
                )
                for index in range(rows)
            ]
            conn.executemany(
                "INSERT INTO observations (station, time, Z) VALUES (?, ?, ?)",
                payload,
            )
        conn.commit()
    finally:
        conn.close()



def _write_timeseries_db(path: Path, *, station: str, rows: int) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS timeseries (station_id TEXT, variable TEXT, time TEXT, value REAL)"
        )
        payload = []
        for variable, base in (("H_up", 100.0), ("Q_in", 50.0), ("Q_out", 40.0)):
            for index in range(rows):
                payload.append(
                    (
                        station,
                        variable,
                        f"2026-01-{(index % 28) + 1:02d}T{index % 24:02d}:00:00",
                        base + index * 0.01,
                    )
                )
        conn.executemany(
            "INSERT INTO timeseries (station_id, variable, time, value) VALUES (?, ?, ?, ?)",
            payload,
        )
        conn.commit()
    finally:
        conn.close()



def _patch_case_config(monkeypatch, *, db_path: Path, station_ids: list[str]) -> None:
    monkeypatch.setattr(target, "WORKSPACE", db_path.parent)
    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda case_id, config_path=None: {
            "case_id": case_id,
            "project_type": "pump_canal",
            "sqlite_paths": [str(db_path)],
            "target_stations": list(station_ids),
            "knowledge": {"reservoirs": {}},
        },
    )


def test_get_station_meta_falls_back_to_target_stations_when_reservoirs_missing() -> None:
    cfg = {
        "project_type": "pump_canal",
        "target_stations": ["XHH-001", "XHH-002"],
        "knowledge": {"reservoirs": {}},
    }

    station_meta = target._get_station_meta(cfg)

    assert set(station_meta) == {"XHH-001", "XHH-002"}
    assert station_meta["XHH-001"] == {
        "name": "XHH-001",
        "h_var": "H_up",
        "q_in_var": "Q_in",
        "q_out_var": "Q_out",
    }



def test_get_station_meta_prefers_target_stations_intersection_with_reservoirs() -> None:
    cfg = {
        "project_type": "cascade_hydro",
        "target_stations": ["瀑布沟前", "深溪沟前"],
        "knowledge": {
            "reservoirs": {
                "s1": {"name": "瀑布沟前"},
                "s2": {"name": "深溪沟前"},
                "s3": {"name": "无关站点"},
            }
        },
    }

    station_meta = target._get_station_meta(cfg)

    assert list(station_meta) == ["s1", "s2"]
    assert station_meta["s1"]["name"] == "瀑布沟前"
    assert station_meta["s2"]["name"] == "深溪沟前"



def test_get_station_meta_maps_topology_nodes_back_to_reservoir_station_ids() -> None:
    cfg = {
        "project_type": "cascade_hydro",
        "target_stations": ["瀑布沟前", "深溪沟后"],
        "knowledge": {
            "reservoirs": {
                "s1": {"name": "瀑布沟"},
                "s2": {"name": "深溪沟"},
            },
            "topology": {
                "nodes": {
                    "瀑布沟前": {"nodeType": 0},
                    "深溪沟后": {"nodeType": 0},
                    "无关节点": {"nodeType": 0},
                }
            },
        },
    }

    station_meta = target._get_station_meta(cfg)

    assert list(station_meta) == ["s1", "s2"]
    assert station_meta["s1"]["name"] == "瀑布沟"
    assert station_meta["s2"]["name"] == "深溪沟"


def test_get_station_meta_fails_closed_for_boundary_only_topology_nodes() -> None:
    cfg = {
        "project_type": "cascade_hydro",
        "target_stations": ["石棉入流"],
        "knowledge": {
            "reservoirs": {
                "s1": {"name": "瀑布沟"},
                "s2": {"name": "深溪沟"},
            },
            "topology": {
                "nodes": {
                    "石棉入流": {"nodeType": 2},
                }
            },
        },
    }

    station_meta = target._get_station_meta(cfg)

    assert station_meta == {}



def test_get_station_meta_fails_closed_for_boundary_collision_with_reservoir_name() -> None:
    cfg = {
        "project_type": "cascade_hydro",
        "target_stations": ["瀑布沟入流"],
        "knowledge": {
            "reservoirs": {
                "s1": {"name": "瀑布沟"},
            },
            "topology": {
                "nodes": {
                    "瀑布沟入流": {"nodeType": 2},
                }
            },
        },
    }

    station_meta = target._get_station_meta(cfg)

    assert station_meta == {}


def test_get_station_meta_fails_closed_when_targets_do_not_match_known_metadata() -> None:
    cfg = {
        "project_type": "cascade_hydro",
        "target_stations": ["不存在的站点"],
        "knowledge": {
            "reservoirs": {
                "s1": {"name": "瀑布沟前"},
                "s2": {"name": "深溪沟前"},
            },
            "topology": {
                "nodes": {
                    "瀑布沟前": {"nodeType": 0},
                    "深溪沟前": {"nodeType": 0},
                }
            },
        },
    }

    station_meta = target._get_station_meta(cfg)

    assert station_meta == {}



def test_get_station_meta_fails_closed_when_topology_is_missing_for_alias_target() -> None:
    cfg = {
        "project_type": "cascade_hydro",
        "target_stations": ["瀑布沟入流"],
        "knowledge": {
            "reservoirs": {
                "s1": {"name": "瀑布沟"},
            },
        },
    }

    station_meta = target._get_station_meta(cfg)

    assert station_meta == {}


def test_calibrate_and_validate_records_insufficient_data_for_timeseries_station(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "timeseries.sqlite"
    _write_timeseries_db(db_path, station="XHH-001", rows=49)
    _patch_case_config(monkeypatch, db_path=db_path, station_ids=["XHH-001"])

    report = target.calibrate_and_validate("xuhonghe", generate_report=False)

    assert report["outcome_status"] == "no_data"
    assert report["quality_gate_passed"] is False
    assert "有效时序不足" in str(report["quality_reason"])
    assert report["summary"]["n_candidate_stations"] == 1
    assert report["summary"]["n_station_results"] == 1
    assert report["summary"]["n_insufficient_data_stations"] == 1
    assert report["station_results"]["XHH-001"]["status"] == "insufficient_data"
    assert report["station_results"]["XHH-001"]["n"] == 49
    assert (
        tmp_path / "cases" / "xuhonghe" / "contracts" / "hydraulic_calibration.latest.json"
    ).is_file()



def test_find_db_rejects_sqlite_without_supported_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "unsupported.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE metadata (id INTEGER PRIMARY KEY, value TEXT)")
        conn.commit()
    finally:
        conn.close()

    cfg = {"sqlite_paths": [str(db_path)], "scan_dirs": [], "knowledge": {}}

    assert target._find_db(cfg) is None



def test_calibrate_and_validate_reports_ambiguous_observation_aliases(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "observations.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
        rows = []
        for index in range(240):
            timestamp = f"2026-01-{(index % 28) + 1:02d}T{index % 24:02d}:00:00"
            rows.append(("prefix/XHH-001", timestamp, 100.0 + index * 0.01, 50.0 + index * 0.02))
            rows.append(("archive/XHH-001", timestamp, 110.0 + index * 0.01, 60.0 + index * 0.02))
        conn.executemany(
            "INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    _patch_case_config(monkeypatch, db_path=db_path, station_ids=["XHH-001"])

    report = target.calibrate_and_validate("xuhonghe", generate_report=False)

    assert report["outcome_status"] == "no_data"
    assert report["quality_gate_passed"] is False
    assert "观测站别名歧义" in str(report["quality_reason"])
    assert report["summary"]["n_ambiguous_observation_stations"] == 1
    assert report["station_results"]["XHH-001"]["status"] == "ambiguous_observation_station_aliases"
    assert sorted(report["station_results"]["XHH-001"]["aliases"]) == ["archive/XHH-001", "prefix/XHH-001"]



def test_calibrate_and_validate_records_missing_timeseries_when_station_not_found(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "timeseries.sqlite"
    _write_timeseries_db(db_path, station="OTHER-001", rows=240)
    _patch_case_config(monkeypatch, db_path=db_path, station_ids=["XHH-001"])

    report = target.calibrate_and_validate("xuhonghe", generate_report=False)

    assert report["outcome_status"] == "no_data"
    assert report["quality_gate_passed"] is False
    assert "缺少有效时序" in str(report["quality_reason"])
    assert report["summary"]["n_missing_timeseries_stations"] == 1
    assert report["station_results"]["XHH-001"]["status"] == "missing_timeseries"


def test_calibrate_and_validate_fails_closed_when_observations_missing_flow_columns(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "observations.sqlite"
    _write_observations_db(db_path, station="XHH-001", rows=240, include_q=False)
    _patch_case_config(monkeypatch, db_path=db_path, station_ids=["XHH-001"])

    report = target.calibrate_and_validate("xuhonghe", generate_report=False)

    assert report["outcome_status"] == "no_data"
    assert report["quality_gate_passed"] is False
    assert "缺少 observations 所需变量列" in str(report["quality_reason"])
    assert report["summary"]["n_unsupported_observation_variable_stations"] == 1
    assert report["station_results"]["XHH-001"]["status"] == "unsupported_observation_variable"
    assert report["station_results"]["XHH-001"]["available_columns"] == ["Z", "station", "time"]



def test_calibrate_and_validate_fails_closed_when_observations_only_has_shared_q_column(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "observations_shared_q.sqlite"
    _write_observations_db(db_path, station="XHH-001", rows=240, include_q=True)
    _patch_case_config(monkeypatch, db_path=db_path, station_ids=["XHH-001"])

    report = target.calibrate_and_validate("xuhonghe", generate_report=False)

    assert report["outcome_status"] == "no_data"
    assert report["quality_gate_passed"] is False
    assert "缺少 observations 所需变量列" in str(report["quality_reason"])
    assert report["summary"]["n_unsupported_observation_variable_stations"] == 1
    assert report["station_results"]["XHH-001"]["status"] == "unsupported_observation_variable"
    assert report["station_results"]["XHH-001"]["available_columns"] == ["Q", "Z", "station", "time"]


def test_find_db_prefers_supported_timeseries_over_invalid_observations_candidate(tmp_path: Path) -> None:
    invalid_db = tmp_path / "invalid_observations.sqlite"
    conn = sqlite3.connect(invalid_db)
    try:
        conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
        conn.execute(
            "INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)",
            ("XHH-001", "2026-01-01T00:00:00", 100.0, 50.0),
        )
        conn.commit()
    finally:
        conn.close()

    preferred_db = tmp_path / "supported_timeseries.sqlite"
    _write_timeseries_db(preferred_db, station="XHH-001", rows=240)

    cfg = {
        "sqlite_paths": [str(invalid_db), str(preferred_db)],
        "scan_dirs": [],
        "knowledge": {},
    }

    assert target._find_db(cfg) == str(preferred_db.resolve())


def test_calibrate_and_validate_falls_back_to_valid_observations_when_timeseries_table_is_malformed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mixed.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE timeseries (station_id TEXT, variable TEXT)")
        conn.execute(
            "CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q_in REAL, Q_out REAL)"
        )
        rows = [
            (
                "XHH-001",
                f"2026-01-{(index // 24) + 1:02d}T{index % 24:02d}:00:00",
                100.0 + index * 0.01,
                50.0 + index * 0.02,
                40.0 + index * 0.02,
            )
            for index in range(240)
        ]
        conn.executemany(
            "INSERT INTO observations (station, time, Z, Q_in, Q_out) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    _patch_case_config(monkeypatch, db_path=db_path, station_ids=["XHH-001"])

    def _fake_calibrate_station(*, Q_in, Q_out, H_obs, **kwargs):
        assert len(H_obs) == len(Q_in) == len(Q_out) == 240
        assert float(H_obs[0]) == 100.0
        assert float(Q_in[0]) == 50.0
        assert float(Q_out[0]) == 40.0
        assert float(H_obs[-1]) == 100.0 + 239 * 0.01
        assert float(Q_in[-1]) == 50.0 + 239 * 0.02
        assert float(Q_out[-1]) == 40.0 + 239 * 0.02
        return {
            "status": "completed",
            "cal_metrics": {"nse": 0.9, "rmse": 0.1},
            "val_metrics": {"nse": 0.8, "rmse": 0.2},
            "model_params": {"A_eff": 1234.0, "alpha": 0.8},
            "phases_used": ["basic"],
            "n_cal": 168,
            "n_val": 72,
        }

    monkeypatch.setattr(target, "calibrate_station", _fake_calibrate_station)

    report = target.calibrate_and_validate("xuhonghe", generate_report=False)

    assert report["outcome_status"] == "completed"
    assert report["quality_gate_passed"] is True
    assert report["summary"]["n_stations_calibrated"] == 1
    assert "calibration" in report["station_results"]["XHH-001"]


def test_calibrate_and_validate_fails_closed_when_timeseries_and_observations_are_both_unsupported(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mixed_invalid.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE timeseries (station_id TEXT, variable TEXT)")
        conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
        conn.execute(
            "INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)",
            ("XHH-001", "2026-01-01T00:00:00", 100.0, 50.0),
        )
        conn.commit()
    finally:
        conn.close()

    _patch_case_config(monkeypatch, db_path=db_path, station_ids=["XHH-001"])

    report = target.calibrate_and_validate("xuhonghe", generate_report=False)

    assert report["outcome_status"] == "no_data"
    assert report["quality_gate_passed"] is False
    assert "缺少 observations 所需变量列" in str(report["quality_reason"])
    assert report["summary"]["n_unsupported_observation_variable_stations"] == 1
    assert report["station_results"]["XHH-001"]["status"] == "unsupported_observation_variable"


def test_calibrate_and_validate_marks_partial_station_failures_as_degraded(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mixed.sqlite"
    _write_timeseries_db(db_path, station="XHH-001", rows=240)
    _write_observations_db(db_path, station="XHH-002", rows=240, include_q=False)
    _patch_case_config(monkeypatch, db_path=db_path, station_ids=["XHH-001", "XHH-002"])

    def _fake_calibrate_station(*, Q_in, Q_out, H_obs, **kwargs):
        n = min(len(Q_in), len(Q_out), len(H_obs))
        return {
            "status": "completed",
            "cal_metrics": {"nse": 0.9, "rmse": 0.1},
            "val_metrics": {"nse": 0.4, "rmse": 0.2},
            "model_params": {"A_eff": 1234.0, "alpha": 0.8},
            "phases_used": ["basic"],
            "n_cal": int(n * 0.7),
            "n_val": n - int(n * 0.7),
        }

    monkeypatch.setattr(target, "calibrate_station", _fake_calibrate_station)

    report = target.calibrate_and_validate("xuhonghe", generate_report=False)

    assert report["outcome_status"] == "degraded"
    assert report["quality_gate_passed"] is False
    assert "部分候选站点完成率定" in str(report["quality_reason"])
    assert report["summary"]["n_stations_calibrated"] == 1
    assert report["summary"]["n_unsupported_observation_variable_stations"] == 1
    assert "calibration" in report["station_results"]["XHH-001"]
    assert report["station_results"]["XHH-002"]["status"] == "unsupported_observation_variable"



def test_load_ts_with_metadata_returns_timestamped_series(tmp_path: Path) -> None:
    db_path = tmp_path / "timeseries.sqlite"
    _write_timeseries_db(db_path, station="XHH-001", rows=3)

    values, metadata = target._load_ts_with_metadata(str(db_path), "XHH-001", "H_up")

    assert metadata is None
    assert list(values.index.astype(str)) == [
        "2026-01-01T00:00:00",
        "2026-01-02T01:00:00",
        "2026-01-03T02:00:00",
    ]
    assert list(values.values) == [100.0, 100.01, 100.02]



def test_calibrate_and_validate_aligns_series_by_timestamp_intersection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "misaligned.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE timeseries (station_id TEXT, variable TEXT, time TEXT, value REAL)"
        )
        timeseries_rows = []
        for index in range(240):
            timestamp = f"2026-01-{(index // 24) + 1:02d}T{index % 24:02d}:00:00"
            if index >= 10:
                timeseries_rows.append(("XHH-001", "H_up", timestamp, 100.0 + index * 0.01))
            timeseries_rows.append(("XHH-001", "Q_in", timestamp, 50.0 + index * 0.01))
            timeseries_rows.append(("XHH-001", "Q_out", timestamp, 40.0 + index * 0.01))
        conn.executemany(
            "INSERT INTO timeseries (station_id, variable, time, value) VALUES (?, ?, ?, ?)",
            timeseries_rows,
        )
        conn.commit()
    finally:
        conn.close()

    _patch_case_config(monkeypatch, db_path=db_path, station_ids=["XHH-001"])

    observed_lengths = {}

    def _fake_calibrate_station(*, Q_in, Q_out, H_obs, **kwargs):
        observed_lengths["n"] = len(H_obs)
        assert len(H_obs) == len(Q_in) == len(Q_out) == 230
        return {
            "status": "completed",
            "cal_metrics": {"nse": 0.9, "rmse": 0.1},
            "val_metrics": {"nse": 0.8, "rmse": 0.2},
            "model_params": {"A_eff": 1234.0, "alpha": 0.8},
            "phases_used": ["basic"],
            "n_cal": int(len(H_obs) * 0.7),
            "n_val": len(H_obs) - int(len(H_obs) * 0.7),
        }

    monkeypatch.setattr(target, "calibrate_station", _fake_calibrate_station)

    report = target.calibrate_and_validate("xuhonghe", generate_report=False)

    assert observed_lengths["n"] == 230
    assert report["outcome_status"] == "completed"
    assert report["summary"]["n_stations_calibrated"] == 1
