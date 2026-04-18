"""bootstrap_case_triad_minimal.minimal_payloads 与 hydromind-contracts 程序契约校验对齐。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
HYDROLOGY = WORKSPACE / "Hydrology"
HC_ROOT = WORKSPACE / "hydromind-contracts"
if HC_ROOT.is_dir():
    sys.path.insert(0, str(HC_ROOT))

for _p in (HYDROLOGY, HYDROLOGY / "scripts"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)


@unittest.skipUnless(HC_ROOT.is_dir(), "hydromind-contracts repo missing")
class TestBootstrapTriadContractAlignment(unittest.TestCase):
    def test_minimal_payloads_pass_program_validation(self) -> None:
        from hydromind_contracts.program_validation import (
            load_and_validate_release_manifest,
            load_and_validate_review_bundle,
            load_and_validate_workflow_run,
        )

        from bootstrap_case_triad_minimal import minimal_payloads

        wf, rb, rm = minimal_payloads("ut_bootstrap_contract_case")
        _, e1 = load_and_validate_workflow_run(wf)
        self.assertEqual(e1, [], e1)
        _, e2 = load_and_validate_review_bundle(rb)
        self.assertEqual(e2, [], e2)
        _, e3 = load_and_validate_release_manifest(rm)
        self.assertEqual(e3, [], e3)


if __name__ == "__main__":
    unittest.main()
