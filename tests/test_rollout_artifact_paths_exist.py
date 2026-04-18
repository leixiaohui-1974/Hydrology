"""rollout_repo_artifact_gates：各案例必达相对路径在仓库中真实存在（与 HydroDesk e2e/contracts-repo-gates 对齐）。"""

from __future__ import annotations

import unittest

from rollout_gates_parse import WORKSPACE_ROOT as REPO, artifact_paths_for_case, load_rollout_gates


class TestRolloutArtifactPathsExist(unittest.TestCase):
    def setUp(self) -> None:
        self.gates = load_rollout_gates()

    def test_all_profiled_cases_have_rollout_paths_on_disk(self) -> None:
        cmap = self.gates.get("case_artifact_profile") or {}
        for case_id in sorted(cmap.keys()):
            with self.subTest(case_id=case_id):
                missing: list[str] = []
                for rel in artifact_paths_for_case(case_id, self.gates):
                    abs_path = REPO / rel
                    if not abs_path.is_file():
                        missing.append(rel)
                self.assertEqual(
                    missing,
                    [],
                    f"{case_id}: missing rollout artifact files — run workflows or bootstrap triad",
                )


if __name__ == "__main__":
    unittest.main()
