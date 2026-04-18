"""Regression checks for expansion rollout case manifests."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
EXPANSION_CASES = [
    "yjdt",
]


class TestExpansionCaseManifests(unittest.TestCase):
    def _load_manifest(self, case_id: str) -> dict:
        manifest_path = ROOT_DIR / "cases" / case_id / "manifest.yaml"
        self.assertTrue(manifest_path.exists(), f"manifest missing: {manifest_path}")
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        self.assertIsInstance(payload, dict)
        return payload

    def test_expansion_manifests_have_workspace_relative_paths(self) -> None:
        abs_prefix = "/Users/rainfields/hydrosis-local/research/"
        for case_id in EXPANSION_CASES:
            manifest = self._load_manifest(case_id)
            serialized = yaml.safe_dump(manifest, allow_unicode=True)
            self.assertNotIn(
                abs_prefix,
                serialized,
                f"{case_id} manifest still contains absolute workspace path",
            )

    def test_expansion_latest_slots_are_present_and_well_formed(self) -> None:
        for case_id in EXPANSION_CASES:
            manifest = self._load_manifest(case_id)
            latest_source = manifest.get("latest_source_bundle", {}) or {}
            latest_workflow = manifest.get("latest_workflow_run", {}) or {}
            latest_review = manifest.get("latest_review_bundle", {}) or {}
            latest_release = manifest.get("latest_release_manifest", {}) or {}

            self.assertTrue(
                str(latest_source.get("path", "")).strip(),
                f"{case_id} latest_source_bundle.path missing",
            )
            self.assertTrue(
                str(latest_workflow.get("path", "")).strip(),
                f"{case_id} latest_workflow_run.path missing",
            )
            self.assertTrue(
                str(latest_review.get("path", "")).strip(),
                f"{case_id} latest_review_bundle.path missing",
            )
            self.assertTrue(
                str(latest_release.get("path", "")).strip(),
                f"{case_id} latest_release_manifest.path missing",
            )

            self.assertFalse(
                Path(str(latest_source.get("path", ""))).is_absolute(),
                f"{case_id} source path should be relative",
            )
            self.assertFalse(
                Path(str(latest_workflow.get("path", ""))).is_absolute(),
                f"{case_id} workflow path should be relative",
            )
            self.assertFalse(
                Path(str(latest_review.get("path", ""))).is_absolute(),
                f"{case_id} review path should be relative",
            )
            self.assertFalse(
                Path(str(latest_release.get("path", ""))).is_absolute(),
                f"{case_id} release path should be relative",
            )

            self.assertIn(case_id, str(latest_workflow.get("run_id", "")), f"{case_id} run_id should include case id")
            self.assertIn(case_id, str(latest_review.get("review_id", "")), f"{case_id} review_id should include case id")
            self.assertIn(case_id, str(latest_release.get("release_id", "")), f"{case_id} release_id should include case id")


if __name__ == "__main__":
    unittest.main()
