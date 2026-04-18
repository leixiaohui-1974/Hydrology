from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HYDROLOGY_DIR = PROJECT_ROOT / "Hydrology"
if str(HYDROLOGY_DIR) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY_DIR))

from workflows._shared import WORKSPACE


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch a case control YAML with generic review defaults.")
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()

    case_id = str(args.case_id).strip()
    yaml_path = WORKSPACE / "Hydrology" / "configs" / f"{case_id}.yaml"

    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    cfg["water_demand_plan"] = {
        "outlets": {
            "NODE-main-14": {
                "normal": 50.0,
                "ecological": 5.0,
                "maintenance_factor": 1.0,
            }
        }
    }

    control_cfg = cfg.setdefault("control", {})
    control_cfg["odd_bounds"] = {
        "maintenance": {
            "max_flow": 40.0,
            "min_level": 5.0,
        },
        "emergency": {
            "max_flow": 20.0,
            "min_level": 2.0,
        },
        "ecological_replenishment": {
            "max_flow": 60.0,
            "min_level": 8.0,
        },
    }

    scenarios_cfg = cfg.setdefault("scenarios", {})
    scenarios_cfg["maintenance"] = {"active": True}
    scenarios_cfg["ecological_replenishment"] = {"active": True}

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)

    print(f"Updated {case_id}.yaml with water_demand_plan, odd_bounds, and scenarios.")


if __name__ == "__main__":
    main()
