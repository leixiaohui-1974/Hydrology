"""bootstrap_case_triad_minimal.triad_json_absent：仅有 .contract.json 时仍应允许补写 .json。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
for _p in (WORKSPACE / "Hydrology" / "scripts",):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from bootstrap_case_triad_minimal import triad_json_absent  # noqa: E402


class TestBootstrapTriadJsonAbsent(unittest.TestCase):
    def test_contract_only_implies_json_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cdir = Path(tmp)
            (cdir / "workflow_run.contract.json").write_text("{}", encoding="utf-8")
            self.assertTrue(triad_json_absent(cdir, "workflow_run"))
            (cdir / "workflow_run.json").write_text("{}", encoding="utf-8")
            self.assertFalse(triad_json_absent(cdir, "workflow_run"))


if __name__ == "__main__":
    unittest.main()
