"""scada 回放窗口与 DB 路径由 YAML 解析（无硬编码日期）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
HYD = REPO / "Hydrology"
if str(HYD) not in sys.path:
    sys.path.insert(0, str(HYD))

from workflows.hydrodesk_e2e_actions import (  # noqa: E402
    merge_scada_replay_cli_overrides,
    resolve_scada_replay_config,
    resolve_scada_replay_paths,
    resolve_scada_replay_scenario_id,
)


class TestScadaReplayConfigResolution(unittest.TestCase):
    def test_defaults_file_exists(self) -> None:
        p = HYD / "configs" / "scada_replay_defaults.yaml"
        self.assertTrue(p.is_file(), f"missing {p}")

    def test_daduhe_sqlite_path_convention(self) -> None:
        qs, qe, db = resolve_scada_replay_paths("daduhe")
        self.assertIsNotNone(qs)
        self.assertIsNotNone(qe)
        self.assertTrue(str(db).endswith("daduhe_hydromind.sqlite3"), db)

    def test_scenario_id_from_defaults_when_case_empty(self) -> None:
        self.assertEqual(resolve_scada_replay_scenario_id("daduhe"), "replay_baseline")

    def test_scenario_id_case_yaml_overrides_defaults(self) -> None:
        with mock.patch("workflows.hydrodesk_e2e_actions.load_case_config") as m:
            m.return_value = {"scada_replay": {"scenario_id": "case_tag_x"}}
            self.assertEqual(resolve_scada_replay_scenario_id("any_case"), "case_tag_x")

    def test_resolve_scada_replay_config_matches_delegates(self) -> None:
        qs, qe, sp, sid = resolve_scada_replay_config("daduhe")
        self.assertEqual((qs, qe, sp), resolve_scada_replay_paths("daduhe"))
        self.assertEqual(sid, resolve_scada_replay_scenario_id("daduhe"))

    def test_unknown_case_uses_defaults_window_and_sqlite_guess(self) -> None:
        qs, qe, db = resolve_scada_replay_paths("nonexistent_case_xyz")
        self.assertIsNotNone(qs)
        self.assertIsNotNone(qe)
        self.assertIn("nonexistent_case_xyz_hydromind.sqlite3", str(db))

    def test_merge_cli_no_op_when_empty(self) -> None:
        base = REPO / "cases" / "daduhe" / "daduhe_hydromind.sqlite3"
        qs, qe, sp = merge_scada_replay_cli_overrides("s0", "e0", base.resolve())
        self.assertEqual(qs, "s0")
        self.assertEqual(qe, "e0")
        self.assertEqual(sp, base.resolve())

    def test_merge_cli_trims_and_overrides_sqlite_relative_to_repo(self) -> None:
        base = REPO / "tmp_placeholder.sqlite3"
        rel = "Hydrology/configs/scada_replay_defaults.yaml"
        qs, qe, sp = merge_scada_replay_cli_overrides(
            "orig_s",
            "orig_e",
            base,
            query_start_cli="  2022-01-01 00:00:00  ",
            query_end_cli="",
            sqlite_path_cli=rel,
        )
        self.assertEqual(qs, "2022-01-01 00:00:00")
        self.assertEqual(qe, "orig_e")
        self.assertEqual(sp, (REPO / rel).resolve())


if __name__ == "__main__":
    unittest.main()
