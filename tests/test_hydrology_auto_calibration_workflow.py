import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import pytest

import workflows.run_hydrological_simulation as target


ALLOWED_PARAMETERS = [
    "rainfall_multiplier",
    "soil_storage_scale",
    "baseflow_recession_factor",
]


def _write_activation(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "hydrology": {
                    "rainfall_multiplier": 1.0,
                    "soil_storage_scale": 1.0,
                    "baseflow_recession_factor": 1.0,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_inventory(path: Path, parameters: list[dict]) -> None:
    path.write_text(
        json.dumps({"stages": {"hydrology": parameters}}, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_sensitivity(path: Path) -> None:
    path.write_text(
        json.dumps({"stages": {"hydrology": {"status": "ok"}}}, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_governance(
    path: Path,
    activation: Path,
    inventory: Optional[Path],
    primary_candidates: list[str],
    *,
    sensitivity: Optional[Path] = None,
    workflow_recommendations: Optional[dict] = None,
) -> None:
    artifact_paths = {
        "correction_activation_record": str(activation),
    }
    if inventory is not None:
        artifact_paths["parameter_inventory"] = str(inventory)
    if sensitivity is not None:
        artifact_paths["sensitivity_report"] = str(sensitivity)

    path.write_text(
        json.dumps(
            {
                "artifact_paths": artifact_paths,
                "workflow_recommendations": workflow_recommendations
                or {
                    "suggested_workflows": ["model"],
                    "supports_auto_modeling_hints": True,
                    "stage_activation_guidance": {
                        "hydrology": {
                            "status": "recommended",
                            "matched_workflows": ["model"],
                        }
                    },
                },
                "candidate_set": {
                    "hydrology": {
                        "primary_candidates": primary_candidates,
                        "secondary_candidates": ["baseflow_recession_factor"],
                        "forbidden_candidates": [],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_observation_sqlite(path: Path, *, time_step: str = "1D") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE stations (
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
            INSERT INTO stations (id, name, station_type, source, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "15005012",
                    "五角枫调压塔水位-A",
                    "open_channel",
                    "station_meta.csv",
                    json.dumps({"station_name": "五角枫调压塔水位-A"}, ensure_ascii=False),
                ),
                (
                    "24001201",
                    "取水口",
                    "open_channel",
                    "station_meta.csv",
                    json.dumps({"station_name": "取水口"}, ensure_ascii=False),
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO timeseries_meta
            (station_id, variable, unit, time_step, start_time, end_time, n_records, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("15005012", "flow", "m3/s", time_step, "2025-07-01 00:00:00", "2025-07-03 00:00:00", 3, "observed_flow.csv"),
                ("15005012", "water_level", "m", time_step, "2025-07-01 00:00:00", "2025-07-03 00:00:00", 3, "observed_water_level.csv"),
                ("15005012", "velocity", "m/s", time_step, "2025-07-01 00:00:00", "2025-07-03 00:00:00", 3, "observed_velocity.csv"),
                ("24001201", "flow", "m3/s", time_step, "2025-07-01 00:00:00", "2025-07-03 00:00:00", 3, "observed_flow.csv"),
                ("24001201", "water_level", "m", time_step, "2025-07-01 00:00:00", "2025-07-03 00:00:00", 3, "observed_water_level.csv"),
                ("24001201", "velocity", "m/s", time_step, "2025-07-01 00:00:00", "2025-07-03 00:00:00", 3, "observed_velocity.csv"),
            ],
        )
        rows = []
        active_samples = {
            "flow": [3.2, 3.6, 4.1],
            "water_level": [347.2, 347.5, 347.8],
            "velocity": [1.0, 1.1, 1.2],
        }
        comparison_samples = {
            "flow": [3.0, 3.3, 3.7],
            "water_level": [282.0, 282.0, 282.0],
            "velocity": [0.0, 0.0, 0.0],
        }
        for station_id, samples in [("15005012", comparison_samples), ("24001201", active_samples)]:
            for variable, values in samples.items():
                for index, value in enumerate(values, start=1):
                    rows.append(
                        (
                            station_id,
                            variable,
                            time_step,
                            f"2025-07-0{index} 00:00:00",
                            value,
                            1,
                        )
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


def test_run_hydrological_simulation_requires_hydrology_primary_candidates_for_closure(
    monkeypatch, tmp_path: Path
) -> None:
    data_pack = tmp_path / "data_pack.json"
    data_pack.write_text(json.dumps({"case_id": "daduhe"}), encoding="utf-8")
    sim_config = tmp_path / "simulation.yaml"
    sim_config.write_text("name: demo\n", encoding="utf-8")
    activation = tmp_path / "activation.json"
    _write_activation(activation)
    inventory = tmp_path / "inventory.json"
    _write_inventory(
        inventory,
        [
            {"parameter_id": "rainfall_multiplier", "bounds": [0.7, 1.3]},
            {"parameter_id": "soil_storage_scale", "bounds": [0.5, 1.5]},
            {"parameter_id": "baseflow_recession_factor", "bounds": [0.7, 1.3]},
        ],
    )
    sensitivity = tmp_path / "sensitivity.json"
    _write_sensitivity(sensitivity)
    governance = tmp_path / "parameter_governance.json"
    _write_governance(governance, activation, inventory, [], sensitivity=sensitivity)

    monkeypatch.setattr(target, "run_python", lambda path, args: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_hydrological_simulation.py",
            "--case-id",
            "daduhe",
            "--data-pack-json",
            str(data_pack),
            "--simulation-config",
            str(sim_config),
            "--parameter-governance-json",
            str(governance),
        ],
    )

    with pytest.raises(ValueError, match="hydrology primary_candidates"):
        target.main()


def test_build_hydrology_closure_param_space_uses_inventory_artifact(tmp_path: Path) -> None:
    activation = tmp_path / "activation.json"
    _write_activation(activation)
    inventory = tmp_path / "inventory.json"
    _write_inventory(
        inventory,
        [
            {"parameter_id": "rainfall_multiplier", "bounds": [0.7, 1.3]},
            {"parameter_id": "soil_storage_scale", "bounds": [0.5, 1.5]},
            {"parameter_id": "baseflow_recession_factor", "bounds": [0.7, 1.3]},
        ],
    )
    governance = tmp_path / "parameter_governance.json"
    _write_governance(governance, activation, inventory, ["rainfall_multiplier", "soil_storage_scale"])

    param_space = target._build_hydrology_closure_param_space(json.loads(governance.read_text(encoding="utf-8")))

    assert param_space == {
        "rainfall_multiplier": (0.7, 1.3, 5),
        "soil_storage_scale": (0.5, 1.5, 5),
    }


def test_build_hydrology_closure_param_space_rejects_non_whitelisted_candidates(tmp_path: Path) -> None:
    activation = tmp_path / "activation.json"
    _write_activation(activation)
    inventory = tmp_path / "inventory.json"
    _write_inventory(
        inventory,
        [
            {"parameter_id": "rainfall_multiplier", "bounds": [0.7, 1.3]},
            {"parameter_id": "surface_roughness_scale", "bounds": [0.5, 1.5]},
        ],
    )
    governance = tmp_path / "parameter_governance.json"
    _write_governance(governance, activation, inventory, ["rainfall_multiplier", "surface_roughness_scale"])

    with pytest.raises(ValueError, match="only allows"):
        target._build_hydrology_closure_param_space(json.loads(governance.read_text(encoding="utf-8")))


def test_run_hydrological_simulation_requires_parameter_inventory_for_closure(monkeypatch, tmp_path: Path) -> None:
    data_pack = tmp_path / "data_pack.json"
    data_pack.write_text(json.dumps({"case_id": "daduhe"}), encoding="utf-8")
    sim_config = tmp_path / "simulation.yaml"
    sim_config.write_text("name: demo\n", encoding="utf-8")
    activation = tmp_path / "activation.json"
    _write_activation(activation)
    sensitivity = tmp_path / "sensitivity.json"
    _write_sensitivity(sensitivity)
    governance = tmp_path / "parameter_governance.json"
    _write_governance(governance, activation, None, ["rainfall_multiplier"], sensitivity=sensitivity)

    monkeypatch.setattr(target, "run_python", lambda path, args: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_hydrological_simulation.py",
            "--case-id",
            "daduhe",
            "--data-pack-json",
            str(data_pack),
            "--simulation-config",
            str(sim_config),
            "--parameter-governance-json",
            str(governance),
        ],
    )

    with pytest.raises(ValueError, match="parameter_inventory"):
        target.main()


def test_load_real_hydrology_series_prefers_real_observation_bundle_for_yinchuojiliao(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "yinchuojiliao_hydromind.sqlite3"
    _write_observation_sqlite(db_path)

    monkeypatch.setattr(target, "load_case_config", lambda case_id: {"case_id": case_id, "sqlite_paths": [str(db_path)]})
    monkeypatch.setattr(target, "_find_hydromind_sqlite", lambda cfg: db_path)

    input_series, observed, data_window = target._load_real_hydrology_series("yinchuojiliao")

    assert input_series.tolist() == [3.2, 3.6, 4.1]
    assert observed.tolist() == [347.2, 347.5, 347.8]
    assert data_window["station_id"] == "24001201"
    assert data_window["input_variable"] == "flow"
    assert data_window["observed_variable"] == "water_level"
    assert data_window["time_step"] == "1D"


def test_load_real_hydrology_series_accepts_non_daily_real_observation_bundle(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "yinchuojiliao_hydromind.sqlite3"
    _write_observation_sqlite(db_path, time_step="1min")

    monkeypatch.setattr(target, "load_case_config", lambda case_id: {"case_id": case_id, "sqlite_paths": [str(db_path)]})
    monkeypatch.setattr(target, "_find_hydromind_sqlite", lambda cfg: db_path)

    input_series, observed, data_window = target._load_real_hydrology_series("yinchuojiliao")

    assert input_series.tolist() == [3.2, 3.6, 4.1]
    assert observed.tolist() == [347.2, 347.5, 347.8]
    assert data_window["station_id"] == "24001201"
    assert data_window["time_step"] == "1min"


def test_load_real_hydrology_series_prefers_explicit_case_binding_over_heuristic(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "yinchuojiliao_hydromind.sqlite3"
    _write_observation_sqlite(db_path)

    cfg = {
        "case_id": "yinchuojiliao",
        "sqlite_paths": [str(db_path)],
        "modeling": {
            "hydrology": {
                "closure_binding": {
                    "time_step": "1D",
                    "input": {
                        "station_id": "24001201",
                        "station_name": "取水口",
                        "variable": "flow",
                    },
                    "observed": {
                        "station_id": "15005012",
                        "station_name": "五角枫调压塔水位-A",
                        "variable": "flow",
                    },
                }
            }
        },
    }
    monkeypatch.setattr(target, "load_case_config", lambda case_id, config_path=None: cfg)
    monkeypatch.setattr(target, "_find_hydromind_sqlite", lambda case_cfg: db_path)

    input_series, observed, data_window = target._load_real_hydrology_series("yinchuojiliao")

    assert input_series.tolist() == [3.2, 3.6, 4.1]
    assert observed.tolist() == [3.0, 3.3, 3.7]
    assert data_window["input_station_id"] == "24001201"
    assert data_window["input_station_name"] == "取水口"
    assert data_window["observed_station_id"] == "15005012"
    assert data_window["observed_station_name"] == "五角枫调压塔水位-A"
    assert data_window["input_variable"] == "flow"
    assert data_window["observed_variable"] == "flow"
    assert data_window["selection_mode"] == "explicit_case_binding"
    assert data_window["time_step"] == "1D"


def test_run_hydrological_simulation_writes_case_facing_calibration_result(monkeypatch, tmp_path: Path) -> None:
    data_pack = tmp_path / "data_pack.json"
    data_pack.write_text(json.dumps({"case_id": "daduhe"}), encoding="utf-8")
    sim_config = tmp_path / "simulation.yaml"
    sim_config.write_text("name: demo\n", encoding="utf-8")
    activation = tmp_path / "activation.json"
    _write_activation(activation)
    inventory = tmp_path / "inventory.json"
    _write_inventory(
        inventory,
        [
            {"parameter_id": "rainfall_multiplier", "bounds": [0.7, 1.3]},
            {"parameter_id": "soil_storage_scale", "bounds": [0.5, 1.5]},
            {"parameter_id": "baseflow_recession_factor", "bounds": [0.7, 1.3]},
        ],
    )
    sensitivity = tmp_path / "sensitivity.json"
    _write_sensitivity(sensitivity)
    governance = tmp_path / "parameter_governance.json"
    _write_governance(
        governance,
        activation,
        inventory,
        ["rainfall_multiplier", "soil_storage_scale"],
        sensitivity=sensitivity,
    )

    contracts_dir = tmp_path / "cases" / "daduhe" / "contracts"
    contracts_dir.mkdir(parents=True)

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "run_python", lambda path, args: None)
    monkeypatch.setattr(
        target,
        "_load_real_hydrology_series",
        lambda case_id, case_config=None: (
            [1.0, 2.0, 3.0],
            [1.1, 1.9, 3.2],
            {
                "start": "2026-01-01",
                "end": "2026-01-03",
                "count": 3,
                "selection_mode": "explicit_case_binding",
                "input_station_id": "24001201",
                "observed_station_id": "15005012",
            },
        ),
    )
    monkeypatch.setattr(
        target,
        "run_full_cv",
        lambda **kwargs: {
            "best_params": {"rainfall_multiplier": 1.05, "soil_storage_scale": 0.95},
            "best_objective": 0.82,
            "calibration_metrics": {"nse": 0.82},
            "validation_metrics": {"nse": 0.77},
            "param_space": kwargs["param_space"],
            "progressive_rounds": 2,
            "assessment": {"consistency": "稳定"},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_hydrological_simulation.py",
            "--case-id",
            "daduhe",
            "--data-pack-json",
            str(data_pack),
            "--simulation-config",
            str(sim_config),
            "--parameter-governance-json",
            str(governance),
        ],
    )

    target.main()

    result_path = contracts_dir / "hydrology_calibration.latest.json"
    assert result_path.exists()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["workflow"] == "hydrology_calibration"
    assert payload["best_params"]["rainfall_multiplier"] == 1.05
    assert payload["optimized_parameters"] == ["rainfall_multiplier", "soil_storage_scale"]
    assert payload["data_window"]["count"] == 3
    assert payload["data_window"]["selection_mode"] == "explicit_case_binding"
    assert payload["data_window"]["input_station_id"] == "24001201"
    assert payload["data_window"]["observed_station_id"] == "15005012"
    assert payload["hydrology_stage_guidance"]["status"] == "recommended"
    assert payload["workflow_recommendations"]["supports_auto_modeling_hints"] is True

    evidence_path = contracts_dir / "hydrology_nse_evidence.latest.json"
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["case_id"] == "daduhe"
    assert evidence["source_workflow"] == "hydrology_calibration"
    assert evidence["comparable_nse"] == 0.77
    assert evidence["stations"][0]["station_id"] == "15005012"
    assert evidence["stations"][0]["validation_nse"] == 0.77
    assert evidence["stations"][0]["selection_mode"] == "explicit_case_binding"

    report_path = contracts_dir / "hydrology_calibration_report.md"
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "Slice scope" in report
    assert "Initial vs best" in report
    assert "Calibration metrics" in report
    assert "Validation metrics" in report
    assert "Interpretation" in report
    assert "Governance recommendation" in report
    assert "Hydrology stage guidance: recommended" in report
