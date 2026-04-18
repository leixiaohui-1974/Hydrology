#!/usr/bin/env python3
"""识地 (ShiDi) — 地形分析与DEM处理

HydroMind 水智工坊 · Agent #3

Deterministic end-to-end pipeline: source discovery → data pack → watershed delineation.

This script chains three confirmed-deterministic steps:
1. Source discovery product pipeline (knowledge mining + reliability scoring)
2. Data pack construction (DEM + outlet compatibility validation)
3. WhiteboxTools watershed delineation (BreachDepressionsLeastCost + snap + Watershed)

All operations are deterministic — same inputs always produce same outputs.
AI/LLM is NOT invoked anywhere in this script.

Usage:
    python3 run_source_to_delineation.py --case-id zhongxian
    python3 run_source_to_delineation.py --case-id zhongxian --snap-distance 5000 --stream-threshold 100
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_source_bundle(workspace: Path, case_id: str) -> Path:
    """查找 source_bundle 路径。不硬编码项目名。"""
    candidates = [
        workspace / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id / "contracts" / "source_bundle.contract.json",
        workspace / "cases" / case_id / "contracts" / "source_bundle.contract.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # fallback


def _resolve_case_paths(case_id: str) -> dict[str, Path]:
    """Resolve all canonical paths for a case. Deterministic path resolution."""
    case_dir = WORKSPACE / "cases" / case_id
    return {
        "case_dir": case_dir,
        "contracts_dir": case_dir / "contracts",
        "pipeline_script": case_dir / "source_selection" / "product" / "pipeline.py",
        "product_outputs": case_dir / "source_selection" / "product_outputs",
        "case_manifest": case_dir / "contracts" / "case_manifest.json",
        "source_bundle": (
            _find_source_bundle(WORKSPACE, case_id)
        ),
    }


# ── Step 1: Source Discovery ─────────────────────────────────────────────────

def run_source_discovery(paths: dict[str, Path]) -> dict[str, Any]:
    """Run the knowledge mining pipeline. Deterministic: scans files, scores, normalizes."""
    pipeline = paths["pipeline_script"]
    if not pipeline.exists():
        raise FileNotFoundError(f"Source discovery pipeline not found: {pipeline}")

    result = subprocess.run(
        [sys.executable, str(pipeline), "run-all"],
        capture_output=True, text=True, cwd=str(pipeline.parent),
    )
    if result.returncode != 0:
        raise RuntimeError(f"Source discovery failed:\n{result.stderr}")

    payload = json.loads(result.stdout)

    # Verify outputs exist
    ready_path = paths["product_outputs"] / "outlets.delineation_ready.json"
    if not ready_path.exists():
        raise FileNotFoundError(f"Expected output not found: {ready_path}")

    ready = _load_json(ready_path)
    return {
        "stage": "source_discovery",
        "status": "completed",
        "total_outlets": len(payload.get("outlets", {}).get("outlets", [])),
        "delineation_ready": ready["count"],
        "excluded": payload.get("delineation_ready", {}).get("excluded_stations", []),
        "outputs": {
            "delineation_ready_json": str(ready_path),
            "control_station_mapping": str(paths["product_outputs"] / "control_station_mapping.json"),
            "source_reliability": str(paths["product_outputs"] / "source_reliability.json"),
            "coordinate_validation": str(paths["product_outputs"] / "coordinate_validation.json"),
        },
    }


# ── Step 2: Data Pack Build ──────────────────────────────────────────────────

def run_data_pack_build(paths: dict[str, Path]) -> dict[str, Any]:
    """Build data pack: validate DEM + outlet compatibility. Deterministic."""
    outlets_json = paths["product_outputs"] / "outlets.delineation_ready.json"
    output_path = paths["contracts_dir"] / "data_pack.latest.json"

    build_script = BASE_DIR / "workflows" / "build_data_pack.py"
    result = subprocess.run(
        [
            sys.executable, str(build_script),
            "--case-manifest", str(paths["case_manifest"]),
            "--source-bundle-json", str(paths["source_bundle"]),
            "--outlets-json", str(outlets_json),
        "--simulation-config", str(paths["simulation_config"]),
        "--output", str(output_path),
    ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Data pack build failed:\n{result.stderr}")

    pack = _load_json(output_path)
    validation = pack.get("summary", {}).get("dem_outlet_validation", {})
    return {
        "stage": "data_pack_build",
        "status": "completed",
        "all_outlets_within_dem": validation.get("all_outlets_within_dem"),
        "outlet_count": validation.get("outlet_count"),
        "outside_outlets": validation.get("outside_outlets", []),
        "outputs": {"data_pack_json": str(output_path)},
    }


# ── Step 3: Watershed Delineation ────────────────────────────────────────────

def run_watershed_delineation(
    paths: dict[str, Path],
    *,
    snap_distance: float = 5000.0,
    stream_threshold: float = 100.0,
) -> dict[str, Any]:
    """Run WhiteboxTools delineation. Deterministic: same DEM + outlets = same basins."""
    from hydro_model.whitebox_delineation import run_whitebox_watershed_delineation

    outlets_json = paths["product_outputs"] / "outlets.delineation_ready.json"
    outlets_data = _load_json(outlets_json)
    outlets = [{"name": o["name"], "lat": o["lat"], "lon": o["lon"]} for o in outlets_data["outlets"]]

    # Resolve DEM from source bundle
    source_bundle = _load_json(paths["source_bundle"])
    dem_path = None
    for role in ("dem_primary", "dem_cropped_tif", "dem_fallback"):
        for rec in source_bundle.get("records", []):
            if rec.get("role") == role:
                p = Path(rec.get("artifact", {}).get("path", ""))
                if p.exists():
                    dem_path = str(p)
                    break
        if dem_path:
            break
    if not dem_path:
        raise FileNotFoundError("No DEM found in source bundle")

    result = run_whitebox_watershed_delineation(
        dem_path=dem_path,
        outlets=outlets,
        subtract_upstream=True,
        stream_threshold=stream_threshold,
        snap_distance=snap_distance,
    )

    output_path = paths["contracts_dir"] / "watershed_delineation_result.latest.json"
    _write_json(output_path, result)

    return {
        "stage": "watershed_delineation",
        "status": "completed",
        "total_area_km2": result["total_area_km2"],
        "basin_count": len(result["basins"]),
        "basins": [
            {"name": b["name"], "area_km2": round(b["area_km2"], 1)}
            for b in sorted(result["basins"], key=lambda x: -x["area_km2"])
        ],
        "params": {
            "snap_distance": snap_distance,
            "stream_threshold": stream_threshold,
            "engine": "whiteboxtools_mainline",
            "depression_method": "BreachDepressionsLeastCost",
        },
        "outputs": {"delineation_result_json": str(output_path)},
    }


# ── Orchestrator ─────────────────────────────────────────────────────────────

def run_full_pipeline(
    case_id: str,
    snap_distance: float = 5000.0,
    stream_threshold: float = 100.0,
) -> dict[str, Any]:
    """Run the complete deterministic pipeline end-to-end."""
    started_at = datetime.utcnow().isoformat(timespec="seconds")
    paths = _resolve_case_paths(case_id)

    report: dict[str, Any] = {
        "case_id": case_id,
        "pipeline": "source_to_delineation",
        "started_at": started_at,
        "steps": [],
    }

    # Step 1
    step1 = run_source_discovery(paths)
    report["steps"].append(step1)
    print(f"[1/3] Source discovery: {step1['delineation_ready']} ready outlets, excluded {step1['excluded']}")

    # Step 2
    step2 = run_data_pack_build(paths)
    report["steps"].append(step2)
    ok = "PASS" if step2["all_outlets_within_dem"] else "FAIL"
    print(f"[2/3] Data pack: {step2['outlet_count']} outlets, DEM check={ok}")

    if not step2["all_outlets_within_dem"]:
        report["status"] = "failed"
        report["failure_reason"] = f"Outlets outside DEM: {step2['outside_outlets']}"
        return report

    # Step 3
    step3 = run_watershed_delineation(paths, snap_distance=snap_distance, stream_threshold=stream_threshold)
    report["steps"].append(step3)
    print(f"[3/3] Delineation: {step3['total_area_km2']:.0f} km², {step3['basin_count']} basins")

    report["status"] = "completed"
    report["completed_at"] = datetime.utcnow().isoformat(timespec="seconds")
    report["summary"] = {
        "total_area_km2": step3["total_area_km2"],
        "basins": step3["basins"],
    }

    # Save pipeline report
    report_path = paths["contracts_dir"] / "pipeline_report.latest.json"
    _write_json(report_path, report)
    print(f"\nPipeline report: {report_path}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic end-to-end: source discovery → data pack → watershed delineation"
    )
    parser.add_argument("--case-id", required=True, help="Case identifier (e.g. zhongxian)")
    parser.add_argument("--snap-distance", type=float, default=5000.0, help="Snap distance in meters")
    parser.add_argument("--stream-threshold", type=float, default=100.0, help="Stream extraction threshold")
    args = parser.parse_args()

    report = run_full_pipeline(
        case_id=args.case_id,
        snap_distance=args.snap_distance,
        stream_threshold=args.stream_threshold,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
