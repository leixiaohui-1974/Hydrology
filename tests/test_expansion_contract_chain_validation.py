"""Regression checks for expansion-case bootstrap Run->Review->Release chains."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
EXPANSION_CASES = [
    "yjdt",
]


class TestExpansionContractChainValidation(unittest.TestCase):
    @staticmethod
    def _load_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_expansion_case_chain_files_exist_and_ids_align(self) -> None:
        for case_id in EXPANSION_CASES:
            manifest_path = ROOT_DIR / "cases" / case_id / "manifest.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

            latest_workflow = manifest.get("latest_workflow_run", {}) or {}
            latest_review = manifest.get("latest_review_bundle", {}) or {}
            latest_release = manifest.get("latest_release_manifest", {}) or {}

            workflow_path = ROOT_DIR / str(latest_workflow.get("path", ""))
            review_path = ROOT_DIR / str(latest_review.get("path", ""))
            release_path = ROOT_DIR / str(latest_release.get("path", ""))

            self.assertTrue(workflow_path.exists(), f"{case_id}: missing workflow contract")
            self.assertTrue(review_path.exists(), f"{case_id}: missing review contract")
            self.assertTrue(release_path.exists(), f"{case_id}: missing release contract")

            workflow = self._load_json(workflow_path)
            review = self._load_json(review_path)
            release = self._load_json(release_path)

            workflow_run_id = workflow.get("run_id")
            review_run_id = review.get("run_id")
            review_id = review.get("review_id")
            included_runs = release.get("included_runs", []) or []
            review_refs = release.get("review_refs", []) or []

            self.assertEqual(
                review_run_id,
                workflow_run_id,
                f"{case_id}: review.run_id must reference workflow.run_id",
            )
            self.assertIn(
                workflow_run_id,
                included_runs,
                f"{case_id}: release.included_runs must include workflow.run_id",
            )
            self.assertIn(
                review_id,
                review_refs,
                f"{case_id}: release.review_refs must include review.review_id",
            )

            self.assertEqual(latest_workflow.get("run_id"), workflow_run_id, f"{case_id}: manifest run_id mismatch")
            self.assertIn(
                workflow_run_id,
                str(latest_review.get("review_id", "")),
                f"{case_id}: manifest review_id should reference workflow run id",
            )
            self.assertIn(
                case_id,
                str(latest_release.get("release_id", "")),
                f"{case_id}: manifest release_id should include case id",
            )

    def test_expansion_chain_paths_are_workspace_relative(self) -> None:
        for case_id in EXPANSION_CASES:
            manifest_path = ROOT_DIR / "cases" / case_id / "manifest.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

            latest_workflow = manifest.get("latest_workflow_run", {}) or {}
            latest_review = manifest.get("latest_review_bundle", {}) or {}
            latest_release = manifest.get("latest_release_manifest", {}) or {}

            self.assertFalse(
                Path(str(latest_workflow.get("path", ""))).is_absolute(),
                f"{case_id}: workflow path should be relative",
            )
            self.assertFalse(
                Path(str(latest_review.get("path", ""))).is_absolute(),
                f"{case_id}: review path should be relative",
            )
            self.assertFalse(
                Path(str(latest_release.get("path", ""))).is_absolute(),
                f"{case_id}: release path should be relative",
            )


if __name__ == "__main__":
    unittest.main()
