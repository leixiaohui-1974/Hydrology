"""workflow_autonomy_policy 合并、分级、CLI 辅助、legacy auto_learning 兼容。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from argparse import Namespace
from unittest import mock

from workflows._autonomy_policy import (
    apply_cli_overrides,
    grade_nse,
    load_merged_autonomy_policy,
    load_raw_autonomy_yaml,
    policy_section,
    section,
)


class TestAutonomyPolicyMerge(unittest.TestCase):
    def test_raw_has_e2e_alignment(self) -> None:
        raw = load_raw_autonomy_yaml()
        self.assertIn("e2e_alignment", raw)
        self.assertIn("acceptance_rollout_path", raw["e2e_alignment"])

    def test_daduhe_dl_autolearn_batch(self) -> None:
        dl = section("daduhe", "dl_autolearn")
        self.assertEqual(dl.get("weak_point_batch_size"), 8)
        self.assertEqual(dl.get("target_nse"), 0.9)

    def test_unknown_case_defaults(self) -> None:
        sip = section("__no_such_case_for_policy__", "self_improving_pipeline")
        self.assertEqual(sip.get("target_nse"), 0.85)

    def test_reporting_grade(self) -> None:
        rep = section("daduhe", "reporting")
        self.assertEqual(grade_nse(0.91, rep), "优秀")
        self.assertEqual(grade_nse(0.81, rep), "良好")
        self.assertEqual(grade_nse(None, rep), "无数据")
        self.assertEqual(grade_nse(0.05, rep), "不合格")

    def test_apply_cli_overrides_skips_when_flag_present(self) -> None:
        args = Namespace(target_nse=0.5)
        old = sys.argv[:]
        try:
            sys.argv = ["prog", "--target-nse", "0.99"]
            _, keys = apply_cli_overrides(
                {"target_nse": 0.82},
                args,
                [("target_nse", "target_nse", "--target-nse")],
            )
            self.assertEqual(args.target_nse, 0.5)
            self.assertEqual(keys, [])
        finally:
            sys.argv = old

    def test_apply_cli_overrides_applies_when_flag_absent(self) -> None:
        args = Namespace(target_nse=0.5)
        old = sys.argv[:]
        try:
            sys.argv = ["prog"]
            _, keys = apply_cli_overrides(
                {"target_nse": 0.82},
                args,
                [("target_nse", "target_nse", "--target-nse")],
            )
            self.assertEqual(args.target_nse, 0.82)
            self.assertEqual(keys, ["target_nse"])
        finally:
            sys.argv = old

    def test_case_autonomy_policy_overlay(self) -> None:
        fake_cfg = {
            "case_id": "overlay_case",
            "autonomy_policy": {
                "self_improving_pipeline": {"target_nse": 0.91},
                "reporting": {"pass_val_nse": 0.88},
            },
        }
        with mock.patch("workflows._shared.load_case_config", return_value=fake_cfg):
            p = load_merged_autonomy_policy("overlay_case", None)
        self.assertEqual(policy_section(p, "self_improving_pipeline").get("target_nse"), 0.91)
        self.assertEqual(policy_section(p, "reporting").get("pass_val_nse"), 0.88)

    def test_auto_learning_hydrology_merge(self) -> None:
        p = load_merged_autonomy_policy("daduhe", None)
        alo = p.get("auto_learning_loop") or {}
        hyd = alo.get("hydrology") or {}
        self.assertEqual(hyd.get("max_iter"), 10)
        self.assertEqual(hyd.get("target_value"), 0.85)
        self.assertEqual(hyd.get("metric_file"), "cases/{case_id}/contracts/hydrology_nse_evidence.latest.json")
        self.assertEqual(hyd.get("metric_key"), "comparable_nse")
        self.assertIn("--no-calibrate", hyd.get("workflow_cmd", ""))

    def test_auto_learning_hydrology_defaults_are_case_bound_for_rollout_cases(self) -> None:
        p = load_merged_autonomy_policy("zhongxian", None)
        alo = p.get("auto_learning_loop") or {}
        hyd = alo.get("hydrology") or {}
        self.assertEqual(hyd.get("max_iter"), 10)
        self.assertEqual(hyd.get("target_value"), 0.85)
        self.assertEqual(hyd.get("metric_file"), "cases/{case_id}/contracts/hydrology_nse_evidence.latest.json")
        self.assertEqual(hyd.get("metric_key"), "comparable_nse")
        workflow_cmd = hyd.get("workflow_cmd", "")
        self.assertIn("Hydrology/workflows/run_hydrological_simulation.py", workflow_cmd)
        self.assertIn("cases/{case_id}/contracts/data_pack.latest.json", workflow_cmd)
        self.assertIn("cases/{case_id}/contracts/parameter_governance.latest.json", workflow_cmd)
        self.assertNotIn("Hydrology/examples", workflow_cmd)

    def test_auto_learning_target_validation_rejects_pseudo_convergence_threshold(self) -> None:
        from workflows.run_auto_learning_loop import validate_target_threshold

        result = validate_target_threshold(
            case_id="daduhe",
            stage="hydrology",
            requested_target=0.6548,
            metric_file="cases/daduhe/contracts/hydrology_calibration.latest.json",
            metric_key="calibration_metrics.nse",
            config_path=None,
        )
        self.assertEqual(result.get("status"), "rejected")
        self.assertEqual(result.get("business_threshold"), 0.85)
        reason = str(result.get("reason", ""))
        self.assertIn("below business threshold", reason)
        # When resolved current metric is above the requested fake target, append pseudo-convergence hint.
        if result.get("current_metric") is not None and 0.6548 <= float(result["current_metric"]):
            self.assertIn("pseudo-converged", reason)

    def test_auto_learning_target_validation_accepts_business_threshold(self) -> None:
        from workflows.run_auto_learning_loop import validate_target_threshold

        result = validate_target_threshold(
            case_id="daduhe",
            stage="hydrology",
            requested_target=0.85,
            metric_file="cases/daduhe/contracts/hydrology_calibration.latest.json",
            metric_key="calibration_metrics.nse",
            config_path=None,
        )
        self.assertEqual(result.get("status"), "accepted")
        self.assertEqual(result.get("business_threshold"), 0.85)

    def test_sync_metric_contract_skips_case_bound_contract_metric(self) -> None:
        from workflows.run_auto_learning_loop import _sync_metric_contract

        with tempfile.TemporaryDirectory() as tmpdir:
            contracts_dir = Path(tmpdir) / "cases" / "zhongxian" / "contracts"
            contracts_dir.mkdir(parents=True)
            metric_path = contracts_dir / "hydrology_calibration.latest.json"
            metric_path.write_text('{"calibration_metrics":{"nse":0.91}}', encoding="utf-8")

            synced = _sync_metric_contract(str(metric_path), contracts_dir)

            self.assertIsNone(synced)
            self.assertFalse((contracts_dir / "pipeline_evaluation.latest.json").exists())

    def test_sync_metric_contract_copies_legacy_shared_pipeline_summary(self) -> None:
        from workflows.run_auto_learning_loop import _sync_metric_contract

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            contracts_dir = root / "cases" / "zhongxian" / "contracts"
            contracts_dir.mkdir(parents=True)
            shared_metric = root / "Hydrology" / "examples" / "results" / "pipeline.run_summary.json"
            shared_metric.parent.mkdir(parents=True)
            shared_metric.write_text('{"metrics":{"NSE":0.12}}', encoding="utf-8")

            synced = _sync_metric_contract(str(shared_metric), contracts_dir)

            self.assertEqual(synced, contracts_dir / "pipeline_evaluation.latest.json")
            self.assertTrue(synced.exists())

    def test_precision_weak_batch_default_zero(self) -> None:
        p = section("daduhe", "precision_improvement")
        self.assertEqual(p.get("weak_point_batch_size"), 0)

    def test_diagnose_heuristic_keys(self) -> None:
        d = section("daduhe", "diagnose")
        self.assertEqual(d.get("data_audit_min_weak_stations"), 3)
        self.assertEqual(d.get("large_gap_nse_threshold"), 0.15)

    def test_hydraulic_data_gates_in_yaml(self) -> None:
        h = section("daduhe", "hydraulic_precision_improvement")
        self.assertEqual(h.get("min_points_daily"), 100)
        self.assertEqual(h.get("time_step_seconds", {}).get("1D"), 86400.0)

    def test_coupled_min_series_in_yaml(self) -> None:
        c = section("daduhe", "coupled_precision_improvement")
        self.assertEqual(c.get("min_series_points"), 300)

    def test_hydraulic_data_gates_helper(self) -> None:
        from workflows.run_hydraulic_precision_improvement import hydraulic_data_gates

        md, mh, dt = hydraulic_data_gates({"min_points_daily": 50, "min_points_hourly": 200})
        self.assertEqual(md, 50)
        self.assertEqual(mh, 200)
        self.assertEqual(dt.get("1D"), 86400.0)

    def test_select_weak_station_batch(self) -> None:
        from workflows.run_precision_improvement import select_weak_station_batch

        w = [
            {"station_id": "a", "validation": {"nse": 0.8}},
            {"station_id": "b", "validation": {"nse": 0.5}},
            {"station_id": "c", "validation": {"nse": 0.6}},
        ]
        s = select_weak_station_batch(w, 2)
        self.assertEqual([x["station_id"] for x in s], ["b", "c"])
        self.assertEqual(len(select_weak_station_batch(w, 0)), 3)

    def test_phase_diagnose_recommended_actions_from_policy(self) -> None:
        from workflows.run_self_improving_pipeline import phase_diagnose

        fake_report = {
            "stations": [
                {"station_id": "a", "station_name": "A", "status": "completed", "validation": {"nse": 0.5}},
                {"station_id": "b", "station_name": "B", "status": "completed", "validation": {"nse": 0.55}},
                {"station_id": "c", "station_name": "C", "status": "completed", "validation": {"nse": 0.6}},
            ]
        }
        pol = {"data_audit_min_weak_stations": 2, "large_gap_nse_threshold": 0.05}
        with mock.patch("workflows._autonomy_policy.section", return_value=pol):
            with mock.patch(
                "workflows.run_self_improving_pipeline._read_contract", return_value=fake_report,
            ):
                with mock.patch("workflows.run_self_improving_pipeline._write_contract"):
                    r = phase_diagnose("tcase", {}, 0.85, None)
        actions = [a["action"] for a in r["recommended_actions"]]
        self.assertIn("data_quality_audit", actions)
        self.assertIn("dl_autolearn_or_alternate_model", actions)


if __name__ == "__main__":
    unittest.main()
