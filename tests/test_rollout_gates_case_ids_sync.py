"""rollout_repo_artifact_gates.json 的 case_artifact_profile 键集与闭环 YAML 解析的 case_ids 一致。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "Hydrology" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402

LOOP = REPO / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
GATES = REPO / "Hydrology" / "configs" / "rollout_repo_artifact_gates.json"


class TestRolloutGatesCaseIdsSync(unittest.TestCase):
    def test_profile_keys_match_loop_case_ids(self) -> None:
        cfg = load_loop_yaml(REPO, LOOP.resolve())
        loop_ids = set(resolve_case_ids(cfg, REPO))
        data = json.loads(GATES.read_text(encoding="utf-8"))
        self.assertEqual(data.get("version"), 2)
        cmap = data.get("case_artifact_profile") or {}
        self.assertIsInstance(cmap, dict)
        self.assertEqual(set(cmap.keys()), loop_ids)


if __name__ == "__main__":
    unittest.main()
