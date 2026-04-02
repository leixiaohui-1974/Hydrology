"""Tests for Hydrology program contract bridge."""

import json
import os
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "common" / "program_contract_bridge.py"
spec = importlib.util.spec_from_file_location("program_contract_bridge", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)

CONTRACTS_AVAILABLE = module.CONTRACTS_AVAILABLE
PROGRAM_SCHEMA_VERSION = module.PROGRAM_SCHEMA_VERSION
load_and_validate_payload = module.load_and_validate_payload
program_contract_kinds = module.program_contract_kinds
validate_payload = module.validate_payload


@unittest.skipUnless(CONTRACTS_AVAILABLE, "hydromind-contracts repo not available")
class TestProgramContractBridge(unittest.TestCase):
    def test_program_contract_kinds_contains_expected_entries(self):
        self.assertIn("source_bundle", program_contract_kinds())
        self.assertIn("data_pack", program_contract_kinds())
        self.assertIn("review_bundle", program_contract_kinds())

    def test_validate_payload_accepts_minimal_source_bundle(self):
        payload = {
            "bundle_id": "bundle-001",
            "case_id": "daduhe",
            "records": [
                {
                    "role": "dem",
                    "confidence": 0.95,
                    "artifact": {
                        "artifact_id": "dem-001",
                        "artifact_type": "raster",
                        "path": "/tmp/dem.tif",
                        "metadata": {},
                    },
                    "evidence": ["matched filename"],
                    "needs_review": False,
                }
            ],
            "gaps": [],
            "review_required": [],
            "metadata": {},
            "schema_version": PROGRAM_SCHEMA_VERSION,
        }
        contract, errors = validate_payload("source_bundle", payload)
        self.assertEqual(contract.case_id, "daduhe")
        self.assertEqual(errors, [])

    def test_load_and_validate_payload_reads_json_file(self):
        payload = {
            "review_id": "review-001",
            "run_id": "run-001",
            "case_id": "daduhe",
            "verdict": "pass",
            "findings": [],
            "report_artifacts": [],
            "metadata": {},
            "schema_version": PROGRAM_SCHEMA_VERSION,
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            temp_path = handle.name

        try:
            contract, errors = load_and_validate_payload("review_bundle", temp_path)
            self.assertEqual(contract.review_id, "review-001")
            self.assertEqual(errors, [])
        finally:
            os.unlink(temp_path)

    def test_validate_payload_accepts_minimal_data_pack(self):
        payload = {
            "kind": "data_pack",
            "case_manifest": "/tmp/case_manifest.json",
            "source_bundle_json": "/tmp/source_bundle.contract.json",
            "outlets_json": "/tmp/outlets.normalized.json",
            "review_gates": {"basin_validation_json": None},
            "strict": False,
            "summary": {"outlet_count": 7},
            "metadata": {},
            "schema_version": PROGRAM_SCHEMA_VERSION,
        }
        contract, errors = validate_payload("data_pack", payload)
        self.assertEqual(contract.kind, "data_pack")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
