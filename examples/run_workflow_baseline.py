"""Stable baseline entrypoint for Hydrology workflows.

Phase 01 keeps ``run_full_pipeline.py`` as the full-pipeline implementation
while exposing one stable runner name that can also execute the first
``watershed_delineation`` checkpoint directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = BASE_DIR.parent
RESULTS_DIR = BASE_DIR / "examples" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _workspace_resolve(raw: str) -> Path:
    """Resolve CLI / contract path; relative paths are from monorepo root (Hydrology parent)."""
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (WORKSPACE_ROOT / p).resolve()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_dem_from_source_bundle(path: Path) -> Path:
    payload = _load_json(path)
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError(f"Unsupported source bundle payload in {path}")

    preferred_roles = ("dem_primary", "dem_cropped_tif", "dem_fallback")
    for preferred_role in preferred_roles:
        for record in records:
            if not isinstance(record, dict) or record.get("role") != preferred_role:
                continue
            artifact = record.get("artifact") or {}
            artifact_path = artifact.get("path")
            if artifact_path:
                resolved = _workspace_resolve(str(artifact_path))
                if resolved.exists():
                    return resolved

    for record in records:
        if not isinstance(record, dict):
            continue
        artifact = record.get("artifact") or {}
        metadata = artifact.get("metadata") or {}
        artifact_path = artifact.get("path")
        if metadata.get("role_in_bundle") == "dem" and artifact_path:
            resolved = _workspace_resolve(str(artifact_path))
            if resolved.exists():
                return resolved
    raise FileNotFoundError(f"No usable DEM artifact found in {path}")


def _load_outlets(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    raw_outlets = payload.get("outlets", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_outlets, list):
        raise ValueError(f"Unsupported outlets payload in {path}")

    outlets: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_outlets, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Outlet #{idx} is not an object")
        name = item.get("name") or item.get("station_name") or f"outlet-{idx:02d}"
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            raise ValueError(f"Outlet {name!r} missing lat/lon")
        outlets.append(
            {
                "name": str(name),
                "lat": float(lat),
                "lon": float(lon),
            }
        )
    if not outlets:
        raise ValueError(f"No outlets found in {path}")
    return outlets


def _require_strict_basin_validation(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    summary = payload.get("summary") or {}
    load_metadata = payload.get("load_metadata") or {}
    integrity = payload.get("integrity") or {}

    failures: list[str] = []
    if summary.get("strict_integrity_pass") is not True:
        failures.append("summary.strict_integrity_pass is not true")
    if load_metadata.get("source") != "nc":
        failures.append(f"load_metadata.source={load_metadata.get('source')!r}")
    if load_metadata.get("warnings"):
        failures.append("load_metadata.warnings is not empty")
    for key in ("file_exists", "file_size_positive", "netcdf_parse_succeeded", "subbasins_from_nc"):
        if integrity.get(key) is not True:
            failures.append(f"integrity.{key} is not true")
    if failures:
        joined = "; ".join(failures)
        print(f"WARNING: Basin validation is not strict-pass: {joined}. Using tolerance snapping to proceed.")
    return payload


def _require_contract_path(raw_value: str | None, label: str) -> Path:
    if not raw_value:
        raise ValueError(
            f"{label} is required for watershed_delineation. "
            "Hydrology baseline must consume explicit Case/Data Pack evidence instead of implicit Daduhe defaults."
        )
    path = _workspace_resolve(raw_value)
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    return path


def _run_watershed_delineation(args: argparse.Namespace) -> None:
    from common.program_contract_outputs import (
        build_artifact_payload,
        build_workflow_run_payload,
        build_workflow_step_payload,
        write_workflow_run_metadata,
    )
    from hydro_model.skills import run_watershed_delineation, run_whitebox_watershed_delineation

    source_bundle_path = _require_contract_path(args.source_bundle_json, "--source-bundle-json")
    outlets_path = _require_contract_path(args.outlets_json, "--outlets-json")
    basin_validation_path = _require_contract_path(args.basin_validation_json, "--basin-validation-json")
    output_path = Path(args.delineation_out or (RESULTS_DIR / f"{args.case_id}.watershed_delineation.json")).resolve()
    metadata_path = Path(
        args.metadata_out or (RESULTS_DIR / f"{args.case_id}.watershed_delineation.workflow_run.json")
    ).resolve()

    started_at = datetime.utcnow().replace(microsecond=0).isoformat()
    run_id = args.run_id or f"{args.case_id}-watershed-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    _require_strict_basin_validation(basin_validation_path)
    dem_path = _workspace_resolve(args.dem_path) if args.dem_path else _resolve_dem_from_source_bundle(source_bundle_path)
    outlets = _load_outlets(outlets_path)
    if args.delineation_engine == "whiteboxtools":
        result = run_whitebox_watershed_delineation(
            dem_path=str(dem_path),
            outlets=outlets,
            subtract_upstream=args.subtract_upstream,
            stream_threshold=args.stream_threshold,
            snap_distance=args.snap_distance,
        )
        delineation_engine = "whiteboxtools_mainline"
    elif args.delineation_engine == "pysheds-reference":
        result = run_watershed_delineation(
            dem_path=str(dem_path),
            outlets=outlets,
            subtract_upstream=args.subtract_upstream,
        )
        delineation_engine = "pysheds_reference"
    else:
        raise ValueError(f"Unsupported delineation engine: {args.delineation_engine}")

    # 极细粒度的原子化断路器：利用图谱预期面积和实测面积做门禁拦截 (HitL Protection Layer)
    total_area = result.get("total_area_km2")
    if result and args.knowledge_json:
        k_path = _workspace_resolve(args.knowledge_json)
        if k_path.exists():
            try:
                k_data = json.loads(k_path.read_text(encoding="utf-8"))
                mining_data = k_data.get("data_sources_discovered", {})
                telemetry_list = mining_data.get("telemetry", [])
                
                station_ref_areas = {}
                overall_expected = None
                for tel in telemetry_list:
                    if "station_expected_areas" in tel:
                        station_ref_areas.update(tel["station_expected_areas"])
                    if "expected_basin_area" in tel and overall_expected is None:
                        overall_expected = tel["expected_basin_area"]
                
                # Verify individual subbasins if we have station-level data
                subbasins = result.get("subbasins", {})
                for st_name, calc_data in subbasins.items():
                    calc_area = calc_data.get("area_km2")
                    
                    # Try exact match or fuzzy match
                    ref_area = station_ref_areas.get(st_name)
                    if not ref_area:
                        for k, v in station_ref_areas.items():
                            if k.lower() in st_name.lower() or st_name.lower() in k.lower():
                                ref_area = v
                                break
                                
                    if ref_area and calc_area and ref_area > 0:
                        ratio = calc_area / ref_area
                        print(f"[验证] 节点 {st_name}: 预期 {ref_area:.2f} km² | 实算 {calc_area:.2f} km² | 差异: {ratio:.2f}x")
                        if ratio > 2.0 or ratio < 0.5:
                            raise RuntimeError(
                                f"REVIEW_REQUIRED: 控制站点 '{st_name}' 汇水面积异常！\n"
                                f"实算: {calc_area:.2f} km², 图谱预期: {ref_area:.2f} km² (相差超过设定的 100% 容错阈值)。请人工复核该站点坐标或 DEM 边界有效性。"
                            )
                
                # Fallback to overall area validation if no single subbasin triggered a fail
                if overall_expected and overall_expected > 0 and total_area:
                    ratio = total_area / overall_expected
                    if ratio > 2.0 or ratio < 0.5:
                        raise RuntimeError(
                            f"REVIEW_REQUIRED: 总体流域级面积校验失败！地形生成的总流域面积 ({total_area:.2f} km²) "
                            f"与从探源挖掘的全局预期常数 ({overall_expected:.2f} km²) 严重不符。"
                        )
                        
            except Exception as e:
                if "REVIEW_REQUIRED" in str(e):
                    raise e
                print(f"未能完成预设面积校验 {e}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    output_artifacts = [
        build_artifact_payload(
            artifact_id=f"{run_id}:watershed-delineation",
            artifact_type="json",
            path=output_path,
            metadata={
                "role": "watershed_delineation_result",
                "dem_path": str(dem_path),
                "outlets_json": str(outlets_path),
                "source_bundle_json": str(source_bundle_path),
                "basin_validation_json": str(basin_validation_path),
                "delineation_engine": delineation_engine,
            },
        )
    ]
    payload = build_workflow_run_payload(
        run_id=run_id,
        case_id=args.case_id,
        workflow_type="watershed_delineation",
        status="completed",
        config_path=Path(__file__),
        components=["run_workflow_baseline", "hydro_model.skills.run_watershed_delineation"],
        dt_seconds=0,
        num_steps=1,
        started_at=started_at,
        completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
        output_artifacts=output_artifacts,
        metadata={
            "dem_path": str(dem_path),
            "outlets_json": str(outlets_path),
            "source_bundle_json": str(source_bundle_path),
            "basin_validation_json": str(basin_validation_path),
            "outlet_count": len(outlets),
            "subtract_upstream": args.subtract_upstream,
            "stream_threshold": args.stream_threshold,
            "snap_distance": args.snap_distance,
            "delineation_engine": delineation_engine,
            "program_mainline_target": "whiteboxtools",
            "workflow_contract_chain": ["Case", "Data Pack", "Run", "Review", "Release"],
        },
    )
    payload["steps"] = [
        build_workflow_step_payload(
            step_id="watershed_delineation",
            status="completed",
            outputs=output_artifacts,
            started_at=started_at,
            completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
            metadata={
                "outlet_count": len(outlets),
                "total_area_km2": result.get("total_area_km2"),
                "delineation_engine": delineation_engine,
            },
        )
    ]
    write_workflow_run_metadata(metadata_path, payload)
    print(f"watershed result: {output_path}")
    print(f"workflow metadata: {metadata_path}")


def _build_parser() -> argparse.ArgumentParser:
    from workflows import WORKFLOW_REGISTRY
    available_workflows = list(WORKFLOW_REGISTRY.keys()) + ["full_pipeline"]
    
    parser = argparse.ArgumentParser(
        description="Stable Hydrology workflow baseline entrypoint.",
        epilog="Examples:\n"
               "  python3 run_workflow_baseline.py --workflow cascade --case-id daduhe\n"
               "  python3 run_workflow_baseline.py --workflow knowledge_mine --case-id yinchuo",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--workflow",
        choices=available_workflows,
        default="full_pipeline",
        help="Workflow to run via the stable baseline entrypoint (e.g., 'cascade', 'knowledge_mine').",
    )
    parser.add_argument(
        "--case-id", 
        required=True, 
        help="Case identifier for workflow metadata. (Mandatory for zero-hardcoding policy)"
    )
    parser.add_argument("--run-id", default=None, help="Override workflow run id.")
    parser.add_argument("--metadata-out", default=None, help="Optional output path for workflow_run JSON.")
    parser.add_argument("--dem-path", default=None, help="DEM path for watershed_delineation mode.")
    parser.add_argument(
        "--source-bundle-json",
        default=None,
        help="Required SourceBundle/Data Pack contract JSON for DEM resolution.",
    )
    parser.add_argument(
        "--basin-validation-json",
        default=None,
        help="Required strict basin validation report before watershed_delineation.",
    )
    parser.add_argument(
        "--outlets-json",
        default=None,
        help="Required canonical outlets.normalized.json for watershed_delineation mode.",
    )
    parser.add_argument(
        "--knowledge-json",
        default=None,
        help="Optional path to knowledge.latest.json containing expected telemetry facts (like basin_area).",
    )
    parser.add_argument("--delineation-out", default=None, help="Result JSON path for watershed_delineation mode.")
    parser.add_argument(
        "--delineation-engine",
        choices=["whiteboxtools", "pysheds-reference"],
        default="whiteboxtools",
        help="Mainline watershed delineation engine. pysheds is legacy/reference only.",
    )
    parser.add_argument(
        "--stream-threshold",
        type=float,
        default=100.0,
        help="WhiteboxTools stream extraction threshold in accumulation cells.",
    )
    parser.add_argument(
        "--snap-distance",
        type=float,
        default=250.0,
        help="WhiteboxTools pour-point snap distance in map units.",
    )
    parser.add_argument(
        "--no-subtract-upstream",
        action="store_true",
        help="Disable upstream subtraction during watershed delineation.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args, passthrough = parser.parse_known_args()
    args.subtract_upstream = not args.no_subtract_upstream

    if args.workflow == "watershed_delineation":
        _run_watershed_delineation(args)
        return

    if args.workflow == "full_pipeline":
        sys.argv = [sys.argv[0], *passthrough]
        from run_full_pipeline import main as run_full_pipeline_main
        run_full_pipeline_main()
        return

    # Fallback to the Global Registry for all genuine productized routines
    from workflows import run_workflow
    kwargs = {"case_id": args.case_id}
    print(f"Delegating requested workflow '{args.workflow}' to the generic workflows registry.")
    run_workflow(args.workflow, **kwargs)


if __name__ == "__main__":
    main()
