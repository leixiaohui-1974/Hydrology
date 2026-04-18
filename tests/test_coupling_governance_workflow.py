import json
import sqlite3
import sys
from pathlib import Path

import workflows.run_coupled_hydro_hydraulic as target



def test_run_coupled_requires_parameter_governance_json(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_coupled_hydro_hydraulic.py",
            "--case-id",
            "daduhe",
        ],
    )

    try:
        target.main()
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("Expected coupling runner to require parameter governance input")



def test_run_coupled_loads_coupling_activation(monkeypatch, tmp_path: Path) -> None:
    activation = tmp_path / "activation.json"
    activation.write_text(
        json.dumps(
            {
                "coupling": {
                    "runoff_to_channel_lag": 0.0,
                    "channel_inflow_scale": 1.0,
                    "coupling_transfer_bias": 0.0,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    governance = tmp_path / "parameter_governance.json"
    governance.write_text(
        json.dumps(
            {
                "artifact_paths": {"correction_activation_record": str(activation)},
                "candidate_set": {
                    "coupling": {
                        "primary_candidates": ["runoff_to_channel_lag", "channel_inflow_scale"],
                        "secondary_candidates": ["coupling_transfer_bias"],
                        "forbidden_candidates": [],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    captured = {}
    monkeypatch.setattr(target, "run_coupled", lambda case_id, config_path=None, coupling_mode="offline", coupling_activation=None: captured.update({"case_id": case_id, "coupling_activation": coupling_activation}) or {"status": "completed"})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_coupled_hydro_hydraulic.py",
            "--case-id",
            "daduhe",
            "--parameter-governance-json",
            str(governance),
        ],
    )

    target.main()

    assert captured["coupling_activation"]["channel_inflow_scale"] == 1.0


def test_find_db_accepts_generic_sqlite_path(tmp_path: Path) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    conn.commit()
    conn.close()

    cfg = {"sqlite_paths": [str(db_path)], "scan_dirs": []}

    assert target._find_db(cfg) == str(db_path.resolve())


def test_run_coupled_writes_degraded_report_when_d2_params_missing(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda case_id, config_path=None: {"sqlite_paths": [str(db_path)], "scan_dirs": [], "knowledge": {}},
    )
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "save_knowledge_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(target, "_load_d2_params", lambda case_id: {})

    report = target.run_coupled("xuhonghe")

    assert report["status"] == "degraded"
    assert report["outcome_status"] == "degraded"
    assert report["quality_gate_passed"] is False
    assert "D2 率定参数" in str(report["quality_reason"])
    assert "降级版耦合结果" in report["business_status_zh"]
    assert "hyd_cal" in report["recommended_next_action"]
    assert report["artifact_guidance"][0]["artifact"] == "coupled_hydro_hydraulic.latest.json"
    assert report["summary"]["n_stations"] == 0
    assert (tmp_path / "cases" / "xuhonghe" / "contracts" / "coupled_hydro_hydraulic.latest.json").is_file()


def test_load_hourly_reads_observations_table_with_prefixed_station_name(tmp_path: Path) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    conn.execute(
        "INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)",
        ("prefix/XHH-001", "2026-01-01T00:00:00", 123.4, 56.7),
    )
    conn.commit()
    conn.close()

    h = target.load_hourly(str(db_path), "XHH-001", "H_up")
    q = target.load_hourly(str(db_path), "XHH-001", "Q_in")

    assert h.tolist() == [123.4]
    assert q.tolist() == [56.7]


def test_load_hourly_avoids_cross_matching_multiple_observation_aliases(tmp_path: Path) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    conn.executemany(
        "INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)",
        [
            ("prefix/XHH-001", "2026-01-01T00:00:00", 123.4, 56.7),
            ("archive/XHH-001", "2026-01-01T01:00:00", 999.9, 888.8),
        ],
    )
    conn.commit()
    conn.close()

    h = target.load_hourly(str(db_path), "XHH-001", "H_up")
    q = target.load_hourly(str(db_path), "XHH-001", "Q_in")

    assert h.size == 0
    assert q.size == 0


def test_load_hourly_reads_distinct_q_in_and_q_out_columns_from_observations(tmp_path: Path) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL, Q_in REAL, Q_out REAL)")
    conn.execute(
        "INSERT INTO observations (station, time, Z, Q, Q_in, Q_out) VALUES (?, ?, ?, ?, ?, ?)",
        ("prefix/XHH-001", "2026-01-01T00:00:00", 123.4, 56.7, 11.1, 22.2),
    )
    conn.commit()
    conn.close()

    q_in = target.load_hourly(str(db_path), "XHH-001", "Q_in")
    q_out = target.load_hourly(str(db_path), "XHH-001", "Q_out")

    assert q_in.tolist() == [11.1]
    assert q_out.tolist() == [22.2]


def test_find_db_resolves_relative_scada_timeseries_files_against_workspace(
    monkeypatch, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "obs.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    cfg = {
        "sqlite_paths": [],
        "scan_dirs": [],
        "knowledge": {"scada_timeseries": {"files": [{"path": "data/obs.db"}]}},
    }

    assert target._find_db(cfg) == str(db_path.resolve())


def test_find_db_prefers_explicit_sqlite_paths_over_scan_dirs(tmp_path: Path) -> None:
    explicit_db = tmp_path / "explicit.db"
    conn = sqlite3.connect(explicit_db)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    conn.commit()
    conn.close()

    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    scanned_db = scan_dir / "hydromind.db"
    conn = sqlite3.connect(scanned_db)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    conn.commit()
    conn.close()

    cfg = {
        "sqlite_paths": [str(explicit_db)],
        "scan_dirs": [str(scan_dir)],
        "knowledge": {},
    }

    assert target._find_db(cfg) == str(explicit_db.resolve())


def test_run_coupled_reports_ambiguous_observation_aliases_as_degraded(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    rows = []
    for i in range(240):
        rows.append(("prefix/XHH-001", f"2026-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00", 100.0 + i * 0.01, 50.0 + i * 0.02))
        rows.append(("archive/XHH-001", f"2026-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00", 110.0 + i * 0.01, 60.0 + i * 0.02))
    conn.executemany("INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda case_id, config_path=None: {"sqlite_paths": [str(db_path)], "scan_dirs": [], "knowledge": {}},
    )
    monkeypatch.setattr(
        target,
        "_load_d2_params",
        lambda case_id: {
            "XHH-001": {"A_eff": 1000.0, "alpha": 1.0, "k_area": 0.0, "lag": 0, "beta": 0.0}
        },
    )
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "write_json", lambda path, payload: path)
    monkeypatch.setattr(target, "save_knowledge_file", lambda *args, **kwargs: None)

    report = target.run_coupled("xuhonghe")

    assert report["status"] == "degraded"
    assert report["summary"]["n_stations"] == 0
    assert report["skipped_stations"][0]["station_id"] == "XHH-001"
    assert report["skipped_stations"][0]["reason"] == "ambiguous_observation_station_aliases"


def test_run_coupled_degrades_when_observations_only_expose_single_generic_q(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    rows = []
    for i in range(240):
        rows.append(("prefix/XHH-001", f"2026-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00", 100.0 + i * 0.01, 50.0 + i * 0.02))
    conn.executemany("INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda case_id, config_path=None: {"sqlite_paths": [str(db_path)], "scan_dirs": [], "knowledge": {}},
    )
    monkeypatch.setattr(
        target,
        "_load_d2_params",
        lambda case_id: {
            "XHH-001": {"A_eff": 1000.0, "alpha": 1.0, "k_area": 0.0, "lag": 0, "beta": 0.0}
        },
    )
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "write_json", lambda path, payload: path)
    monkeypatch.setattr(target, "save_knowledge_file", lambda *args, **kwargs: None)

    report = target.run_coupled("xuhonghe")

    assert report["status"] == "degraded"
    assert report["summary"]["n_stations"] == 0
    assert report["summary"]["n_skipped_stations"] == 1
    assert report["skipped_stations"][0]["station_id"] == "XHH-001"
    assert report["skipped_stations"][0]["reason"] == "ambiguous_observation_flow_column"


def test_run_coupled_degrades_when_only_one_flow_uses_generic_q_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL, Q_in REAL)")
    rows = []
    for i in range(240):
        rows.append(("prefix/XHH-001", f"2026-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00", 100.0 + i * 0.01, 50.0 + i * 0.02, 40.0 + i * 0.03))
    conn.executemany("INSERT INTO observations (station, time, Z, Q, Q_in) VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda case_id, config_path=None: {"sqlite_paths": [str(db_path)], "scan_dirs": [], "knowledge": {}},
    )
    monkeypatch.setattr(
        target,
        "_load_d2_params",
        lambda case_id: {
            "XHH-001": {"A_eff": 1000.0, "alpha": 1.0, "k_area": 0.0, "lag": 0, "beta": 0.0}
        },
    )
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "write_json", lambda path, payload: path)
    monkeypatch.setattr(target, "save_knowledge_file", lambda *args, **kwargs: None)

    report = target.run_coupled("xuhonghe")

    assert report["status"] == "degraded"
    assert report["summary"]["n_stations"] == 0
    assert report["summary"]["n_skipped_stations"] == 1
    assert report["skipped_stations"][0]["reason"] == "ambiguous_observation_flow_column"
    assert report["skipped_stations"][0]["variables"] == ["Q_out"]


def test_run_coupled_marks_insufficient_station_data_as_degraded(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL, Q_in REAL, Q_out REAL)")
    rows = []
    for i in range(120):
        rows.append(("prefix/XHH-001", f"2026-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00", 100.0 + i * 0.01, 50.0 + i * 0.02, 40.0 + i * 0.03, 30.0 + i * 0.01))
    conn.executemany("INSERT INTO observations (station, time, Z, Q, Q_in, Q_out) VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda case_id, config_path=None: {"sqlite_paths": [str(db_path)], "scan_dirs": [], "knowledge": {}},
    )
    monkeypatch.setattr(
        target,
        "_load_d2_params",
        lambda case_id: {
            "XHH-001": {"A_eff": 1000.0, "alpha": 1.0, "k_area": 0.0, "lag": 0, "beta": 0.0}
        },
    )
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "write_json", lambda path, payload: path)
    monkeypatch.setattr(target, "save_knowledge_file", lambda *args, **kwargs: None)

    report = target.run_coupled("xuhonghe")

    assert report["status"] == "degraded"
    assert report["summary"]["n_stations"] == 0
    assert report["summary"]["n_skipped_stations"] == 1
    assert report["skipped_stations"][0]["station_id"] == "XHH-001"
    assert report["skipped_stations"][0]["reason"] == "insufficient_station_data"
    assert report["skipped_stations"][0]["n_steps"] == 120


def test_run_coupled_reports_missing_expected_station_metadata_as_degraded(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
    rows = []
    for i in range(240):
        rows.append(("OTHER-001", f"2026-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00", 100.0 + i * 0.01, 50.0 + i * 0.02))
    conn.executemany("INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda case_id, config_path=None: {"sqlite_paths": [str(db_path)], "scan_dirs": [], "knowledge": {}},
    )
    monkeypatch.setattr(
        target,
        "_load_d2_params",
        lambda case_id: {
            "XHH-001": {"A_eff": 1000.0, "alpha": 1.0, "k_area": 0.0, "lag": 0, "beta": 0.0}
        },
    )
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "write_json", lambda path, payload: path)
    monkeypatch.setattr(target, "save_knowledge_file", lambda *args, **kwargs: None)

    report = target.run_coupled("xuhonghe")

    assert report["status"] == "degraded"
    assert report["summary"]["n_stations"] == 0
    assert report["summary"]["n_skipped_stations"] == 1
    assert report["skipped_stations"][0]["station_id"] == "XHH-001"
    assert report["skipped_stations"][0]["reason"] == "missing_station_metadata"


def test_run_coupled_applies_coupling_activation_and_reports_it(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(target, "load_case_config", lambda case_id, config_path=None: {})
    monkeypatch.setattr(target, "_find_db", lambda cfg: "dummy.db")
    monkeypatch.setattr(
        target,
        "_load_d2_params",
        lambda case_id: {
            "XHH-001": {"A_eff": 1000.0, "alpha": 1.0, "k_area": 0.0, "lag": 0, "beta": 0.0}
        },
    )
    monkeypatch.setattr(
        target,
        "_resolve_station_meta",
        lambda db_path, cfg, d2_params: {"XHH-001": {"name": "XHH-001", "vars": ["H_up", "Q_in", "Q_out"]}},
    )

    def fake_load_hourly_with_metadata(db_path: str, station_id: str, variable: str):
        if variable == "H_up":
            return target.np.linspace(100.0, 102.39, 240), None
        if variable == "Q_in":
            return target.np.arange(240, dtype=float), None
        return target.np.zeros(240), None

    def fake_reservoir_sim(q_in, q_out, h0, a_eff, alpha, dt=3600.0, k_area=0.0, H_ref=0.0, lag=0, beta=0.0):
        captured["q_driver"] = q_in.copy()
        return target.np.linspace(h0, h0 + 1.0, len(q_in))

    monkeypatch.setattr(target, "_load_hourly_with_metadata", fake_load_hourly_with_metadata)
    monkeypatch.setattr(target, "reservoir_sim", fake_reservoir_sim)
    monkeypatch.setattr(target, "compute_metrics", lambda obs, sim: {"rmse": 0.0, "mae": 0.0, "nse": 1.0, "n": len(obs)})
    monkeypatch.setattr(target, "write_json", lambda path, payload: path)
    monkeypatch.setattr(target, "save_knowledge_file", lambda *args, **kwargs: None)

    activation = {
        "runoff_to_channel_lag": 2.0,
        "channel_inflow_scale": 1.5,
        "coupling_transfer_bias": 3.0,
    }
    report = target.run_coupled("xuhonghe", coupling_activation=activation)

    assert target.np.allclose(captured["q_driver"][:5], target.np.array([3.0, 3.0, 3.0, 4.5, 6.0]))
    assert report["coupling_activation"] == activation
    assert report["status"] == "completed"
    assert report["outcome_status"] == "completed"


def test_run_coupled_uses_station_fallback_when_reservoir_knowledge_missing(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "observations_only.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL, Q_in REAL, Q_out REAL)")
    rows = []
    for i in range(240):
        rows.append(("prefix/XHH-001", f"2026-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00", 100.0 + i * 0.01, 50.0 + i * 0.02, 40.0 + i * 0.03, 30.0 + i * 0.01))
    conn.executemany("INSERT INTO observations (station, time, Z, Q, Q_in, Q_out) VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda case_id, config_path=None: {"sqlite_paths": [str(db_path)], "scan_dirs": [], "knowledge": {}},
    )
    monkeypatch.setattr(
        target,
        "_load_d2_params",
        lambda case_id: {
            "XHH-001": {"A_eff": 1000.0, "alpha": 1.0, "k_area": 0.0, "lag": 0, "beta": 0.0}
        },
    )
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "write_json", lambda path, payload: path)
    monkeypatch.setattr(target, "save_knowledge_file", lambda *args, **kwargs: None)

    report = target.run_coupled("xuhonghe")

    assert "error" not in report
    assert report["summary"]["n_stations"] == 1
    assert "XHH-001" in report["station_results"]
