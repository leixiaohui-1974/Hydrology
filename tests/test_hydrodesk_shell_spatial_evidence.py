"""hydrodesk_shell.full_spatial_hydro_evidence_case_ids 解析与导出校验。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "Hydrology" / "scripts"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import export_playwright_rollout_registry as epr  # noqa: E402
from hydrodesk_loop_yaml_util import (  # noqa: E402
    resolve_default_active_case_id,
    resolve_full_spatial_hydro_evidence_case_ids,
)


class TestHydrodeskShellSpatialEvidence(unittest.TestCase):
    def test_resolve_empty_when_missing(self) -> None:
        self.assertEqual(resolve_full_spatial_hydro_evidence_case_ids({}), [])

    def test_resolve_strips_and_skips_non_strings(self) -> None:
        cfg = {
            "hydrodesk_shell": {
                "full_spatial_hydro_evidence_case_ids": [" daduhe ", "yjdt", "", 3, None],
            }
        }
        self.assertEqual(resolve_full_spatial_hydro_evidence_case_ids(cfg), ["daduhe", "yjdt"])

    def test_compute_rollout_rejects_unknown_spatial_id(self) -> None:
        fake_cfg = {
            "case_selection": {"mode": "explicit", "case_ids": ["daduhe"]},
            "hydrodesk_shell": {"full_spatial_hydro_evidence_case_ids": ["daduhe", "ghost_case"]},
        }
        with patch("export_playwright_rollout_registry.load_loop_yaml", return_value=fake_cfg):
            with self.assertRaises(ValueError) as ctx:
                epr.compute_rollout_registry(REPO, epr.DEFAULT_LOOP.resolve())
        self.assertIn("ghost_case", str(ctx.exception))

    def test_default_loop_spatial_subset(self) -> None:
        computed = epr.compute_rollout_registry(REPO, epr.DEFAULT_LOOP.resolve())
        ids = computed.get("full_spatial_hydro_evidence_case_ids") or []
        case_ids = computed.get("case_ids") or []
        self.assertTrue(all(x in case_ids for x in ids))
        dac = computed.get("default_active_case_id")
        self.assertEqual(dac, "zhongxian")
        self.assertIn(dac, case_ids)

    def test_resolve_default_active_none(self) -> None:
        self.assertIsNone(resolve_default_active_case_id({}))
        self.assertIsNone(
            resolve_default_active_case_id({"hydrodesk_shell": {"default_active_case_id": "  "}})
        )

    def test_compute_rollout_rejects_bad_default_active(self) -> None:
        fake_cfg = {
            "case_selection": {"mode": "explicit", "case_ids": ["daduhe"]},
            "hydrodesk_shell": {"default_active_case_id": "nope"},
        }
        with patch("export_playwright_rollout_registry.load_loop_yaml", return_value=fake_cfg):
            with self.assertRaises(ValueError) as ctx:
                epr.compute_rollout_registry(REPO, epr.DEFAULT_LOOP.resolve())
        self.assertIn("default_active_case_id", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
