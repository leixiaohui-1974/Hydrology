import json
import sys
from pathlib import Path

import workflows.run_data_assimilation as target



def test_run_data_assimilation_requires_parameter_governance_json(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_data_assimilation.py",
            "--case-id",
            "daduhe",
        ],
    )

    try:
        target.main()
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("Expected assimilation runner to require parameter governance input")



def test_run_data_assimilation_loads_assimilation_activation(monkeypatch, tmp_path: Path) -> None:
    activation = tmp_path / "activation.json"
    activation.write_text(
        json.dumps(
            {
                "assimilation": {
                    "process_noise_scale": 0.1,
                    "observation_noise_scale": 0.1,
                    "observation_bias": 0.0,
                    "initial_state_bias": 0.0,
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
                    "assimilation": {
                        "primary_candidates": ["process_noise_scale", "observation_noise_scale"],
                        "secondary_candidates": ["initial_state_bias", "observation_bias"],
                        "forbidden_candidates": [],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    captured = {}
    monkeypatch.setattr(target, "run_data_assimilation", lambda case_id, config_path=None, methods=None, targets=None, process_noise=0.1, meas_noise=0.5, dt_seconds=3600.0, parameter_governance=None: captured.update({"case_id": case_id, "parameter_governance": parameter_governance}) or {"status": "completed"})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_data_assimilation.py",
            "--case-id",
            "daduhe",
            "--parameter-governance-json",
            str(governance),
        ],
    )

    target.main()

    assert captured["parameter_governance"]["process_noise_scale"] == 0.1
