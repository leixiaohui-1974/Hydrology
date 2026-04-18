import argparse
import json
from pathlib import Path
from typing import Any

def evaluate_gain(results: dict[str, Any], baseline_method: str = "EKF", min_nse: float = 0.8, min_rmse_improvement: float = 0.0) -> dict[str, Any]:
    """
    Quantify accuracy improvements of EnKF/UKF over a baseline.
    Enforce minimum NSE and RMSE improvement targets.
    """
    targets = results.get("results", {})
    gains = {}
    summary_gains = {}
    
    # Track if any method meets the criteria across the entire evaluation
    meets_standards = False
    
    for target, stations in targets.items():
        gains[target] = {}
        target_reductions = {}
        for station_name, station_data in stations.items():
            if station_name == "_best":
                continue
            
            station_gains = {}
            baseline_rmse = None
            if baseline_method in station_data and isinstance(station_data[baseline_method], dict) and station_data[baseline_method].get("status") == "completed":
                baseline_rmse = station_data[baseline_method].get("rmse")
                
            for method, metrics in station_data.items():
                if method == "_best" or not isinstance(metrics, dict) or metrics.get("status") != "completed":
                    continue
                
                rmse = metrics.get("rmse")
                nse = metrics.get("nse")
                if rmse is not None and baseline_rmse is not None and baseline_rmse > 0:
                    gain_pct = ((baseline_rmse - rmse) / baseline_rmse) * 100.0
                else:
                    gain_pct = None
                    
                station_gains[method] = {
                    "rmse": rmse,
                    "rmse_reduction_pct": round(gain_pct, 2) if gain_pct is not None else None,
                    "nse": nse
                }
                
                # Check standards
                is_nse_valid = nse is not None and nse >= min_nse
                is_rmse_valid = gain_pct is not None and gain_pct >= min_rmse_improvement
                if is_nse_valid and is_rmse_valid:
                    meets_standards = True
                
                if gain_pct is not None:
                    if method not in target_reductions:
                        target_reductions[method] = []
                    target_reductions[method].append(gain_pct)
                    
            gains[target][station_name] = station_gains
            
        summary_gains[target] = {
            method: round(sum(pcts) / len(pcts), 2) if pcts else None
            for method, pcts in target_reductions.items()
        }
            
    if not meets_standards:
        raise ValueError(
            f"Blocking Exception: Assimilation gain failed to meet standards. "
            f"Required minimum NSE >= {min_nse} and RMSE improvement >= {min_rmse_improvement}%. "
            f"Poor models are prevented from reaching the MPC control stage."
        )

    return gains, summary_gains

def main():
    parser = argparse.ArgumentParser(description="Evaluate Assimilation Gain for EnKF/UKF")
    parser.add_argument("--case-id", required=True, help="Case ID to evaluate")
    parser.add_argument("--baseline", default="EKF", help="Baseline method for comparison")
    parser.add_argument("--output", help="Optional output JSON path")
    parser.add_argument("--min-nse", type=float, default=0.8, help="Minimum acceptable NSE score")
    parser.add_argument("--min-rmse-improvement", type=float, default=0.0, help="Minimum acceptable RMSE improvement percentage")
    args = parser.parse_args()

    contract_dir = Path(f"cases/{args.case_id}/contracts")
    da_path = contract_dir / "data_assimilation.latest.json"
    
    if not da_path.exists():
        print(f"Error: {da_path} not found.")
        return
        
    with open(da_path, "r", encoding="utf-8") as f:
        results = json.load(f)
        
    try:
        gains, summary_gains = evaluate_gain(
            results, 
            baseline_method=args.baseline,
            min_nse=args.min_nse,
            min_rmse_improvement=args.min_rmse_improvement
        )
    except ValueError as e:
        print(str(e))
        import sys
        sys.exit(1)
    
    summary = {
        "case_id": args.case_id,
        "baseline_method": args.baseline,
        "average_rmse_reduction_pct": summary_gains,
        "assimilation_gains": gains
    }
    
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"Gains evaluated and saved to {args.output}")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
