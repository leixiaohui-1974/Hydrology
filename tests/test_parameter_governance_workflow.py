import json
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "workflows" / "build_parameter_governance.py"
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


def _run_build(case_id: str, manifest_path: Path, data_pack_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--case-id",
            case_id,
            "--case-manifest",
            str(manifest_path),
            "--data-pack-json",
            str(data_pack_path),
        ],
        check=True,
        cwd=str(ROOT_DIR),
    )


def test_build_parameter_governance_writes_all_expected_contracts(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "daduhe"
    contracts_dir = case_dir / "contracts"
    contracts_dir.mkdir(parents=True)
    manifest_path = case_dir / "manifest.yaml"
    manifest_path.write_text("case_id: daduhe\n", encoding="utf-8")
    data_pack_path = tmp_path / "data_pack.contract.json"
    data_pack_path.write_text(
        json.dumps(
            {
                "case_id": "daduhe",
                "delineation_params": {
                    "stream_threshold": 100.0,
                    "snap_distance": 250.0,
                },
                "review_gates": {
                    "basin_validation_json": "cases/daduhe/contracts/basin_validation.latest.json"
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _run_build("daduhe", manifest_path, data_pack_path)

    for name in [
        "parameter_inventory.latest.json",
        "sensitivity_report.latest.json",
        "candidate_set.latest.json",
        "error_model_spec.latest.json",
        "correction_parameter_catalog.latest.json",
        "correction_activation_record.latest.json",
        "parameter_governance.latest.json",
    ]:
        assert (contracts_dir / name).exists(), name


def test_build_parameter_governance_consumes_modeling_hints_contract(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "daduhe"
    contracts_dir = case_dir / "contracts"
    contracts_dir.mkdir(parents=True)
    manifest_path = case_dir / "manifest.yaml"
    manifest_path.write_text("case_id: daduhe\n", encoding="utf-8")
    (contracts_dir / "modeling_hints.latest.json").write_text(
        json.dumps(
            {
                "case_id": "daduhe",
                "suggested_workflows": ["source_to_delineation", "model"],
                "graphify_supports_auto_modeling_hints": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    data_pack_path = tmp_path / "data_pack.contract.json"
    data_pack_path.write_text(
        json.dumps(
            {
                "case_id": "daduhe",
                "delineation_params": {"stream_threshold": 100.0, "snap_distance": 250.0},
                "review_gates": {"basin_validation_json": "cases/daduhe/contracts/basin_validation.latest.json"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _run_build("daduhe", manifest_path, data_pack_path)

    governance = json.loads((contracts_dir / "parameter_governance.latest.json").read_text(encoding="utf-8"))
    candidate_set = json.loads((contracts_dir / "candidate_set.latest.json").read_text(encoding="utf-8"))
    assert governance["modeling_hints"]["graphify_supports_auto_modeling_hints"] is True
    assert governance["modeling_hints"]["suggested_workflows"] == ["source_to_delineation", "model"]
    assert governance["artifact_paths"]["modeling_hints"] == "cases/daduhe/contracts/modeling_hints.latest.json"
    assert governance["workflow_recommendations"]["supports_auto_modeling_hints"] is True
    assert governance["workflow_recommendations"]["stage_activation_guidance"]["watershed_delineation"]["status"] == "recommended"
    assert governance["workflow_recommendations"]["stage_activation_guidance"]["hydrology"]["status"] == "recommended"
    assert governance["workflow_recommendations"]["stage_activation_guidance"]["hydraulics"]["status"] == "deferred"
    assert governance["workflow_recommendations"]["stage_activation_guidance"]["identification"]["status"] == "deferred"
    assert governance["workflow_recommendations"]["stage_activation_guidance"]["scheduling_control"]["status"] == "deferred"
    assert governance["workflow_recommendations"]["stage_activation_guidance"]["sil_odd"]["status"] == "deferred"
    assert candidate_set["workflow_recommendations"]["suggested_workflows"] == ["source_to_delineation", "model"]
    assert candidate_set["workflow_recommendations"]["stage_activation_guidance"]["assimilation"]["status"] == "deferred"



def test_build_parameter_governance_emits_hydrology_sections(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "daduhe"
    contracts_dir = case_dir / "contracts"
    contracts_dir.mkdir(parents=True)
    manifest_path = case_dir / "manifest.yaml"
    manifest_path.write_text("case_id: daduhe\n", encoding="utf-8")
    data_pack_path = tmp_path / "data_pack.contract.json"
    data_pack_path.write_text(
        json.dumps(
            {
                "case_id": "daduhe",
                "delineation_params": {"stream_threshold": 100.0, "snap_distance": 250.0},
                "review_gates": {"basin_validation_json": "cases/daduhe/contracts/basin_validation.latest.json"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _run_build("daduhe", manifest_path, data_pack_path)

    sensitivity = json.loads((contracts_dir / "sensitivity_report.latest.json").read_text(encoding="utf-8"))
    candidates = json.loads((contracts_dir / "candidate_set.latest.json").read_text(encoding="utf-8"))
    activation = json.loads((contracts_dir / "correction_activation_record.latest.json").read_text(encoding="utf-8"))

    assert sensitivity["stages"]["hydrology"][0]["parameter_id"] == "rainfall_multiplier"
    assert candidates["stages"]["hydrology"]["primary_candidates"] == ["rainfall_multiplier", "soil_storage_scale"]
    assert activation["hydrology"]["baseflow_recession_factor"] == 1.0


def test_build_parameter_governance_includes_real_hydraulics_stage(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "daduhe"
    contracts_dir = case_dir / "contracts"
    contracts_dir.mkdir(parents=True)
    manifest_path = case_dir / "manifest.yaml"
    manifest_path.write_text("case_id: daduhe\n", encoding="utf-8")
    data_pack_path = tmp_path / "data_pack.contract.json"
    data_pack_path.write_text(
        json.dumps(
            {
                "case_id": "daduhe",
                "delineation_params": {"stream_threshold": 100.0, "snap_distance": 250.0},
                "review_gates": {"basin_validation_json": "cases/daduhe/contracts/basin_validation.latest.json"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _run_build("daduhe", manifest_path, data_pack_path)

    inventory = json.loads((contracts_dir / "parameter_inventory.latest.json").read_text(encoding="utf-8"))
    hydraulics = inventory["stages"]["hydraulics"]
    assert [item["parameter_id"] for item in hydraulics] == [
        "manning_n_scale",
        "boundary_inflow_bias",
        "section_geometry_scale",
        "section_substitute_mode",
        "bottom_width_scale",
        "bank_slope_scale",
        "turbine_efficiency_scale",
        "gate_discharge_coefficient",
    ]


def test_build_parameter_governance_emits_hydraulics_sections(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "daduhe"
    contracts_dir = case_dir / "contracts"
    contracts_dir.mkdir(parents=True)
    manifest_path = case_dir / "manifest.yaml"
    manifest_path.write_text("case_id: daduhe\n", encoding="utf-8")
    data_pack_path = tmp_path / "data_pack.contract.json"
    data_pack_path.write_text(
        json.dumps(
            {
                "case_id": "daduhe",
                "delineation_params": {"stream_threshold": 100.0, "snap_distance": 250.0},
                "review_gates": {"basin_validation_json": "cases/daduhe/contracts/basin_validation.latest.json"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _run_build("daduhe", manifest_path, data_pack_path)

    sensitivity = json.loads((contracts_dir / "sensitivity_report.latest.json").read_text(encoding="utf-8"))
    candidates = json.loads((contracts_dir / "candidate_set.latest.json").read_text(encoding="utf-8"))
    activation = json.loads((contracts_dir / "correction_activation_record.latest.json").read_text(encoding="utf-8"))

    assert sensitivity["stages"]["hydraulics"][0]["parameter_id"] == "manning_n_scale"
    assert candidates["stages"]["hydraulics"]["primary_candidates"] == ["manning_n_scale", "section_geometry_scale", "bottom_width_scale"]
    assert candidates["stages"]["hydraulics"]["secondary_candidates"] == ["boundary_inflow_bias", "bank_slope_scale", "turbine_efficiency_scale", "gate_discharge_coefficient"]
    assert "section_substitute_mode" in activation["hydraulics"]



def test_build_parameter_governance_emits_coupling_sections(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "daduhe"
    contracts_dir = case_dir / "contracts"
    contracts_dir.mkdir(parents=True)
    manifest_path = case_dir / "manifest.yaml"
    manifest_path.write_text("case_id: daduhe\n", encoding="utf-8")
    data_pack_path = tmp_path / "data_pack.contract.json"
    data_pack_path.write_text(
        json.dumps(
            {
                "case_id": "daduhe",
                "delineation_params": {"stream_threshold": 100.0, "snap_distance": 250.0},
                "review_gates": {"basin_validation_json": "cases/daduhe/contracts/basin_validation.latest.json"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _run_build("daduhe", manifest_path, data_pack_path)

    sensitivity = json.loads((contracts_dir / "sensitivity_report.latest.json").read_text(encoding="utf-8"))
    candidates = json.loads((contracts_dir / "candidate_set.latest.json").read_text(encoding="utf-8"))
    activation = json.loads((contracts_dir / "correction_activation_record.latest.json").read_text(encoding="utf-8"))

    assert sensitivity["stages"]["coupling"][0]["parameter_id"] == "runoff_to_channel_lag"
    assert candidates["stages"]["coupling"]["primary_candidates"] == ["runoff_to_channel_lag", "channel_inflow_scale"]
    assert candidates["stages"]["coupling"]["secondary_candidates"] == ["coupling_transfer_bias"]
    assert activation["coupling"]["channel_inflow_scale"] == 1.0



def test_build_parameter_governance_emits_assimilation_sections(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "daduhe"
    contracts_dir = case_dir / "contracts"
    contracts_dir.mkdir(parents=True)
    manifest_path = case_dir / "manifest.yaml"
    manifest_path.write_text("case_id: daduhe\n", encoding="utf-8")
    data_pack_path = tmp_path / "data_pack.contract.json"
    data_pack_path.write_text(
        json.dumps(
            {
                "case_id": "daduhe",
                "delineation_params": {"stream_threshold": 100.0, "snap_distance": 250.0},
                "review_gates": {"basin_validation_json": "cases/daduhe/contracts/basin_validation.latest.json"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _run_build("daduhe", manifest_path, data_pack_path)

    sensitivity = json.loads((contracts_dir / "sensitivity_report.latest.json").read_text(encoding="utf-8"))
    candidates = json.loads((contracts_dir / "candidate_set.latest.json").read_text(encoding="utf-8"))
    activation = json.loads((contracts_dir / "correction_activation_record.latest.json").read_text(encoding="utf-8"))

    assert sensitivity["stages"]["assimilation"][0]["parameter_id"] == "process_noise_scale"
    assert candidates["stages"]["assimilation"]["primary_candidates"] == ["process_noise_scale", "observation_noise_scale"]
    assert candidates["stages"]["assimilation"]["secondary_candidates"] == ["initial_state_bias", "observation_bias"]
    assert activation["assimilation"]["observation_bias"] == 0.0


def test_build_parameter_governance_emits_multistage_schema_and_legacy_mirror(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "daduhe"
    contracts_dir = case_dir / "contracts"
    contracts_dir.mkdir(parents=True)
    manifest_path = case_dir / "manifest.yaml"
    manifest_path.write_text("case_id: daduhe\n", encoding="utf-8")
    data_pack_path = tmp_path / "data_pack.contract.json"
    data_pack_path.write_text(
        json.dumps(
            {
                "case_id": "daduhe",
                "delineation_params": {"stream_threshold": 100.0, "snap_distance": 250.0},
                "review_gates": {"basin_validation_json": "cases/daduhe/contracts/basin_validation.latest.json"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _run_build("daduhe", manifest_path, data_pack_path)

    governance = json.loads((contracts_dir / "parameter_governance.latest.json").read_text(encoding="utf-8"))
    assert governance["schema_version"] == "parameter_governance_multistage.v1"
    assert governance["primary_stage"] == "watershed_delineation"
    assert governance["canonical_stage_order"] == CANONICAL_STAGE_ORDER
    assert list(governance["stages"]) == CANONICAL_STAGE_ORDER
    assert governance["schema"]["legacy_compatibility"]["top_level_parameters_mirror_stage"] == "watershed_delineation"
    assert governance["stage_catalog"]["hydrology"]["parameter_ids"] == [
        "rainfall_multiplier",
        "soil_storage_scale",
        "baseflow_recession_factor",
    ]
    assert governance["stage_catalog"]["identification"]["minimum_parameter_surface"] == [
        "response_time_constant_hours",
        "dead_time_hours",
        "gain_scale",
    ]
    assert governance["stage_catalog"]["scheduling_control"]["case_variant_fields"] == [
        "default_value",
        "bounds",
        "source_of_truth",
        "dependencies",
        "validation_metric_links",
    ]
    assert governance["candidate_set"]["hydraulics"]["primary_candidates"] == [
        "manning_n_scale",
        "section_geometry_scale",
        "bottom_width_scale",
    ]
    assert governance["candidate_set"]["primary_candidates"] == governance["candidate_set"]["watershed_delineation"]["primary_candidates"]
    assert governance["stages"]["sil_odd"][0]["parameter_id"] == "scenario_inflow_multiplier"
