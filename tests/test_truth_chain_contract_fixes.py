import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "workflows") not in sys.path:
    sys.path.insert(0, str(ROOT / "workflows"))

import rebuild_case_pipeline_summaries
import run_auto_learning_loop


def test_validate_target_threshold_uses_calibration_fallback_when_nse_evidence_missing(tmp_path: Path) -> None:
    contracts_dir = tmp_path / "cases" / "daduhe" / "contracts"
    contracts_dir.mkdir(parents=True)
    calibration_path = contracts_dir / "hydrology_calibration.latest.json"
    calibration_path.write_text(
        '{"calibration_metrics": {"nse": 0.654893641025093}}',
        encoding="utf-8",
    )

    validation = run_auto_learning_loop.validate_target_threshold(
        case_id="daduhe",
        stage="hydrology",
        requested_target=0.6548,
        metric_file=str(contracts_dir / "hydrology_nse_evidence.latest.json"),
        metric_key="comparable_nse",
        config_path=str(ROOT / "configs" / "daduhe.yaml"),
    )

    assert validation["status"] == "rejected"
    assert validation["metric_source_mode"] == "hydrology_calibration_fallback"
    assert validation["current_metric"] == 0.654893641025093
    assert "pseudo-converged success" in validation["reason"]


def test_build_case_pipeline_evaluation_rewrites_rollout_cases_as_case_bound() -> None:
    path, payload = rebuild_case_pipeline_summaries.build_case_pipeline_evaluation("zhongxian")

    assert path.name == "pipeline_evaluation.latest.json"
    assert payload["case_id"] == "zhongxian"
    assert payload["workflow"] == "case_bound_contract_rebuild"
    assert payload["evaluation_basis"] == "case_bound_contracts"
    assert payload["coverage_pct"] >= 90.0
    assert payload["source_contracts"][0].endswith("self_improving_pipeline.latest.json")
