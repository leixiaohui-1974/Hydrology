"""playwrightRollout.generated.json 与闭环 YAML + case_manifest 导出结果一致。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "Hydrology" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import export_playwright_rollout_registry as epr  # noqa: E402

GEN = REPO / "HydroDesk" / "src" / "config" / "playwrightRollout.generated.json"


class TestPlaywrightRolloutRegistrySync(unittest.TestCase):
    def test_generated_matches_compute(self) -> None:
        self.assertTrue(GEN.is_file(), f"missing {GEN}")
        computed = epr.compute_rollout_registry(REPO, epr.DEFAULT_LOOP.resolve())
        on_disk = json.loads(GEN.read_text(encoding="utf-8"))
        self.assertEqual(
            epr._normalize_for_compare(computed),
            epr._normalize_for_compare(on_disk),
        )


if __name__ == "__main__":
    unittest.main()
