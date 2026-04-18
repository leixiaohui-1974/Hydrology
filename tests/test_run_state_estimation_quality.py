from __future__ import annotations

from pathlib import Path

import numpy as np

from workflows import run_state_estimation as target


class _DummyReportGenerator:
    def __init__(self, case_id: str, report_dir: Path) -> None:
        self.case_id = case_id
        self.report_dir = report_dir
        self.generated_reports: list[str] = []

    def generate_report(self, **kwargs: object) -> None:
        self.generated_reports.append(str(kwargs.get("object_id", "unknown")))

    def save_index(self) -> None:
        return None


def test_state_estimation_uses_primary_sites_for_quality_gate(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "ObjectReportGenerator", _DummyReportGenerator)
    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda case_id, config_path=None: {
            "knowledge": {
                "reservoirs": {
                    "real_station": {"name": "real_station", "Amin": 22500.0},
                    "synthetic_station": {"name": "synthetic_station", "Amin": 22500.0},
                },
                "topology": {
                    "nodes": {
                        "synthetic_station前": {"zb": 100.0},
                    }
                },
            }
        },
    )
    monkeypatch.setattr(
        target,
        "_load_hydraulic_levels",
        lambda contracts_dir: {"real_station": np.array([1.0, 1.1, 1.2])},
    )
    monkeypatch.setattr(target, "_load_inflows", lambda contracts_dir: {})

    def fake_ekf_reservoir(z_obs, **kwargs):
        if len(z_obs) == 3:
            return {
                "status": "completed",
                "rmse_m": 0.1,
                "nse": 0.9,
                "converged": True,
                "mean_kalman_gain": 0.5,
                "max_innovation_m": 0.1,
                "z_est_first5": [1.0, 1.1, 1.2],
                "z_obs_first5": [1.0, 1.1, 1.2],
                "process_noise": 0.01,
                "meas_noise": 0.5,
            }
        return {
            "status": "completed",
            "rmse_m": 5.0,
            "nse": -10.0,
            "converged": False,
            "mean_kalman_gain": 0.1,
            "max_innovation_m": 5.0,
            "z_est_first5": [100.0] * 5,
            "z_obs_first5": [100.0] * 5,
            "process_noise": 0.01,
            "meas_noise": 0.5,
        }

    monkeypatch.setattr(target, "ekf_reservoir", fake_ekf_reservoir)
    monkeypatch.setattr(
        target,
        "_write_json",
        lambda path, data: captured.setdefault("report", data),
    )

    report = target.run_state_estimation("demo")

    assert report["outcome_status"] == "degraded"
    assert report["quality_gate_passed"] is False
    assert "synthetic_from_params 回退" in str(report["quality_reason"])
    assert "整体质量未达标" not in str(report["quality_reason"])
    assert report["summary"]["primary_completed"] == 1
    assert report["summary"]["primary_converged"] == 1
    assert report["summary"]["primary_avg_nse"] == 0.9
    assert report["summary"]["synthetic_fallback"] == 1
    assert captured["report"] == report
