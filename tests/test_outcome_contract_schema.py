"""Outcome contract schema validation tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows.outcome_contract import build_outcome_contract, validate_outcome_contract


class TestOutcomeContractSchema(unittest.TestCase):
    def test_build_contract_contains_required_dimensions(self) -> None:
        contract = build_outcome_contract(
            workflow="data_audit",
            case_id="daduhe",
            result={"summary": {"rows": 123}, "report_path": "cases/daduhe/contracts/data_quality_audit.md"},
            status="completed",
            execution_profile="fast_validation",
        )
        errors = validate_outcome_contract(contract)
        self.assertEqual(errors, [])
        dims = contract["dimensions"]
        for key in ("data", "business", "process", "method", "result", "accuracy", "conclusion", "recommendation"):
            self.assertIn(key, dims)
            self.assertIsInstance(dims[key], list)

    def test_failed_contract_has_recommendation(self) -> None:
        contract = build_outcome_contract(
            workflow="strict_revalidation_ext",
            case_id="daduhe",
            result={"error": "timeout"},
            status="failed",
            execution_profile="default",
        )
        errors = validate_outcome_contract(contract)
        self.assertEqual(errors, [])
        self.assertEqual(contract["status"], "failed")
        self.assertGreaterEqual(len(contract["dimensions"]["recommendation"]), 1)

    def test_strict_revalidation_marks_quality_failed_process_status(self) -> None:
        summary_path = ROOT_DIR.parent / "reports" / "acceptance" / "ut_strict_revalidation_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "modules": {
                        "physics": {"failed_tests": 1, "pass_rate": 0.9, "average_score": 0.98},
                        "control": {"failed_tests": 3, "pass_rate": 0.2, "average_score": 0.1},
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        try:
            contract = build_outcome_contract(
                workflow="strict_revalidation_ext",
                case_id="daduhe",
                result={"quality_report_path": "reports/acceptance/ut_strict_revalidation_summary.json"},
                status="completed",
                execution_profile="default",
            )
            process = {
                str(item.get("label")): item.get("value")
                for item in contract["dimensions"]["process"]
                if isinstance(item, dict)
            }
            self.assertEqual(process.get("执行状态"), "quality_failed")
        finally:
            summary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
