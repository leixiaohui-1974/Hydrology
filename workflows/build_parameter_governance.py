from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hydro_model.parameter_governance import (
    ParameterDefinition,
    StageGovernanceArtifact,
    analyze_local_sensitivity,
    freeze_candidate_set,
    screen_parameters,
    write_json,
)

SCHEMA_VERSION = "parameter_governance_multistage.v1"
CANONICAL_STAGE_ORDER = [
    "watershed_delineation",
    "hydrology",
    "hydraulics",
    "coupling",
    "assimilation",
    "identification",
    "scheduling_control",
    "sil_odd",
]
LEGACY_COMPATIBILITY_STAGE = "watershed_delineation"
CASE_VARIANT_FIELDS = [
    "default_value",
    "bounds",
    "source_of_truth",
    "dependencies",
    "validation_metric_links",
]
CROSS_CASE_INVARIANT_FIELDS = [
    "parameter_id",
    "stage",
    "category",
    "physical_meaning",
    "unit",
    "sensitivity_enabled",
    "calibration_enabled",
    "assimilation_enabled",
    "error_model_role",
]


def _safe_load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _derive_workflow_recommendations(modeling_hints: dict) -> dict:
    existing = modeling_hints.get("workflow_recommendations")
    if isinstance(existing, dict):
        return existing
    suggested = [str(x) for x in (modeling_hints.get("suggested_workflows") or []) if str(x).strip()]
    supports = bool(modeling_hints.get("graphify_supports_auto_modeling_hints"))
    stage_map = {
        "watershed_delineation": {"source_to_delineation", "section_analysis"},
        "hydrology": {"model", "hyd_sim", "hydro_report"},
        "hydraulics": {"section_analysis", "hydraulic_simulation", "hydraulic_review"},
        "coupling": {"cascade"},
        "assimilation": {"state_est", "assimilate"},
        "identification": {"identification", "identify_parameters", "pid_autotune"},
        "scheduling_control": {"scheduling", "control", "dispatch", "mpc"},
        "sil_odd": {"sil", "odd", "verification", "wnal"},
    }
    stage_activation_guidance = {}
    suggested_set = set(suggested)
    deferred_stages = []
    for stage in CANONICAL_STAGE_ORDER:
        workflow_names = stage_map.get(stage, set())
        matched = sorted(suggested_set & workflow_names)
        if matched:
            stage_activation_guidance[stage] = {
                "status": "recommended",
                "matched_workflows": matched,
            }
        elif supports:
            stage_activation_guidance[stage] = {
                "status": "deferred",
                "matched_workflows": [],
            }
            deferred_stages.append(stage)
        else:
            stage_activation_guidance[stage] = {
                "status": "default",
                "matched_workflows": [],
            }
    return {
        "suggested_workflows": suggested,
        "deferred_stages": deferred_stages,
        "stage_activation_guidance": stage_activation_guidance,
        "supports_auto_modeling_hints": supports,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build parameter governance artifacts for a case.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--case-manifest", required=True)
    parser.add_argument("--data-pack-json", required=True)
    return parser



def _contracts_dir(case_manifest: Path) -> Path:
    if case_manifest.name == "case_manifest.json" and case_manifest.parent.name == "contracts":
        return case_manifest.parent
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
            bounds=(50.0, 10000.0),
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
        ParameterDefinition(
            parameter_id="bottom_width_scale",
            stage="hydraulics",
            category="correction_parameter",
            physical_meaning="Scales the bottom width of channel cross-sections.",
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
            parameter_id="bank_slope_scale",
            stage="hydraulics",
            category="correction_parameter",
            physical_meaning="Scales the bank slope of channel cross-sections.",
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
            parameter_id="turbine_efficiency_scale",
            stage="hydraulics",
            category="physical_parameter",
            physical_meaning="Scales the efficiency of turbines.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.8, 1.0),
            source_of_truth="hydraulics.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["power_output_error"],
        ),
        ParameterDefinition(
            parameter_id="gate_discharge_coefficient",
            stage="hydraulics",
            category="physical_parameter",
            physical_meaning="Discharge coefficient for gates.",
            unit="dimensionless",
            default_value=0.6,
            bounds=(0.5, 0.8),
            source_of_truth="hydraulics.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["stage_discharge_bias"],
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


def _identification_parameters() -> list[ParameterDefinition]:
    return [
        ParameterDefinition(
            parameter_id="response_time_constant_hours",
            stage="identification",
            category="identification_parameter",
            physical_meaning="Represents the dominant response time constant used by reduced-order identification.",
            unit="hours",
            default_value=6.0,
            bounds=(1.0, 48.0),
            source_of_truth="identification.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["fit_rmse", "response_lag_error"],
        ),
        ParameterDefinition(
            parameter_id="dead_time_hours",
            stage="identification",
            category="identification_parameter",
            physical_meaning="Captures transport delay before the identified response begins.",
            unit="hours",
            default_value=1.0,
            bounds=(0.0, 12.0),
            source_of_truth="identification.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["response_lag_error", "residual_whiteness"],
        ),
        ParameterDefinition(
            parameter_id="gain_scale",
            stage="identification",
            category="identification_parameter",
            physical_meaning="Scales the identified steady-state gain before control synthesis.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.7, 1.3),
            source_of_truth="identification.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=True,
            assimilation_enabled=False,
            validation_metric_links=["fit_rmse", "parameter_identifiability_score"],
        ),
    ]


def _scheduling_control_parameters() -> list[ParameterDefinition]:
    return [
        ParameterDefinition(
            parameter_id="prediction_horizon_hours",
            stage="scheduling_control",
            category="control_parameter",
            physical_meaning="Sets the receding-horizon lookahead used by scheduling and MPC routines.",
            unit="hours",
            default_value=24.0,
            bounds=(6.0, 72.0),
            source_of_truth="scheduling_control.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=False,
            validation_metric_links=["constraint_violation_count", "dispatch_cost"],
        ),
        ParameterDefinition(
            parameter_id="control_interval_minutes",
            stage="scheduling_control",
            category="control_parameter",
            physical_meaning="Defines the controller update interval for gate and unit dispatch.",
            unit="minutes",
            default_value=60.0,
            bounds=(15.0, 240.0),
            source_of_truth="scheduling_control.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=False,
            validation_metric_links=["control_stability", "dispatch_cost"],
        ),
        ParameterDefinition(
            parameter_id="storage_safety_weight",
            stage="scheduling_control",
            category="control_parameter",
            physical_meaning="Weights storage safety against economic objectives in scheduling.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.5, 3.0),
            source_of_truth="scheduling_control.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=False,
            validation_metric_links=["constraint_violation_count", "storage_safety_margin"],
        ),
        ParameterDefinition(
            parameter_id="gate_change_penalty",
            stage="scheduling_control",
            category="control_parameter",
            physical_meaning="Penalizes overly aggressive gate or turbine command changes.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.1, 5.0),
            source_of_truth="scheduling_control.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=False,
            validation_metric_links=["control_stability", "gate_action_smoothness"],
        ),
    ]


def _sil_odd_parameters() -> list[ParameterDefinition]:
    return [
        ParameterDefinition(
            parameter_id="scenario_inflow_multiplier",
            stage="sil_odd",
            category="validation_parameter",
            physical_meaning="Scales inflow forcing when stress-testing SIL and ODD scenario envelopes.",
            unit="ratio",
            default_value=1.0,
            bounds=(0.5, 1.5),
            source_of_truth="sil_odd.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=False,
            validation_metric_links=["scenario_pass_rate", "safety_margin_breach_count"],
        ),
        ParameterDefinition(
            parameter_id="sensor_dropout_tolerance_minutes",
            stage="sil_odd",
            category="validation_parameter",
            physical_meaning="Specifies the tolerated sensor outage duration before SIL degrades the scenario verdict.",
            unit="minutes",
            default_value=30.0,
            bounds=(0.0, 180.0),
            source_of_truth="sil_odd.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=False,
            validation_metric_links=["scenario_pass_rate", "observability_gap_minutes"],
        ),
        ParameterDefinition(
            parameter_id="emergency_storage_buffer_ratio",
            stage="sil_odd",
            category="validation_parameter",
            physical_meaning="Reserves emergency storage margin during ODD boundary validation.",
            unit="ratio",
            default_value=0.15,
            bounds=(0.05, 0.4),
            source_of_truth="sil_odd.governance.default",
            sensitivity_enabled=True,
            calibration_enabled=False,
            assimilation_enabled=False,
            validation_metric_links=["safety_margin_breach_count", "scenario_pass_rate"],
        ),
    ]


def _stage_parameters(data_pack: dict) -> dict[str, list[ParameterDefinition]]:
    return {
        "watershed_delineation": _watershed_parameters(data_pack),
        "hydrology": _hydrology_parameters(),
        "hydraulics": _hydraulics_parameters(),
        "coupling": _coupling_parameters(),
        "assimilation": _assimilation_parameters(),
        "identification": _identification_parameters(),
        "scheduling_control": _scheduling_control_parameters(),
        "sil_odd": _sil_odd_parameters(),
    }


def _stage_catalog(stage_parameters: dict[str, list[ParameterDefinition]]) -> dict[str, dict[str, object]]:
    catalog: dict[str, dict[str, object]] = {}
    for stage in CANONICAL_STAGE_ORDER:
        parameters = stage_parameters[stage]
        catalog[stage] = {
            "parameter_count": len(parameters),
            "parameter_ids": [item.parameter_id for item in parameters],
            "minimum_parameter_surface": [item.parameter_id for item in parameters],
            "case_variant_fields": CASE_VARIANT_FIELDS,
            "cross_case_invariant_fields": CROSS_CASE_INVARIANT_FIELDS,
        }
    return catalog


def _multistage_schema() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "multi_stage_catalog",
        "canonical_stage_order": CANONICAL_STAGE_ORDER,
        "legacy_compatibility": {
            "top_level_stage": LEGACY_COMPATIBILITY_STAGE,
            "top_level_parameters_mirror_stage": LEGACY_COMPATIBILITY_STAGE,
            "top_level_sensitivity_report_mirror_stage": LEGACY_COMPATIBILITY_STAGE,
            "top_level_candidate_set_mirror_stage": LEGACY_COMPATIBILITY_STAGE,
        },
        "case_variant_fields": CASE_VARIANT_FIELDS,
        "cross_case_invariant_fields": CROSS_CASE_INVARIANT_FIELDS,
    }


def main() -> None:
    args = _build_parser().parse_args()
    case_manifest = Path(args.case_manifest).resolve()
    contracts_dir = _contracts_dir(case_manifest)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    data_pack = json.loads(Path(args.data_pack_json).read_text(encoding="utf-8"))
    modeling_hints = _safe_load_json(contracts_dir / "modeling_hints.latest.json")
    workflow_recommendations = _derive_workflow_recommendations(modeling_hints)

    all_stage_parameters = _stage_parameters(data_pack)
    stage_catalog = _stage_catalog(all_stage_parameters)
    stages_payload = {
        stage: [item.to_dict() for item in all_stage_parameters[stage]]
        for stage in CANONICAL_STAGE_ORDER
    }
    watershed_parameters = all_stage_parameters["watershed_delineation"]
    screened = screen_parameters(watershed_parameters)
    baseline = {item.parameter_id: float(item.default_value) for item in screened}

    def evaluator(values: dict[str, float]) -> float:
        stream_component = abs(values["stream_threshold"] - 120.0) / 120.0
        snap_component = abs(values["snap_distance"] - 250.0) / 250.0
        area_component = abs(values["area_correction_factor"] - 1.0)
        return stream_component + snap_component + area_component

    sensitivity = analyze_local_sensitivity(baseline, evaluator, perturbation=0.1)
    candidates = freeze_candidate_set(sensitivity, primary_limit=2)

    hydrology_parameters = all_stage_parameters["hydrology"]
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

    hydraulics_parameters = all_stage_parameters["hydraulics"]
    hydraulics_screened = screen_parameters([item for item in hydraulics_parameters if item.parameter_id != "section_substitute_mode"])
    hydraulics_baseline = {item.parameter_id: float(item.default_value) for item in hydraulics_screened}

    def hydraulics_evaluator(values: dict[str, float]) -> float:
        roughness_component = abs(values["manning_n_scale"] - 1.0)
        boundary_component = abs(values["boundary_inflow_bias"] - 1.0)
        section_component = abs(values["section_geometry_scale"] - 1.0)
        bottom_width_component = abs(values["bottom_width_scale"] - 1.0)
        bank_slope_component = abs(values["bank_slope_scale"] - 1.0)
        turbine_eff_component = abs(values["turbine_efficiency_scale"] - 1.0)
        gate_cd_component = abs(values["gate_discharge_coefficient"] - 0.6)
        return roughness_component + boundary_component + section_component + bottom_width_component + bank_slope_component + turbine_eff_component + gate_cd_component

    hydraulics_sensitivity = analyze_local_sensitivity(hydraulics_baseline, hydraulics_evaluator, perturbation=0.1)
    hydraulics_candidates = {
        "primary_candidates": ["manning_n_scale", "section_geometry_scale", "bottom_width_scale"],
        "secondary_candidates": ["boundary_inflow_bias", "bank_slope_scale", "turbine_efficiency_scale", "gate_discharge_coefficient"],
        "forbidden_candidates": [],
        "structural_state": {"section_substitute_mode": "observed"},
    }

    coupling_parameters = all_stage_parameters["coupling"]
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

    assimilation_parameters = all_stage_parameters["assimilation"]
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
    identification_parameters = all_stage_parameters["identification"]
    identification_screened = screen_parameters(identification_parameters)
    identification_baseline = {item.parameter_id: float(item.default_value) for item in identification_screened}

    def identification_evaluator(values: dict[str, float]) -> float:
        response_component = abs(values["response_time_constant_hours"] - 8.0) / 8.0
        dead_time_component = abs(values["dead_time_hours"] - 1.0)
        gain_component = abs(values["gain_scale"] - 1.0)
        return response_component + dead_time_component + gain_component

    identification_sensitivity = analyze_local_sensitivity(identification_baseline, identification_evaluator, perturbation=0.1)
    identification_candidates = {
        "primary_candidates": ["response_time_constant_hours", "gain_scale"],
        "secondary_candidates": ["dead_time_hours"],
        "forbidden_candidates": [],
    }

    scheduling_control_parameters = all_stage_parameters["scheduling_control"]
    scheduling_control_screened = screen_parameters(scheduling_control_parameters)
    scheduling_control_baseline = {
        item.parameter_id: float(item.default_value) for item in scheduling_control_screened
    }

    def scheduling_control_evaluator(values: dict[str, float]) -> float:
        horizon_component = abs(values["prediction_horizon_hours"] - 24.0) / 24.0
        interval_component = abs(values["control_interval_minutes"] - 60.0) / 60.0
        safety_component = abs(values["storage_safety_weight"] - 1.2)
        penalty_component = abs(values["gate_change_penalty"] - 1.0)
        return horizon_component + interval_component + safety_component + penalty_component

    scheduling_control_sensitivity = analyze_local_sensitivity(
        scheduling_control_baseline,
        scheduling_control_evaluator,
        perturbation=0.1,
    )
    scheduling_control_candidates = {
        "primary_candidates": ["prediction_horizon_hours", "storage_safety_weight"],
        "secondary_candidates": ["control_interval_minutes", "gate_change_penalty"],
        "forbidden_candidates": [],
    }

    sil_odd_parameters = all_stage_parameters["sil_odd"]
    sil_odd_screened = screen_parameters(sil_odd_parameters)
    sil_odd_baseline = {item.parameter_id: float(item.default_value) for item in sil_odd_screened}

    def sil_odd_evaluator(values: dict[str, float]) -> float:
        inflow_component = abs(values["scenario_inflow_multiplier"] - 1.0)
        dropout_component = abs(values["sensor_dropout_tolerance_minutes"] - 30.0) / 30.0
        storage_component = abs(values["emergency_storage_buffer_ratio"] - 0.15) / 0.15
        return inflow_component + dropout_component + storage_component

    sil_odd_sensitivity = analyze_local_sensitivity(sil_odd_baseline, sil_odd_evaluator, perturbation=0.1)
    sil_odd_candidates = {
        "primary_candidates": ["scenario_inflow_multiplier", "emergency_storage_buffer_ratio"],
        "secondary_candidates": ["sensor_dropout_tolerance_minutes"],
        "forbidden_candidates": [],
    }

    stage_sensitivity = {
        "watershed_delineation": sensitivity,
        "hydrology": hydrology_sensitivity,
        "hydraulics": hydraulics_sensitivity,
        "coupling": coupling_sensitivity,
        "assimilation": assimilation_sensitivity,
        "identification": identification_sensitivity,
        "scheduling_control": scheduling_control_sensitivity,
        "sil_odd": sil_odd_sensitivity,
    }
    stage_candidate_set = {
        "watershed_delineation": candidates,
        "hydrology": hydrology_candidates,
        "hydraulics": hydraulics_candidates,
        "coupling": coupling_candidates,
        "assimilation": assimilation_candidates,
        "identification": identification_candidates,
        "scheduling_control": scheduling_control_candidates,
        "sil_odd": sil_odd_candidates,
    }
    stage_activation_record = {
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
            "bottom_width_scale": hydraulics_baseline["bottom_width_scale"],
            "bank_slope_scale": hydraulics_baseline["bank_slope_scale"],
            "turbine_efficiency_scale": hydraulics_baseline["turbine_efficiency_scale"],
            "gate_discharge_coefficient": hydraulics_baseline["gate_discharge_coefficient"],
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
        "identification": {
            "response_time_constant_hours": identification_baseline["response_time_constant_hours"],
            "dead_time_hours": identification_baseline["dead_time_hours"],
            "gain_scale": identification_baseline["gain_scale"],
        },
        "scheduling_control": {
            "prediction_horizon_hours": scheduling_control_baseline["prediction_horizon_hours"],
            "control_interval_minutes": scheduling_control_baseline["control_interval_minutes"],
            "storage_safety_weight": scheduling_control_baseline["storage_safety_weight"],
            "gate_change_penalty": scheduling_control_baseline["gate_change_penalty"],
        },
        "sil_odd": {
            "scenario_inflow_multiplier": sil_odd_baseline["scenario_inflow_multiplier"],
            "sensor_dropout_tolerance_minutes": sil_odd_baseline["sensor_dropout_tolerance_minutes"],
            "emergency_storage_buffer_ratio": sil_odd_baseline["emergency_storage_buffer_ratio"],
        },
    }
    compatibility_candidate_set = {
        LEGACY_COMPATIBILITY_STAGE: candidates,
        **stage_candidate_set,
        **candidates,
        "default_stage": LEGACY_COMPATIBILITY_STAGE,
    }

    write_json(
        contracts_dir / "parameter_inventory.latest.json",
        {
            "case_id": args.case_id,
            "schema_version": SCHEMA_VERSION,
            "canonical_stage_order": CANONICAL_STAGE_ORDER,
            "stages": stages_payload,
        },
    )
    write_json(
        contracts_dir / "sensitivity_report.latest.json",
        {
            "case_id": args.case_id,
            "schema_version": SCHEMA_VERSION,
            "canonical_stage_order": CANONICAL_STAGE_ORDER,
            "stages": stage_sensitivity,
        },
    )
    write_json(
        contracts_dir / "candidate_set.latest.json",
        {
            "case_id": args.case_id,
            "schema_version": SCHEMA_VERSION,
            "canonical_stage_order": CANONICAL_STAGE_ORDER,
            "workflow_recommendations": workflow_recommendations,
            "stages": stage_candidate_set,
        },
    )
    write_json(
        contracts_dir / "error_model_spec.latest.json",
        {
            "geometry_topology": ["area_correction_factor", "snap_distance", "stream_threshold"],
            "forcing_input": ["rainfall_multiplier"],
            "state_error": ["process_noise_scale", "observation_noise_scale"],
            "system_identification": ["response_time_constant_hours", "dead_time_hours", "gain_scale"],
            "control_policy": ["prediction_horizon_hours", "storage_safety_weight", "gate_change_penalty"],
            "sil_odd_scenario": [
                "scenario_inflow_multiplier",
                "sensor_dropout_tolerance_minutes",
                "emergency_storage_buffer_ratio",
            ],
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
        stage_activation_record,
    )

    envelope = StageGovernanceArtifact(case_id=args.case_id, stage="watershed_delineation", parameters=watershed_parameters, metadata={"status": "pilot"})
    write_json(
        contracts_dir / "parameter_governance.latest.json",
        {
            **envelope.to_dict(),
            "schema_version": SCHEMA_VERSION,
            "primary_stage": LEGACY_COMPATIBILITY_STAGE,
            "canonical_stage_order": CANONICAL_STAGE_ORDER,
            "schema": _multistage_schema(),
            "stage_catalog": stage_catalog,
            "stages": stages_payload,
            "modeling_hints": modeling_hints,
            "workflow_recommendations": workflow_recommendations,
            "sensitivity_report": sensitivity,
            "candidate_set": compatibility_candidate_set,
            "artifact_paths": {
                "modeling_hints": f"cases/{args.case_id}/contracts/modeling_hints.latest.json",
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
