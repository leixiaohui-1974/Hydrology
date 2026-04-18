import json
from pathlib import Path

import pytest

from workflows.run_control_review_pipeline import sync_control_review_contracts


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_sync_control_review_contracts_writes_canonical_summary_and_enriches_triad(tmp_path: Path) -> None:
    case_root = tmp_path / "cases" / "demo_case"
    contracts_dir = case_root / "contracts"
    pipeline_summary = tmp_path / "pipedream" / "demo_pipeline_summary.json"
    sil_results = tmp_path / "pipedream" / "sil_results.json"
    odd_results = tmp_path / "pipedream" / "phase6_odd.json"
    control_report = tmp_path / "E2EControl" / "reports" / "acceptance" / "control_effectiveness_analysis.json"
    strict_report = tmp_path / "E2EControl" / "reports" / "acceptance" / "strict_revalidation_summary.json"

    _write_json(
        contracts_dir / "workflow_run.json",
        {
            "run_id": "demo_case-watershed",
            "case_id": "demo_case",
            "workflow_type": "watershed_delineation",
            "status": "completed_with_review",
            "inputs": [],
            "outputs": [],
            "steps": [],
            "started_at": "2026-04-11T00:00:00",
            "completed_at": "2026-04-11T00:10:00",
            "metadata": {},
            "schema_version": "0.1.0",
        },
    )
    _write_json(
        contracts_dir / "review_bundle.json",
        {
            "review_id": "review-demo_case",
            "run_id": "demo_case-watershed",
            "case_id": "demo_case",
            "verdict": "pass",
            "findings": [],
            "report_artifacts": [],
            "metadata": {},
            "schema_version": "0.1.0",
        },
    )
    _write_json(
        contracts_dir / "release_manifest.json",
        {
            "release_id": "release-demo_case",
            "case_id": "demo_case",
            "version": "v0.1.0",
            "channel": "staging",
            "status": "published",
            "included_runs": ["demo_case-watershed"],
            "artifacts": [],
            "review_refs": ["review-demo_case"],
            "metadata": {},
            "schema_version": "0.1.0",
            "governance_gates": {
                "index_rel": "Hydrology/configs/platform_governance_gates.index.json",
                "index_version": 1,
                "note": "test",
            },
        },
    )
    _write_json(
        pipeline_summary,
        {
            "timestamp": "2026-04-11 10:00:00",
            "closedloop_validation": {
                "mpc_improvement_pct": 12.5,
                "disturbance_tested": True,
            },
            "sil_verification": {
                "has_sil": True,
                "n_scenarios": 4,
                "pass_rate": 0.25,
            },
            "odd_validation": {
                "validated_in_simulation": True,
                "n_scenarios": 6,
                "n_transitions": 5,
            },
        },
    )
    _write_json(
        sil_results,
        {
            "n_scenarios": 4,
            "n_passed": 1,
            "pass_rate": 0.25,
            "scene_coverage": 0.75,
        },
    )
    _write_json(
        odd_results,
        {
            "validated_in_simulation": True,
            "n_boundary_conditions": 14,
            "n_scenarios_passed": 6,
            "odd_validation_match": 1.0,
            "fsm_chain_verified": True,
            "fsm_transitions": [{"from": "Normal", "to": "Limited"}],
        },
    )
    _write_json(
        control_report,
        {
            "report": {
                "physics_backend": "segmented_hf",
                "controller_backend": "mpc",
                "total_tests": 8,
                "passed_tests": 6,
                "failed_tests": 2,
                "average_tracking_error": 0.18,
            },
            "summary": "control ok",
        },
    )
    _write_json(
        strict_report,
        {
            "overall_status": "warning",
            "modules": {
                "control": {
                    "pass_rate": 0.75,
                    "failed_tests": 2,
                }
            },
        },
    )

    result = sync_control_review_contracts(
        case_id="demo_case",
        case_root=case_root,
        workspace_root=tmp_path,
        pipeline_summary_path=pipeline_summary,
        sil_results_path=sil_results,
        odd_results_path=odd_results,
        control_report_path=control_report,
        strict_revalidation_path=strict_report,
        release_version="v2026.04.11-control",
    )

    control_validation_path = contracts_dir / "control_validation.latest.json"
    assert result["control_validation"] == str(control_validation_path)
    assert control_validation_path.exists()

    control_validation = json.loads(control_validation_path.read_text(encoding="utf-8"))
    assert control_validation["case_id"] == "demo_case"
    assert control_validation["summary"]["overall_status"] == "attention_required"
    assert control_validation["sil"]["pass_rate"] == 0.25
    assert control_validation["odd"]["validated_in_simulation"] is True
    assert control_validation["control"]["controller_backend"] == "mpc"

    workflow_run = json.loads((contracts_dir / "workflow_run.json").read_text(encoding="utf-8"))
    assert workflow_run["run_id"] == "demo_case-control-review"
    assert workflow_run["workflow_type"] == "control_review_pipeline"
    output_paths = {item["path"] for item in workflow_run["outputs"]}
    assert "cases/demo_case/contracts/control_validation.latest.json" in output_paths
    step_ids = {step["step_id"] for step in workflow_run["steps"]}
    assert {"control_execution", "sil_verification", "odd_validation", "strict_revalidation"} <= step_ids

    review_bundle = json.loads((contracts_dir / "review_bundle.json").read_text(encoding="utf-8"))
    assert review_bundle["review_id"] == "review-demo_case-control"
    assert review_bundle["run_id"] == "demo_case-control-review"
    assert review_bundle["verdict"] == "pass_with_comments"
    assert review_bundle["metadata"]["control_validation"]["overall_status"] == "attention_required"
    assert any("SIL" in finding["summary"] for finding in review_bundle["findings"])

    release_manifest = json.loads((contracts_dir / "release_manifest.json").read_text(encoding="utf-8"))
    assert release_manifest["release_id"] == "release-demo_case-v2026.04.11-control"
    assert release_manifest["included_runs"] == ["demo_case-control-review"]
    assert release_manifest["review_refs"] == ["review-demo_case-control"]
    release_paths = {item["path"] for item in release_manifest["artifacts"]}
    assert "cases/demo_case/contracts/control_validation.latest.json" in release_paths
    assert "E2EControl/reports/acceptance/control_effectiveness_analysis.json" in release_paths
    assert release_manifest["metadata"]["control_validation"]["overall_status"] == "attention_required"


def test_sync_control_review_contracts_rejects_invalid_review_bundle_schema_at_runtime(tmp_path: Path) -> None:
    case_root = tmp_path / "cases" / "demo_case"
    contracts_dir = case_root / "contracts"
    pipeline_summary = tmp_path / "pipedream" / "demo_pipeline_summary.json"
    sil_results = tmp_path / "pipedream" / "sil_results.json"
    odd_results = tmp_path / "pipedream" / "phase6_odd.json"
    control_report = tmp_path / "E2EControl" / "reports" / "acceptance" / "control_effectiveness_analysis.json"

    _write_json(
        contracts_dir / "workflow_run.json",
        {
            "run_id": "demo_case-watershed",
            "case_id": "demo_case",
            "workflow_type": "watershed_delineation",
            "status": "completed_with_review",
            "inputs": [],
            "outputs": [],
            "steps": [],
            "started_at": "2026-04-11T00:00:00",
            "completed_at": "2026-04-11T00:10:00",
            "metadata": {},
            "schema_version": "0.1.0",
        },
    )
    _write_json(
        contracts_dir / "review_bundle.json",
        {
            "review_id": "review-demo_case",
            "run_id": "demo_case-watershed",
            "case_id": "demo_case",
            "verdict": "pass",
            "findings": [
                {
                    "finding_id": "broken-finding",
                    "severity": "medium",
                    "artifact_refs": [],
                    "metadata": {},
                }
            ],
            "report_artifacts": [],
            "metadata": {},
            "schema_version": "0.1.0",
        },
    )
    _write_json(
        pipeline_summary,
        {
            "timestamp": "2026-04-11 10:00:00",
            "closedloop_validation": {
                "mpc_improvement_pct": 12.5,
                "disturbance_tested": True,
            },
            "sil_verification": {
                "has_sil": True,
                "n_scenarios": 4,
                "pass_rate": 1.0,
            },
            "odd_validation": {
                "validated_in_simulation": True,
                "n_scenarios": 6,
                "n_transitions": 5,
            },
        },
    )
    _write_json(
        sil_results,
        {
            "n_scenarios": 4,
            "n_passed": 4,
            "pass_rate": 1.0,
            "scene_coverage": 1.0,
        },
    )
    _write_json(
        odd_results,
        {
            "validated_in_simulation": True,
            "n_boundary_conditions": 14,
            "n_scenarios_passed": 6,
            "odd_validation_match": 1.0,
            "fsm_chain_verified": True,
            "fsm_transitions": [{"from": "Normal", "to": "Limited"}],
        },
    )
    _write_json(
        control_report,
        {
            "report": {
                "physics_backend": "segmented_hf",
                "controller_backend": "mpc",
                "total_tests": 8,
                "passed_tests": 8,
                "failed_tests": 0,
                "average_tracking_error": 0.12,
            },
            "summary": "control ok",
        },
    )

    with pytest.raises((ValueError, KeyError), match="summary"):
        sync_control_review_contracts(
            case_id="demo_case",
            case_root=case_root,
            workspace_root=tmp_path,
            pipeline_summary_path=pipeline_summary,
            sil_results_path=sil_results,
            odd_results_path=odd_results,
            control_report_path=control_report,
            release_version="v2026.04.12-control",
        )


def test_sync_control_review_contracts_falls_back_to_quality_gate_when_overall_status_missing(tmp_path: Path) -> None:
    case_root = tmp_path / "cases" / "demo_case"
    contracts_dir = case_root / "contracts"
    pipeline_summary = tmp_path / "pipedream" / "demo_pipeline_summary.json"
    sil_results = tmp_path / "pipedream" / "sil_results.json"
    odd_results = tmp_path / "pipedream" / "phase6_odd.json"
    control_report = tmp_path / "E2EControl" / "reports" / "acceptance" / "control_effectiveness_analysis.json"
    strict_report = tmp_path / "E2EControl" / "reports" / "acceptance" / "strict_revalidation_summary.json"

    _write_json(
        contracts_dir / "workflow_run.json",
        {
            "run_id": "demo_case-watershed",
            "case_id": "demo_case",
            "workflow_type": "watershed_delineation",
            "status": "completed_with_review",
            "inputs": [],
            "outputs": [],
            "steps": [],
            "started_at": "2026-04-11T00:00:00",
            "completed_at": "2026-04-11T00:10:00",
            "metadata": {},
            "schema_version": "0.1.0",
        },
    )
    _write_json(
        contracts_dir / "review_bundle.json",
        {
            "review_id": "review-demo_case",
            "run_id": "demo_case-watershed",
            "case_id": "demo_case",
            "verdict": "pass",
            "findings": [],
            "report_artifacts": [],
            "metadata": {},
            "schema_version": "0.1.0",
        },
    )
    _write_json(
        contracts_dir / "release_manifest.json",
        {
            "release_id": "release-demo_case",
            "case_id": "demo_case",
            "version": "v0.1.0",
            "channel": "staging",
            "status": "published",
            "included_runs": ["demo_case-watershed"],
            "artifacts": [],
            "review_refs": ["review-demo_case"],
            "metadata": {},
            "schema_version": "0.1.0",
            "governance_gates": {
                "index_rel": "Hydrology/configs/platform_governance_gates.index.json",
                "index_version": 1,
                "note": "test",
            },
        },
    )
    _write_json(
        pipeline_summary,
        {
            "timestamp": "2026-04-11 10:00:00",
            "sil_verification": {"has_sil": True, "n_scenarios": 4, "pass_rate": 1.0},
            "odd_validation": {"validated_in_simulation": True, "n_scenarios": 6, "n_transitions": 5},
        },
    )
    _write_json(
        sil_results,
        {
            "n_scenarios": 4,
            "n_passed": 4,
            "pass_rate": 1.0,
            "scene_coverage": 1.0,
        },
    )
    _write_json(
        odd_results,
        {
            "validated_in_simulation": True,
            "n_boundary_conditions": 14,
            "n_scenarios_passed": 6,
            "odd_validation_match": 1.0,
            "fsm_transitions": [{"from": "Normal", "to": "Limited"}],
        },
    )
    _write_json(
        control_report,
        {
            "report": {
                "physics_backend": "segmented_hf",
                "controller_backend": "mpc",
                "total_tests": 8,
                "passed_tests": 8,
                "failed_tests": 0,
                "average_tracking_error": 0.18,
            },
            "summary": "control ok",
        },
    )
    _write_json(
        strict_report,
        {
            "quality_gate_passed": True,
            "quality_gate": {"status": "passed"},
            "modules": {
                "control": {
                    "pass_rate": 0.975,
                    "failed_tests": 0,
                }
            },
        },
    )

    sync_control_review_contracts(
        case_id="demo_case",
        case_root=case_root,
        workspace_root=tmp_path,
        pipeline_summary_path=pipeline_summary,
        sil_results_path=sil_results,
        odd_results_path=odd_results,
        control_report_path=control_report,
        strict_revalidation_path=strict_report,
        release_version="v2026.04.11-control",
    )

    control_validation = json.loads((contracts_dir / "control_validation.latest.json").read_text(encoding="utf-8"))
    assert control_validation["strict_revalidation"]["status"] == "passed"
    assert control_validation["strict_revalidation"]["control_pass_rate"] == 0.975


def test_sync_control_review_contracts_normalizes_legacy_step_artifact_paths(tmp_path: Path) -> None:
    case_root = tmp_path / "cases" / "demo_case"
    contracts_dir = case_root / "contracts"
    pipeline_summary = tmp_path / "pipedream" / "demo_pipeline_summary.json"
    sil_results = tmp_path / "pipedream" / "sil_results.json"
    odd_results = tmp_path / "pipedream" / "phase6_odd.json"
    control_report = tmp_path / "E2EControl" / "reports" / "acceptance" / "control_effectiveness_analysis.json"
    strict_report = tmp_path / "E2EControl" / "reports" / "acceptance" / "strict_revalidation_summary.json"

    _write_json(
        contracts_dir / "workflow_run.json",
        {
            "run_id": "demo_case-source-to-delineation",
            "case_id": "demo_case",
            "workflow_type": "source_to_delineation",
            "status": "failed",
            "inputs": [
                {
                    "artifact_id": "demo_case:case-manifest",
                    "artifact_type": "json",
                    "path": "cases/demo_case/contracts/case_manifest.json",
                    "uri": None,
                    "checksum": None,
                    "metadata": {"role": "case_manifest"},
                }
            ],
            "outputs": [
                {
                    "artifact_id": "demo_case:data-pack",
                    "artifact_type": "json",
                    "path": "cases/demo_case/contracts/data_pack.latest.json",
                    "uri": None,
                    "checksum": None,
                    "metadata": {"role": "data_pack"},
                }
            ],
            "steps": [
                {
                    "step_id": "source_to_delineation_evidence_link",
                    "status": "failed",
                    "inputs": [
                        "cases/demo_case/contracts/case_manifest.json",
                        "cases/demo_case/contracts/source_bundle.contract.json",
                    ],
                    "outputs": [
                        "cases/demo_case/contracts/data_pack.latest.json",
                        "cases/demo_case/contracts/outcomes/source_to_delineation.latest.json",
                    ],
                    "started_at": "2026-04-06T04:39:12Z",
                    "completed_at": "2026-04-07T11:33:06+00:00",
                    "metadata": {"source_contract": "cases/demo_case/contracts/outcomes/source_to_delineation.latest.json"},
                }
            ],
            "started_at": "2026-04-06T04:39:12Z",
            "completed_at": "2026-04-07T11:33:06+00:00",
            "metadata": {"outcome_contract": "cases/demo_case/contracts/outcomes/source_to_delineation.latest.json"},
            "schema_version": "0.1.0",
        },
    )
    _write_json(
        contracts_dir / "review_bundle.json",
        {
            "review_id": "review-demo_case",
            "run_id": "demo_case-source-to-delineation",
            "case_id": "demo_case",
            "verdict": "pass",
            "findings": [],
            "report_artifacts": [],
            "metadata": {},
            "schema_version": "0.1.0",
        },
    )
    _write_json(
        contracts_dir / "release_manifest.json",
        {
            "release_id": "release-demo_case",
            "case_id": "demo_case",
            "version": "v0.1.0",
            "channel": "staging",
            "status": "published",
            "included_runs": ["demo_case-source-to-delineation"],
            "artifacts": [],
            "review_refs": ["review-demo_case"],
            "metadata": {},
            "schema_version": "0.1.0",
            "governance_gates": {
                "index_rel": "Hydrology/configs/platform_governance_gates.index.json",
                "index_version": 1,
                "note": "test",
            },
        },
    )
    _write_json(
        pipeline_summary,
        {
            "timestamp": "2026-04-11 10:00:00",
            "sil_verification": {"has_sil": True, "n_scenarios": 4, "pass_rate": 1.0},
            "odd_validation": {"validated_in_simulation": True, "n_scenarios": 6, "n_transitions": 5},
        },
    )
    _write_json(
        sil_results,
        {
            "n_scenarios": 4,
            "n_passed": 4,
            "pass_rate": 1.0,
            "scene_coverage": 1.0,
        },
    )
    _write_json(
        odd_results,
        {
            "validated_in_simulation": True,
            "n_boundary_conditions": 14,
            "n_scenarios_passed": 6,
            "odd_validation_match": 1.0,
            "fsm_transitions": [{"from": "Normal", "to": "Limited"}],
        },
    )
    _write_json(
        control_report,
        {
            "report": {
                "physics_backend": "segmented_hf",
                "controller_backend": "mpc",
                "total_tests": 8,
                "passed_tests": 8,
                "failed_tests": 0,
                "average_tracking_error": 0.18,
            },
            "summary": "control ok",
        },
    )
    _write_json(
        strict_report,
        {
            "quality_gate_passed": True,
            "quality_gate": {"status": "passed"},
            "modules": {"control": {"pass_rate": 0.975, "failed_tests": 0}},
        },
    )

    sync_control_review_contracts(
        case_id="demo_case",
        case_root=case_root,
        workspace_root=tmp_path,
        pipeline_summary_path=pipeline_summary,
        sil_results_path=sil_results,
        odd_results_path=odd_results,
        control_report_path=control_report,
        strict_revalidation_path=strict_report,
        release_version="v2026.04.11-control",
    )

    workflow_run = json.loads((contracts_dir / "workflow_run.json").read_text(encoding="utf-8"))
    assert workflow_run["run_id"] == "demo_case-control-review"
    assert workflow_run["workflow_type"] == "control_review_pipeline"
    legacy_step = workflow_run["steps"][0]
    assert all(isinstance(item, dict) for item in legacy_step["inputs"])
    assert all(isinstance(item, dict) for item in legacy_step["outputs"])
    assert all("artifact_id" in item for item in legacy_step["inputs"])
    assert all("artifact_id" in item for item in legacy_step["outputs"])
    review_bundle = json.loads((contracts_dir / "review_bundle.json").read_text(encoding="utf-8"))
    assert review_bundle["review_id"] == "review-demo_case-control"
    assert review_bundle["run_id"] == "demo_case-control-review"
    release_manifest = json.loads((contracts_dir / "release_manifest.json").read_text(encoding="utf-8"))
    assert release_manifest["included_runs"] == ["demo_case-control-review"]
    assert release_manifest["review_refs"] == ["review-demo_case-control"]
