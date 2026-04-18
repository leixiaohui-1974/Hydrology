from __future__ import annotations

import json
from pathlib import Path

from scripts.control_testing_readiness import build_control_testing_readiness


def test_build_control_testing_readiness_for_pressurized_cascade(tmp_path: Path) -> None:
    case_id = "demo_case"
    configs_dir = tmp_path / "Hydrology" / "configs"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    configs_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (configs_dir / f"{case_id}.yaml").write_text(
        """
project_type: cascade_hydro
topology:
  system_type: pressurized_cascade
""".strip(),
        encoding="utf-8",
    )
    (contracts_dir / "station_topology.latest.json").write_text(
        json.dumps({"summary": {"station_count": 5}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "source_import_session.latest.json").write_text(
        json.dumps({"source_mode": "copied_contract"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "control_optimization_report.json").write_text(
        json.dumps({"status": "ready", "metrics": {"control_score": 0.97, "scheduling_score": 0.97}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "sil_verification_report.json").write_text(
        json.dumps({"status": "ready", "metrics": {"sil_score": 0.7}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "odd_coverage_report.json").write_text(
        json.dumps({"coverage_metrics": {"total_scenarios_tested": 10}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "outlets.normalized.json").write_text(
        json.dumps({"count": 0}, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = build_control_testing_readiness(case_id, tmp_path)

    assert payload is not None
    assert payload["contract_type"] == "control_testing_readiness"
    assert payload["status"] == "ready_for_case_bound_control_testing"
    assert payload["acceptance_scope"] == "case_bound_control_testing"
    assert payload["acceptance_signal"] == "provisional_pass_with_traceability_gaps"
    assert payload["ready_for"] == [
        "pressurized_cascade_control",
        "mpc_scheduling",
        "sil_odd_case_bound_testing",
    ]
    assert payload["not_ready_for"] == [
        "watershed_delineation",
        "authoritative_outlet_driven_data_pack",
    ]
    assert payload["waived_requirements"][0]["current_status"] == "outlets_empty"
    assert payload["source_contracts"]["control_validation_report"] is None
    assert payload["acceptance_basis"]["control_report_status"] == "ready"
    assert payload["acceptance_basis"]["control_validation_status"] is None
    assert payload["resolved_traceability_gaps"] == []
    assert payload["open_traceability_gaps"][:3] == [
        "missing_control_pass_rate",
        "missing_controller_backend",
        "missing_physics_backend",
    ]


def test_build_control_testing_readiness_quantifies_control_validation_gaps(tmp_path: Path) -> None:
    case_id = "demo_case"
    configs_dir = tmp_path / "Hydrology" / "configs"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    configs_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (configs_dir / f"{case_id}.yaml").write_text(
        """
project_type: cascade_hydro
topology:
  system_type: pressurized_cascade
""".strip(),
        encoding="utf-8",
    )
    (contracts_dir / "station_topology.latest.json").write_text(
        json.dumps({"summary": {"station_count": 5}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "source_import_session.latest.json").write_text(
        json.dumps({"source_mode": "copied_contract"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "control_optimization_report.json").write_text(
        json.dumps({"status": "ready", "metrics": {"control_score": 0.97, "scheduling_score": 0.97}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "control_validation.latest.json").write_text(
        json.dumps(
            {
                "control": {
                    "pass_rate": 0.63,
                    "controller_backend": "base_mpc",
                    "physics_backend": "segmented_hf",
                    "average_tracking_error": 0.07,
                },
                "sil": {
                    "pass_rate": 0.17,
                    "scene_coverage": 0.75,
                },
                "strict_revalidation": {
                    "status": "missing",
                    "control_pass_rate": 0.975,
                },
                "summary": {
                    "overall_status": "attention_required",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "sil_verification_report.json").write_text(
        json.dumps({"status": "ready", "metrics": {"sil_score": 0.7}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "odd_coverage_report.json").write_text(
        json.dumps({"coverage_metrics": {"total_scenarios_tested": 10}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "outlets.normalized.json").write_text(
        json.dumps({"count": 0}, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = build_control_testing_readiness(case_id, tmp_path)

    assert payload is not None
    assert payload["acceptance_signal"] == "provisional_pass_with_quantified_traceability_gaps"
    assert payload["source_contracts"]["control_validation_report"] == f"cases/{case_id}/contracts/control_validation.latest.json"
    assert payload["evidence"]["control_pass_rate"] == 0.63
    assert payload["evidence"]["controller_backend"] == "base_mpc"
    assert payload["evidence"]["physics_backend"] == "segmented_hf"
    assert payload["evidence"]["average_tracking_error"] == 0.07
    assert payload["evidence"]["sil_pass_rate"] == 0.17
    assert payload["evidence"]["sil_scene_coverage"] == 0.75
    assert payload["evidence"]["strict_revalidation_status"] == "missing"
    assert payload["evidence"]["strict_revalidation_control_pass_rate"] == 0.975
    assert payload["acceptance_basis"]["control_validation_status"] == "attention_required"
    assert payload["resolved_traceability_gaps"] == [
        "missing_control_pass_rate",
        "missing_controller_backend",
        "missing_physics_backend",
        "missing_average_tracking_error",
        "missing_sil_pass_rate",
        "missing_sil_scene_coverage",
    ]
    assert payload["open_traceability_gaps"] == ["missing_strict_revalidation_status"]


def test_build_control_testing_readiness_marks_full_traceability_when_strict_status_present(tmp_path: Path) -> None:
    case_id = "demo_case"
    configs_dir = tmp_path / "Hydrology" / "configs"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    configs_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (configs_dir / f"{case_id}.yaml").write_text(
        """
project_type: cascade_hydro
topology:
  system_type: pressurized_cascade
""".strip(),
        encoding="utf-8",
    )
    (contracts_dir / "station_topology.latest.json").write_text(
        json.dumps({"summary": {"station_count": 5}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "source_import_session.latest.json").write_text(
        json.dumps({"source_mode": "copied_contract"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "control_optimization_report.json").write_text(
        json.dumps({"status": "ready", "metrics": {"control_score": 0.97, "scheduling_score": 0.97}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "control_validation.latest.json").write_text(
        json.dumps(
            {
                "control": {
                    "pass_rate": 0.63,
                    "controller_backend": "base_mpc",
                    "physics_backend": "segmented_hf",
                    "average_tracking_error": 0.07,
                },
                "sil": {
                    "pass_rate": 0.17,
                    "scene_coverage": 0.75,
                },
                "strict_revalidation": {
                    "status": "passed",
                    "control_pass_rate": 0.975,
                },
                "summary": {
                    "overall_status": "attention_required",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "sil_verification_report.json").write_text(
        json.dumps({"status": "ready", "metrics": {"sil_score": 0.7}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "odd_coverage_report.json").write_text(
        json.dumps({"coverage_metrics": {"total_scenarios_tested": 10}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "outlets.normalized.json").write_text(
        json.dumps({"count": 0}, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = build_control_testing_readiness(case_id, tmp_path)

    assert payload is not None
    assert payload["acceptance_signal"] == "provisional_pass_with_full_traceability"
    assert payload["resolved_traceability_gaps"] == [
        "missing_control_pass_rate",
        "missing_controller_backend",
        "missing_physics_backend",
        "missing_average_tracking_error",
        "missing_sil_pass_rate",
        "missing_sil_scene_coverage",
        "missing_strict_revalidation_status",
    ]
    assert payload["open_traceability_gaps"] == []
