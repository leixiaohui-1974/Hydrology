"""playwrightE2eAcceptance.generated.json 与闭环 YAML + acceptance YAML 导出结果一致。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "Hydrology" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import export_playwright_e2e_acceptance as epa  # noqa: E402

GEN = REPO / "HydroDesk" / "src" / "config" / "playwrightE2eAcceptance.generated.json"


class TestPlaywrightE2eAcceptanceSync(unittest.TestCase):
    def test_generated_matches_compute(self) -> None:
        self.assertTrue(GEN.is_file(), f"missing {GEN}")
        computed = epa.compute_e2e_acceptance(
            REPO,
            epa.DEFAULT_LOOP.resolve(),
            epa.DEFAULT_ACCEPTANCE.resolve(),
        )
        on_disk = json.loads(GEN.read_text(encoding="utf-8"))
        self.assertEqual(
            epa._normalize_for_compare(computed),
            epa._normalize_for_compare(on_disk),
        )


if __name__ == "__main__":
    unittest.main()
