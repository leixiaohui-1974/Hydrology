import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import export_case_p1_contracts


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_export_case_contracts_writes_triplet_from_existing_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(export_case_p1_contracts, "WORKSPACE", tmp_path)
    case_id = "demo_case"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"

    _write_json(
        contracts_dir / "d1d4_precision_report.latest.json",
        {
            "case_id": case_id,
            "wnal_score": 0.72,
            "wnal_level": "L3",
            "capability_score": 4.65,
            "target_nse": 0.85,
            "dimensions": {"d1": {"mean_val_nse": 0.91, "stations_total": 3}},
            "overall_problems": ["weak_station"],
            "overall_recommendations": ["improve calibration"],
        },
    )
    _write_json(
        contracts_dir / "autonomy_assessment.latest.json",
        {
            "case_id": case_id,
            "scores": {
                "control": 0.91,
                "scheduling": 0.88,
                "sil": 0.70,
                "odd": 0.65,
                "wnal": 0.72,
            },
            "recommended_actions": [{"dimension": "simulation", "workflow": "hyd_sim"}],
        },
    )
    _write_json(
        contracts_dir / "odd_coverage_report.json",
        {
            "coverage_metrics": {
                "total_scenarios_tested": 8,
                "recovery_success_rate": 1.0,
            }
        },
    )
    _write_json(
        contracts_dir / "control_validation.latest.json",
        {
            "control": {
                "pass_rate": 0.63,
                "controller_backend": "base_mpc",
                "physics_backend": "segmented_hf",
                "average_tracking_error": 0.12,
            },
            "sil": {
                "pass_rate": 0.5,
                "scene_coverage": 0.75,
                "scenario_count": 6,
                "passed_count": 3,
            },
            "strict_revalidation": {"status": "missing"},
            "summary": {"blockers": ["SIL pass rate below 100%"]},
        },
    )

    result = export_case_p1_contracts.export_case_contracts(case_id)

    wnal_path = contracts_dir / "wnal_level_report.json"
    control_path = contracts_dir / "control_optimization_report.json"
    sil_path = contracts_dir / "sil_verification_report.json"

    assert result["wnal_level_report"] == f"cases/{case_id}/contracts/wnal_level_report.json"
    assert result["control_optimization_report"] == f"cases/{case_id}/contracts/control_optimization_report.json"
    assert result["sil_verification_report"] == f"cases/{case_id}/contracts/sil_verification_report.json"

    wnal = json.loads(wnal_path.read_text(encoding="utf-8"))
    assert wnal["status"] == "ready"
    assert wnal["metrics"]["wnal_level"] == "L3"
    assert wnal["metrics"]["wnal_score"] == 0.72

    control = json.loads(control_path.read_text(encoding="utf-8"))
    assert control["status"] == "review"
    assert control["metrics"]["control_score"] == 0.91
    assert control["metrics"]["scheduling_score"] == 0.88
    assert control["metrics"]["control_pass_rate"] == 0.63

    sil = json.loads(sil_path.read_text(encoding="utf-8"))
    assert sil["status"] == "review"
    assert sil["metrics"]["sil_score"] == 0.70
    assert sil["metrics"]["sil_pass_rate"] == 0.5
    assert sil["metrics"]["scenario_count"] == 6


def test_export_case_contracts_prefers_pipedream_wnal_for_canal_cases(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(export_case_p1_contracts, "WORKSPACE", tmp_path)
    case_id = "demo_case"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"

    _write_json(
        contracts_dir / "d1d4_precision_report.latest.json",
        {
            "case_id": case_id,
            "wnal_score": 0.0,
            "wnal_level": "L0",
            "dimensions": {"d1": {"mean_val_nse": 0.0, "stations_total": 0}},
        },
    )
    _write_json(
        contracts_dir / "autonomy_assessment.latest.json",
        {
            "case_id": case_id,
            "scores": {"wnal": 0.0},
        },
    )

    control_case_dir = tmp_path / "pipedream-hydrology-integration-lab" / "hydromind_control_server" / "configs" / "cases"
    control_case_dir.mkdir(parents=True, exist_ok=True)
    (control_case_dir / "demo_case.yaml").write_text(
        "wnal:\n  current_level: L3\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        export_case_p1_contracts,
        "load_case_config",
        lambda cid: {"case_id": cid, "project_type": "canal"},
    )
    monkeypatch.setattr(export_case_p1_contracts, "CONTROL_CASE_DIR", control_case_dir)

    result = export_case_p1_contracts.export_case_contracts(case_id)

    wnal = json.loads((contracts_dir / "wnal_level_report.json").read_text(encoding="utf-8"))
    assert result["wnal_level_report"] == f"cases/{case_id}/contracts/wnal_level_report.json"
    assert wnal["status"] == "ready"
    assert wnal["metrics"]["wnal_score"] == 0.7
    assert wnal["metrics"]["wnal_level"] == "L3"
    assert wnal["metrics"]["control_yaml_wnal_level"] == "L3"
    assert wnal["evidence"]["primary_source_contract"].endswith("pipedream-hydrology-integration-lab/hydromind_control_server/configs/cases/demo_case.yaml")
    assert wnal["source_contracts"][0].endswith("pipedream-hydrology-integration-lab/hydromind_control_server/configs/cases/demo_case.yaml")
