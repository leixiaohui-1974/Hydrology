import json
import sys
from pathlib import Path

import pytest

import workflows.run_hydraulic_simulation as target


def test_run_hydraulic_simulation_requires_parameter_governance_json(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    monkeypatch.setattr(target, "run_simulation", lambda case_id, mode="all", hydraulics_activation=None: captured.update({"case_id": case_id, "mode": mode, "hydraulics_activation": hydraulics_activation}) or {"replay": {}, "cascade": {}})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_hydraulic_simulation.py",
            "--case-id",
            "daduhe",
        ],
    )

    with pytest.raises(SystemExit):
        target.main()



def test_run_hydraulic_simulation_loads_hydraulics_activation(monkeypatch, tmp_path: Path) -> None:
    activation = tmp_path / "activation.json"
    activation.write_text(
        json.dumps(
            {
                "hydraulics": {
                    "manning_n_scale": 1.0,
                    "boundary_inflow_bias": 1.0,
                    "section_geometry_scale": 1.0,
                    "section_substitute_mode": "observed",
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
                "artifact_paths": {
                    "correction_activation_record": str(activation),
                },
                "candidate_set": {
                    "hydraulics": {
                        "primary_candidates": ["manning_n_scale", "section_geometry_scale"],
                        "secondary_candidates": ["boundary_inflow_bias"],
                        "forbidden_candidates": [],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    captured = {}
    monkeypatch.setattr(target, "run_simulation", lambda case_id, mode="all", hydraulics_activation=None: captured.update({"case_id": case_id, "mode": mode, "hydraulics_activation": hydraulics_activation}) or {"replay": {}, "cascade": {}})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_hydraulic_simulation.py",
            "--case-id",
            "daduhe",
            "--parameter-governance-json",
            str(governance),
        ],
    )

    target.main()

    assert captured["case_id"] == "daduhe"
    assert captured["hydraulics_activation"]["section_substitute_mode"] == "observed"
