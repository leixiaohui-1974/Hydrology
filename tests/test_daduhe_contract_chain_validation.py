"""Regression checks for the daduhe Run->Review->Release contract chain."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]


class TestDaduheContractChainValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_root = ROOT_DIR
        self.contract_root = ROOT_DIR / "cases" / "daduhe" / "contracts"
        self.workflow_run_path = self.contract_root / "workflow_run.json"
        self.review_bundle_path = self.contract_root / "review_bundle.json"
        self.release_manifest_path = self.contract_root / "release_manifest.json"
        self.case_manifest_path = ROOT_DIR / "cases" / "daduhe" / "manifest.yaml"

        self.workflow_run = self._load_json(self.workflow_run_path)
        self.review_bundle = self._load_json(self.review_bundle_path)
        self.release_manifest = self._load_json(self.release_manifest_path)
        self.case_manifest = yaml.safe_load(self.case_manifest_path.read_text(encoding="utf-8")) or {}

    @staticmethod
    def _load_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _artifact_paths(self) -> list[tuple[str, str]]:
        collected: list[tuple[str, str]] = []
        groups = (
            ("workflow_run.inputs", self.workflow_run.get("inputs", [])),
            ("workflow_run.outputs", self.workflow_run.get("outputs", [])),
            ("review_bundle.report_artifacts", self.review_bundle.get("report_artifacts", [])),
            ("release_manifest.artifacts", self.release_manifest.get("artifacts", [])),
        )
        for group_name, items in groups:
            if not isinstance(items, list):
                continue
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if isinstance(path, str) and path.strip():
                    collected.append((f"{group_name}[{idx}]", path))
        return collected

    def test_run_review_release_ids_form_single_chain(self) -> None:
        workflow_run_id = self.workflow_run.get("run_id")
        review_run_id = self.review_bundle.get("run_id")
        review_id = self.review_bundle.get("review_id")
        included_runs = self.release_manifest.get("included_runs", [])
        review_refs = self.release_manifest.get("review_refs", [])

        self.assertEqual(
            review_run_id,
            workflow_run_id,
            "ReviewBundle.run_id must reference the canonical WorkflowRun.run_id",
        )
        self.assertIn(
            workflow_run_id,
            included_runs,
            "ReleaseManifest.included_runs must include the canonical WorkflowRun.run_id",
        )
        self.assertIn(
            review_id,
            review_refs,
            "ReleaseManifest.review_refs must include ReviewBundle.review_id",
        )

    def test_all_contract_artifact_paths_exist(self) -> None:
        missing: list[str] = []
        for label, raw_path in self._artifact_paths():
            path = Path(raw_path)
            resolved = path if path.is_absolute() else self.workspace_root / path
            if not resolved.exists():
                missing.append(f"{label} -> {raw_path}")
        self.assertEqual(missing, [], f"Missing contract artifact paths: {missing}")

    def test_all_contract_artifact_paths_are_workspace_relative(self) -> None:
        absolute_paths = [
            f"{label} -> {raw_path}"
            for label, raw_path in self._artifact_paths()
            if Path(raw_path).is_absolute()
        ]
        self.assertEqual(
            absolute_paths,
            [],
            f"Contract artifact paths must be workspace-relative: {absolute_paths}",
        )

    def test_manifest_latest_contracts_match_three_piece_chain(self) -> None:
        latest_workflow = self.case_manifest.get("latest_workflow_run", {}) or {}
        latest_review = self.case_manifest.get("latest_review_bundle", {}) or {}
        latest_release = self.case_manifest.get("latest_release_manifest", {}) or {}

        self.assertEqual(latest_workflow.get("run_id"), self.workflow_run.get("run_id"))
        self.assertEqual(latest_review.get("review_id"), self.review_bundle.get("review_id"))
        self.assertEqual(latest_release.get("release_id"), self.release_manifest.get("release_id"))
        self.assertEqual(latest_review.get("status"), self.review_bundle.get("verdict"))
        self.assertEqual(latest_release.get("status"), self.release_manifest.get("status"))
        self.assertFalse(Path(str(latest_workflow.get("path", ""))).is_absolute())
        self.assertFalse(Path(str(latest_review.get("path", ""))).is_absolute())
        self.assertFalse(Path(str(latest_release.get("path", ""))).is_absolute())


if __name__ == "__main__":
    unittest.main()
