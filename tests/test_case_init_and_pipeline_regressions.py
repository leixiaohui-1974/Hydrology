from __future__ import annotations

import subprocess
from types import SimpleNamespace


def test_create_case_directory_repairs_broken_product_outputs_symlink(
    monkeypatch, tmp_path
) -> None:
    from workflows import run_case_init as target

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)

    case_id = "demo_case"
    case_dir = tmp_path / "cases" / case_id
    source_selection_dir = case_dir / "source_selection"
    source_selection_dir.mkdir(parents=True, exist_ok=True)

    broken_product_outputs = source_selection_dir / "product_outputs"
    broken_product_outputs.symlink_to(source_selection_dir / "missing_product_outputs")

    result = target.create_case_directory(
        case_id,
        "演示案例",
        {"project_type": "canal", "scan_dirs": [], "_auto_generated": {}},
    )

    assert result == case_dir
    assert broken_product_outputs.exists()
    assert broken_product_outputs.is_dir()
    assert not broken_product_outputs.is_symlink()


def test_phase_calibrate_rejects_empty_calibration_report(monkeypatch) -> None:
    from workflows import run_self_improving_pipeline as target

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )
    monkeypatch.setattr(
        target,
        "_read_contract",
        lambda case_id, name: {"stations": []} if name == "calibration_report" else None,
    )

    result = target.phase_calibrate("demo_case", {})

    assert result["phase"] == "calibrate"
    assert result["status"] == "error"
    assert result["error"] == "empty calibration_report"
    assert result["total_stations"] == 0
    assert result["completed_stations"] == 0


def test_phase_diagnose_blocks_convergence_for_empty_calibration_report(
    monkeypatch,
) -> None:
    from workflows import run_self_improving_pipeline as target

    captured = {}

    monkeypatch.setattr(
        target,
        "_read_contract",
        lambda case_id, name: {"stations": []} if name == "calibration_report" else None,
    )
    monkeypatch.setattr(
        target,
        "_write_contract",
        lambda case_id, name, payload: captured.setdefault(name, payload),
    )

    result = target.phase_diagnose("demo_case", {}, 0.8, None)

    assert result["phase"] == "diagnose"
    assert result["status"] == "completed"
    assert result["convergence"] is False
    assert result["reason"] == "empty calibration_report"
    assert result["recommended_actions"][0]["action"] == "rerun_calibration"
    assert captured["diagnosis"]["convergence"] is False


def test_phase_diagnose_prefers_shared_hydrology_nse_evidence(monkeypatch) -> None:
    from workflows import run_self_improving_pipeline as target

    captured = {}

    def _fake_read_contract(case_id, name):
        if name == "calibration_report":
            return {
                "stations": [
                    {
                        "station_id": "legacy-station",
                        "station_name": "Legacy",
                        "status": "completed",
                        "validation": {"nse": 0.91},
                    }
                ]
            }
        if name == "hydrology_nse_evidence":
            return {
                "stations": [
                    {
                        "station_id": "shared-station",
                        "station_name": "Shared",
                        "validation_nse": 0.61,
                    }
                ],
                "comparable_nse": 0.61,
            }
        return None

    monkeypatch.setattr(target, "_read_contract", _fake_read_contract)
    monkeypatch.setattr(
        target,
        "_write_contract",
        lambda case_id, name, payload: captured.setdefault(name, payload),
    )

    result = target.phase_diagnose("demo_case", {}, 0.8, None)

    assert result["convergence"] is False
    assert result["weak_stations"][0]["station_id"] == "shared-station"
    assert result["weak_stations"][0]["nse"] == 0.61
    assert captured["diagnosis"]["weak_stations"][0]["station_id"] == "shared-station"
