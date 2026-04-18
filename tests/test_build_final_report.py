"""Tests for Hydrology final report contract generation."""

from __future__ import annotations

import json
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _assert_no_workspace_absolute_paths(value: object, workspace_root: str | Path | None = None) -> None:
    root = Path(workspace_root).resolve() if workspace_root is not None else WORKSPACE_ROOT.resolve()

    def _walk(item: object) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                _walk(nested)
            return
        if isinstance(item, (list, tuple)):
            for nested in item:
                _walk(nested)
            return
        if isinstance(item, str):
            text = item.strip()
            if text.startswith("[external]/"):
                return
            if Path(text).is_absolute():
                raise AssertionError(f"unexpected absolute path: {item}")
            assert str(root) not in item, f"unexpected workspace absolute path: {item}"

    _walk(value)


def test_build_final_report_writes_contract_with_readiness_and_assertions(
    monkeypatch, tmp_path: Path
) -> None:
    import workflows.build_final_report as target
    import workflows._shared as shared

    workspace = tmp_path
    contracts_dir = workspace / "cases" / "demo_case" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    (contracts_dir / "workflow_run.json").write_text(
        json.dumps(
            {
                "run_id": "run-001",
                "case_id": "demo_case",
                "workflow_type": "hydrology_full_pipeline",
                "status": "completed",
                "schema_version": "0.1.0",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "review_bundle.json").write_text(
        json.dumps(
            {
                "review_id": "review-001",
                "run_id": "run-001",
                "case_id": "demo_case",
                "verdict": "pass_with_comments",
                "findings": [],
                "report_artifacts": [
                    {
                        "artifact_id": "review-001:acceptance",
                        "artifact_type": "html_report",
                        "path": "cases/demo_case/contracts/e2e_review_bundle.html",
                        "metadata": {"role": "acceptance_report"},
                    }
                ],
                "schema_version": "0.1.0",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "release_manifest.json").write_text(
        json.dumps(
            {
                "release_id": "release-demo_case-v1.0.0",
                "case_id": "demo_case",
                "version": "v1.0.0",
                "status": "review_pending",
                "channel": "hydrodesk-shell",
                "included_runs": ["run-001"],
                "review_refs": ["review-001"],
                "artifacts": [],
                "schema_version": "0.1.0",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "outcome_coverage_report.latest.json").write_text(
        json.dumps(
            {
                "gate_status": "needs-review",
                "outcome_coverage": 0.75,
                "schema_valid_count": 3,
                "evidence_bound_count": 2,
                "total_executed": 4,
                "outcomes_generated": 3,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "e2e_outcome_verification_report.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-04-12T00:00:00Z",
                "stage2_execution_integrity": {
                    "closure_check_passed": True,
                    "pending_workflows": [],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (workspace / "cases" / "rollout_readiness_baseline.latest.json").write_text(
        json.dumps(
            {
                "readiness_release_board": {
                    "cases": [
                        {
                            "case_id": "demo_case",
                            "release_gate": {
                                "status": "needs-review",
                                "summary": "still needs manual review",
                            },
                            "dimensions": {
                                "e2e_gate": {"status": "review"},
                            },
                        }
                    ]
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    governance_path = workspace / "Hydrology" / "configs" / "final_report_governance.yaml"
    governance_path.parent.mkdir(parents=True, exist_ok=True)
    governance_path.write_text(
        """
schema_version: final_report_governance.v1
artifact_acceptance_scope: case
review_verdict_semantics:
  pass_with_comments:
    semantic_lane: promotion_pending_with_comments
    labels:
      zh: 带意见待提升
      en: promotion_pending_with_comments
  _default:
    semantic_lane: unspecified
    labels: {}
release_gate_assertion:
  require_rollout_board_row: true
  allowed_non_blocked_statuses:
    - needs-review
    - release-ready
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", workspace)
    monkeypatch.setattr(target, "DEFAULT_FINAL_REPORT_GOVERNANCE", governance_path)
    monkeypatch.setattr(shared, "WORKSPACE", workspace)
    monkeypatch.setattr(
        target,
        "run_readiness",
        lambda case_id, config_path, rules_path: {
            "case_id": case_id,
            "summary": {
                "pipeline_contract_ready": True,
                "workflow_outputs_count": 3,
                "source_bundle_present": True,
                "source_import_session_path": str(workspace / "cases" / case_id / "contracts" / "source_import_session.latest.json"),
            },
            "entry_inputs": {
                "case_manifest": str(workspace / "cases" / case_id / "manifest.yaml"),
                "source_bundle_json": str(workspace / "cases" / case_id / "contracts" / "source_bundle.contract.json"),
            },
            "graphify_sidecar": {
                "graph_run_summary": {
                    "output_dir": str(workspace / ".graphify" / "pilots" / f"case-{case_id}" / "graphify-out")
                }
            },
        },
    )

    output_path = contracts_dir / "final_report.latest.json"
    payload = target.build_final_report(
        case_id="demo_case",
        output_path=output_path,
    )

    assert output_path.is_file()
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == saved
    assert saved["schema_version"] == "final_report.v1"
    assert saved["case_id"] == "demo_case"
    assert saved.get("acceptance_scope") == "case"
    assert saved["review"]["verdict"] == "pass_with_comments"
    assert saved["release"]["status"] == "review_pending"
    assert saved["readiness"]["platform"]["summary"]["pipeline_contract_ready"] is True
    assert saved["readiness"]["platform"]["summary"]["source_import_session_path"] == "cases/demo_case/contracts/source_import_session.latest.json"
    assert saved["readiness"]["platform"]["entry_inputs"] == {
        "case_manifest": "cases/demo_case/manifest.yaml",
        "source_bundle_json": "cases/demo_case/contracts/source_bundle.contract.json",
    }
    assert saved["readiness"]["platform"]["graphify_sidecar"]["graph_run_summary"]["output_dir"] == ".graphify/pilots/case-demo_case/graphify-out"
    _assert_no_workspace_absolute_paths(saved["readiness"]["platform"], workspace)
    _assert_no_workspace_absolute_paths(saved, workspace)
    assert saved["readiness"]["release_board"]["status"] == "needs-review"
    assert saved["business_metrics"]["normalized_outcome_coverage"] == 0.75
    assert saved["contracts"]["final_report"]["path"] == "cases/demo_case/contracts/final_report.latest.json"
    assertion_keys = [item["key"] for item in saved["assertions"]]
    assert assertion_keys == [
        "pipeline_contract_ready",
        "verification_closure_check_passed",
        "verification_pending_workflows_empty",
        "zero_hardcoding_gate_passed",
        "acceptance_artifact_present",
        "review_bundle_verdict_present",
        "release_manifest_present",
        "release_gate_not_blocked",
    ]
    assert all(item["passed"] for item in saved["assertions"])
    ps = saved["governance"]["promotion_semantics"]
    assert ps["semantic_lane"] == "promotion_pending_with_comments"
    assert ps["review_verdict"] == "pass_with_comments"
    assert ps["observed_manifest_status"] == "review_pending"
    assert ps["observed_release_board_gate_status"] == "needs-review"
    assert saved["governance"]["schema_version"] == "final_report_governance.v1"
    assert saved["governance"]["final_report_governance_path"].endswith("final_report_governance.yaml")


def test_build_final_report_truthfully_fails_when_hardcoding_gate_is_red(
    monkeypatch, tmp_path: Path
) -> None:
    import workflows.build_final_report as target

    workspace = tmp_path
    contracts_dir = workspace / "cases" / "yinchuojiliao" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    (contracts_dir / "workflow_run.json").write_text(
        json.dumps({"run_id": "run-yinchuo", "case_id": "yinchuojiliao"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (contracts_dir / "review_bundle.json").write_text(
        json.dumps(
            {
                "review_id": "review-yinchuo",
                "run_id": "run-yinchuo",
                "case_id": "yinchuojiliao",
                "verdict": "pass_with_comments",
                "report_artifacts": [
                    {
                        "artifact_id": "review-yinchuo:acceptance",
                        "artifact_type": "html_report",
                        "path": "cases/yinchuojiliao/contracts/e2e_review_bundle.html",
                        "metadata": {"role": "acceptance_report"},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "release_manifest.json").write_text(
        json.dumps(
            {
                "release_id": "release-yinchuo",
                "status": "review_pending",
                "artifacts": [
                    {
                        "artifact_id": "review-yinchuo:acceptance",
                        "artifact_type": "html_report",
                        "path": "cases/yinchuojiliao/contracts/e2e_review_bundle.html",
                        "metadata": {"role": "acceptance_report"},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "outcome_coverage_report.latest.json").write_text(
        json.dumps(
            {
                "gate_status": "passed",
                "outcome_coverage": 0.96,
                "schema_valid_count": 39,
                "evidence_bound_count": 39,
                "total_executed": 41,
                "outcomes_generated": 39,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "e2e_outcome_verification_report.json").write_text(
        json.dumps(
            {
                "stage2_execution_integrity": {
                    "closure_check_passed": True,
                    "pending_workflows": [],
                },
                "stage3_outcome_quality": {
                    "coverage_report": {
                        "gate_status": "failed_by_hardcoding_linter",
                    }
                },
                "zero_hardcoding_gate": "failed",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (workspace / "cases" / "rollout_readiness_baseline.latest.json").write_text(
        json.dumps(
            {
                "readiness_release_board": {
                    "cases": [
                        {
                            "case_id": "yinchuojiliao",
                            "release_gate": {
                                "status": "needs-review",
                                "summary": "coverage passed but hardcoding gate failed",
                            },
                            "dimensions": {
                                "e2e_gate": {"status": "review"},
                            },
                        }
                    ]
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", workspace)
    monkeypatch.setattr(
        target,
        "run_readiness",
        lambda case_id, config_path, rules_path: {
            "case_id": case_id,
            "summary": {
                "pipeline_contract_ready": True,
            },
        },
    )

    payload = target.build_final_report(case_id="yinchuojiliao")
    assertions = {item["key"]: item["passed"] for item in payload["assertions"]}

    assert assertions["acceptance_artifact_present"] is True
    assert assertions["zero_hardcoding_gate_passed"] is False
    assert payload["overall_status"] == "attention_required"
    assert payload["assertion_summary"] == {
        "total": 8,
        "passed": 7,
        "failed": 1,
    }
    assert payload["governance"]["promotion_semantics"]["semantic_lane"] == "promotion_pending_with_comments"


def test_release_gate_not_blocked_fails_when_rollout_board_missing_case_row(
    monkeypatch, tmp_path: Path
) -> None:
    """无匹配 case 行时不应将 release_gate 视为已放行。"""
    import workflows.build_final_report as target

    workspace = tmp_path
    contracts_dir = workspace / "cases" / "demo_case" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    def _minimal_contracts():
        (contracts_dir / "workflow_run.json").write_text(
            json.dumps({"run_id": "r1", "case_id": "demo_case"}, ensure_ascii=False),
            encoding="utf-8",
        )
        (contracts_dir / "review_bundle.json").write_text(
            json.dumps(
                {
                    "verdict": "pass",
                    "report_artifacts": [
                        {
                            "metadata": {"role": "acceptance_report"},
                            "artifact_type": "html_report",
                            "artifact_id": "a1",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (contracts_dir / "release_manifest.json").write_text(
            json.dumps({"release_id": "rel1", "status": "review_pending", "artifacts": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        (contracts_dir / "outcome_coverage_report.latest.json").write_text(
            json.dumps({"gate_status": "passed", "outcome_coverage": 1.0}, ensure_ascii=False),
            encoding="utf-8",
        )
        (contracts_dir / "e2e_outcome_verification_report.json").write_text(
            json.dumps(
                {
                    "zero_hardcoding_gate": "passed",
                    "stage2_execution_integrity": {"closure_check_passed": True, "pending_workflows": []},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    _minimal_contracts()
    (workspace / "cases" / "rollout_readiness_baseline.latest.json").write_text(
        json.dumps({"readiness_release_board": {"cases": [{"case_id": "other_case", "release_gate": {"status": "release-ready"}}]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", workspace)
    monkeypatch.setattr(
        target,
        "run_readiness",
        lambda case_id, config_path, rules_path: {
            "case_id": case_id,
            "summary": {"pipeline_contract_ready": True},
        },
    )

    payload = target.build_final_report(case_id="demo_case")
    by_key = {a["key"]: a["passed"] for a in payload["assertions"]}
    assert by_key["release_gate_not_blocked"] is False
    assert payload["readiness"]["release_board"] == {
        "status": "rollout-case-row-missing",
        "summary": "rollout readiness board missing case row for demo_case; release gate cannot pass",
        "dimensions": {},
    }
    assert payload["overall_status"] == "attention_required"


def test_release_gate_not_blocked_fails_when_rollout_board_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """board 缺失时必须给出明确非通过语义，且 overall 不能 pass。"""
    import workflows.build_final_report as target

    workspace = tmp_path
    contracts_dir = workspace / "cases" / "demo_case" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    (contracts_dir / "workflow_run.json").write_text(
        json.dumps({"run_id": "r1", "case_id": "demo_case"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "review_bundle.json").write_text(
        json.dumps(
            {
                "verdict": "pass",
                "report_artifacts": [
                    {"metadata": {"role": "acceptance_report"}, "artifact_type": "html_report", "artifact_id": "a1"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "release_manifest.json").write_text(
        json.dumps({"release_id": "rel1", "status": "review_pending", "artifacts": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "outcome_coverage_report.latest.json").write_text(
        json.dumps({"gate_status": "passed", "outcome_coverage": 1.0}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "e2e_outcome_verification_report.json").write_text(
        json.dumps(
            {
                "zero_hardcoding_gate": "passed",
                "stage2_execution_integrity": {"closure_check_passed": True, "pending_workflows": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (workspace / "cases" / "rollout_readiness_baseline.latest.json").write_text(
        json.dumps({}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", workspace)
    monkeypatch.setattr(
        target,
        "run_readiness",
        lambda case_id, config_path, rules_path: {
            "case_id": case_id,
            "summary": {"pipeline_contract_ready": True},
        },
    )

    payload = target.build_final_report(case_id="demo_case")
    by_key = {a["key"]: a["passed"] for a in payload["assertions"]}
    assert by_key["release_gate_not_blocked"] is False
    assert payload["readiness"]["release_board"] == {
        "status": "rollout-board-missing",
        "summary": "rollout readiness board missing; release gate cannot pass",
        "dimensions": {},
    }
    assert payload["overall_status"] == "attention_required"


def test_release_gate_not_blocked_fails_when_release_gate_status_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """board 有行但 release_gate.status 为空时不通过。"""
    import workflows.build_final_report as target

    workspace = tmp_path
    contracts_dir = workspace / "cases" / "demo_case" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    (contracts_dir / "workflow_run.json").write_text(
        json.dumps({"run_id": "r1", "case_id": "demo_case"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "review_bundle.json").write_text(
        json.dumps(
            {
                "verdict": "pass",
                "report_artifacts": [
                    {"metadata": {"role": "acceptance_report"}, "artifact_type": "html_report", "artifact_id": "a1"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "release_manifest.json").write_text(
        json.dumps({"release_id": "rel1", "status": "review_pending", "artifacts": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "outcome_coverage_report.latest.json").write_text(
        json.dumps({"gate_status": "passed", "outcome_coverage": 1.0}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "e2e_outcome_verification_report.json").write_text(
        json.dumps(
            {
                "zero_hardcoding_gate": "passed",
                "stage2_execution_integrity": {"closure_check_passed": True, "pending_workflows": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (workspace / "cases" / "rollout_readiness_baseline.latest.json").write_text(
        json.dumps(
            {
                "readiness_release_board": {
                    "cases": [
                        {
                            "case_id": "demo_case",
                            "release_gate": {},
                            "dimensions": {},
                        }
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", workspace)
    monkeypatch.setattr(
        target,
        "run_readiness",
        lambda case_id, config_path, rules_path: {
            "case_id": case_id,
            "summary": {"pipeline_contract_ready": True},
        },
    )

    payload = target.build_final_report(case_id="demo_case")
    by_key = {a["key"]: a["passed"] for a in payload["assertions"]}
    assert by_key["release_gate_not_blocked"] is False
    assert payload["overall_status"] == "attention_required"
