"""workflowRegistry.playwright.fixture.json 与公开暴露工作流同步。"""
from __future__ import annotations

import json
import unittest
from pathlib import Path


class TestWorkflowRegistryPlaywrightFixtureSync(unittest.TestCase):
    def test_fixture_matches_registry(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        fixture_path = repo / "HydroDesk" / "src" / "config" / "workflowRegistry.playwright.fixture.json"
        self.assertTrue(fixture_path.is_file(), f"missing {fixture_path}")

        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        names_fixture = {x["name"] for x in data}

        import sys

        sys.path.insert(0, str(repo / "Hydrology"))
        from workflows import list_workflows  # noqa: PLC0415

        self.assertEqual(names_fixture, {item["name"] for item in list_workflows()})


if __name__ == "__main__":
    unittest.main()
