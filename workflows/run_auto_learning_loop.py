#!/usr/bin/env python3
"""
Auto-learning loop for self-diagnosis and self-learning.
Dynamically adjusts parameters in `parameter_governance` based on metric gaps
and triggers recalculation until convergence.
"""

import argparse
import json
import sys
import shlex
import subprocess
from pathlib import Path
from scipy.optimize import differential_evolution
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import load_json, write_json, WORKSPACE, abs_path
from workflows._autonomy_policy import governance_source_relpath, load_merged_autonomy_policy

DEFAULT_HYDROLOGY_WORKFLOW_CMD = (
    "python3 Hydrology/workflows/run_hydrological_simulation.py "
    "--case-id {case_id} "
    "--data-pack-json cases/{case_id}/contracts/data_pack.latest.json "
    "--simulation-config Hydrology/configs/{case_id}.yaml "
    "--parameter-governance-json cases/{case_id}/contracts/parameter_governance.latest.json "
    "--no-calibrate"
)
DEFAULT_HYDROLOGY_METRIC_FILE = "cases/{case_id}/contracts/hydrology_calibration.latest.json"
DEFAULT_HYDROLOGY_METRIC_KEY = "calibration_metrics.nse"


def _metric_source_candidates(metric_file: str, metric_key: str) -> list[tuple[Path, str, str]]:
    metric_path = Path(metric_file)
    candidates: list[tuple[Path, str, str]] = [(metric_path, metric_key, "requested")]
    if (
        metric_path.name == "hydrology_nse_evidence.latest.json"
        and metric_key == "comparable_nse"
    ):
        candidates.append(
            (
                metric_path.with_name("hydrology_calibration.latest.json"),
                "calibration_metrics.nse",
                "hydrology_calibration_fallback",
            )
        )
    return candidates


def _argv_has_cli_flag(flag: str) -> bool:
    return flag in sys.argv


def _merge_auto_learning_from_config(
    case_id: str, stage: str, config_path: Optional[str] = None,
) -> Tuple[dict[str, Any], List[str]]:
    """合并 workflow_autonomy_policy（含 legacy auto_learning_by_case 底层）；返回 (merged_stage_dict, applied_keys)。"""
    policy = load_merged_autonomy_policy(case_id, config_path)
    alo = policy.get("auto_learning_loop") or {}
    if not isinstance(alo, dict):
        return {}, []
    merged = alo.get(stage) or {}
    if not isinstance(merged, dict):
        return {}, []
    applied: list[str] = []
    mapping = [
        ("target_value", "--target-value", "target_value", float),
        ("max_iter", "--max-iter", "max_iter", int),
        ("metric_file", "--metric-file", "metric_file", str),
        ("metric_key", "--metric-key", "metric_key", str),
        ("workflow_cmd", "--workflow-cmd", "workflow_cmd", str),
    ]
    out: dict[str, Any] = {}
    for yaml_key, cli_flag, out_key, caster in mapping:
        if yaml_key not in merged:
            continue
        if _argv_has_cli_flag(cli_flag):
            continue
        try:
            out[out_key] = caster(merged[yaml_key])
        except (TypeError, ValueError):
            continue
        applied.append(yaml_key)
    return out, applied


def _maybe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_business_threshold(
    case_id: str, stage: str, config_path: Optional[str] = None,
) -> Optional[float]:
    policy = load_merged_autonomy_policy(case_id, config_path)
    targets = policy.get("targets") or {}
    if not isinstance(targets, dict):
        targets = {}

    stage_candidates: dict[str, list[tuple[str, ...]]] = {
        "hydrology": [
            ("targets", "d1_nse"),
            ("self_improving_pipeline", "target_nse"),
        ],
        "hydraulics": [
            ("targets", "d2_nse"),
            ("hydraulic_precision_improvement", "calibrate_target_nse"),
            ("hydraulic_precision_improvement", "threshold"),
        ],
    }

    candidates = stage_candidates.get(stage, [])
    for path in candidates:
        current: Any = policy
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        threshold = _maybe_float(current)
        if threshold is not None:
            return threshold
    return None


def _read_metric_from_payload(metric_data: dict[str, Any], metric_key: str) -> Optional[float]:
    value: Any = metric_data
    for key in metric_key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return _maybe_float(value)


def _resolve_metric_source(metric_file: str, metric_key: str) -> tuple[Optional[float], Optional[str], str]:
    for candidate_path, candidate_key, source_label in _metric_source_candidates(metric_file, metric_key):
        if not candidate_path.exists():
            continue
        metric_data = load_json(candidate_path)
        metric_value = _read_metric_from_payload(metric_data, candidate_key)
        if metric_value is None:
            continue
        return metric_value, str(candidate_path), source_label
    return None, None, "missing"


def _read_metric_value(metric_file: str, metric_key: str) -> Optional[float]:
    metric_value, _, _ = _resolve_metric_source(metric_file, metric_key)
    return metric_value


def _sync_metric_contract(metric_file: str, contracts_dir: Path) -> Optional[Path]:
    """Keep legacy pipeline evaluation sync only for shared baseline summaries."""
    metric_path = Path(metric_file)
    if not metric_path.exists():
        return None
    if metric_path.resolve().parent == contracts_dir.resolve():
        return None
    if metric_path.name != "pipeline.run_summary.json":
        return None

    import shutil

    dest_file = contracts_dir / "pipeline_evaluation.latest.json"
    shutil.copy(metric_path, dest_file)
    return dest_file


def validate_target_threshold(
    case_id: str,
    stage: str,
    requested_target: float,
    metric_file: str,
    metric_key: str,
    config_path: Optional[str] = None,
) -> dict[str, Any]:
    business_threshold = _resolve_business_threshold(case_id, stage, config_path)
    current_metric, metric_source_path, metric_source_mode = _resolve_metric_source(metric_file, metric_key)
    validation = {
        "requested_target": float(requested_target),
        "business_threshold": business_threshold,
        "current_metric": current_metric,
        "metric_source_path": metric_source_path,
        "metric_source_mode": metric_source_mode,
        "status": "accepted",
        "reason": "",
    }
    if business_threshold is not None and float(requested_target) < float(business_threshold):
        validation["status"] = "rejected"
        validation["reason"] = (
            f"requested target_value {requested_target:.4f} is below "
            f"business threshold {business_threshold:.4f}"
        )
        if current_metric is not None and requested_target <= current_metric:
            validation["reason"] += (
                f"; current metric is {current_metric:.4f}, so this would create a pseudo-converged success"
            )
    return validation

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generic auto-learning loop.")
    parser.add_argument("--case-id", required=True, help="Case ID")
    parser.add_argument("--stage", default="hydrology", help="Stage (e.g., hydrology, hydraulics)")
    parser.add_argument("--workflow-cmd", default=DEFAULT_HYDROLOGY_WORKFLOW_CMD, help="Command to trigger recalculation")
    parser.add_argument("--metric-file", default=DEFAULT_HYDROLOGY_METRIC_FILE, help="Path to JSON file containing the metric")
    parser.add_argument("--metric-key", default=DEFAULT_HYDROLOGY_METRIC_KEY, help="Key in the JSON file for the metric")
    parser.add_argument("--target-value", type=float, default=0.85, help="Target value for the metric")
    parser.add_argument("--maximize", action="store_true", default=True, help="Set if the metric should be maximized (e.g., NSE)")
    parser.add_argument("--max-iter", type=int, default=10, help="Maximum iterations for optimization")
    return parser

def main():
    parser = _build_parser()
    parser.add_argument("--config", default=None, help="可选 case YAML，用于合并 autonomy_policy 块")
    args = parser.parse_args()

    yaml_over, yaml_applied_keys = _merge_auto_learning_from_config(
        args.case_id, args.stage, args.config,
    )
    if "target_value" in yaml_over:
        args.target_value = yaml_over["target_value"]
    if "max_iter" in yaml_over:
        args.max_iter = yaml_over["max_iter"]
    if "metric_file" in yaml_over:
        args.metric_file = yaml_over["metric_file"]
    if "metric_key" in yaml_over:
        args.metric_key = yaml_over["metric_key"]
    if "workflow_cmd" in yaml_over:
        args.workflow_cmd = yaml_over["workflow_cmd"]

    args.workflow_cmd = args.workflow_cmd.format(case_id=args.case_id)
    args.metric_file = args.metric_file.format(case_id=args.case_id)

    contracts_dir = WORKSPACE / "cases" / args.case_id / "contracts"
    candidate_set_path = contracts_dir / "candidate_set.latest.json"
    inventory_path = contracts_dir / "parameter_inventory.latest.json"
    activation_path = contracts_dir / "correction_activation_record.latest.json"
    report_path = contracts_dir / f"{args.stage}_auto_learning_report.json"
    threshold_validation = validate_target_threshold(
        args.case_id,
        args.stage,
        float(args.target_value),
        args.metric_file,
        args.metric_key,
        args.config,
    )

    if threshold_validation["status"] != "accepted":
        report_data = {
            "case_id": args.case_id,
            "stage": args.stage,
            "target_metric": args.metric_key,
            "target_value": float(
                threshold_validation["business_threshold"]
                if threshold_validation.get("business_threshold") is not None
                else args.target_value
            ),
            "best_parameters": {},
            "best_gap": None,
            "success": False,
            "message": threshold_validation["reason"],
            "threshold_validation": threshold_validation,
            "config_merge": {
                "source": governance_source_relpath(),
                "applied_yaml_keys": yaml_applied_keys,
                "stage": args.stage,
            },
        }
        write_json(report_path, report_data)
        print(f"Rejected auto-learning target. Report saved to {report_path}")
        raise SystemExit(2)

    candidate_set = load_json(candidate_set_path)
    inventory = load_json(inventory_path)
    activation = load_json(activation_path)

    stage_candidates = candidate_set.get("stages", {}).get(args.stage, {}).get("primary_candidates", [])
    if not stage_candidates:
        print(f"No primary candidates found for stage {args.stage}")
        return

    # Get bounds for candidates
    bounds = []
    param_names = []
    inventory_params = inventory.get("stages", {}).get(args.stage, [])
    
    for cand in stage_candidates:
        for p in inventory_params:
            if p["parameter_id"] == cand:
                bounds.append(tuple(p["bounds"]))
                param_names.append(cand)
                break

    if len(bounds) != len(stage_candidates):
        print("Mismatch between candidates and found bounds.")
        return

    def objective(x):
        # 1. Update activation record
        for name, val in zip(param_names, x):
            if args.stage not in activation:
                activation[args.stage] = {}
            activation[args.stage][name] = float(val)
        
        write_json(activation_path, activation)

        # 2. Trigger recalculation
        cmd = shlex.split(args.workflow_cmd)
        print(f"Triggering recalculation with parameters: {dict(zip(param_names, x))}")
        try:
            subprocess.run(cmd, check=True)

            synced_metric = _sync_metric_contract(args.metric_file, contracts_dir)
            if synced_metric is not None:
                print(f"Copied metric file to {synced_metric}")

        except subprocess.CalledProcessError as e:
            print(f"Workflow execution failed: {e}")
            return 1e6

        # 3. Read metric
        metric_val, metric_source_path, metric_source_mode = _resolve_metric_source(args.metric_file, args.metric_key)
        print(
            "DEBUG: "
            f"metric_file={args.metric_file}, metric_key={args.metric_key}, "
            f"metric_source_path={metric_source_path}, metric_source_mode={metric_source_mode}"
        )

        if metric_val is None:
            print(f"Warning: metric key {args.metric_key} not found in resolved metric sources. Returning penalty.")
            return 1e6

        # 4. Calculate gap
        if args.maximize:
            gap = args.target_value - metric_val
            # if we exceeded target, gap is negative, which is better
        else:
            gap = metric_val - args.target_value
            
        print(f"Evaluated metric: {metric_val}, Gap: {gap}")
        return gap

    print(f"Starting optimization for {args.stage} with parameters: {param_names}")
    result = differential_evolution(
        objective, 
        bounds, 
        maxiter=args.max_iter,
        popsize=5,
        disp=True
    )

    print("\nOptimization completed.")
    print(f"Best parameters: {dict(zip(param_names, result.x))}")
    print(f"Best metric gap: {result.fun}")

    # Save best parameters
    best_params_dict = {}
    for name, val in zip(param_names, result.x):
        best_params_dict[name] = float(val)
        activation[args.stage][name] = float(val)
    write_json(activation_path, activation)
    
    # Generate report
    report_data = {
        "case_id": args.case_id,
        "stage": args.stage,
        "target_metric": args.metric_key,
        "target_value": float(args.target_value),
        "best_parameters": best_params_dict,
        "best_gap": float(result.fun),
        "success": bool(result.fun <= 0),
        "message": str(result.message),
        "metric_source_path": threshold_validation.get("metric_source_path"),
        "metric_source_mode": threshold_validation.get("metric_source_mode"),
        "threshold_validation": threshold_validation,
        "config_merge": {
            "source": governance_source_relpath(),
            "applied_yaml_keys": yaml_applied_keys,
            "stage": args.stage,
        },
    }
    write_json(report_path, report_data)
    print(f"Auto-learning report saved to {report_path}")

if __name__ == "__main__":
    main()
