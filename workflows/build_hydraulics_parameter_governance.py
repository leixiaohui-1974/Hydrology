from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import WORKSPACE, abs_path, load_json, write_json


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build hydraulics governance gate artifact for a case.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--parameter-governance-json")
    parser.add_argument("--hydraulic-calibration-json")
    parser.add_argument("--output-json")
    return parser


def _default_contract_path(case_id: str, name: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts" / name


def _rel_or_abs(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(WORKSPACE))
    except ValueError:
        return str(path)


def main() -> None:
    args = _build_parser().parse_args()

    governance_path = abs_path(
        args.parameter_governance_json or _default_contract_path(args.case_id, "parameter_governance.latest.json"),
        label="parameter governance json",
    )
    calibration_path = abs_path(
        args.hydraulic_calibration_json or _default_contract_path(args.case_id, "hydraulic_calibration.latest.json"),
        label="hydraulic calibration json",
    )
    output_path = abs_path(
        args.output_json or _default_contract_path(args.case_id, "hydraulics_parameter_governance.latest.json"),
        label="output json",
        required=False,
    )

    governance = load_json(governance_path)
    calibration = load_json(calibration_path)

    activation_path = (
        governance.get("artifact_paths", {}).get("correction_activation_record")
        if isinstance(governance, dict)
        else None
    )
    activation = {}
    resolved_activation_path = None
    if activation_path:
        resolved_activation_path = abs_path(activation_path, label="correction activation record", required=False)
        if resolved_activation_path and resolved_activation_path.exists():
            activation = load_json(resolved_activation_path)

    hydraulics_activation = activation.get("hydraulics", {}) if isinstance(activation, dict) else {}
    required_keys = {
        "manning_n_scale",
        "boundary_inflow_bias",
        "section_geometry_scale",
        "section_substitute_mode",
    }
    activation_keys = set(hydraulics_activation.keys()) if isinstance(hydraulics_activation, dict) else set()

    station_results = calibration.get("station_results", {}) if isinstance(calibration, dict) else {}
    validation_count = sum(1 for row in station_results.values() if isinstance(row, dict) and isinstance(row.get("validation"), dict))
    stations_total = len(station_results) if isinstance(station_results, dict) else 0

    checks = [
        {
          "key": "parameter_governance",
          "label": "共享治理合同存在",
          "status": "pass" if isinstance(governance, dict) and bool(governance) else "fail",
          "detail": _rel_or_abs(governance_path) if governance_path.exists() else "missing",
        },
        {
          "key": "hydraulics_activation",
          "label": "hydraulics activation 完整",
          "status": "pass" if required_keys.issubset(activation_keys) else "fail",
          "detail": f"keys={sorted(activation_keys)}",
        },
        {
          "key": "hydraulic_calibration",
          "label": "hydraulic calibration 合同存在",
          "status": "pass" if stations_total > 0 else "fail",
          "detail": f"stations={stations_total}",
        },
        {
          "key": "validation_metrics",
          "label": "validation 指标可用",
          "status": "pass" if validation_count > 0 else "fail",
          "detail": f"validation_stations={validation_count}",
        },
    ]

    gate_ok = all(item["status"] == "pass" for item in checks)
    payload = {
        "schema": "hydraulics.parameter_governance.gate",
        "version": 1,
        "case_id": args.case_id,
        "gate_key": "hydraulics",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "gate_status": "pass" if gate_ok else "fail",
        "quality_gate_passed": gate_ok,
        "status": "ready" if gate_ok else "blocked",
        "checks": checks,
        "summary": {
            "stations_total": stations_total,
            "validation_stations": validation_count,
            "activation_keys": sorted(activation_keys),
        },
        "artifacts": {
            "parameter_governance_json": _rel_or_abs(governance_path),
            "correction_activation_record": _rel_or_abs(resolved_activation_path),
            "hydraulic_calibration_json": _rel_or_abs(calibration_path),
        },
        "_auto_generated": True,
    }
    write_json(output_path, payload)
    print(str(output_path))


if __name__ == "__main__":
    main()
