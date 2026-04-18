from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows import WORKFLOW_REGISTRY


class TestAgentVisibleWorkflowsConfig(unittest.TestCase):
    def test_allowlist_normalizes_to_known_workflows(self) -> None:
        config_path = ROOT_DIR / "configs" / "agent_visible_workflows.yaml"
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        aliases = payload.get("aliases") or {}
        allowlist = payload.get("allowlist") or []

        for raw_key in allowlist:
            key = str(raw_key).strip()
            normalized = str(aliases.get(key) or key).strip()
            self.assertIn(normalized, WORKFLOW_REGISTRY, msg=f"unknown workflow key: {raw_key}")

    def test_alias_targets_exist_and_alias_sources_stay_out_of_allowlist(self) -> None:
        config_path = ROOT_DIR / "configs" / "agent_visible_workflows.yaml"
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        aliases = payload.get("aliases") or {}
        allowlist = {str(item).strip() for item in payload.get("allowlist") or []}

        for alias, target in aliases.items():
            alias_key = str(alias).strip()
            target_key = str(target).strip()
            self.assertNotIn(alias_key, allowlist, msg=f"alias key should not appear in allowlist: {alias_key}")
            self.assertIn(target_key, WORKFLOW_REGISTRY, msg=f"alias target missing from registry: {target_key}")

    def test_allowlist_excludes_cross_repo_external_integrations(self) -> None:
        config_path = ROOT_DIR / "configs" / "agent_visible_workflows.yaml"
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        allowlist = {str(item).strip() for item in payload.get("allowlist") or []}

        cross_repo_keys = {
            key
            for key, meta in WORKFLOW_REGISTRY.items()
            if meta.get("external_script") and not str(meta.get("external_script")).startswith("Hydrology/")
        }
        self.assertTrue(cross_repo_keys)
        self.assertFalse(allowlist & cross_repo_keys)


if __name__ == "__main__":
    unittest.main()
