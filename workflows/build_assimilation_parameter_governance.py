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
    parser = argparse.ArgumentParser(description="Build assimilation governance gate artifact for a case.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--parameter-governance-json")
    parser.add_argument("--candidate-set-json")
    parser.add_argument("--state-estimation-json")
    parser.add_argument("--hydraulic-assimilation-json")
    parser.add_argument("--coupled-assimilation-json")
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


def _optional_json(path: Path | None) -> tuple[dict, Path | None]:
    if not path or not path.exists():
        return {}, None
    return load_json(path), path


def main() -> None:
    args = _build_parser().parse_args()

    governance_path = abs_path(
        args.parameter_governance_json or _default_contract_path(args.case_id, "parameter_governance.latest.json"),
        label="parameter governance json",
    )
    candidate_set_path = abs_path(
        args.candidate_set_json or _default_contract_path(args.case_id, "candidate_set.latest.json"),
        label="candidate set json",
    )
    state_estimation_path = abs_path(
        args.state_estimation_json or _default_contract_path(args.case_id, "state_estimation.latest.json"),
        label="state estimation json",
        required=False,
    )
    hydraulic_assimilation_path = abs_path(
        args.hydraulic_assimilation_json or _default_contract_path(args.case_id, "hydraulic_assimilation.latest.json"),
        label="hydraulic assimilation json",
        required=False,
    )
    coupled_assimilation_path = abs_path(
        args.coupled_assimilation_json or _default_contract_path(args.case_id, "coupled_assimilation.latest.json"),
        label="coupled assimilation json",
        required=False,
    )
    output_path = abs_path(
        args.output_json or _default_contract_path(args.case_id, "assimilation_parameter_governance.latest.json"),
        label="output json",
        required=False,
    )

    governance = load_json(governance_path)
    candidate_set = load_json(candidate_set_path)
    state_estimation, resolved_state_estimation_path = _optional_json(state_estimation_path)
    hydraulic_assimilation, resolved_hydraulic_assimilation_path = _optional_json(hydraulic_assimilation_path)
    coupled_assimilation, resolved_coupled_assimilation_path = _optional_json(coupled_assimilation_path)

    activation_path = governance.get("artifact_paths", {}).get("correction_activation_record") if isinstance(governance, dict) else None
    activation = {}
    resolved_activation_path = None
    if activation_path:
      resolved_activation_path = abs_path(activation_path, label="correction activation record", required=False)
      if resolved_activation_path and resolved_activation_path.exists():
          activation = load_json(resolved_activation_path)

    assimilation_activation = activation.get("assimilation", {}) if isinstance(activation, dict) else {}
    required_keys = {
        "process_noise_scale",
        "observation_noise_scale",
        "observation_bias",
        "initial_state_bias",
    }
    activation_keys = set(assimilation_activation.keys()) if isinstance(assimilation_activation, dict) else set()

    assimilation_candidates = (
        candidate_set.get("stages", {}).get("assimilation", {})
        if isinstance(candidate_set, dict)
        else {}
    )
    primary_candidates = assimilation_candidates.get("primary_candidates", []) if isinstance(assimilation_candidates, dict) else []
    secondary_candidates = assimilation_candidates.get("secondary_candidates", []) if isinstance(assimilation_candidates, dict) else []

    station_count = len(state_estimation.get("stations", {})) if isinstance(state_estimation.get("stations"), dict) else 0
    completed_count = state_estimation.get("summary", {}).get("completed", 0) if isinstance(state_estimation, dict) else 0
    converged_count = state_estimation.get("summary", {}).get("converged", 0) if isinstance(state_estimation, dict) else 0
    hydraulic_improved = hydraulic_assimilation.get("summary", {}).get("improved_count", 0) if isinstance(hydraulic_assimilation, dict) else 0
    coupled_station_count = len(coupled_assimilation.get("station_results", [])) if isinstance(coupled_assimilation.get("station_results"), list) else 0

    checks = [
        {
            "key": "parameter_governance",
            "label": "共享治理合同存在",
            "status": "pass" if isinstance(governance, dict) and bool(governance) else "fail",
            "detail": _rel_or_abs(governance_path) if governance_path.exists() else "missing",
        },
        {
            "key": "assimilation_activation",
            "label": "assimilation activation 完整",
            "status": "pass" if required_keys.issubset(activation_keys) else "fail",
            "detail": f"keys={sorted(activation_keys)}",
        },
        {
            "key": "assimilation_candidate_freeze",
            "label": "assimilation 候选集已冻结",
            "status": "pass" if len(primary_candidates) + len(secondary_candidates) > 0 else "fail",
            "detail": f"primary={primary_candidates}; secondary={secondary_candidates}",
        },
        {
            "key": "state_estimation",
            "label": "state estimation 合同存在",
            "status": "pass" if completed_count > 0 else "fail",
            "detail": f"stations={station_count}; completed={completed_count}; converged={converged_count}",
        },
        {
            "key": "assimilation_outputs",
            "label": "同化结果合同存在",
            "status": "pass" if hydraulic_improved > 0 or coupled_station_count > 0 else "fail",
            "detail": f"hydraulic_improved={hydraulic_improved}; coupled_stations={coupled_station_count}",
        },
    ]

    gate_ok = all(item["status"] == "pass" for item in checks)
    payload = {
        "schema": "assimilation.parameter_governance.gate",
        "version": 1,
        "case_id": args.case_id,
        "gate_key": "assimilation",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "gate_status": "pass" if gate_ok else "fail",
        "quality_gate_passed": gate_ok,
        "status": "ready" if gate_ok else "blocked",
        "checks": checks,
        "summary": {
            "station_count": station_count,
            "completed_count": completed_count,
            "converged_count": converged_count,
            "hydraulic_improved_count": hydraulic_improved,
            "coupled_station_count": coupled_station_count,
            "activation_keys": sorted(activation_keys),
            "primary_candidates": primary_candidates,
            "secondary_candidates": secondary_candidates,
        },
        "artifacts": {
            "parameter_governance_json": _rel_or_abs(governance_path),
            "correction_activation_record": _rel_or_abs(resolved_activation_path),
            "candidate_set_json": _rel_or_abs(candidate_set_path),
            "state_estimation_json": _rel_or_abs(resolved_state_estimation_path),
            "hydraulic_assimilation_json": _rel_or_abs(resolved_hydraulic_assimilation_path),
            "coupled_assimilation_json": _rel_or_abs(resolved_coupled_assimilation_path),
        },
        "_auto_generated": True,
    }
    write_json(output_path, payload)
    print(str(output_path))


if __name__ == "__main__":
    main()
