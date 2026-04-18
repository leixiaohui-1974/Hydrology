from pathlib import Path
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _run_case(case_id: str) -> dict:
    script = ROOT / "scripts" / "export_case_model_strategy.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--case-id", case_id],
        cwd=str(ROOT.parent),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    return payload["case"]


def test_export_case_model_strategy_daduhe_prefers_full_watershed_chain() -> None:
    row = _run_case("daduhe")
    assert row["strategy_key"] == "watershed_hydrology_hydrodynamics"
    assert row["should_build_watershed_model"] is True
    assert row["should_build_hydrology_model"] is True
    assert row["evidence"]["has_catchment_truth"] is True
    assert row["evidence"]["has_station_control_area_truth"] is True


def test_export_case_model_strategy_zhongxian_prefers_control_digital_twin() -> None:
    row = _run_case("zhongxian")
    assert row["strategy_key"] == "hydraulic_control_digital_twin"
    assert row["should_build_hydrology_model"] is False
    assert row["should_build_control_model"] is True
    assert "缺 catchment/subbasin 真相" in row["blocked_capabilities"]


def test_export_case_model_strategy_yjdt_prefers_cascade_operation() -> None:
    row = _run_case("yjdt")
    assert row["strategy_key"] == "cascade_hydrodynamic_operation"
    assert row["should_build_hydrology_model"] is False
    assert row["should_build_control_model"] is True
    assert row["evidence"]["has_reservoirs"] is True


def test_export_case_model_strategy_batch_rollup_matches_six_cases() -> None:
    script = ROOT / "scripts" / "export_case_model_strategy.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--batch"],
        cwd=str(ROOT.parent),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert len(payload["case_ids"]) == 6
    rollup = payload["rollup"]
    assert rollup["watershed_hydrology_hydrodynamics"] == 1
    assert rollup["cascade_hydrodynamic_operation"] == 1
    assert rollup["hydraulic_control_digital_twin"] == 4
