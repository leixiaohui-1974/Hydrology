"""review_surface_gates.yaml 可解析且含统一 gate id。"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "Hydrology" / "configs" / "review_surface_gates.yaml"


def test_review_surface_gates_yaml_loads() -> None:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "review_surface_gates.v1"
    ids = [g.get("id") for g in (data.get("gates") or [])]
    assert "hydraulics" in ids
    assert "coupling" in ids
    assert "assimilation" in ids
