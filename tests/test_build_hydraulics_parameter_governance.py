import json
import sys
from pathlib import Path

import workflows.build_hydraulics_parameter_governance as target


def test_build_hydraulics_parameter_governance_outputs_gate(tmp_path: Path, monkeypatch) -> None:
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
    calibration = tmp_path / "hydraulic_calibration.latest.json"
    calibration.write_text(
        json.dumps(
            {
                "station_results": {
                    "s1": {
                        "validation": {
                            "nse": 0.9,
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "hydraulics_parameter_governance.latest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_hydraulics_parameter_governance.py",
            "--case-id",
            "daduhe",
            "--parameter-governance-json",
            str(governance),
            "--hydraulic-calibration-json",
            str(calibration),
            "--output-json",
            str(out),
        ],
    )

    target.main()

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate_key"] == "hydraulics"
    assert payload["gate_status"] == "pass"
    assert payload["quality_gate_passed"] is True
