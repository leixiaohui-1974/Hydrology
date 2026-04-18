"""Tests for scripts/normalize_mcp_all_agents_e2e_report.py rollup/normalize logic."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_normalize_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "normalize_mcp_all_agents_e2e_report.py"
    spec = importlib.util.spec_from_file_location("_mcp_e2e_norm", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_mcp_e2e_norm"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_normalize_module()
_rollup = _mod._rollup
normalize_report = _mod.normalize_report


class TestMcpE2eRollup(unittest.TestCase):
    def test_empty_agents(self):
        r = _rollup({"agent_results": []})
        self.assertEqual(
            r,
            {
                "workflow_calls": 0,
                "passed": 0,
                "failed": 0,
                "timeout": 0,
                "skipped": 0,
                "other_status": 0,
            },
        )

    def test_mixed_statuses(self):
        report = {
            "agent_results": [
                {
                    "workflow_results": [
                        {"status": "passed"},
                        {"status": "failed"},
                        {"status": "timeout"},
                        {"status": "skipped_not_in_mcp_registry"},
                        {"status": "UNKNOWN"},
                    ]
                }
            ]
        }
        r = _rollup(report)
        self.assertEqual(r["workflow_calls"], 5)
        self.assertEqual(r["passed"], 1)
        self.assertEqual(r["failed"], 1)
        self.assertEqual(r["timeout"], 1)
        self.assertEqual(r["skipped"], 1)
        self.assertEqual(r["other_status"], 1)

    def test_normalize_sets_totals_and_root(self):
        raw = {
            "case_id": "x",
            "totals": {"workflow_calls": 1, "passed": 9, "failed": 0, "timeout": 0, "skipped": 0},
            "passed": 0,
            "agent_results": [
                {"workflow_results": [{"status": "passed"}, {"status": "skipped_not_in_mcp_registry"}]}
            ],
        }
        out = normalize_report(raw)
        self.assertEqual(out["totals"]["workflow_calls"], 2)
        self.assertEqual(out["totals"]["passed"], 1)
        self.assertEqual(out["totals"]["skipped"], 1)
        self.assertEqual(out["passed"], 1)
        self.assertEqual(out["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
