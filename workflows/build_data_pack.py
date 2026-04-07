from __future__ import annotations

import argparse
import sys
from pathlib import Path

import rasterio

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import WORKSPACE, abs_path, load_json, write_json


def _workspace_rel_path(path: Path) -> str:
    """Emit workspace-root-relative POSIX paths in pack JSON (productization)."""
    try:
        return path.resolve().relative_to(WORKSPACE.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _require_strict_basin_validation(path: Path) -> None:
    payload = load_json(path)
    summary = payload.get("summary") or {}
    load_metadata = payload.get("load_metadata") or {}
    integrity = payload.get("integrity") or {}

    failures = []
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
        raise ValueError(f"strict basin validation failed: {'; '.join(failures)}")


def _resolve_dem_from_source_bundle(payload: dict) -> Path:
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("source bundle records must be a list")

    preferred_roles = ("dem_primary", "dem_cropped_tif", "dem_fallback")
    for preferred_role in preferred_roles:
        for record in records:
            if not isinstance(record, dict) or record.get("role") != preferred_role:
                continue
            artifact = record.get("artifact") or {}
            artifact_path = artifact.get("path")
            if artifact_path:
                resolved = Path(artifact_path).resolve()
                if resolved.exists():
                    return resolved

    for record in records:
        if not isinstance(record, dict):
            continue
        artifact = record.get("artifact") or {}
        metadata = artifact.get("metadata") or {}
        artifact_path = artifact.get("path")
        if metadata.get("role_in_bundle") == "dem" and artifact_path:
            resolved = Path(artifact_path).resolve()
            if resolved.exists():
                return resolved
    raise FileNotFoundError("No usable DEM artifact found in source bundle")


def _load_outlets(payload: object) -> list[dict]:
    raw_outlets = payload.get("outlets", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_outlets, list):
        raise ValueError("outlets payload must be a list or object with `outlets`")
    outlets: list[dict] = []
    for idx, item in enumerate(raw_outlets, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"outlet #{idx} is not an object")
        outlets.append(
            {
                "name": str(item.get("name") or item.get("station_name") or f"outlet-{idx:02d}"),
                "lon": float(item["lon"]),
                "lat": float(item["lat"]),
            }
        )
    if not outlets:
        raise ValueError("outlets payload is empty")
    return outlets


def _validate_dem_outlet_compatibility(source_payload: dict, outlets_payload: object) -> dict[str, object]:
    dem = _resolve_dem_from_source_bundle(source_payload)
    outlets = _load_outlets(outlets_payload)
    with rasterio.open(dem) as ds:
        bounds = ds.bounds
        outside = [
            outlet["name"]
            for outlet in outlets
            if not (bounds.left <= outlet["lon"] <= bounds.right and bounds.bottom <= outlet["lat"] <= bounds.top)
        ]
    return {
        "dem_path": _workspace_rel_path(dem),
        "dem_bounds": [bounds.left, bounds.bottom, bounds.right, bounds.top],
        "outlet_count": len(outlets),
        "outside_outlets": outside,
        "all_outlets_within_dem": not outside,
    }


def _outlet_count_only(outlets_payload: object) -> int | None:
    if isinstance(outlets_payload, dict):
        raw = outlets_payload.get("outlets", outlets_payload)
    else:
        raw = outlets_payload
    if isinstance(raw, list):
        return len(raw)
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a deterministic Hydrology data-pack payload.")
    parser.add_argument("--case-manifest", required=True, help="Case manifest path")
    parser.add_argument("--source-bundle-json", required=True, help="SourceBundle contract JSON")
    parser.add_argument("--outlets-json", required=True, help="Canonical outlets JSON")
    parser.add_argument("--basin-validation-json", default=None, help="Optional strict basin validation report")
    parser.add_argument("--output", required=True, help="Output path for data_pack.contract.json")
    parser.add_argument("--strict", action="store_true", help="Fail when required review gates are missing")
    parser.add_argument(
        "--relax-dem-outlet-validation",
        action="store_true",
        help="Skip DEM/outlet extent check when source bundle has no usable DEM (rollout / e2e bundles); "
        "summary records dem_outlet_validation.skipped=true for audit.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    case_manifest = abs_path(args.case_manifest, label="--case-manifest")
    source_bundle = abs_path(args.source_bundle_json, label="--source-bundle-json")
    outlets = abs_path(args.outlets_json, label="--outlets-json")
    basin_validation = abs_path(args.basin_validation_json, label="--basin-validation-json", required=False)

    payload = {
        "kind": "data_pack",
        "schema_version": "0.1.0",
        "case_manifest": _workspace_rel_path(case_manifest),
        "source_bundle_json": _workspace_rel_path(source_bundle),
        "outlets_json": _workspace_rel_path(outlets),
        "review_gates": {
            "basin_validation_json": _workspace_rel_path(basin_validation) if basin_validation else None,
        },
        "strict": bool(args.strict),
    }

    if args.strict and basin_validation is None:
        raise ValueError("--strict requires --basin-validation-json")
    if args.strict and basin_validation is not None:
        _require_strict_basin_validation(basin_validation)

    source_payload = load_json(source_bundle)
    outlets_payload = load_json(outlets)
    if args.relax_dem_outlet_validation:
        n_rec = len(source_payload.get("records", [])) if isinstance(source_payload, dict) else None
        payload["summary"] = {
            "source_bundle_records": n_rec,
            "outlet_count": _outlet_count_only(outlets_payload),
            "dem_outlet_validation": {
                "skipped": True,
                "reason": "relax_dem_outlet_validation",
            },
            "_relax_dem_outlet_validation": True,
        }
    else:
        dem_outlet_validation = _validate_dem_outlet_compatibility(source_payload, outlets_payload)
        payload["summary"] = {
            "source_bundle_records": len(source_payload.get("records", [])) if isinstance(source_payload, dict) else None,
            "outlet_count": len(outlets_payload.get("outlets", outlets_payload))
            if isinstance(outlets_payload, (dict, list))
            else None,
            "dem_outlet_validation": dem_outlet_validation,
        }
        if args.strict and not dem_outlet_validation["all_outlets_within_dem"]:
            outside = ", ".join(str(name) for name in dem_outlet_validation["outside_outlets"])
            raise ValueError(f"strict DEM/outlet validation failed: outlets outside DEM extent: {outside}")

    out = Path(args.output).resolve()
    write_json(out, payload)
    print(f"data pack: {out}")


if __name__ == "__main__":
    main()
