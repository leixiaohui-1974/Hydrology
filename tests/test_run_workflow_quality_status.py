"""Regression tests for workflow execution-vs-quality status semantics."""

from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import workflows


class TestRunWorkflowQualityStatus(unittest.TestCase):
    def test_external_quality_gate_failure_maps_to_quality_failed_outcome(self) -> None:
        workflow_key = "ut_external_quality_gate"
        workflows.WORKFLOW_REGISTRY[workflow_key] = {
            "module": "workflows.external.ut_external_quality_gate",
            "entry": "_run_external_script",
            "description": "UT workflow for quality gate semantics",
            "required_args": ["case_id"],
            "external_script": "E2EControl/scripts/run_strict_revalidation.py",
            "external_args_template": [],
        }

        captured: dict[str, str] = {}

        def _fake_external_script(spec: dict, **kwargs: object) -> dict:
            return {
                "kind": "external_script",
                "quality_gate_passed": False,
                "quality_status": "failed",
                "quality_reason": "ut injected gate failure",
                "outcome_status": "quality_failed",
            }

        def _fake_generate_and_write_outcome(*, status: str, **kwargs: object) -> dict:
            captured["status"] = status
            return {}

        try:
            with (
                patch.object(workflows, "_run_external_script", side_effect=_fake_external_script),
                patch.object(workflows, "generate_and_write_outcome", side_effect=_fake_generate_and_write_outcome),
                patch.object(workflows, "emit_workflow_report", return_value={}),
            ):
                result = workflows.run_workflow(workflow_key, case_id="daduhe")
        finally:
            workflows.WORKFLOW_REGISTRY.pop(workflow_key, None)

        self.assertEqual(captured.get("status"), "quality_failed")
        self.assertIsInstance(result, dict)
        self.assertIs(result.get("quality_gate_passed"), False)

    def test_internal_partial_status_maps_to_partial_outcome(self) -> None:
        workflow_key = "ut_internal_partial"
        workflows.WORKFLOW_REGISTRY[workflow_key] = {
            "module": "workflows.ut_internal_partial",
            "entry": "run_pipeline",
            "description": "UT workflow for partial status semantics",
            "required_args": ["case_id"],
        }

        captured: dict[str, str] = {}
        fake_module = SimpleNamespace(
            run_pipeline=lambda **kwargs: {
                "status": "partial",
                "quality_gate_passed": False,
                "quality_reason": "ut partial failure",
            }
        )

        def _fake_generate_and_write_outcome(*, status: str, **kwargs: object) -> dict:
            captured["status"] = status
            return {}

        try:
            with (
                patch("importlib.import_module", return_value=fake_module),
                patch.object(workflows, "generate_and_write_outcome", side_effect=_fake_generate_and_write_outcome),
                patch.object(workflows, "emit_workflow_report", return_value={}),
            ):
                result = workflows.run_workflow(workflow_key, case_id="daduhe")
        finally:
            workflows.WORKFLOW_REGISTRY.pop(workflow_key, None)

        self.assertEqual(captured.get("status"), "partial")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("status"), "partial")
        self.assertIs(result.get("quality_gate_passed"), False)


if __name__ == "__main__":
    unittest.main()
