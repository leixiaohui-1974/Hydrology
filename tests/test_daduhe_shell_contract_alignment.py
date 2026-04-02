"""Regression checks for daduhe shell contract alignment."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
HYDROLOGY_DIR = ROOT_DIR / "Hydrology"
if str(HYDROLOGY_DIR) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY_DIR))

BRIDGE_PATH = HYDROLOGY_DIR / "common" / "program_contract_bridge.py"
spec = importlib.util.spec_from_file_location("program_contract_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(bridge)


class TestDaduheShellContractAlignment(unittest.TestCase):
    def setUp(self) -> None:
        self.contract_root = ROOT_DIR / "cases" / "daduhe" / "contracts"
        self.manifest_path = ROOT_DIR / "cases" / "daduhe" / "manifest.yaml"
        self.links_path = ROOT_DIR / "cases" / "daduhe" / "links.yaml"
        self.shell_js_path = ROOT_DIR / "HydroDesk" / "src" / "data" / "daduheShell.js"

    def test_contract_triad_validates_against_program_contracts(self) -> None:
        triad = {
            "workflow_run": self.contract_root / "workflow_run.json",
            "review_bundle": self.contract_root / "review_bundle.json",
            "release_manifest": self.contract_root / "release_manifest.json",
        }
        for kind, path in triad.items():
            self.assertTrue(path.exists(), f"{kind} contract missing: {path}")
            _, errors = bridge.load_and_validate_payload(kind, path)
            self.assertEqual(errors, [], f"{kind} validation errors: {errors}")

    def test_manifest_points_to_canonical_shell_contracts(self) -> None:
        manifest = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8"))
        expected = {
            "workflow_run": str(self.contract_root / "workflow_run.json"),
            "review_bundle": str(self.contract_root / "review_bundle.json"),
            "release_manifest": str(self.contract_root / "release_manifest.json"),
        }

        self.assertEqual(manifest["release_handoff"]["artifacts"], expected)
        self.assertEqual(manifest["latest_workflow_run"]["path"], expected["workflow_run"])
        self.assertEqual(manifest["latest_review_bundle"]["path"], expected["review_bundle"])
        self.assertEqual(manifest["latest_release_manifest"]["path"], expected["release_manifest"])

        shell_entrypoints = manifest["shell_entrypoints"]
        self.assertEqual(
            shell_entrypoints["run"]["path"],
            str(ROOT_DIR / "Hydrology" / "workflows" / "run_case_pipeline.py"),
        )
        self.assertEqual(
            shell_entrypoints["review"]["path"],
            str(ROOT_DIR / "Hydrology" / "workflows" / "build_review_bundle.py"),
        )
        self.assertEqual(
            shell_entrypoints["release"]["path"],
            str(ROOT_DIR / "Hydrology" / "workflows" / "build_release_manifest.py"),
        )

    def test_links_and_shell_data_expose_run_review_release_entrypoints(self) -> None:
        links = yaml.safe_load(self.links_path.read_text(encoding="utf-8"))["links"]
        shell_js = self.shell_js_path.read_text(encoding="utf-8")

        self.assertEqual(
            links["hydrology_case_pipeline"]["path"],
            str(ROOT_DIR / "Hydrology" / "workflows" / "run_case_pipeline.py"),
        )
        self.assertEqual(
            links["hydrology_run_entry"]["path"],
            str(ROOT_DIR / "Hydrology" / "workflows" / "run_watershed_delineation.py"),
        )
        self.assertEqual(
            links["hydrology_review_entry"]["path"],
            str(ROOT_DIR / "Hydrology" / "workflows" / "build_review_bundle.py"),
        )
        self.assertEqual(
            links["hydrology_release_builder"]["path"],
            str(ROOT_DIR / "Hydrology" / "workflows" / "build_release_manifest.py"),
        )

        for expected_path in (
            "Hydrology/workflows/run_case_pipeline.py",
            "Hydrology/workflows/build_review_bundle.py",
            "Hydrology/workflows/build_release_manifest.py",
        ):
            self.assertIn(expected_path, shell_js)

        for expected_fragment in (
            "workflow_run.json",
            "review_bundle.json",
            "release_manifest.json",
            "const contractRoot = `cases/${resolvedCaseId}/contracts`;",
        ):
            self.assertIn(expected_fragment, shell_js)


if __name__ == "__main__":
    unittest.main()
