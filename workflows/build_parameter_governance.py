from __future__ import annotations

import argparse
import json
from pathlib import Path

from hydro_model.parameter_governance import (
    ParameterDefinition,
    StageGovernanceArtifact,
    analyze_local_sensitivity,
    freeze_candidate_set,
    screen_parameters,
    write_json,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build parameter governance artifacts for a case.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--case-manifest", required=True)
    parser.add_argument("--data-pack-json", required=True)
    return parser



def _contracts_dir(case_manifest: Path) -> Path:
    return case_manifest.parent / "contracts"



def _watershed_parameters(data_pack: dict) -> list[ParameterDefinition]:
    delineation = data_pack.get("delineation_params", {}) or {}
    return [
        ParameterDefinition(
            parameter_id="stream_threshold",
            stage="watershed_delineation",
            category="physical_parameter",
            physical_meaning="Controls river extraction density for WhiteboxTools delineation.",
            unit="cells",
            default_value=float(delineation.get("stream_threshold", 100.0)),
            bounds=(50.0, 300.0),
            source_of_truth="data_pack.delineation_params.stream_threshold",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["area_closure_error"],
        ),
        ParameterDefinition(
            parameter_id="snap_distance",
            stage="watershed_delineation",
            category="physical_parameter",
            physical_meaning="Controls outlet snapping tolerance before delineation.",
            unit="meters",
            default_value=float(delineation.get("snap_distance", 250.0)),
            bounds=(50.0, 1000.0),
            source_of_truth="data_pack.delineation_params.snap_distance",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["outlet_dem_compatibility"],
        ),
        ParameterDefinition(
            parameter_id="area_correction_factor",
            stage="watershed_delineation",
            category="correction_parameter",
            physical_meaning="Scale residual basin-area mismatch after topology cleanup.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.8, 1.2),
            source_of_truth="cases/<case_id>/contracts/basin_validation.latest.json",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            error_model_role="structural_correction",
            validation_metric_links=["area_closure_error"],
        ),
    ]



def _hydrology_parameters() -> list[ParameterDefinition]:
    return [
        ParameterDefinition(
            parameter_id="rainfall_multiplier",
            stage="hydrology",
            category="physical_parameter",
            physical_meaning="Scales hydrologic forcing intensity before runoff generation.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.7, 1.3),
            source_of_truth="hydrology.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["nse", "kge", "bias"],
        ),
        ParameterDefinition(
            parameter_id="soil_storage_scale",
            stage="hydrology",
            category="physical_parameter",
            physical_meaning="Scales effective soil storage capacity before release.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.5, 1.5),
            source_of_truth="hydrology.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["nse", "kge", "bias"],
        ),
        ParameterDefinition(
            parameter_id="baseflow_recession_factor",
            stage="hydrology",
            category="physical_parameter",
            physical_meaning="Controls gradual hydrologic recession behavior.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.7, 1.3),
            source_of_truth="hydrology.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["rmse", "low_flow_bias"],
        ),
    ]



def _hydraulics_parameters() -> list[ParameterDefinition]:
    return [
        ParameterDefinition(
            parameter_id="manning_n_scale",
            stage="hydraulics",
            category="physical_parameter",
            physical_meaning="Scales hydraulic roughness consistently across the current network.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.7, 1.3),
            source_of_truth="hydraulics.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["rmse", "peak_magnitude_error"],
        ),
        ParameterDefinition(
            parameter_id="boundary_inflow_bias",
            stage="hydraulics",
            category="correction_parameter",
            physical_meaning="Captures systematic hydraulic boundary inflow mismatch.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.8, 1.2),
            source_of_truth="hydraulics.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            error_model_role="bias",
            validation_metric_links=["boundary_bias", "peak_magnitude_error"],
        ),
        ParameterDefinition(
            parameter_id="section_geometry_scale",
            stage="hydraulics",
            category="correction_parameter",
            physical_meaning="Scales imperfect observed cross-section geometry before substitution is considered.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.8, 1.2),
            source_of_truth="hydraulics.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            error_model_role="structural_correction",
            validation_metric_links=["wetted_area_error", "stage_discharge_bias"],
        ),
        ParameterDefinition(
            parameter_id="section_substitute_mode",
            stage="hydraulics",
            category="structural_state",
            physical_meaning="Declares whether current sections are observed, simplified, or proxy-based.",
            unit="enum",
            default_value="observed",
            bounds=None,
            source_of_truth="hydraulics.governance.default",
            sensitivity_enabled=False,
            calibration_enabled=False,
            assimilation_enabled=False,
            error_model_role="structural_state",
            validation_metric_links=["section_confidence"],
        ),
    ]



def _coupling_parameters() -> list[ParameterDefinition]:
    return [
        ParameterDefinition(
            parameter_id="runoff_to_channel_lag",
            stage="coupling",
            category="transfer_parameter",
            physical_meaning="Shifts D1 runoff timing before D2 channel input.",
            unit="hours",
            default_value=0.0,
            bounds=(0.0, 24.0),
            source_of_truth="coupling.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["peak_timing_error"],
        ),
        ParameterDefinition(
            parameter_id="channel_inflow_scale",
            stage="coupling",
            category="correction_parameter",
            physical_meaning="Scales D1 runoff magnitude before it becomes D2 inflow.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.8, 1.2),
            source_of_truth="coupling.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            error_model_role="scaling_correction",
            validation_metric_links=["peak_magnitude_error", "bias"],
        ),
        ParameterDefinition(
            parameter_id="coupling_transfer_bias",
            stage="coupling",
            category="correction_parameter",
            physical_meaning="Captures residual transfer mismatch after lag and scale corrections.",
            unit="ratio",
            default_value=0.0,
            bounds=(-0.2, 0.2),
            source_of_truth="coupling.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            error_model_role="bias",
            validation_metric_links=["bias", "rmse"],
        ),
    ]



def _assimilation_parameters() -> list[ParameterDefinition]:
    return [
        ParameterDefinition(
            parameter_id="process_noise_scale",
            stage="assimilation",
            category="assimilation_parameter",
            physical_meaning="Scales process uncertainty in the state estimator.",
            unit="ratio",
            default_value=0.1,
            bounds=(0.01, 1.0),
            source_of_truth="assimilation.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=True,
            error_model_role="process_noise",
            validation_metric_links=["rmse", "state_stability"],
        ),
        ParameterDefinition(
            parameter_id="observation_noise_scale",
            stage="assimilation",
            category="assimilation_parameter",
            physical_meaning="Scales observation uncertainty in the estimator.",
            unit="ratio",
            default_value=0.1,
            bounds=(0.01, 1.0),
            source_of_truth="assimilation.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=True,
            error_model_role="observation_noise",
            validation_metric_links=["rmse", "innovation_consistency"],
        ),
        ParameterDefinition(
            parameter_id="observation_bias",
            stage="assimilation",
            category="correction_parameter",
            physical_meaning="Captures persistent observation offset not explained by noise.",
            unit="ratio",
            default_value=0.0,
            bounds=(-0.2, 0.2),
            source_of_truth="assimilation.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=True,
            error_model_role="bias",
            validation_metric_links=["bias", "innovation_consistency"],
        ),
        ParameterDefinition(
            parameter_id="initial_state_bias",
            stage="assimilation",
            category="assimilation_parameter",
            physical_meaning="Corrects state mismatch at the beginning of the assimilation window.",
            unit="ratio",
            default_value=0.0,
            bounds=(-0.3, 0.3),
            source_of_truth="assimilation.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=True,
            error_model_role="state_initialization",
            validation_metric_links=["rmse", "state_stability"],
        ),
    ]



def _stage_templates() -> dict[str, list[dict[str, object]]]:
    return {
        "hydrology": [item.to_dict() for item in _hydrology_parameters()],
        "hydraulics": [item.to_dict() for item in _hydraulics_parameters()],
        "coupling": [item.to_dict() for item in _coupling_parameters()],
        "assimilation": [item.to_dict() for item in _assimilation_parameters()],
    }



def main() -> None:
    args = _build_parser().parse_args()
    case_manifest = Path(args.case_manifest).resolve()
    contracts_dir = _contracts_dir(case_manifest)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    data_pack = json.loads(Path(args.data_pack_json).read_text(encoding="utf-8"))

    watershed_parameters = _watershed_parameters(data_pack)
    screened = screen_parameters(watershed_parameters)
    baseline = {item.parameter_id: float(item.default_value) for item in screened}

    def evaluator(values: dict[str, float]) -> float:
        stream_component = abs(values["stream_threshold"] - 120.0) / 120.0
        snap_component = abs(values["snap_distance"] - 250.0) / 250.0
        area_component = abs(values["area_correction_factor"] - 1.0)
        return stream_component + snap_component + area_component

    sensitivity = analyze_local_sensitivity(baseline, evaluator, perturbation=0.1)
    candidates = freeze_candidate_set(sensitivity, primary_limit=2)

    hydrology_parameters = _hydrology_parameters()
    hydrology_screened = screen_parameters(hydrology_parameters)
    hydrology_baseline = {item.parameter_id: float(item.default_value) for item in hydrology_screened}

    def hydrology_evaluator(values: dict[str, float]) -> float:
        rainfall_component = abs(values["rainfall_multiplier"] - 1.1)
        storage_component = abs(values["soil_storage_scale"] - 0.9)
        recession_component = abs(values["baseflow_recession_factor"] - 1.0)
        return rainfall_component + storage_component + recession_component

    hydrology_sensitivity = analyze_local_sensitivity(hydrology_baseline, hydrology_evaluator, perturbation=0.1)
    hydrology_candidates = {
        "primary_candidates": ["rainfall_multiplier", "soil_storage_scale"],
        "secondary_candidates": ["baseflow_recession_factor"],
        "forbidden_candidates": [],
    }

    hydraulics_parameters = _hydraulics_parameters()
    hydraulics_screened = screen_parameters([item for item in hydraulics_parameters if item.parameter_id != "section_substitute_mode"])
    hydraulics_baseline = {item.parameter_id: float(item.default_value) for item in hydraulics_screened}

    def hydraulics_evaluator(values: dict[str, float]) -> float:
        roughness_component = abs(values["manning_n_scale"] - 1.0)
        boundary_component = abs(values["boundary_inflow_bias"] - 1.0)
        section_component = abs(values["section_geometry_scale"] - 1.0)
        return roughness_component + boundary_component + section_component

    hydraulics_sensitivity = analyze_local_sensitivity(hydraulics_baseline, hydraulics_evaluator, perturbation=0.1)
    hydraulics_candidates = {
        "primary_candidates": ["manning_n_scale", "section_geometry_scale"],
        "secondary_candidates": ["boundary_inflow_bias"],
        "forbidden_candidates": [],
        "structural_state": {"section_substitute_mode": "observed"},
    }

    coupling_parameters = _coupling_parameters()
    coupling_screened = screen_parameters(coupling_parameters)
    coupling_baseline = {item.parameter_id: float(item.default_value) for item in coupling_screened}

    def coupling_evaluator(values: dict[str, float]) -> float:
        lag_component = abs(values["runoff_to_channel_lag"] - 2.0)
        scale_component = abs(values["channel_inflow_scale"] - 1.0)
        bias_component = abs(values["coupling_transfer_bias"] - 0.0)
        return lag_component + scale_component + bias_component

    coupling_sensitivity = analyze_local_sensitivity(coupling_baseline, coupling_evaluator, perturbation=0.1)
    coupling_candidates = {
        "primary_candidates": ["runoff_to_channel_lag", "channel_inflow_scale"],
        "secondary_candidates": ["coupling_transfer_bias"],
        "forbidden_candidates": [],
    }

    assimilation_parameters = _assimilation_parameters()
    assimilation_screened = screen_parameters(assimilation_parameters)
    assimilation_baseline = {item.parameter_id: float(item.default_value) for item in assimilation_screened}

    def assimilation_evaluator(values: dict[str, float]) -> float:
        process_component = 10.0 * abs(values["process_noise_scale"] - 0.1)
        observation_component = 9.0 * abs(values["observation_noise_scale"] - 0.1)
        bias_component = 0.5 * abs(values["observation_bias"] - 0.0)
        state_component = 0.5 * abs(values["initial_state_bias"] - 0.0)
        return process_component + observation_component + bias_component + state_component

    assimilation_sensitivity = analyze_local_sensitivity(assimilation_baseline, assimilation_evaluator, perturbation=0.1)
    assimilation_candidates = {
        "primary_candidates": ["process_noise_scale", "observation_noise_scale"],
        "secondary_candidates": ["initial_state_bias", "observation_bias"],
        "forbidden_candidates": [],
    }

    write_json(
        contracts_dir / "parameter_inventory.latest.json",
        {
            "case_id": args.case_id,
            "stages": {
                "watershed_delineation": [item.to_dict() for item in watershed_parameters],
                **_stage_templates(),
            },
        },
    )
    write_json(
        contracts_dir / "sensitivity_report.latest.json",
        {
            "case_id": args.case_id,
            "stages": {
                "watershed_delineation": sensitivity,
                "hydrology": hydrology_sensitivity,
                "hydraulics": hydraulics_sensitivity,
                "coupling": coupling_sensitivity,
                "assimilation": assimilation_sensitivity,
            },
        },
    )
    write_json(
        contracts_dir / "candidate_set.latest.json",
        {
            "case_id": args.case_id,
            "stages": {
                "watershed_delineation": candidates,
                "hydrology": hydrology_candidates,
                "hydraulics": hydraulics_candidates,
                "coupling": coupling_candidates,
                "assimilation": assimilation_candidates,
            },
        },
    )
    write_json(
        contracts_dir / "error_model_spec.latest.json",
        {
            "geometry_topology": ["area_correction_factor", "snap_distance", "stream_threshold"],
            "forcing_input": ["rainfall_multiplier"],
            "state_error": ["process_noise_scale", "observation_noise_scale"],
        },
    )
    write_json(
        contracts_dir / "correction_parameter_catalog.latest.json",
        {
            "parameters": [
                {"parameter_id": "area_correction_factor", "error_model_role": "structural_correction"},
                {"parameter_id": "rating_curve_bias", "error_model_role": "bias"},
                {"parameter_id": "observation_noise_scale", "error_model_role": "noise"},
            ]
        },
    )
    write_json(
        contracts_dir / "correction_activation_record.latest.json",
        {
            "watershed_delineation": {
                "stream_threshold": baseline["stream_threshold"],
                "snap_distance": baseline["snap_distance"],
                "area_correction_factor": baseline["area_correction_factor"],
            },
            "hydrology": {
                "rainfall_multiplier": hydrology_baseline["rainfall_multiplier"],
                "soil_storage_scale": hydrology_baseline["soil_storage_scale"],
                "baseflow_recession_factor": hydrology_baseline["baseflow_recession_factor"],
            },
            "hydraulics": {
                "manning_n_scale": hydraulics_baseline["manning_n_scale"],
                "boundary_inflow_bias": hydraulics_baseline["boundary_inflow_bias"],
                "section_geometry_scale": hydraulics_baseline["section_geometry_scale"],
                "section_substitute_mode": "observed",
                "section_source_type": "observed",
                "section_confidence": 1.0,
            },
            "coupling": {
                "runoff_to_channel_lag": coupling_baseline["runoff_to_channel_lag"],
                "channel_inflow_scale": coupling_baseline["channel_inflow_scale"],
                "coupling_transfer_bias": coupling_baseline["coupling_transfer_bias"],
            },
            "assimilation": {
                "process_noise_scale": assimilation_baseline["process_noise_scale"],
                "observation_noise_scale": assimilation_baseline["observation_noise_scale"],
                "observation_bias": assimilation_baseline["observation_bias"],
                "initial_state_bias": assimilation_baseline["initial_state_bias"],
            },
        },
    )

    envelope = StageGovernanceArtifact(case_id=args.case_id, stage="watershed_delineation", parameters=watershed_parameters, metadata={"status": "pilot"})
    write_json(
        contracts_dir / "parameter_governance.latest.json",
        {
            **envelope.to_dict(),
            "sensitivity_report": sensitivity,
            "candidate_set": candidates,
            "artifact_paths": {
                "parameter_inventory": f"cases/{args.case_id}/contracts/parameter_inventory.latest.json",
                "sensitivity_report": f"cases/{args.case_id}/contracts/sensitivity_report.latest.json",
                "candidate_set": f"cases/{args.case_id}/contracts/candidate_set.latest.json",
                "error_model_spec": f"cases/{args.case_id}/contracts/error_model_spec.latest.json",
                "correction_parameter_catalog": f"cases/{args.case_id}/contracts/correction_parameter_catalog.latest.json",
                "correction_activation_record": f"cases/{args.case_id}/contracts/correction_activation_record.latest.json",
            },
        },
    )


if __name__ == "__main__":
    main()
