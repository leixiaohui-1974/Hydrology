from __future__ import annotations

from pathlib import Path

import yaml


def test_agent_registry_excludes_daduhe_specific_runtime_workflows() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry_path = repo_root / "Hydrology" / "configs" / "agent_registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}

    agents = registry.get("agents", {})
    workflow_entries = [
        workflow
        for agent in agents.values()
        for workflow in (agent or {}).get("workflows", [])
    ]

    assert workflow_entries
    assert all("run_daduhe_" not in workflow for workflow in workflow_entries)
