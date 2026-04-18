"""Tests for Hydrology contract-aware output helpers."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
MODULE_PATH = ROOT_DIR / "common" / "program_contract_outputs.py"
spec = importlib.util.spec_from_file_location("program_contract_outputs", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)


class TestProgramContractOutputs(unittest.TestCase):
    def test_build_workflow_run_payload_and_write_metadata(self):
        payload = module.build_workflow_run_payload(
            run_id="run-001",
            case_id="daduhe",
            workflow_type="hydrological_simulation",
            status="completed",
            config_path="/tmp/config.yaml",
            components=["Catchment1", "Outlet1"],
            dt_seconds=3600,
            num_steps=24,
            started_at="2026-03-30T00:00:00",
            completed_at="2026-03-30T01:00:00",
        )
        self.assertEqual(payload["run_id"], "run-001")
        self.assertEqual(payload["inputs"][0]["artifact_type"], "config")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "run.json"
            written = module.write_workflow_run_metadata(output_path, payload)
            self.assertTrue(written.exists())
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["workflow_type"], "hydrological_simulation")

    def test_build_review_bundle_payload_and_write_metadata(self):
        payload = module.build_review_bundle_payload(
            review_id="review-001",
            run_id="run-001",
            case_id="daduhe",
            verdict="pass_with_comments",
            report_path="/tmp/report.html",
            findings=[
                {
                    "finding_id": "finding-001",
                    "severity": "info",
                    "summary": "NSE=0.84",
                    "artifact_refs": [],
                    "metadata": {},
                }
            ],
            metadata={"generator": "test"},
        )
        self.assertEqual(payload["report_artifacts"][0]["artifact_type"], "html_report")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "review.json"
            written = module.write_review_bundle_metadata(output_path, payload)
            self.assertTrue(written.exists())
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["review_id"], "review-001")

    def test_build_workflow_step_payload(self):
        artifact = module.build_artifact_payload(
            artifact_id="artifact-001",
            artifact_type="table",
            path="/tmp/results.csv",
            metadata={"role": "simulation_results"},
        )
        step = module.build_workflow_step_payload(
            step_id="hydrological_simulation",
            status="completed",
            outputs=[artifact],
            started_at="2026-03-30T00:00:00",
            completed_at="2026-03-30T01:00:00",
            metadata={"n_timesteps": 24},
        )
        self.assertEqual(step["step_id"], "hydrological_simulation")
        self.assertEqual(step["outputs"][0]["artifact_type"], "table")

    def test_build_release_manifest_payload_and_write_metadata(self):
        artifact = module.build_artifact_payload(
            artifact_id="artifact-001",
            artifact_type="workflow_run",
            path="/tmp/workflow_run.json",
            metadata={"role": "workflow_run_metadata"},
        )
        payload = module.build_release_manifest_payload(
            release_id="release-daduhe-v1.0.0",
            case_id="daduhe",
            version="v1.0.0",
            channel="staging",
            status="published",
            included_runs=["run-001"],
            review_refs=["review-001"],
            artifacts=[artifact],
            metadata={"source": "test"},
        )
        self.assertEqual(payload["included_runs"], ["run-001"])
        self.assertIn("governance_gates", payload)
        self.assertEqual(
            payload["governance_gates"].get("index_rel"),
            "Hydrology/configs/platform_governance_gates.index.json",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "release.json"
            written = module.write_release_manifest_metadata(output_path, payload)
            self.assertTrue(written.exists())
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["release_id"], "release-daduhe-v1.0.0")
            self.assertIn("governance_gates", saved)


if __name__ == "__main__":
    unittest.main()
