from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

target = importlib.import_module("workflows.run_full_modeling")


def _stub_paths(tmp_path: Path) -> dict[str, Path]:
    case_dir = tmp_path / "cases" / "demo_case"
    contracts_dir = case_dir / "contracts"
    product_outputs_dir = case_dir / "source_selection" / "product_outputs"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    product_outputs_dir.mkdir(parents=True, exist_ok=True)
    return {
        "case_dir": case_dir,
        "contracts": contracts_dir,
        "pipeline_script": case_dir / "source_selection" / "product" / "pipeline.py",
        "product_outputs": product_outputs_dir,
        "case_manifest": contracts_dir / "case_manifest.json",
        "source_bundle": contracts_dir / "source_bundle.contract.json",
    }


def test_run_pipeline_marks_skipped_stages_as_degraded(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(
        target,
        "_load_json",
        lambda path: {},
    )
    monkeypatch.setattr(
        target,
        "run_source_discovery",
        lambda paths: {"stage": "source_discovery", "status": "completed"},
    )
    monkeypatch.setattr(
        target,
        "run_data_pack",
        lambda paths: {"stage": "data_pack", "status": "completed"},
    )
    monkeypatch.setattr(
        target,
        "run_delineation",
        lambda paths, cfg: {"stage": "delineation", "status": "completed"},
    )
    monkeypatch.setattr(
        target,
        "run_hydrology",
        lambda paths, cfg: {"stage": "hydrology", "status": "completed"},
    )
    monkeypatch.setattr(
        target,
        "run_hydraulics_steady",
        lambda paths, cfg: {"stage": "hydraulics_steady", "status": "completed"},
    )
    monkeypatch.setattr(
        target,
        "run_hydraulics_unsteady",
        lambda paths, cfg: {"stage": "hydraulics_unsteady", "status": "completed"},
    )
    monkeypatch.setattr(
        target,
        "run_coupled",
        lambda paths, cfg_hydro, cfg_hydraulics: {"stage": "coupled", "status": "completed"},
    )
    monkeypatch.setattr(
        target,
        "_write_json",
        lambda path, payload: None,
    )

    report = target.run_pipeline(
        case_id="demo_case",
        stages=[
            "source_discovery",
            "data_pack",
            "delineation",
            "hydrology",
            "hydraulics_steady",
            "hydraulics_unsteady",
            "coupled",
        ],
    )

    assert report["status"] == "degraded"
    assert report["outcome_status"] == "degraded"
    assert report["quality_gate_passed"] is False
    assert "hydraulics_steady" in str(report["quality_reason"])
    assert "coupled" in str(report["quality_reason"])


def test_source_bundle_cross_section_role_unblocks_d2(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    bundle_path = tmp_path / "cross_section_mileage.nc"
    bundle_path.write_text("stub", encoding="utf-8")

    def fake_load_json(path: Path) -> dict:
        if path == paths["source_bundle"]:
            return {
                "records": [
                    {
                        "role": "cross_section_mileage",
                        "artifact": {"path": str(bundle_path)},
                    }
                ]
            }
        return {}

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", fake_load_json)
    monkeypatch.setattr(target, "run_source_discovery", lambda paths: {"stage": "source_discovery", "status": "completed"})
    monkeypatch.setattr(target, "run_data_pack", lambda paths: {"stage": "data_pack", "status": "completed"})
    monkeypatch.setattr(target, "run_delineation", lambda paths, cfg: {"stage": "delineation", "status": "completed"})
    monkeypatch.setattr(target, "run_hydrology", lambda paths, cfg: {"stage": "hydrology", "status": "completed"})
    monkeypatch.setattr(target, "run_hydraulics_steady", lambda paths, cfg: {"stage": "hydraulics_steady", "status": "completed"})
    monkeypatch.setattr(target, "run_hydraulics_unsteady", lambda paths, cfg: {"stage": "hydraulics_unsteady", "status": "completed"})
    monkeypatch.setattr(target, "run_coupled", lambda paths, cfg_hydro, cfg_hydraulics: {"stage": "coupled", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)

    report = target.run_pipeline(case_id="demo_case", stages=["hydraulics_steady", "hydraulics_unsteady", "coupled"])

    assert report["status"] == "completed"
    assert [step["status"] for step in report["steps"]] == ["completed", "completed", "completed"]


def test_hydraulic_params_section_count_unblocks_d2(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    (paths["product_outputs"] / "hydraulic_params.json").write_text("{}", encoding="utf-8")

    def fake_load_json(path: Path) -> dict:
        if path == paths["source_bundle"]:
            return {"records": []}
        if path == paths["product_outputs"] / "hydraulic_params.json":
            return {"channels": [{"section_count": 2}]}
        return {}

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", fake_load_json)
    monkeypatch.setattr(target, "run_hydraulics_steady", lambda paths, cfg: {"stage": "hydraulics_steady", "status": "completed"})
    monkeypatch.setattr(target, "run_hydraulics_unsteady", lambda paths, cfg: {"stage": "hydraulics_unsteady", "status": "completed"})
    monkeypatch.setattr(target, "run_coupled", lambda paths, cfg_hydro, cfg_hydraulics: {"stage": "coupled", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)

    report = target.run_pipeline(case_id="demo_case", stages=["hydraulics_steady"])

    assert report["status"] == "completed"
    assert report["steps"][0]["status"] == "completed"


def test_hydraulic_params_sections_count_unblocks_d2(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    (paths["product_outputs"] / "hydraulic_params.json").write_text("{}", encoding="utf-8")

    def fake_load_json(path: Path) -> dict:
        if path == paths["source_bundle"]:
            return {"records": []}
        if path == paths["product_outputs"] / "hydraulic_params.json":
            return {"sections_count": 3}
        return {}

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", fake_load_json)
    monkeypatch.setattr(target, "run_hydraulics_steady", lambda paths, cfg: {"stage": "hydraulics_steady", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)

    report = target.run_pipeline(case_id="demo_case", stages=["hydraulics_steady"])

    assert report["status"] == "completed"
    assert report["steps"][0]["status"] == "completed"


def test_knowledge_cross_section_data_type_unblocks_d2(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)

    def fake_load_json(path: Path) -> dict:
        if path == paths["source_bundle"]:
            return {"records": []}
        if path == paths["contracts"] / "knowledge.latest.json":
            return {"assets": [{"data_type": "CROSS_SECTION"}]}
        return {}

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", fake_load_json)
    monkeypatch.setattr(target, "run_hydraulics_steady", lambda paths, cfg: {"stage": "hydraulics_steady", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)
    (paths["contracts"] / "knowledge.latest.json").write_text("{}", encoding="utf-8")

    report = target.run_pipeline(case_id="demo_case", stages=["hydraulics_steady"])

    assert report["status"] == "completed"
    assert report["steps"][0]["status"] == "completed"


def test_non_cross_section_knowledge_asset_does_not_unblock_d2(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)

    def fake_load_json(path: Path) -> dict:
        if path == paths["source_bundle"]:
            return {"records": []}
        if path == paths["contracts"] / "knowledge.latest.json":
            return {"assets": [{"data_type": "LONGITUDINAL_SECTION"}]}
        return {}

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", fake_load_json)
    monkeypatch.setattr(target, "run_hydraulics_steady", lambda paths, cfg: {"stage": "hydraulics_steady", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)
    (paths["contracts"] / "knowledge.latest.json").write_text("{}", encoding="utf-8")

    report = target.run_pipeline(case_id="demo_case", stages=["hydraulics_steady"])

    assert report["status"] == "degraded"
    assert report["steps"][0]["status"] == "Skipped_Data_Missing"


def test_missing_cross_sections_still_skips_d2(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    (paths["product_outputs"] / "hydraulic_params.json").write_text("{}", encoding="utf-8")

    def fake_load_json(path: Path) -> dict:
        if path == paths["source_bundle"]:
            return {"records": []}
        if path == paths["product_outputs"] / "hydraulic_params.json":
            return {"channels": [{"section_count": 0}], "sections_count": 0}
        return {}

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", fake_load_json)
    monkeypatch.setattr(target, "run_hydraulics_steady", lambda paths, cfg: {"stage": "hydraulics_steady", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)

    report = target.run_pipeline(case_id="demo_case", stages=["hydraulics_steady"])

    assert report["status"] == "degraded"
    assert report["steps"][0]["status"] == "Skipped_Data_Missing"
    assert report["steps"][0]["reason"] == "Missing Cross-Section data"


def test_run_source_discovery_reuses_existing_outputs_when_pipeline_missing(tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    ready_path = paths["product_outputs"] / "outlets.delineation_ready.json"
    control_map_path = paths["product_outputs"] / "control_station_mapping.json"
    reliability_path = paths["product_outputs"] / "source_reliability.json"
    coordinate_path = paths["product_outputs"] / "coordinate_validation.json"
    ready_path.write_text('{"count": 1, "outlets": [{"name": "A", "lat": 1.0, "lon": 2.0}]}', encoding="utf-8")
    control_map_path.write_text("{}", encoding="utf-8")
    reliability_path.write_text("{}", encoding="utf-8")
    coordinate_path.write_text("{}", encoding="utf-8")

    result = target.run_source_discovery(paths)

    assert result["status"] == "completed"
    assert result["mode"] == "reused_existing_outputs"
    assert result["pipeline_present"] is False
    assert result["outlet_count"] == 1
    assert result["outputs"] == {
        "outlets_delineation_ready": str(ready_path),
        "control_station_mapping": str(control_map_path),
        "source_reliability": str(reliability_path),
        "coordinate_validation": str(coordinate_path),
    }


def test_run_source_discovery_reports_insufficient_data_when_cached_outlets_empty(tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    ready_path = paths["product_outputs"] / "outlets.delineation_ready.json"
    (paths["product_outputs"] / "control_station_mapping.json").write_text("{}", encoding="utf-8")
    (paths["product_outputs"] / "source_reliability.json").write_text("{}", encoding="utf-8")
    (paths["product_outputs"] / "coordinate_validation.json").write_text("{}", encoding="utf-8")
    ready_path.write_text('{"count": 0, "outlets": []}', encoding="utf-8")

    result = target.run_source_discovery(paths)

    assert result["status"] == "insufficient_data"
    assert result["reason"] == "No delineation-ready outlets"
    assert result["reason_code"] == "no_delineation_ready_outlets"
    assert result["outlet_count"] == 0


def test_run_source_discovery_fails_without_pipeline_or_complete_cached_outputs(tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    (paths["product_outputs"] / "outlets.delineation_ready.json").write_text('{"count": 1, "outlets": [{"name": "A", "lat": 1.0, "lon": 2.0}]}', encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="cached source_discovery outputs are incomplete"):
        target.run_source_discovery(paths)


def test_run_source_discovery_fails_without_pipeline_or_cached_outputs(tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)

    with pytest.raises(FileNotFoundError, match="Pipeline not found"):
        target.run_source_discovery(paths)


def test_run_data_pack_reports_insufficient_data_when_outlets_empty(tmp_path: Path, monkeypatch) -> None:
    paths = _stub_paths(tmp_path)
    (paths["product_outputs"] / "outlets.delineation_ready.json").write_text('{"count": 0, "outlets": []}', encoding="utf-8")
    monkeypatch.setattr(target, "subprocess", None)

    result = target.run_data_pack(paths)

    assert result == {
        "stage": "data_pack",
        "status": "insufficient_data",
        "reason": "No delineation-ready outlets",
        "reason_code": "no_delineation_ready_outlets",
        "outlet_count": 0,
    }


def test_run_data_pack_reports_insufficient_data_when_count_zero_without_outlet_list(tmp_path: Path, monkeypatch) -> None:
    paths = _stub_paths(tmp_path)
    (paths["product_outputs"] / "outlets.delineation_ready.json").write_text('{"count": 0}', encoding="utf-8")
    monkeypatch.setattr(target, "subprocess", None)

    result = target.run_data_pack(paths)

    assert result["status"] == "insufficient_data"
    assert result["reason"] == "No delineation-ready outlets"
    assert result["reason_code"] == "no_delineation_ready_outlets"


def test_run_pipeline_skips_downstream_when_no_delineation_ready_outlets(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", lambda path: {"records": []})
    monkeypatch.setattr(target, "run_source_discovery", lambda paths: {"stage": "source_discovery", "status": "insufficient_data", "reason": "No delineation-ready outlets", "reason_code": "no_delineation_ready_outlets", "outlet_count": 0})
    monkeypatch.setattr(target, "run_data_pack", lambda paths: {"stage": "data_pack", "status": "insufficient_data", "reason": "No delineation-ready outlets", "reason_code": "no_delineation_ready_outlets", "outlet_count": 0})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)

    report = target.run_pipeline(case_id="demo_case", stages=["source_discovery", "data_pack", "delineation", "hydrology", "hydraulics_steady", "coupled"])

    assert report["status"] == "degraded"
    assert [step["status"] for step in report["steps"]] == [
        "insufficient_data",
        "insufficient_data",
        "Skipped_Data_Missing",
        "Skipped_Data_Missing",
        "Skipped_Data_Missing",
        "Skipped_Data_Missing",
    ]
    assert all(step.get("reason") == "No delineation-ready outlets" for step in report["steps"][2:])
    assert all(step.get("reason_code") == "no_delineation_ready_outlets" for step in report["steps"][2:])


def test_run_pipeline_uses_reason_code_instead_of_reason_text(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", lambda path: {"records": []})
    monkeypatch.setattr(
        target,
        "run_source_discovery",
        lambda paths: {
            "stage": "source_discovery",
            "status": "insufficient_data",
            "reason": "custom wording that should not control flow",
            "reason_code": "no_delineation_ready_outlets",
            "outlet_count": 0,
        },
    )
    monkeypatch.setattr(target, "run_delineation", lambda paths, cfg: {"stage": "delineation", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)

    report = target.run_pipeline(case_id="demo_case", stages=["source_discovery", "delineation"])

    assert report["steps"][1]["status"] == "Skipped_Data_Missing"
    assert report["steps"][1]["reason"] == "No delineation-ready outlets"
    assert report["steps"][1]["reason_code"] == "no_delineation_ready_outlets"


def test_run_pipeline_does_not_use_reason_text_without_reason_code(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", lambda path: {"records": []})
    monkeypatch.setattr(
        target,
        "run_source_discovery",
        lambda paths: {
            "stage": "source_discovery",
            "status": "insufficient_data",
            "reason": "No delineation-ready outlets",
            "outlet_count": 0,
        },
    )
    monkeypatch.setattr(target, "run_delineation", lambda paths, cfg: {"stage": "delineation", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)

    report = target.run_pipeline(case_id="demo_case", stages=["source_discovery", "delineation"])

    assert report["steps"][1]["status"] == "completed"


def test_run_pipeline_uses_data_pack_reason_code_instead_of_reason_text(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", lambda path: {"records": []})
    monkeypatch.setattr(target, "run_source_discovery", lambda paths: {"stage": "source_discovery", "status": "completed"})
    monkeypatch.setattr(
        target,
        "run_data_pack",
        lambda paths: {
            "stage": "data_pack",
            "status": "insufficient_data",
            "reason": "custom wording that should not control flow",
            "reason_code": "no_delineation_ready_outlets",
            "outlet_count": 0,
        },
    )
    monkeypatch.setattr(target, "run_delineation", lambda paths, cfg: {"stage": "delineation", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)

    report = target.run_pipeline(case_id="demo_case", stages=["source_discovery", "data_pack", "delineation"])

    assert report["steps"][2]["status"] == "Skipped_Data_Missing"
    assert report["steps"][2]["reason"] == "No delineation-ready outlets"
    assert report["steps"][2]["reason_code"] == "no_delineation_ready_outlets"


def test_run_pipeline_does_not_use_data_pack_reason_text_without_reason_code(monkeypatch, tmp_path: Path) -> None:
    paths = _stub_paths(tmp_path)
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_paths", lambda case_id: paths)
    monkeypatch.setattr(target, "_load_yaml", lambda path: {})
    monkeypatch.setattr(target, "_load_json", lambda path: {"records": []})
    monkeypatch.setattr(target, "run_source_discovery", lambda paths: {"stage": "source_discovery", "status": "completed"})
    monkeypatch.setattr(
        target,
        "run_data_pack",
        lambda paths: {
            "stage": "data_pack",
            "status": "insufficient_data",
            "reason": "No delineation-ready outlets",
            "outlet_count": 0,
        },
    )
    monkeypatch.setattr(target, "run_delineation", lambda paths, cfg: {"stage": "delineation", "status": "completed"})
    monkeypatch.setattr(target, "_write_json", lambda path, payload: None)

    report = target.run_pipeline(case_id="demo_case", stages=["source_discovery", "data_pack", "delineation"])

    assert report["steps"][2]["status"] == "completed"
