"""run_autonomy_autorun regression tests."""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows.run_autonomy_autorun import run_autonomy_autorun


class TestRunAutonomyAutorun(unittest.TestCase):
    def test_run_autonomy_autorun_writes_launch_review_path_assets(self) -> None:
        case_id = "ut_autonomy_autorun_launch_path"
        contracts_dir = ROOT_DIR.parent / "cases" / case_id / "contracts"
        reports_dir = ROOT_DIR.parent / "reports" / "acceptance"
        summary_path = reports_dir / "strict_revalidation_summary.json"
        original_summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else None
        contracts_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

        for rel_path, content in {
            "E2E_LIVE_DASHBOARD.html": "<html>live</html>",
            "E2E_LIVE_DASHBOARD.md": "# live",
            "outcome_coverage_report.latest.json": "{}",
            "e2e_outcome_verification_report.json": "{}",
            "e2e_outcome_verification_report.md": "# verification",
        }.items():
            (contracts_dir / rel_path).write_text(content, encoding="utf-8")
        summary_path.write_text(
            json.dumps({"scenario_count": 3, "modules": {}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        assess_payload = {
            "judge": {
                "verdict": "PASS",
                "overall_score": 0.88,
                "weak_dimensions": [],
            },
            "recommended_actions": [],
        }

        try:
            with patch("workflows.run_autonomy_autorun._run_assess", side_effect=[assess_payload, assess_payload]):
                result = run_autonomy_autorun(
                    case_id=case_id,
                    execution_profile="fast_validation",
                    max_rounds=1,
                )

            expected_launch_path = {
                "strict_revalidation_summary": "reports/acceptance/strict_revalidation_summary.json",
                "live_dashboard": [
                    f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
                    f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.md",
                ],
                "verification_assets": [
                    f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
                    f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
                    f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
                ],
                "review_sequence": [
                    "reports/acceptance/strict_revalidation_summary.json",
                    f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
                    f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.md",
                    f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
                    f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
                    f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
                ],
            }

            self.assertEqual(result["launch_review_path"], expected_launch_path)

            report_json = json.loads((contracts_dir / "autonomy_autorun.latest.json").read_text(encoding="utf-8"))
            self.assertEqual(report_json["launch_review_path"], expected_launch_path)

            report_md = (contracts_dir / "autonomy_autorun.latest.md").read_text(encoding="utf-8")
            self.assertIn("## 下游启动 / 审查路径", report_md)
            self.assertIn("reports/acceptance/strict_revalidation_summary.json", report_md)
            self.assertIn(f"cases/{case_id}/contracts/e2e_outcome_verification_report.json", report_md)
        finally:
            shutil.rmtree(contracts_dir.parent, ignore_errors=True)
            if original_summary is None:
                summary_path.unlink(missing_ok=True)
            else:
                summary_path.write_text(original_summary, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
