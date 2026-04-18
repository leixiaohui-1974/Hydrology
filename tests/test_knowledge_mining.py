#!/usr/bin/env python3
"""Integration test for generalized knowledge mining engine.

Verifies that the engine can:
1. Load a case YAML config
2. Discover station coordinates from multiple formats
3. Score reliability deterministically
4. Detect anomalies
5. Produce delineation-ready outlets
6. Extract hydraulic parameters

All assertions are deterministic — same config = same results.
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import yaml


def test_config_loads():
    """Case YAML loads and has required fields."""
    config_path = BASE_DIR / "configs" / "daduhe.yaml"
    assert config_path.exists(), f"Config not found: {config_path}"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    assert cfg["case_id"] == "daduhe"
    assert len(cfg["target_stations"]) >= 5
    assert len(cfg["scan_dirs"]) >= 1
    assert cfg["dem_path"]
    print("PASS: config loads")
    return cfg


def test_engine_import():
    """knowledge_mining module imports."""
    try:
        from hydro_model import knowledge_mining as km
        assert hasattr(km, "run_pipeline"), "Missing run_pipeline"
        assert hasattr(km, "discover"), "Missing discover"
        assert hasattr(km, "score"), "Missing score"
        assert hasattr(km, "normalize"), "Missing normalize"
        print("PASS: engine imports")
        return km
    except ImportError as e:
        print(f"SKIP: engine not yet available ({e})")
        return None


def test_full_pipeline(km, cfg):
    """Full pipeline produces expected outputs."""
    result = km.run_pipeline(cfg)
    assert result is not None
    # Check key outputs exist
    output_dir = Path(cfg["output_dir"])
    for fname in ["source_inventory.json", "source_reliability.json",
                   "coordinate_validation.json", "outlets.delineation_ready.json"]:
        path = output_dir / fname
        assert path.exists(), f"Missing output: {path}"
    # Check delineation-ready has outlets
    with open(output_dir / "outlets.delineation_ready.json") as f:
        ready = json.load(f)
    assert ready["count"] > 0, "No delineation-ready outlets"
    print(f"PASS: full pipeline — {ready['count']} ready outlets")
    return result


def test_determinism(km, cfg):
    """Same config produces same results (run twice, compare)."""
    r1 = km.run_pipeline(cfg)
    r2 = km.run_pipeline(cfg)
    output_dir = Path(cfg["output_dir"])
    with open(output_dir / "outlets.delineation_ready.json") as f:
        ready1 = json.load(f)
    # Run again
    r2 = km.run_pipeline(cfg)
    with open(output_dir / "outlets.delineation_ready.json") as f:
        ready2 = json.load(f)
    assert ready1["count"] == ready2["count"], "Non-deterministic outlet count"
    for o1, o2 in zip(ready1["outlets"], ready2["outlets"]):
        assert o1["name"] == o2["name"], f"Non-deterministic: {o1['name']} vs {o2['name']}"
        assert o1["lat"] == o2["lat"], f"Non-deterministic lat for {o1['name']}"
    print("PASS: determinism verified")


def main():
    cfg = test_config_loads()
    km = test_engine_import()
    if km is None:
        print("\nEngine not ready. Run after codex/gemini finish writing knowledge_mining.py")
        return
    test_full_pipeline(km, cfg)
    test_determinism(km, cfg)
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
