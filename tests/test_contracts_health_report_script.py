"""Tests for the contracts health report generator script."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "cases" / "generate_contracts_health_report.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("contracts_health_report_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class TestContractsHealthReportScript(unittest.TestCase):
    def test_collect_health_rows_reports_all_cases_as_healthy(self) -> None:
        mod = _load_script_module()
        rows = mod.collect_health_rows(workspace_root=ROOT_DIR, cases_root=ROOT_DIR / "cases")
        self.assertGreaterEqual(len(rows), 7)
        by_case = {row.case_id: row for row in rows}
        self.assertIn("daduhe", by_case)
        self.assertIn("yajiang", by_case)
        self.assertIn("yjdt", by_case)
        self.assertTrue(all(row.overall == "HEALTHY" for row in rows))

    def test_render_report_contains_summary_and_bootstrap_status(self) -> None:
        mod = _load_script_module()
        rows = mod.collect_health_rows(workspace_root=ROOT_DIR, cases_root=ROOT_DIR / "cases")
        report = mod.render_report(rows)
        self.assertIn("# Contracts Health Report", report)
        self.assertIn("Summary: total=", report)
        self.assertIn("bootstrap_contract_ready", report)
        self.assertIn("| yajiang | HEALTHY |", report)
        self.assertIn("| yjdt | HEALTHY |", report)


if __name__ == "__main__":
    unittest.main()
