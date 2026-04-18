import sys
import os
import json
import logging
import argparse
from typing import Any, Dict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HYDROLOGY_DIR = PROJECT_ROOT / "Hydrology"
if str(HYDROLOGY_DIR) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY_DIR))

from workflows._shared import load_case_config, WORKSPACE

logger = logging.getLogger(__name__)

def run_predictive_scheduling(case_id: str, cfg: Dict[str, Any]):
    logger.info(f"Running predictive scheduling for case: {case_id}")
    
    demand_plan = cfg.get("water_demand_plan", {})
    if not demand_plan:
        logger.warning("No water_demand_plan found in config. Using default empty plan.")
        demand_plan = {"outlets": {}}

    scheduled_plan = {
        "status": "generated",
        "case_id": case_id,
        "outlets": {}
    }

    # Generate actual execution plan based on demand plan
    for outlet_id, plan in demand_plan.get("outlets", {}).items():
        normal_demand = plan.get("normal", 0.0)
        ecological_demand = plan.get("ecological", 0.0)
        maintenance_factor = plan.get("maintenance_factor", 1.0)
        
        # Determine actual demand (e.g. normal + ecological, modified by maintenance)
        actual_demand = (normal_demand + ecological_demand) * maintenance_factor
        
        scheduled_plan["outlets"][outlet_id] = {
            "target_flow": actual_demand,
            "components": {
                "normal": normal_demand,
                "ecological": ecological_demand
            },
            "maintenance_factor": maintenance_factor
        }

    contract_dir = WORKSPACE / "cases" / case_id / "contracts"
    contract_dir.mkdir(parents=True, exist_ok=True)
    out_path = contract_dir / "scheduled_control_plan.latest.json"
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scheduled_plan, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Scheduled control plan saved to {out_path}")
    return scheduled_plan

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()
    cfg = load_case_config(args.case_id)
    run_predictive_scheduling(args.case_id, cfg)
