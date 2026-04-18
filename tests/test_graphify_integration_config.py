"""graphify_integration.yaml 可解析且含版本字段（战役 Phase 5 最小门禁）。"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "Hydrology" / "configs" / "graphify_integration.yaml"


def test_graphify_integration_yaml_loads() -> None:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "graphify_integration.v1"
    assert "feature_flag_default" in data
    assert data.get("sidecar_readonly") is True
