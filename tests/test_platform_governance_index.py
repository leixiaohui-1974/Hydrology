"""platform_governance_gates.index.json 结构门禁（与 check_rollout_repo_contracts / e2e 平台治理段对齐）。"""

from __future__ import annotations

import unittest

from rollout_gates_parse import validate_platform_governance_index


class TestPlatformGovernanceIndex(unittest.TestCase):
    def test_index_validates(self) -> None:
        errs = validate_platform_governance_index()
        self.assertEqual(errs, [], errs)


if __name__ == "__main__":
    unittest.main()
