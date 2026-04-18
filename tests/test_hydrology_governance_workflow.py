import json
import sys
from pathlib import Path

import pytest

import workflows.run_hydrological_simulation as target


def test_run_hydrological_simulation_requires_parameter_governance_json(monkeypatch, tmp_path: Path) -> None:
    data_pack = tmp_path / "data_pack.json"
    data_pack.write_text(json.dumps({"case_id": "daduhe"}), encoding="utf-8")
    sim_config = tmp_path / "simulation.yaml"
    sim_config.write_text("name: demo\n", encoding="utf-8")

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
        ],
    )

    with pytest.raises(SystemExit):
        target.main()



def test_run_hydrological_simulation_loads_hydrology_activation(monkeypatch, tmp_path: Path) -> None:
    data_pack = tmp_path / "data_pack.json"
    data_pack.write_text(json.dumps({"case_id": "daduhe"}), encoding="utf-8")
    sim_config = tmp_path / "simulation.yaml"
    sim_config.write_text("name: demo\n", encoding="utf-8")
    activation = tmp_path / "activation.json"
    activation.write_text(
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
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "stages": {
                    "hydrology": [
                        {"parameter_id": "rainfall_multiplier", "bounds": [0.7, 1.3]},
                        {"parameter_id": "soil_storage_scale", "bounds": [0.5, 1.5]},
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sensitivity = tmp_path / "sensitivity.json"
    sensitivity.write_text(
        json.dumps({"stages": {"hydrology": {"status": "ok"}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    governance = tmp_path / "parameter_governance.json"
    governance.write_text(
        json.dumps(
            {
                "artifact_paths": {
                    "correction_activation_record": str(activation),
                    "parameter_inventory": str(inventory),
                    "sensitivity_report": str(sensitivity),
                },
                "candidate_set": {
                    "hydrology": {
                        "primary_candidates": ["rainfall_multiplier", "soil_storage_scale"],
                        "secondary_candidates": ["baseflow_recession_factor"],
                        "forbidden_candidates": [],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    captured = {}
    monkeypatch.setattr(target, "run_python", lambda path, args: captured.update({"path": str(path), "args": list(args)}))
    monkeypatch.setattr(target, "_load_real_hydrology_series", lambda case_id: ([1.0, 2.0], [1.1, 1.9], {"start": "2026-01-01", "end": "2026-01-02", "count": 2}))
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

    assert captured["args"][0] == str(sim_config)
