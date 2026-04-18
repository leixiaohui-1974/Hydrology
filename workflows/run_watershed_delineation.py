"""识地 (ShiDi) — 地形分析与DEM处理

HydroMind 水智工坊 · Agent #3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import RESULTS_DIR, abs_path, load_json, resolve_workspace_relpath, run_python


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic watershed delineation workflow entrypoint.")
    parser.add_argument("--case-id", required=True, help="Case identifier")
    parser.add_argument("--data-pack-json", required=True, help="Data pack JSON from build_data_pack.py")
    parser.add_argument("--parameter-governance-json", required=True, help="Parameter governance envelope JSON")
    parser.add_argument("--run-id", default=None, help="Override workflow run id")
    parser.add_argument("--engine", choices=["whiteboxtools", "pysheds-reference"], default="whiteboxtools")
    parser.add_argument("--metadata-out", default=None, help="WorkflowRun output path")
    parser.add_argument("--result-out", default=None, help="Delineation result JSON path")
    parser.add_argument("--no-subtract-upstream", action="store_true", help="Disable upstream subtraction")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.engine != "whiteboxtools":
        raise ValueError("Only --engine whiteboxtools is allowed for the mainline workflow entrypoint")

    data_pack_path = abs_path(args.data_pack_json, label="--data-pack-json")
    governance_path = abs_path(args.parameter_governance_json, label="--parameter-governance-json")
    data_pack = load_json(data_pack_path)
    governance = load_json(governance_path)
    
    if not isinstance(governance, dict):
        raise ValueError("parameter governance json is invalid")
    
    status = governance.get("status")
    metadata_status = governance.get("metadata", {}).get("status")
    if status == "unauthorized" or metadata_status == "unauthorized":
        raise ValueError("parameter governance json is unauthorized")
        
    if "artifact_paths" not in governance:
        raise ValueError("parameter governance json is invalid")

    source_bundle_json = data_pack.get("source_bundle_json")
    outlets_json = data_pack.get("outlets_json")
    basin_validation_json = (data_pack.get("review_gates") or {}).get("basin_validation_json")

    if not source_bundle_json or not outlets_json:
        raise ValueError("data pack must contain source_bundle_json and outlets_json")

    module_path = Path(__file__).resolve().parents[1] / "examples" / "run_workflow_baseline.py"
    result_out = Path(args.result_out).resolve() if args.result_out else RESULTS_DIR / f"{args.case_id}.watershed_delineation.json"
    metadata_out = (
        Path(args.metadata_out).resolve()
        if args.metadata_out
        else RESULTS_DIR / f"{args.case_id}.watershed_delineation.workflow_run.json"
    )
    stream_threshold = data_pack.get("delineation_params", {}).get("stream_threshold", "100.0")
    snap_distance = data_pack.get("delineation_params", {}).get("snap_distance", "250.0")
    target_resolution_m = data_pack.get("delineation_params", {}).get("target_resolution_m")
    activation_record_path = (governance.get("artifact_paths") or {}).get("correction_activation_record")
    if activation_record_path:
        activation_record = load_json(abs_path(activation_record_path, label="correction_activation_record"))
        watershed_activation = activation_record.get("watershed_delineation", {})
        stream_threshold = watershed_activation.get("stream_threshold", stream_threshold)
        snap_distance = watershed_activation.get("snap_distance", snap_distance)
        if "target_resolution_m" in watershed_activation:
            target_resolution_m = watershed_activation["target_resolution_m"]
    cli_args = [
        "--workflow",
        "watershed_delineation",
        "--case-id",
        args.case_id,
        "--delineation-engine",
        "whiteboxtools",
        "--source-bundle-json",
        str(resolve_workspace_relpath(source_bundle_json)),
        "--outlets-json",
        str(resolve_workspace_relpath(outlets_json)),
    ]
    if basin_validation_json:
        cli_args.extend([
            "--basin-validation-json",
            str(resolve_workspace_relpath(basin_validation_json))
        ])
    
    cli_args.extend([
        "--delineation-out",
        str(result_out),
        "--metadata-out",
        str(metadata_out),
        "--stream-threshold",
        str(stream_threshold),
        "--snap-distance",
        str(snap_distance),
    ])
    if target_resolution_m:
        cli_args.extend(["--target-resolution", str(target_resolution_m)])
    if args.run_id:
        cli_args.extend(["--run-id", args.run_id])
    if args.no_subtract_upstream:
        cli_args.append("--no-subtract-upstream")

    run_python(module_path, cli_args)


if __name__ == "__main__":
    main()
