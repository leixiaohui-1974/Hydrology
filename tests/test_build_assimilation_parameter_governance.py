import json
import sys
from pathlib import Path

import workflows.build_assimilation_parameter_governance as target


def test_build_assimilation_parameter_governance_outputs_gate(tmp_path: Path, monkeypatch) -> None:
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
    governance = tmp_path / "parameter_governance.latest.json"
    governance.write_text(
        json.dumps(
            {
                "artifact_paths": {
                    "correction_activation_record": str(activation),
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    candidate_set = tmp_path / "candidate_set.latest.json"
    candidate_set.write_text(
        json.dumps(
            {
                "stages": {
                    "assimilation": {
                        "primary_candidates": ["process_noise_scale", "observation_noise_scale"],
                        "secondary_candidates": ["initial_state_bias", "observation_bias"],
                        "forbidden_candidates": [],
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_estimation = tmp_path / "state_estimation.latest.json"
    state_estimation.write_text(
        json.dumps(
            {
                "stations": {"s1": {"status": "completed"}},
                "summary": {"completed": 1, "converged": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    hydraulic_assimilation = tmp_path / "hydraulic_assimilation.latest.json"
    hydraulic_assimilation.write_text(
        json.dumps(
            {
                "summary": {"improved_count": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    coupled_assimilation = tmp_path / "coupled_assimilation.latest.json"
    coupled_assimilation.write_text(
        json.dumps(
            {
                "station_results": [{"station_id": "s1"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "assimilation_parameter_governance.latest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_assimilation_parameter_governance.py",
            "--case-id",
            "daduhe",
            "--parameter-governance-json",
            str(governance),
            "--candidate-set-json",
            str(candidate_set),
            "--state-estimation-json",
            str(state_estimation),
            "--hydraulic-assimilation-json",
            str(hydraulic_assimilation),
            "--coupled-assimilation-json",
            str(coupled_assimilation),
            "--output-json",
            str(out),
        ],
    )

    target.main()

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate_key"] == "assimilation"
    assert payload["gate_status"] == "pass"
    assert payload["quality_gate_passed"] is True
