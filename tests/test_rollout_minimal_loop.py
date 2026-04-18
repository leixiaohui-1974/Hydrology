from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import rollout_minimal_loop as target


class TestRolloutMinimalLoop(unittest.TestCase):
    def test_collect_case_evidence_flags_missing_and_present_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            contracts = root / "cases" / "demo" / "contracts"
            contracts.mkdir(parents=True, exist_ok=True)
            for name in (
                "source_import_session.latest.json",
                "data_pack.latest.json",
                "pipeline_evaluation.latest.json",
            ):
                (contracts / name).write_text("{}", encoding="utf-8")

            evidence = target.collect_case_evidence("demo", root)

            self.assertFalse(evidence["all_present"])
            self.assertTrue(evidence["artifacts"]["source_discovery"]["present"])
            self.assertTrue(evidence["artifacts"]["data_pack"]["present"])
            self.assertTrue(evidence["artifacts"]["simulation"]["present"])
            self.assertFalse(evidence["artifacts"]["workflow_run"]["present"])

    def test_summarize_case_ready_requires_preflight_and_evidence(self) -> None:
        summary = target.summarize_case(
            "demo",
            {"ok": True, "missing_inputs": [], "planned_steps": ["build_data_pack", "run_watershed_delineation", "run_hydrological_simulation"]},
            {"all_present": True, "artifacts": {}},
        )
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["ready"])
        self.assertIn("hydrological_simulation", summary["phases_covered"])

        failed = target.summarize_case(
            "demo",
            {"ok": False, "missing_inputs": ["simulation_config"], "planned_steps": []},
            {"all_present": True, "artifacts": {}},
        )
        self.assertEqual(failed["status"], "not_ready")
        self.assertFalse(failed["ready"])

    def test_run_rollout_minimal_loop_writes_case_and_summary_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            contracts = root / "cases" / "demo" / "contracts"
            contracts.mkdir(parents=True, exist_ok=True)
            for name in target.REQUIRED_EVIDENCE.values():
                (contracts / name).write_text("{}", encoding="utf-8")

            original_preflight = target.run_case_preflight
            try:
                target.run_case_preflight = lambda case_id, workspace=root: {
                    "ok": True,
                    "missing_inputs": [],
                    "planned_steps": ["build_data_pack", "run_watershed_delineation", "run_hydrological_simulation"],
                }
                result = target.run_rollout_minimal_loop(["demo"], root)
            finally:
                target.run_case_preflight = original_preflight

            case_contract = contracts / "rollout_minimal_loop.latest.json"
            summary_contract = root / "cases" / "rollout_minimal_loop_summary.latest.json"
            self.assertTrue(case_contract.is_file())
            self.assertTrue(summary_contract.is_file())
            loaded_case = json.loads(case_contract.read_text(encoding="utf-8"))
            self.assertTrue(loaded_case["ready"])
            loaded_summary = json.loads(summary_contract.read_text(encoding="utf-8"))
            self.assertEqual(loaded_summary["ready_cases"], ["demo"])
            self.assertTrue(str(result["summary_path"]).endswith("rollout_minimal_loop_summary.latest.json"))


if __name__ == "__main__":
    unittest.main()
