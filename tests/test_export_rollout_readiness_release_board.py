import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import export_rollout_readiness_baseline
from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids


def _fixture_governance() -> dict:
    return export_rollout_readiness_baseline.load_release_readiness_governance(
        export_rollout_readiness_baseline.DEFAULT_GOVERNANCE_CONFIG
    )


def test_release_gate_rules_distinguish_release_ready_needs_review_and_blocked() -> None:
    ready_dimensions = {
        "data_preparedness": export_rollout_readiness_baseline._build_dimension(
            key="data_preparedness",
            label="数据准备度",
            status="ready",
            summary="ok",
            source_contracts=[],
        ),
        "autonomy_quality": export_rollout_readiness_baseline._build_dimension(
            key="autonomy_quality",
            label="自主性总评",
            status="ready",
            summary="PASS",
            source_contracts=[],
        ),
    }
    review_dimensions = {
        **ready_dimensions,
        "e2e_gate": export_rollout_readiness_baseline._build_dimension(
            key="e2e_gate",
            label="E2E Gate",
            status="review",
            summary="coverage passed but hardcoding gate failed",
            source_contracts=["cases/demo/contracts/e2e_outcome_verification_report.json"],
        ),
    }
    blocked_dimensions = {
        **ready_dimensions,
        "wnal": export_rollout_readiness_baseline._build_dimension(
            key="wnal",
            label="WNAL 等级",
            status="blocked",
            summary="WNAL score 0.0",
            source_contracts=["cases/demo/contracts/autonomy_assessment.latest.json"],
        ),
    }

    ready_gate = export_rollout_readiness_baseline._build_release_gate("alpha", ready_dimensions)
    review_gate = export_rollout_readiness_baseline._build_release_gate("beta", review_dimensions)
    blocked_gate = export_rollout_readiness_baseline._build_release_gate("gamma", blocked_dimensions)

    assert ready_gate["status"] == "release-ready"
    assert ready_gate["blockers"] == []
    assert ready_gate["review_items"] == []

    assert review_gate["status"] == "needs-review"
    assert review_gate["blockers"] == []
    assert len(review_gate["review_items"]) == 1
    assert review_gate["review_items"][0]["dimension"] == "e2e_gate"

    assert blocked_gate["status"] == "blocked"
    assert len(blocked_gate["blockers"]) == 1
    assert blocked_gate["blockers"][0]["dimension"] == "wnal"


def test_e2e_gate_treats_hardcoding_linter_failure_as_review_not_blocked(monkeypatch) -> None:
    fixtures = {
        "source_import_session.latest.json": ({"record_count": 1, "imported_at": "2026-04-12T00:00:00Z"}, "cases/demo/contracts/source_import_session.latest.json"),
        "parameter_governance.latest.json": (
            {"stage_catalog": {stage: {"parameter_count": 1} for stage in export_rollout_readiness_baseline.REQUIRED_PARAMETER_STAGES}},
            "cases/demo/contracts/parameter_governance.latest.json",
        ),
        "autonomy_assessment.latest.json": (
            {"scores": {"simulation": 0.9}, "judge": {"verdict": "WARN", "overall_score": 0.8, "weak_dimensions": []}},
            "cases/demo/contracts/autonomy_assessment.latest.json",
        ),
        "autonomy_autorun.latest.json": ({}, None),
        "outcome_coverage_report.latest.json": (
            {"gate_status": "failed_by_hardcoding_linter", "outcome_coverage": 0.97},
            "cases/demo/contracts/outcome_coverage_report.latest.json",
        ),
        "e2e_outcome_verification_report.json": (
            {"stage3_outcome_quality": {"zero_hardcoding_gate": "failed"}},
            "cases/demo/contracts/e2e_outcome_verification_report.json",
        ),
        "odd_coverage_report.json": ({}, None),
        "d1d4_precision_report.latest.json": ({}, None),
        "wnal_level_report.json": ({}, None),
        "control_optimization_report.json": ({}, None),
        "sil_verification_report.json": ({}, None),
        "pipeline_evaluation.latest.json": ({}, None),
        "rollout_minimal_loop.latest.json": ({}, None),
        "final_report.latest.json": ({}, None),
    }

    def fake_load(case_id: str, filename: str):
        assert case_id == "demo"
        return fixtures.get(filename, ({}, None))

    monkeypatch.setattr(export_rollout_readiness_baseline, "_load_contract_json", fake_load)
    monkeypatch.setattr(export_rollout_readiness_baseline, "load_case_config", lambda case_id: {"case_id": case_id, "project_type": "canal"})

    dimensions, _contracts, _raw_contracts = export_rollout_readiness_baseline._build_case_dimensions("demo")
    assert dimensions["e2e_gate"]["status"] == "review"
    assert "hardcoding failed" in dimensions["e2e_gate"]["summary"]


def test_wnal_contract_ready_is_downgraded_when_score_is_zero(monkeypatch) -> None:
    """wnal_level_report.status=ready 不得覆盖 wnal_score=0 的分数结论。"""
    fixtures = {
        "source_import_session.latest.json": ({"record_count": 1, "imported_at": "2026-04-12T00:00:00Z"}, "cases/demo/contracts/source_import_session.latest.json"),
        "parameter_governance.latest.json": (
            {"stage_catalog": {stage: {"parameter_count": 1} for stage in export_rollout_readiness_baseline.REQUIRED_PARAMETER_STAGES}},
            "cases/demo/contracts/parameter_governance.latest.json",
        ),
        "autonomy_assessment.latest.json": (
            {"scores": {"simulation": 0.9}, "judge": {"verdict": "PASS", "overall_score": 0.9, "weak_dimensions": []}},
            "cases/demo/contracts/autonomy_assessment.latest.json",
        ),
        "autonomy_autorun.latest.json": ({}, None),
        "outcome_coverage_report.latest.json": ({"gate_status": "passed", "outcome_coverage": 1.0}, "cases/demo/contracts/outcome_coverage_report.latest.json"),
        "e2e_outcome_verification_report.json": ({}, "cases/demo/contracts/e2e_outcome_verification_report.json"),
        "odd_coverage_report.json": ({"coverage_metrics": {"recovery_success_rate": 1.0, "total_scenarios_tested": 8}}, "cases/demo/contracts/odd_coverage_report.json"),
        "d1d4_precision_report.latest.json": ({}, None),
        "wnal_level_report.json": (
            {"status": "ready", "summary": "stale", "metrics": {"wnal_score": 0.0}},
            "cases/demo/contracts/wnal_level_report.json",
        ),
        "control_optimization_report.json": ({}, None),
        "sil_verification_report.json": ({}, None),
        "pipeline_evaluation.latest.json": (
            {"dimension_scores": {"d1_hydro_modeling": {"mean_nse": 0.9}}, "coverage_pct": 1.0, "case_id": "demo"},
            "cases/demo/contracts/pipeline_evaluation.latest.json",
        ),
        "rollout_minimal_loop.latest.json": (
            {"readiness": {"ready": True, "status": "ready"}},
            "cases/demo/contracts/rollout_minimal_loop.latest.json",
        ),
        "final_report.latest.json": ({}, None),
    }

    def fake_load(case_id: str, filename: str):
        assert case_id == "demo"
        return fixtures.get(filename, ({}, None))

    monkeypatch.setattr(export_rollout_readiness_baseline, "_load_contract_json", fake_load)
    monkeypatch.setattr(export_rollout_readiness_baseline, "load_case_config", lambda case_id: {"case_id": case_id, "project_type": "cascade_hydro"})

    dimensions, _contracts, _raw_contracts = export_rollout_readiness_baseline._build_case_dimensions("demo")
    assert dimensions["wnal"]["status"] == "blocked"
    assert dimensions["wnal"]["summary"] == "WNAL score 0.00 — governance evidence not satisfied"


def test_release_board_exposes_complete_dimensions_for_all_rollout_cases() -> None:
    loop_cfg = load_loop_yaml(
        export_rollout_readiness_baseline.WORKSPACE,
        export_rollout_readiness_baseline.DEFAULT_CONFIG,
    )
    case_ids = resolve_case_ids(loop_cfg, export_rollout_readiness_baseline.WORKSPACE)

    board = export_rollout_readiness_baseline._build_release_board(case_ids, _fixture_governance())

    expected_dimension_keys = {
        "data_preparedness",
        "modeling_readiness",
        "parameter_governance",
        "assimilation_readiness",
        "control_sil_odd",
        "wnal",
        "e2e_gate",
        "autonomy_quality",
    }
    assert board["contract_only_dependencies"] is True
    n = len(case_ids)
    assert board["rollup"]["total_cases"] == n
    assert len(board["cases"]) == n
    assert {item["key"] for item in board["dimension_catalog"]} == expected_dimension_keys
    assert all(set(case_row["dimensions"]) == expected_dimension_keys for case_row in board["cases"])
    assert all(
        path is None or path.startswith("cases/")
        for case_row in board["cases"]
        for path in (case_row.get("contract_paths") or {}).values()
    )


def test_release_board_real_output_contains_blocked_and_non_blocked_cases() -> None:
    loop_cfg = load_loop_yaml(
        export_rollout_readiness_baseline.WORKSPACE,
        export_rollout_readiness_baseline.DEFAULT_CONFIG,
    )
    case_ids = resolve_case_ids(loop_cfg, export_rollout_readiness_baseline.WORKSPACE)

    board = export_rollout_readiness_baseline._build_release_board(case_ids, _fixture_governance())
    rows_by_case = {row["case_id"]: row for row in board["cases"]}

    assert board["rollup"]["non_blocked_count"] >= 1
    assert rows_by_case["zhongxian"]["release_gate"]["status"] in {"blocked", "needs-review"}
    assert rows_by_case["daduhe"]["release_gate"]["status"] in {"needs-review", "release-ready"}
    if rows_by_case["zhongxian"]["release_gate"]["status"] == "blocked":
        assert len(rows_by_case["zhongxian"]["release_gate"]["blockers"]) >= 1
    else:
        assert len(rows_by_case["zhongxian"]["release_gate"]["review_items"]) >= 1
    assert rows_by_case["daduhe"]["dimensions"]["autonomy_quality"]["status"] in {"ready", "review"}
    assert rows_by_case["daduhe"]["final_report_present"] is True
    assert rows_by_case["daduhe"]["final_report_path"].endswith("final_report.latest.json")
    assert rows_by_case["daduhe"]["final_report_acceptance_scope"] == "case"


def test_canal_case_modeling_readiness_uses_loop_readiness_when_nse_is_not_applicable(monkeypatch) -> None:
    fixtures = {
        "source_import_session.latest.json": ({"record_count": 1, "imported_at": "2026-04-12T00:00:00Z"}, "cases/demo/contracts/source_import_session.latest.json"),
        "parameter_governance.latest.json": (
            {"stage_catalog": {stage: {"parameter_count": 1} for stage in export_rollout_readiness_baseline.REQUIRED_PARAMETER_STAGES}},
            "cases/demo/contracts/parameter_governance.latest.json",
        ),
        "autonomy_assessment.latest.json": (
            {
                "scores": {
                    "simulation": 0.0,
                    "control": 0.3,
                    "scheduling": 0.3,
                    "sil": 0.7,
                    "odd": 0.0,
                    "wnal": 0.0,
                },
                "judge": {"verdict": "BLOCK", "overall_score": 0.4, "weak_dimensions": []},
                "generated_at": "2026-04-12T00:00:00Z",
            },
            "cases/demo/contracts/autonomy_assessment.latest.json",
        ),
        "autonomy_autorun.latest.json": ({}, None),
        "outcome_coverage_report.latest.json": ({"gate_status": "passed", "outcome_coverage": 1.0}, "cases/demo/contracts/outcome_coverage_report.latest.json"),
        "e2e_outcome_verification_report.json": ({}, "cases/demo/contracts/e2e_outcome_verification_report.json"),
        "odd_coverage_report.json": ({"coverage_metrics": {"recovery_success_rate": 1.0, "total_scenarios_tested": 8}}, "cases/demo/contracts/odd_coverage_report.json"),
        "d1d4_precision_report.latest.json": ({}, None),
        "wnal_level_report.json": ({}, None),
        "control_optimization_report.json": ({}, None),
        "sil_verification_report.json": ({}, None),
        "pipeline_evaluation.latest.json": (
            {
                "dimension_scores": {"d1_hydro_modeling": {"mean_nse": 0}},
                "coverage_pct": 0.9512,
                "case_id": "demo",
            },
            "cases/demo/contracts/pipeline_evaluation.latest.json",
        ),
        "rollout_minimal_loop.latest.json": (
            {"readiness": {"ready": True, "status": "ready"}},
            "cases/demo/contracts/rollout_minimal_loop.latest.json",
        ),
        "final_report.latest.json": ({}, None),
    }

    def fake_load(case_id: str, filename: str):
        assert case_id == "demo"
        return fixtures.get(filename, ({}, None))

    monkeypatch.setattr(export_rollout_readiness_baseline, "_load_contract_json", fake_load)
    monkeypatch.setattr(export_rollout_readiness_baseline, "load_case_config", lambda case_id: {"case_id": case_id, "project_type": "canal"})

    dimensions, contracts, _raw_contracts = export_rollout_readiness_baseline._build_case_dimensions("demo")

    modeling = dimensions["modeling_readiness"]
    assert modeling["status"] == "ready"
    assert "numeric NSE not applicable" in modeling["summary"]
    assert modeling["metrics"]["canal_case_ready_for_review"] is True
    assert modeling["metrics"]["project_type"] == "canal"
    assert contracts["pipeline_evaluation"].endswith("pipeline_evaluation.latest.json")


def test_greenfield_cascade_case_promotes_modeling_readiness_from_blocked_to_review(monkeypatch) -> None:
    fixtures = {
        "source_import_session.latest.json": ({"record_count": 1, "imported_at": "2026-04-12T00:00:00Z"}, "cases/demo/contracts/source_import_session.latest.json"),
        "parameter_governance.latest.json": (
            {"stage_catalog": {stage: {"parameter_count": 1} for stage in export_rollout_readiness_baseline.REQUIRED_PARAMETER_STAGES}},
            "cases/demo/contracts/parameter_governance.latest.json",
        ),
        "autonomy_assessment.latest.json": (
            {
                "scores": {
                    "simulation": 0.0,
                    "control": 0.3,
                    "scheduling": 0.3,
                    "sil": 0.7,
                    "odd": 0.0,
                    "wnal": 0.0,
                },
                "judge": {"verdict": "BLOCK", "overall_score": 0.4, "weak_dimensions": []},
                "generated_at": "2026-04-12T00:00:00Z",
            },
            "cases/demo/contracts/autonomy_assessment.latest.json",
        ),
        "autonomy_autorun.latest.json": ({}, None),
        "outcome_coverage_report.latest.json": ({"gate_status": "passed", "outcome_coverage": 1.0}, "cases/demo/contracts/outcome_coverage_report.latest.json"),
        "e2e_outcome_verification_report.json": ({}, "cases/demo/contracts/e2e_outcome_verification_report.json"),
        "odd_coverage_report.json": ({"coverage_metrics": {"recovery_success_rate": 1.0, "total_scenarios_tested": 8}}, "cases/demo/contracts/odd_coverage_report.json"),
        "d1d4_precision_report.latest.json": ({}, None),
        "wnal_level_report.json": ({}, None),
        "control_optimization_report.json": ({}, None),
        "sil_verification_report.json": ({}, None),
        "pipeline_evaluation.latest.json": (
            {
                "dimension_scores": {
                    "d1_hydro_modeling": {"mean_nse": 0, "station_count": 0},
                },
                "coverage_pct": 0.9512,
                "case_id": "demo",
            },
            "cases/demo/contracts/pipeline_evaluation.latest.json",
        ),
        "rollout_minimal_loop.latest.json": (
            {"readiness": {"ready": True, "status": "ready"}},
            "cases/demo/contracts/rollout_minimal_loop.latest.json",
        ),
        "final_report.latest.json": ({}, None),
    }

    def fake_load(case_id: str, filename: str):
        assert case_id == "demo"
        return fixtures.get(filename, ({}, None))

    monkeypatch.setattr(export_rollout_readiness_baseline, "_load_contract_json", fake_load)
    monkeypatch.setattr(
        export_rollout_readiness_baseline,
        "load_case_config",
        lambda case_id: {"case_id": case_id, "project_type": "cascade_hydro"},
    )

    dimensions, contracts, _raw_contracts = export_rollout_readiness_baseline._build_case_dimensions("demo")

    modeling = dimensions["modeling_readiness"]
    assert modeling["status"] == "review"
    assert "cascade greenfield" in modeling["summary"]
    assert modeling["metrics"]["greenfield_cascade_lane_gates_met"] is True
    assert modeling["metrics"]["station_count"] == 0
    assert modeling["metrics"]["project_type"] == "cascade_hydro"
    assert contracts["pipeline_evaluation"].endswith("pipeline_evaluation.latest.json")

    gate = export_rollout_readiness_baseline._build_release_gate("demo", dimensions)
    modeling_review = next(r for r in gate["review_items"] if r["dimension"] == "modeling_readiness")
    assert "绿场梯级" in modeling_review["suggested_action"]
    assert "station_geolocation" in modeling_review["suggested_action"]
    assert "simulation" not in modeling_review["suggested_action"]


def test_release_board_exposes_final_report_status_for_rollout_cases() -> None:
    loop_cfg = load_loop_yaml(
        export_rollout_readiness_baseline.WORKSPACE,
        export_rollout_readiness_baseline.DEFAULT_CONFIG,
    )
    case_ids = resolve_case_ids(loop_cfg, export_rollout_readiness_baseline.WORKSPACE)

    board = export_rollout_readiness_baseline._build_release_board(case_ids, _fixture_governance())
    rows_by_case = {row["case_id"]: row for row in board["cases"]}

    for case_id in ("daduhe", "yinchuojiliao", "zhongxian", "xuhonghe", "jiaodongtiaoshui"):
        row = rows_by_case[case_id]
        assert row["final_report_present"] is True
        assert row["final_report_path"].endswith("final_report.latest.json")
        assert "final_report_status" in row
        assert "final_report_release_board_status" in row
        assert "final_report_promotion_status" in row
        assert "final_report_acceptance_scope" in row
        assert "final_report_acceptance_source" in row


def test_case_dimensions_prefer_case_bound_pipeline_and_d1d4_contracts() -> None:
    dimensions, contracts, _raw_contracts = export_rollout_readiness_baseline._build_case_dimensions("zhongxian")

    modeling = dimensions["modeling_readiness"]
    assert modeling["source_contracts"][0].endswith("pipeline_evaluation.latest.json")
    assert modeling["metrics"]["pipeline_case_id"] == "zhongxian"
    assert contracts["pipeline_evaluation"].endswith("pipeline_evaluation.latest.json")

    wnal = dimensions["wnal"]
    assert wnal["source_contracts"][0].endswith("wnal_level_report.json")
    assert contracts["wnal_level_report"].endswith("wnal_level_report.json")
    assert "wnal_level" in wnal["metrics"]


def test_case_dimensions_choose_latest_autonomy_contract_for_release_judgement() -> None:
    dimensions, contracts, _raw_contracts = export_rollout_readiness_baseline._build_case_dimensions("daduhe")

    autonomy = dimensions["autonomy_quality"]
    assert autonomy["status"] in {"ready", "review"}
    assert autonomy["metrics"]["verdict"] in {"PASS", "WARN"}
    assert autonomy["source_contracts"][0] in {
        contracts["autonomy_assessment"],
        contracts["autonomy_autorun"],
    }


def test_canal_case_autonomy_quality_is_ready_when_only_simulation_is_weak_and_modeling_is_ready(monkeypatch) -> None:
    fixtures = {
        "source_import_session.latest.json": (
            {"record_count": 1, "imported_at": "2026-04-12T00:00:00Z"},
            "cases/demo/contracts/source_import_session.latest.json",
        ),
        "parameter_governance.latest.json": (
            {"stage_catalog": {stage: {"parameter_count": 1} for stage in export_rollout_readiness_baseline.REQUIRED_PARAMETER_STAGES}},
            "cases/demo/contracts/parameter_governance.latest.json",
        ),
        "autonomy_assessment.latest.json": (
            {
                "scores": {
                    "simulation": 0.4264,
                    "control": 0.975,
                    "scheduling": 0.975,
                    "sil": 0.7,
                    "odd": 0.65,
                    "wnal": 0.7,
                },
                "judge": {
                    "verdict": "WARN",
                    "overall_score": 0.774,
                    "weak_dimensions": [{"dimension": "simulation", "score": 0.4264, "target": 0.75, "gap": 0.3236}],
                },
                "generated_at": "2026-04-12T00:00:00Z",
            },
            "cases/demo/contracts/autonomy_assessment.latest.json",
        ),
        "autonomy_autorun.latest.json": ({}, None),
        "outcome_coverage_report.latest.json": (
            {"gate_status": "passed", "outcome_coverage": 1.0},
            "cases/demo/contracts/outcome_coverage_report.latest.json",
        ),
        "e2e_outcome_verification_report.json": ({}, "cases/demo/contracts/e2e_outcome_verification_report.json"),
        "odd_coverage_report.json": (
            {"coverage_metrics": {"recovery_success_rate": 1.0, "total_scenarios_tested": 8}},
            "cases/demo/contracts/odd_coverage_report.json",
        ),
        "d1d4_precision_report.latest.json": ({}, None),
        "wnal_level_report.json": (
            {"status": "ready", "summary": "WNAL L3 (0.70)", "metrics": {"wnal_score": 0.7, "wnal_level": "L3"}},
            "cases/demo/contracts/wnal_level_report.json",
        ),
        "control_optimization_report.json": (
            {"status": "ready", "metrics": {"control_score": 0.975, "scheduling_score": 0.975}},
            "cases/demo/contracts/control_optimization_report.json",
        ),
        "sil_verification_report.json": (
            {"status": "ready", "metrics": {"sil_score": 0.70}},
            "cases/demo/contracts/sil_verification_report.json",
        ),
        "pipeline_evaluation.latest.json": (
            {
                "dimension_scores": {"d1_hydro_modeling": {"mean_nse": 1.0}},
                "coverage_pct": 0.9512,
                "case_id": "demo",
            },
            "cases/demo/contracts/pipeline_evaluation.latest.json",
        ),
        "rollout_minimal_loop.latest.json": (
            {"readiness": {"ready": True, "status": "ready"}},
            "cases/demo/contracts/rollout_minimal_loop.latest.json",
        ),
        "final_report.latest.json": ({}, None),
    }

    def fake_load(case_id: str, filename: str):
        assert case_id == "demo"
        return fixtures.get(filename, ({}, None))

    monkeypatch.setattr(export_rollout_readiness_baseline, "_load_contract_json", fake_load)
    monkeypatch.setattr(export_rollout_readiness_baseline, "load_case_config", lambda case_id: {"case_id": case_id, "project_type": "canal"})

    dimensions, _contracts, _raw_contracts = export_rollout_readiness_baseline._build_case_dimensions("demo")

    assert dimensions["modeling_readiness"]["status"] == "ready"
    assert dimensions["autonomy_quality"]["status"] == "ready"
    assert "simulation warning waived by modeling_readiness" in dimensions["autonomy_quality"]["summary"]


def test_canal_case_autonomy_quality_stays_review_when_other_weak_dimensions_exist(monkeypatch) -> None:
    fixtures = {
        "source_import_session.latest.json": (
            {"record_count": 1, "imported_at": "2026-04-12T00:00:00Z"},
            "cases/demo/contracts/source_import_session.latest.json",
        ),
        "parameter_governance.latest.json": (
            {"stage_catalog": {stage: {"parameter_count": 1} for stage in export_rollout_readiness_baseline.REQUIRED_PARAMETER_STAGES}},
            "cases/demo/contracts/parameter_governance.latest.json",
        ),
        "autonomy_assessment.latest.json": (
            {
                "scores": {
                    "simulation": 0.4264,
                    "control": 0.975,
                    "scheduling": 0.975,
                    "sil": 0.7,
                    "odd": 0.65,
                    "wnal": 0.5,
                },
                "judge": {
                    "verdict": "WARN",
                    "overall_score": 0.7501,
                    "weak_dimensions": [
                        {"dimension": "simulation", "score": 0.4264, "target": 0.75, "gap": 0.3236},
                        {"dimension": "wnal", "score": 0.5, "target": 0.7, "gap": 0.2},
                    ],
                },
                "generated_at": "2026-04-12T00:00:00Z",
            },
            "cases/demo/contracts/autonomy_assessment.latest.json",
        ),
        "autonomy_autorun.latest.json": ({}, None),
        "outcome_coverage_report.latest.json": (
            {"gate_status": "passed", "outcome_coverage": 1.0},
            "cases/demo/contracts/outcome_coverage_report.latest.json",
        ),
        "e2e_outcome_verification_report.json": ({}, "cases/demo/contracts/e2e_outcome_verification_report.json"),
        "odd_coverage_report.json": (
            {"coverage_metrics": {"recovery_success_rate": 1.0, "total_scenarios_tested": 8}},
            "cases/demo/contracts/odd_coverage_report.json",
        ),
        "d1d4_precision_report.latest.json": ({}, None),
        "wnal_level_report.json": (
            {"status": "review", "summary": "WNAL L2 (0.50)", "metrics": {"wnal_score": 0.5, "wnal_level": "L2"}},
            "cases/demo/contracts/wnal_level_report.json",
        ),
        "control_optimization_report.json": (
            {"status": "ready", "metrics": {"control_score": 0.975, "scheduling_score": 0.975}},
            "cases/demo/contracts/control_optimization_report.json",
        ),
        "sil_verification_report.json": (
            {"status": "ready", "metrics": {"sil_score": 0.70}},
            "cases/demo/contracts/sil_verification_report.json",
        ),
        "pipeline_evaluation.latest.json": (
            {
                "dimension_scores": {"d1_hydro_modeling": {"mean_nse": 1.0}},
                "coverage_pct": 0.9512,
                "case_id": "demo",
            },
            "cases/demo/contracts/pipeline_evaluation.latest.json",
        ),
        "rollout_minimal_loop.latest.json": (
            {"readiness": {"ready": True, "status": "ready"}},
            "cases/demo/contracts/rollout_minimal_loop.latest.json",
        ),
        "final_report.latest.json": ({}, None),
    }

    def fake_load(case_id: str, filename: str):
        assert case_id == "demo"
        return fixtures.get(filename, ({}, None))

    monkeypatch.setattr(export_rollout_readiness_baseline, "_load_contract_json", fake_load)
    monkeypatch.setattr(export_rollout_readiness_baseline, "load_case_config", lambda case_id: {"case_id": case_id, "project_type": "canal"})

    dimensions, _contracts, _raw_contracts = export_rollout_readiness_baseline._build_case_dimensions("demo")

    assert dimensions["modeling_readiness"]["status"] == "ready"
    assert dimensions["autonomy_quality"]["status"] == "review"


def test_case_dimensions_prefer_new_p1_contracts_when_present(monkeypatch) -> None:
    fixtures = {
        "source_import_session.latest.json": ({"record_count": 1, "imported_at": "2026-04-12T00:00:00Z"}, "cases/demo/contracts/source_import_session.latest.json"),
        "parameter_governance.latest.json": (
            {"stage_catalog": {stage: {"parameter_count": 1} for stage in export_rollout_readiness_baseline.REQUIRED_PARAMETER_STAGES}},
            "cases/demo/contracts/parameter_governance.latest.json",
        ),
        "autonomy_assessment.latest.json": (
            {
                "scores": {
                    "simulation": 0.9,
                    "control": 0.3,
                    "scheduling": 0.3,
                    "sil": 0.3,
                    "odd": 0.65,
                    "wnal": 0.1,
                },
                "judge": {"verdict": "WARN", "overall_score": 0.8, "weak_dimensions": []},
                "generated_at": "2026-04-12T00:00:00Z",
            },
            "cases/demo/contracts/autonomy_assessment.latest.json",
        ),
        "autonomy_autorun.latest.json": ({}, None),
        "outcome_coverage_report.latest.json": ({"gate_status": "passed", "outcome_coverage": 1.0}, "cases/demo/contracts/outcome_coverage_report.latest.json"),
        "e2e_outcome_verification_report.json": ({}, "cases/demo/contracts/e2e_outcome_verification_report.json"),
        "odd_coverage_report.json": (
            {"coverage_metrics": {"recovery_success_rate": 1.0, "total_scenarios_tested": 8}},
            "cases/demo/contracts/odd_coverage_report.json",
        ),
        "d1d4_precision_report.latest.json": ({"wnal_score": 0.0, "wnal_level": "L0"}, "cases/demo/contracts/d1d4_precision_report.latest.json"),
        "wnal_level_report.json": (
            {
                "status": "ready",
                "summary": "WNAL L3 (0.72)",
                "metrics": {"wnal_score": 0.72, "wnal_level": "L3"},
                "source_contracts": ["cases/demo/contracts/d1d4_precision_report.latest.json"],
            },
            "cases/demo/contracts/wnal_level_report.json",
        ),
        "control_optimization_report.json": (
            {
                "status": "ready",
                "metrics": {"control_score": 0.91, "scheduling_score": 0.88},
                "source_contracts": ["cases/demo/contracts/autonomy_assessment.latest.json"],
            },
            "cases/demo/contracts/control_optimization_report.json",
        ),
        "sil_verification_report.json": (
            {
                "status": "review",
                "metrics": {"sil_score": 0.70},
                "source_contracts": ["cases/demo/contracts/autonomy_assessment.latest.json"],
            },
            "cases/demo/contracts/sil_verification_report.json",
        ),
        "pipeline_evaluation.latest.json": (
            {"dimension_scores": {"d1_hydro_modeling": {"mean_nse": 0.9}}, "case_id": "demo"},
            "cases/demo/contracts/pipeline_evaluation.latest.json",
        ),
        "rollout_minimal_loop.latest.json": ({}, None),
    }

    def fake_load(case_id: str, filename: str):
        assert case_id == "demo"
        return fixtures.get(filename, ({}, None))

    monkeypatch.setattr(export_rollout_readiness_baseline, "_load_contract_json", fake_load)

    dimensions, contracts, _raw_contracts = export_rollout_readiness_baseline._build_case_dimensions("demo")

    assert dimensions["wnal"]["status"] == "ready"
    assert dimensions["wnal"]["source_contracts"][0].endswith("wnal_level_report.json")
    assert dimensions["wnal"]["metrics"]["wnal_level"] == "L3"

    assert dimensions["control_sil_odd"]["status"] == "review"
    assert dimensions["control_sil_odd"]["source_contracts"][0].endswith("control_optimization_report.json")
    assert dimensions["control_sil_odd"]["source_contracts"][1].endswith("sil_verification_report.json")
    assert dimensions["control_sil_odd"]["metrics"]["control_contract_status"] == "ready"
    assert dimensions["control_sil_odd"]["metrics"]["sil_contract_status"] == "review"

    assert contracts["wnal_level_report"].endswith("wnal_level_report.json")
    assert contracts["control_optimization_report"].endswith("control_optimization_report.json")
    assert contracts["sil_verification_report"].endswith("sil_verification_report.json")
