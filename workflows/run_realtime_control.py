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

def validate_odd_and_apply_sil(state: Dict[str, Any], odd_bounds: Dict[str, Any], scenarios: Dict[str, Any]):
    """
    Check if the current state exceeds ODD bounds for the active scenarios.
    If it does, apply SIL degradation rules (e.g. cap values).
    Returns (modified_state, violations_count, interventions_count)
    """
    violations = 0
    interventions = 0
    modified_state = state.copy()
    
    active_scenarios = [k for k, v in scenarios.items() if v.get("active", False)]
    
    for outlet, values in state.get("outlets", {}).items():
        flow = values.get("flow", 0.0)
        level = values.get("level", 0.0)
        
        # Check ODD bounds for all active scenarios
        for scenario in active_scenarios:
            bounds = odd_bounds.get(scenario, {})
            max_flow = bounds.get("max_flow")
            min_level = bounds.get("min_level")
            
            violated = False
            if max_flow is not None and flow > max_flow:
                violated = True
                logger.warning(f"ODD Violation: Outlet {outlet} flow {flow} exceeds max_flow {max_flow} for scenario {scenario}")
                # Apply SIL protection
                modified_state["outlets"][outlet]["flow"] = max_flow
                interventions += 1
                
            if min_level is not None and level < min_level:
                violated = True
                logger.warning(f"ODD Violation: Outlet {outlet} level {level} below min_level {min_level} for scenario {scenario}")
                # Apply SIL protection
                modified_state["outlets"][outlet]["level"] = min_level
                interventions += 1
                
            if violated:
                violations += 1
                
    return modified_state, violations, interventions

def run_realtime_control(case_id: str, cfg: Dict[str, Any]):
    logger.info(f"Running real-time control for case: {case_id}")
    
    contract_dir = WORKSPACE / "cases" / case_id / "contracts"
    plan_path = contract_dir / "scheduled_control_plan.latest.json"
    
    if not plan_path.exists():
        logger.error(f"Scheduled plan not found at {plan_path}. Run predictive scheduling first.")
        return None
        
    with open(plan_path, "r", encoding="utf-8") as f:
        scheduled_plan = json.load(f)
        
    odd_bounds = cfg.get("control", {}).get("odd_bounds", {})
    scenarios = cfg.get("scenarios", {})
    
    # Simulate real-time execution step
    current_state = {
        "outlets": {
            outlet: {"flow": data["target_flow"], "level": 10.0} # Mock level for simulation
            for outlet, data in scheduled_plan.get("outlets", {}).items()
        }
    }
    
    # Apply ODD validation and SIL degradation
    safe_state, odd_violations, sil_interventions = validate_odd_and_apply_sil(
        current_state, odd_bounds, scenarios
    )
    
    control_result = {
        "status": "executed",
        "case_id": case_id,
        "target_plan": scheduled_plan,
        "executed_state": safe_state,
        "metrics": {
            "odd_violations": odd_violations,
            "sil_interventions": sil_interventions,
            "completion_rate": 1.0 if odd_violations == 0 else max(0.0, 1.0 - (odd_violations * 0.1))
        }
    }
    
    out_path = contract_dir / "realtime_control_result.latest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(control_result, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Real-time control executed. Violations: {odd_violations}, Interventions: {sil_interventions}")
    return control_result

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()
    cfg = load_case_config(args.case_id)
    run_realtime_control(args.case_id, cfg)
