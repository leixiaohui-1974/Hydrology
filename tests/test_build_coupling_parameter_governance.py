import json
import sys
from pathlib import Path

import workflows.build_coupling_parameter_governance as target


def test_build_coupling_parameter_governance_outputs_gate(tmp_path: Path, monkeypatch) -> None:
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
                    "coupling": {
                        "primary_candidates": ["runoff_to_channel_lag", "channel_inflow_scale"],
                        "secondary_candidates": ["coupling_transfer_bias"],
                        "forbidden_candidates": [],
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    coupled = tmp_path / "coupled_hydro_hydraulic.latest.json"
    coupled.write_text(
        json.dumps(
            {
                "station_results": {
                    "s1": {
                        "overall": {
                            "nse": 0.9,
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "coupling_parameter_governance.latest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_coupling_parameter_governance.py",
            "--case-id",
            "daduhe",
            "--parameter-governance-json",
            str(governance),
            "--candidate-set-json",
            str(candidate_set),
            "--coupled-result-json",
            str(coupled),
            "--output-json",
            str(out),
        ],
    )

    target.main()

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate_key"] == "coupling"
    assert payload["gate_status"] == "pass"
    assert payload["quality_gate_passed"] is True
