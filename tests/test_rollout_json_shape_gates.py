"""Rollout JSON 顶层键门禁（与 HydroDesk e2e/contracts-repo-gates Rollout JSON 段对齐）。"""

from __future__ import annotations

import json
import unittest

from rollout_gates_parse import WORKSPACE_ROOT as REPO, load_rollout_gates, rollout_json_shape_gate_cases


class TestRolloutJsonShapeGates(unittest.TestCase):
    def setUp(self) -> None:
        self.gates = load_rollout_gates()

    def test_json_files_exist_and_have_required_top_level_keys(self) -> None:
        for row in rollout_json_shape_gate_cases(self.gates):
            cid = row["case_id"]
            tpl = row["path_template"]
            keys = row["required_keys"]
            with self.subTest(case_id=cid, path_template=tpl):
                rel = tpl.replace("{case_id}", cid)
                path = REPO / rel
                self.assertTrue(path.is_file(), f"缺少 JSON: {rel}")
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict, rel)
                for k in keys:
                    self.assertIn(k, data, f"缺少键 {k}: {rel}")


if __name__ == "__main__":
    unittest.main()
