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
    parser = argparse.ArgumentParser(description="Build coupling governance gate artifact for a case.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--parameter-governance-json")
    parser.add_argument("--coupled-result-json")
    parser.add_argument("--candidate-set-json")
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
    coupled_path = abs_path(
        args.coupled_result_json or _default_contract_path(args.case_id, "coupled_hydro_hydraulic.latest.json"),
        label="coupled result json",
    )
    candidate_set_path = abs_path(
        args.candidate_set_json or _default_contract_path(args.case_id, "candidate_set.latest.json"),
        label="candidate set json",
    )
    output_path = abs_path(
        args.output_json or _default_contract_path(args.case_id, "coupling_parameter_governance.latest.json"),
        label="output json",
        required=False,
    )

    governance = load_json(governance_path)
    coupled = load_json(coupled_path)
    candidate_set = load_json(candidate_set_path)

    activation_path = governance.get("artifact_paths", {}).get("correction_activation_record") if isinstance(governance, dict) else None
    activation = {}
    resolved_activation_path = None
    if activation_path:
        resolved_activation_path = abs_path(activation_path, label="correction activation record", required=False)
        if resolved_activation_path and resolved_activation_path.exists():
            activation = load_json(resolved_activation_path)

    coupling_activation = activation.get("coupling", {}) if isinstance(activation, dict) else {}
    required_keys = {
        "runoff_to_channel_lag",
        "channel_inflow_scale",
        "coupling_transfer_bias",
    }
    activation_keys = set(coupling_activation.keys()) if isinstance(coupling_activation, dict) else set()

    coupling_candidates = (
        candidate_set.get("stages", {}).get("coupling", {})
        if isinstance(candidate_set, dict)
        else {}
    )
    primary_candidates = coupling_candidates.get("primary_candidates", []) if isinstance(coupling_candidates, dict) else []
    secondary_candidates = coupling_candidates.get("secondary_candidates", []) if isinstance(coupling_candidates, dict) else []

    station_results = coupled.get("station_results", {}) if isinstance(coupled, dict) else {}
    stations_total = len(station_results) if isinstance(station_results, dict) else 0
    overall_metric_count = sum(
        1
        for row in station_results.values()
        if isinstance(row, dict) and isinstance(row.get("overall"), dict) and row.get("overall")
    )

    checks = [
        {
            "key": "parameter_governance",
            "label": "共享治理合同存在",
            "status": "pass" if isinstance(governance, dict) and bool(governance) else "fail",
            "detail": _rel_or_abs(governance_path) if governance_path.exists() else "missing",
        },
        {
            "key": "coupling_activation",
            "label": "coupling activation 完整",
            "status": "pass" if required_keys.issubset(activation_keys) else "fail",
            "detail": f"keys={sorted(activation_keys)}",
        },
        {
            "key": "coupling_candidate_freeze",
            "label": "coupling 候选集已冻结",
            "status": "pass" if len(primary_candidates) + len(secondary_candidates) > 0 else "fail",
            "detail": f"primary={primary_candidates}; secondary={secondary_candidates}",
        },
        {
            "key": "coupled_result",
            "label": "耦合结果合同存在",
            "status": "pass" if stations_total > 0 else "fail",
            "detail": f"stations={stations_total}",
        },
        {
            "key": "overall_metrics",
            "label": "站点 overall 指标可用",
            "status": "pass" if overall_metric_count > 0 else "fail",
            "detail": f"overall_metric_stations={overall_metric_count}",
        },
    ]

    gate_ok = all(item["status"] == "pass" for item in checks)
    payload = {
        "schema": "coupling.parameter_governance.gate",
        "version": 1,
        "case_id": args.case_id,
        "gate_key": "coupling",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "gate_status": "pass" if gate_ok else "fail",
        "quality_gate_passed": gate_ok,
        "status": "ready" if gate_ok else "blocked",
        "checks": checks,
        "summary": {
            "stations_total": stations_total,
            "overall_metric_stations": overall_metric_count,
            "activation_keys": sorted(activation_keys),
            "primary_candidates": primary_candidates,
            "secondary_candidates": secondary_candidates,
        },
        "artifacts": {
            "parameter_governance_json": _rel_or_abs(governance_path),
            "correction_activation_record": _rel_or_abs(resolved_activation_path),
            "candidate_set_json": _rel_or_abs(candidate_set_path),
            "coupled_result_json": _rel_or_abs(coupled_path),
        },
        "_auto_generated": True,
    }
    write_json(output_path, payload)
    print(str(output_path))


if __name__ == "__main__":
    main()
