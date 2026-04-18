"""Regression checks for rollout case manifests (non-daduhe)."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
ROLLOUT_CASES = [
    "jiaodongtiaoshui",
    "xuhonghe",
    "yinchuojiliao",
    "zhongxian",
    "yjdt",
]


class TestRolloutCaseManifests(unittest.TestCase):
    def _load_manifest(self, case_id: str) -> dict:
        manifest_path = ROOT_DIR / "cases" / case_id / "manifest.yaml"
        self.assertTrue(manifest_path.exists(), f"manifest missing: {manifest_path}")
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        self.assertIsInstance(payload, dict)
        return payload

    def test_rollout_manifests_have_workspace_relative_paths(self) -> None:
        abs_prefix = "/Users/rainfields/hydrosis-local/research/"
        for case_id in ROLLOUT_CASES:
            manifest = self._load_manifest(case_id)
            serialized = yaml.safe_dump(manifest, allow_unicode=True)
            self.assertNotIn(
                abs_prefix,
                serialized,
                f"{case_id} manifest still contains absolute workspace path",
            )

    def test_rollout_latest_slots_are_present_and_well_formed(self) -> None:
        for case_id in ROLLOUT_CASES:
            manifest = self._load_manifest(case_id)
            latest_source = manifest.get("latest_source_bundle", {}) or {}
            latest_outlets = manifest.get("latest_outlets", {}) or {}
            latest_workflow = manifest.get("latest_workflow_run", {}) or {}
            latest_review = manifest.get("latest_review_bundle", {}) or {}
            latest_release = manifest.get("latest_release_manifest", {}) or {}

            self.assertTrue(str(latest_source.get("path", "")).strip(), f"{case_id} latest_source_bundle.path missing")
            self.assertTrue(str(latest_outlets.get("path", "")).strip(), f"{case_id} latest_outlets.path missing")
            self.assertTrue(str(latest_workflow.get("path", "")).strip(), f"{case_id} latest_workflow_run.path missing")
            self.assertTrue(str(latest_review.get("path", "")).strip(), f"{case_id} latest_review_bundle.path missing")
            self.assertTrue(str(latest_release.get("path", "")).strip(), f"{case_id} latest_release_manifest.path missing")

            self.assertFalse(Path(str(latest_outlets.get("path", ""))).is_absolute(), f"{case_id} outlets path should be relative")
            self.assertFalse(Path(str(latest_workflow.get("path", ""))).is_absolute(), f"{case_id} workflow path should be relative")
            self.assertFalse(Path(str(latest_review.get("path", ""))).is_absolute(), f"{case_id} review path should be relative")
            self.assertFalse(Path(str(latest_release.get("path", ""))).is_absolute(), f"{case_id} release path should be relative")

            self.assertIn(case_id, str(latest_workflow.get("run_id", "")), f"{case_id} run_id should include case id")
            self.assertIn(case_id, str(latest_review.get("review_id", "")), f"{case_id} review_id should include case id")
            self.assertIn(case_id, str(latest_release.get("release_id", "")), f"{case_id} release_id should include case id")

    def test_rollout_manifests_expose_standard_run_review_release_scaffold(self) -> None:
        expected_targets = [
            "source_discovery",
            "data_pack_build",
            "watershed_delineation",
            "hydrological_simulation",
            "acceptance_review",
            "release_publish",
        ]
        expected_validation_priority = [
            "watershed_delineation",
            "hydrological_simulation",
            "acceptance_review",
            "release_publish",
        ]
        for case_id in ROLLOUT_CASES:
            manifest = self._load_manifest(case_id)
            self.assertEqual(manifest.get("workflow_targets"), expected_targets, case_id)
            self.assertEqual(manifest.get("workflow_validation_priority"), expected_validation_priority, case_id)

            baseline = manifest.get("workflow_baseline") or {}
            self.assertEqual(baseline.get("entrypoint"), "Hydrology/workflows/run_case_pipeline.py", case_id)
            self.assertEqual(baseline.get("implementation"), "Hydrology/workflows/run_watershed_delineation.py", case_id)
            self.assertEqual(baseline.get("status"), "contract_orchestrated", case_id)

            shell_entrypoints = manifest.get("shell_entrypoints") or {}
            self.assertEqual((shell_entrypoints.get("run") or {}).get("path"), "Hydrology/workflows/run_case_pipeline.py", case_id)
            self.assertEqual((shell_entrypoints.get("review") or {}).get("path"), "Hydrology/workflows/build_review_bundle.py", case_id)
            self.assertEqual((shell_entrypoints.get("release") or {}).get("path"), "Hydrology/workflows/build_release_manifest.py", case_id)
            self.assertEqual((shell_entrypoints.get("run") or {}).get("output_contract"), f"cases/{case_id}/contracts/workflow_run.json", case_id)
            self.assertEqual((shell_entrypoints.get("review") or {}).get("output_contract"), f"cases/{case_id}/contracts/review_bundle.json", case_id)
            self.assertEqual((shell_entrypoints.get("release") or {}).get("output_contract"), f"cases/{case_id}/contracts/release_manifest.json", case_id)

            release_handoff = manifest.get("release_handoff") or {}
            self.assertEqual(release_handoff.get("mode"), "json_handoff", case_id)
            self.assertEqual(release_handoff.get("producer_repo"), "Hydrology", case_id)
            self.assertEqual(release_handoff.get("consumer_repo"), "pipedream-hydrology-integration-lab", case_id)
            self.assertEqual(release_handoff.get("handoff_status"), "shell_contract_ready", case_id)
            self.assertEqual(
                release_handoff.get("artifacts"),
                {
                    "workflow_run": f"cases/{case_id}/contracts/workflow_run.json",
                    "review_bundle": f"cases/{case_id}/contracts/review_bundle.json",
                    "release_manifest": f"cases/{case_id}/contracts/release_manifest.json",
                },
                case_id,
            )

    def test_rollout_links_expose_standard_run_review_release_entrypoints(self) -> None:
        for case_id in ROLLOUT_CASES:
            links_path = ROOT_DIR / "cases" / case_id / "links.yaml"
            self.assertTrue(links_path.exists(), f"links missing: {links_path}")
            links = (yaml.safe_load(links_path.read_text(encoding="utf-8")) or {}).get("links") or {}
            self.assertEqual((links.get("hydrology_case_pipeline") or {}).get("path"), "Hydrology/workflows/run_case_pipeline.py", case_id)
            self.assertEqual((links.get("hydrology_run_entry") or {}).get("path"), "Hydrology/workflows/run_watershed_delineation.py", case_id)
            self.assertEqual((links.get("hydrology_review_entry") or {}).get("path"), "Hydrology/workflows/build_review_bundle.py", case_id)
            self.assertEqual((links.get("hydrology_release_builder") or {}).get("path"), "Hydrology/workflows/build_release_manifest.py", case_id)
            self.assertEqual((links.get("shell_workflow_run") or {}).get("path"), f"cases/{case_id}/contracts/workflow_run.json", case_id)
            self.assertEqual((links.get("shell_review_bundle") or {}).get("path"), f"cases/{case_id}/contracts/review_bundle.json", case_id)
            self.assertEqual((links.get("shell_release_manifest") or {}).get("path"), f"cases/{case_id}/contracts/release_manifest.json", case_id)


if __name__ == "__main__":
    unittest.main()
