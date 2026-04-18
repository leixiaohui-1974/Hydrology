from pathlib import Path

from hydro_model.parameter_governance import (
    ParameterDefinition,
    StageGovernanceArtifact,
    analyze_local_sensitivity,
    freeze_candidate_set,
    screen_parameters,
)


def test_parameter_definition_round_trips_to_json(tmp_path: Path) -> None:
    artifact = StageGovernanceArtifact(
        case_id="daduhe",
        stage="watershed_delineation",
        parameters=[
            ParameterDefinition(
                parameter_id="area_correction_factor",
                stage="watershed_delineation",
                category="correction_parameter",
                physical_meaning="Scale residual basin-area mismatch after topology cleanup.",
                unit="ratio",
                default_value=1.0,
                bounds=(0.8, 1.2),
                source_of_truth="cases/daduhe/contracts/basin_validation.latest.json",
                sensitivity_enabled=True,
                calibration_enabled=True,
                assimilation_enabled=False,
                error_model_role="structural_correction",
                dependencies=["basin_validation_json"],
                validation_metric_links=["area_closure_error"],
            )
        ],
        metadata={"mode": "pilot"},
    )

    payload = artifact.to_dict()
    assert payload["stage"] == "watershed_delineation"
    assert payload["parameters"][0]["parameter_id"] == "area_correction_factor"
    assert payload["parameters"][0]["bounds"] == [0.8, 1.2]


def test_screen_parameters_excludes_locked_and_non_sensitive_values() -> None:
    parameters = [
        ParameterDefinition(
            parameter_id="stream_threshold",
            stage="watershed_delineation",
            category="physical_parameter",
            physical_meaning="Controls river extraction density.",
            unit="cells",
            default_value=100.0,
            bounds=(50.0, 200.0),
            source_of_truth="data_pack.delineation_params",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
        ),
        ParameterDefinition(
            parameter_id="dem_path",
            stage="watershed_delineation",
            category="configuration",
            physical_meaning="Resolved DEM input path.",
            unit="path",
            default_value="cases/daduhe/source_selection/product_outputs/dem.tif",
            bounds=None,
            source_of_truth="data_pack.dem_path",
            sensitivity_enabled=False,
            calibration_enabled=False,
            assimilation_enabled=False,
        ),
    ]

    screened = screen_parameters(parameters)
    assert [item.parameter_id for item in screened] == ["stream_threshold"]



def test_freeze_candidate_set_marks_high_risk_parameters_forbidden() -> None:
    findings = [
        {"parameter_id": "stream_threshold", "score": 0.63, "physics_risk_flag": False},
        {"parameter_id": "area_correction_factor", "score": 0.55, "physics_risk_flag": False},
        {"parameter_id": "observation_bias", "score": 0.72, "physics_risk_flag": True},
    ]

    frozen = freeze_candidate_set(findings, primary_limit=2)
    assert frozen["primary_candidates"] == ["stream_threshold", "area_correction_factor"]
    assert frozen["forbidden_candidates"] == ["observation_bias"]



def test_analyze_local_sensitivity_ranks_larger_metric_change_higher() -> None:
    parameters = {
        "stream_threshold": 100.0,
        "snap_distance": 250.0,
    }

    def evaluator(values: dict[str, float]) -> float:
        return abs(values["stream_threshold"] - 120.0) / 120.0 + abs(values["snap_distance"] - 250.0) / 250.0

    findings = analyze_local_sensitivity(parameters, evaluator, perturbation=0.1)
    assert findings[0]["parameter_id"] == "snap_distance"
    assert findings[0]["score"] >= findings[1]["score"]
