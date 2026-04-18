from __future__ import annotations

import json
from pathlib import Path

import workflows.run_autonomy_assessment as target


def test_dim_from_odd_coverage_uses_recovery_success_rate() -> None:
    score = target._dim_from_odd_coverage(
        {
            "coverage_metrics": {
                "total_scenarios_tested": 10,
                "recovery_success_rate": 1.0,
            }
        }
    )
    assert score == 0.65


def test_merge_dimension_scores_prefers_odd_coverage_over_zero_wnal_for_odd_dimension() -> None:
    standard = {
        "dimensions": {
            "simulation": {"weight": 1.0, "min_score": 0.75},
            "testing": {"weight": 1.0, "min_score": 0.8},
            "control": {"weight": 1.0, "min_score": 0.7},
            "sil": {"weight": 1.0, "min_score": 0.7},
            "odd": {"weight": 1.0, "min_score": 0.65},
            "wnal": {"weight": 1.0, "min_score": 0.7},
            "scheduling": {"weight": 1.0, "min_score": 0.65},
        }
    }
    scores = target._merge_dimension_scores(
        standard,
        d1d4_dims={"simulation": 0.0},
        d1d4_report={},
        real_val=0.0,
        physics=0.8,
        control=0.9,
        wnal=0.0,
        odd_coverage_score=0.65,
        caps={},
    )
    assert scores["odd"] == 0.65
    assert scores["wnal"] == 0.0


def test_run_autonomy_assessment_prefers_case_bound_wnal_contract(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path
    contracts_dir = workspace / "cases" / "demo" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    standard_path = workspace / "Hydrology" / "configs" / "autonomy_quality_standard.yaml"
    standard_path.parent.mkdir(parents=True, exist_ok=True)
    standard_path.write_text(
        """schema_version: "1.0"
name: demo
thresholds:
  pass_score: 0.75
  warning_score: 0.60
dimensions:
  simulation: {weight: 0.12, min_score: 0.75}
  identification: {weight: 0.10, min_score: 0.70}
  forecast: {weight: 0.10, min_score: 0.70}
  scheduling: {weight: 0.08, min_score: 0.65}
  control: {weight: 0.10, min_score: 0.70}
  evaluation: {weight: 0.10, min_score: 0.75}
  testing: {weight: 0.10, min_score: 0.80}
  sil: {weight: 0.08, min_score: 0.70}
  odd: {weight: 0.08, min_score: 0.65}
  wnal: {weight: 0.08, min_score: 0.70}
  self_diagnosis: {weight: 0.02, min_score: 0.70}
  self_mining: {weight: 0.01, min_score: 0.60}
  self_upgrade: {weight: 0.01, min_score: 0.60}
  self_learning: {weight: 0.00, min_score: 0.60}
artifacts:
  d1d4_report: "cases/{case_id}/contracts/d1d4_precision_report.latest.json"
  real_validation_report: "cases/{case_id}/contracts/real_validation_report.json"
  strict_revalidation_summary: "cases/{case_id}/contracts/strict_revalidation_summary.json"
  selfdiag: "cases/{case_id}/contracts/hydraulic_selfdiag.latest.json"
  precision_improvement: "cases/{case_id}/contracts/precision_improvement.latest.json"
  autolearn: "cases/{case_id}/contracts/dl_autolearn.latest.json"
  deep_asset_record: "cases/{case_id}/contracts/deep_asset_record.latest.json"
  knowledge_mine: "cases/{case_id}/contracts/knowledge_mining.latest.json"
  wnal_report: "external/wnal_report.json"
action_catalog: {}
""",
        encoding="utf-8",
    )

    (workspace / "external").mkdir(parents=True, exist_ok=True)
    (workspace / "external" / "wnal_report.json").write_text(
        json.dumps({"raw_wnal": {"wnal_overall": {"wnal_score": 0.0}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    (contracts_dir / "wnal_level_report.json").write_text(
        json.dumps({"metrics": {"wnal_score": 0.7, "wnal_level": "L3"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "odd_coverage_report.json").write_text(
        json.dumps({"coverage_metrics": {"total_scenarios_tested": 10, "recovery_success_rate": 1.0}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "d1d4_precision_report.latest.json").write_text(
        json.dumps({"dimensions": {}, "wnal_score": 0.0}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "real_validation_report.json").write_text("{}", encoding="utf-8")
    (contracts_dir / "strict_revalidation_summary.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(target, "WORKSPACE", workspace)

    result = target.run_autonomy_assessment("demo", standard_config="Hydrology/configs/autonomy_quality_standard.yaml")
    saved = json.loads((contracts_dir / "autonomy_assessment.latest.json").read_text(encoding="utf-8"))

    assert result["case_id"] == "demo"
    assert result["json_report"] == "cases/demo/contracts/autonomy_assessment.latest.json"
    assert result["md_report"] == "cases/demo/contracts/autonomy_assessment.latest.md"
    assert saved["standard"]["config_path"] == "Hydrology/configs/autonomy_quality_standard.yaml"
    assert saved["scores"]["wnal"] == 0.7
    assert saved["scores"]["odd"] == 0.65


def test_judge_skips_not_required_dimensions_for_canal_cases() -> None:
    standard = {
        "thresholds": {"pass_score": 0.75, "warning_score": 0.60},
        "dimensions": {
            "simulation": {"weight": 0.12, "min_score": 0.75},
            "identification": {"weight": 0.10, "min_score": 0.70, "not_required_for_project_types": ["canal", "pump_canal"]},
            "forecast": {"weight": 0.10, "min_score": 0.70, "not_required_for_project_types": ["canal"]},
            "evaluation": {"weight": 0.10, "min_score": 0.75, "not_required_for_project_types": ["canal"]},
            "scheduling": {"weight": 0.08, "min_score": 0.65},
            "control": {"weight": 0.10, "min_score": 0.70},
            "testing": {"weight": 0.10, "min_score": 0.80},
            "sil": {"weight": 0.08, "min_score": 0.70},
            "odd": {"weight": 0.08, "min_score": 0.65},
            "wnal": {"weight": 0.08, "min_score": 0.70},
        },
    }
    scores = {
        "simulation": 0.4264,
        "identification": 0.0,
        "forecast": 0.0,
        "evaluation": 0.0,
        "scheduling": 0.975,
        "control": 0.975,
        "testing": 0.9792,
        "sil": 0.7,
        "odd": 0.65,
        "wnal": 0.5,
    }

    judge = target._judge(standard, scores, project_type="canal")

    assert "identification" in judge["skipped_dimensions"]
    assert "forecast" in judge["skipped_dimensions"]
    assert "evaluation" in judge["skipped_dimensions"]
    weak_dimensions = {item["dimension"] for item in judge["weak_dimensions"]}
    assert "identification" not in weak_dimensions
    assert "forecast" not in weak_dimensions
    assert "evaluation" not in weak_dimensions
    assert judge["verdict"] == "WARN"


def test_run_autonomy_assessment_marks_canal_case_as_warn_when_only_core_dimensions_apply(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path
    contracts_dir = workspace / "cases" / "demo" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    standard_path = workspace / "Hydrology" / "configs" / "autonomy_quality_standard.yaml"
    standard_path.parent.mkdir(parents=True, exist_ok=True)
    standard_path.write_text(
        """schema_version: "1.0"
name: demo
thresholds:
  pass_score: 0.75
  warning_score: 0.60
dimensions:
  simulation: {weight: 0.12, min_score: 0.75}
  identification: {weight: 0.10, min_score: 0.70, not_required_for_project_types: [canal]}
  forecast: {weight: 0.10, min_score: 0.70, not_required_for_project_types: [canal]}
  scheduling: {weight: 0.08, min_score: 0.65}
  control: {weight: 0.10, min_score: 0.70}
  evaluation: {weight: 0.10, min_score: 0.75, not_required_for_project_types: [canal]}
  testing: {weight: 0.10, min_score: 0.80}
  sil: {weight: 0.08, min_score: 0.70}
  odd: {weight: 0.08, min_score: 0.65}
  wnal: {weight: 0.08, min_score: 0.70}
  self_diagnosis: {weight: 0.02, min_score: 0.70}
  self_mining: {weight: 0.01, min_score: 0.60}
  self_upgrade: {weight: 0.01, min_score: 0.60, not_required_for_project_types: [canal]}
  self_learning: {weight: 0.00, min_score: 0.60, not_required_for_project_types: [canal]}
artifacts:
  d1d4_report: "cases/{case_id}/contracts/d1d4_precision_report.latest.json"
  real_validation_report: "cases/{case_id}/contracts/real_validation_report.json"
  strict_revalidation_summary: "cases/{case_id}/contracts/strict_revalidation_summary.json"
  selfdiag: "cases/{case_id}/contracts/hydraulic_selfdiag.latest.json"
  precision_improvement: "cases/{case_id}/contracts/precision_improvement.latest.json"
  autolearn: "cases/{case_id}/contracts/dl_autolearn.latest.json"
  deep_asset_record: "cases/{case_id}/contracts/deep_asset_record.latest.json"
  knowledge_mine: "cases/{case_id}/contracts/knowledge_mining.latest.json"
  wnal_report: "external/wnal_report.json"
action_catalog: {}
""",
        encoding="utf-8",
    )

    (workspace / "external").mkdir(parents=True, exist_ok=True)
    (workspace / "external" / "wnal_report.json").write_text(
        json.dumps({"metrics": {"wnal_score": 0.5, "wnal_level": "L2"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "wnal_level_report.json").write_text(
        json.dumps({"metrics": {"wnal_score": 0.5, "wnal_level": "L2"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "odd_coverage_report.json").write_text(
        json.dumps({"coverage_metrics": {"total_scenarios_tested": 10, "recovery_success_rate": 1.0}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "d1d4_precision_report.latest.json").write_text(
        json.dumps({"dimensions": {"d2": {"score": 2.1319}, "d1": {"score": 0.0}, "d3": {"score": 0.0}, "d4": {"score": 0.0}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "real_validation_report.json").write_text("{}", encoding="utf-8")
    (contracts_dir / "strict_revalidation_summary.json").write_text(
        json.dumps({"modules": {"physics": {"pass_rate": 0.9792}, "control": {"pass_rate": 0.975}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "hydraulic_selfdiag.latest.json").write_text(
        json.dumps({"final_verdict": "PASS"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "knowledge_mining.latest.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(target, "WORKSPACE", workspace)
    monkeypatch.setattr(target, "load_case_config", lambda case_id: {"case_id": case_id, "project_type": "canal"})

    result = target.run_autonomy_assessment("demo", standard_config="Hydrology/configs/autonomy_quality_standard.yaml")
    saved = json.loads((contracts_dir / "autonomy_assessment.latest.json").read_text(encoding="utf-8"))

    assert result["case_id"] == "demo"
    assert result["json_report"] == "cases/demo/contracts/autonomy_assessment.latest.json"
    assert result["md_report"] == "cases/demo/contracts/autonomy_assessment.latest.md"
    assert saved["judge"]["verdict"] == "WARN"
    assert "identification" in saved["judge"]["skipped_dimensions"]
    assert "forecast" in saved["judge"]["skipped_dimensions"]
    assert "evaluation" in saved["judge"]["skipped_dimensions"]


def test_run_autonomy_assessment_redacts_external_standard_config_and_relativizes_reports(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path
    contracts_dir = workspace / "cases" / "demo" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    external_dir = tmp_path.parent / "external-autonomy"
    external_dir.mkdir(parents=True, exist_ok=True)
    standard_path = external_dir / "autonomy_quality_standard.yaml"
    standard_path.write_text(
        """schema_version: "1.0"
name: demo
thresholds:
  pass_score: 0.75
  warning_score: 0.60
dimensions:
  simulation: {weight: 0.12, min_score: 0.75}
  identification: {weight: 0.10, min_score: 0.70}
  forecast: {weight: 0.10, min_score: 0.70}
  scheduling: {weight: 0.08, min_score: 0.65}
  control: {weight: 0.10, min_score: 0.70}
  evaluation: {weight: 0.10, min_score: 0.75}
  testing: {weight: 0.10, min_score: 0.80}
  sil: {weight: 0.08, min_score: 0.70}
  odd: {weight: 0.08, min_score: 0.65}
  wnal: {weight: 0.08, min_score: 0.70}
  self_diagnosis: {weight: 0.02, min_score: 0.70}
  self_mining: {weight: 0.01, min_score: 0.60}
  self_upgrade: {weight: 0.01, min_score: 0.60}
  self_learning: {weight: 0.00, min_score: 0.60}
artifacts:
  d1d4_report: "cases/{case_id}/contracts/d1d4_precision_report.latest.json"
  real_validation_report: "cases/{case_id}/contracts/real_validation_report.json"
  strict_revalidation_summary: "cases/{case_id}/contracts/strict_revalidation_summary.json"
  selfdiag: "cases/{case_id}/contracts/hydraulic_selfdiag.latest.json"
  precision_improvement: "cases/{case_id}/contracts/precision_improvement.latest.json"
  autolearn: "cases/{case_id}/contracts/dl_autolearn.latest.json"
  deep_asset_record: "cases/{case_id}/contracts/deep_asset_record.latest.json"
  knowledge_mine: "cases/{case_id}/contracts/knowledge_mining.latest.json"
  wnal_report: "external/wnal_report.json"
action_catalog: {}
""",
        encoding="utf-8",
    )

    (workspace / "external").mkdir(parents=True, exist_ok=True)
    (workspace / "external" / "wnal_report.json").write_text(
        json.dumps({"metrics": {"wnal_score": 0.5, "wnal_level": "L2"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "wnal_level_report.json").write_text(
        json.dumps({"metrics": {"wnal_score": 0.5, "wnal_level": "L2"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "odd_coverage_report.json").write_text(
        json.dumps({"coverage_metrics": {"total_scenarios_tested": 10, "recovery_success_rate": 1.0}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "d1d4_precision_report.latest.json").write_text(
        json.dumps({"dimensions": {}, "wnal_score": 0.0}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "real_validation_report.json").write_text("{}", encoding="utf-8")
    (contracts_dir / "strict_revalidation_summary.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(target, "WORKSPACE", workspace)

    result = target.run_autonomy_assessment("demo", standard_config=str(standard_path))
    saved = json.loads((contracts_dir / "autonomy_assessment.latest.json").read_text(encoding="utf-8"))

    assert result["json_report"] == "cases/demo/contracts/autonomy_assessment.latest.json"
    assert result["md_report"] == "cases/demo/contracts/autonomy_assessment.latest.md"
    assert saved["standard"]["config_path"] == "[external]/autonomy_quality_standard.yaml"
