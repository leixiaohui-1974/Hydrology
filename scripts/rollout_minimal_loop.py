"""Build minimal rollout-loop evidence for non-daduhe cases."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
CASES_DIR = WORKSPACE / "cases"
WORKFLOWS_DIR = WORKSPACE / "Hydrology" / "workflows"
DEFAULT_CASE_IDS = [
    "jiaodongtiaoshui",
    "xuhonghe",
    "yinchuojiliao",
    "zhongxian",
    "yjdt",
]
REQUIRED_EVIDENCE = {
    "source_discovery": "source_import_session.latest.json",
    "data_pack": "data_pack.latest.json",
    "simulation": "pipeline_evaluation.latest.json",
    "workflow_run": "workflow_run.json",
}


def _workspace_rel(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE))
    except ValueError:
        return str(path)


def _contracts_dir(case_id: str, workspace: Path = WORKSPACE) -> Path:
    return workspace / "cases" / case_id / "contracts"


def collect_case_evidence(case_id: str, workspace: Path = WORKSPACE) -> dict[str, Any]:
    contracts_dir = _contracts_dir(case_id, workspace)
    evidence: dict[str, Any] = {"contracts_dir": _workspace_rel(contracts_dir)}
    all_present = True
    for key, filename in REQUIRED_EVIDENCE.items():
        path = contracts_dir / filename
        present = path.is_file()
        all_present = all_present and present
        evidence[key] = {
            "path": _workspace_rel(path),
            "present": present,
        }
    return {
        "all_present": all_present,
        "artifacts": evidence,
    }


def run_case_preflight(case_id: str, workspace: Path = WORKSPACE) -> dict[str, Any]:
    command = [
        sys.executable,
        str(WORKFLOWS_DIR / "run_case_pipeline.py"),
        "--case-id",
        case_id,
        "--phase",
        "simulation",
        "--dry-run",
    ]
    proc = subprocess.run(
        command,
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"preflight failed for {case_id}")
    payload = json.loads(proc.stdout)
    return {
        "ok": bool(payload.get("ok")),
        "missing_inputs": list(payload.get("missing_inputs") or []),
        "planned_steps": [item.get("step") for item in (payload.get("planned_commands") or [])],
        "raw": payload,
    }


def summarize_case(case_id: str, preflight: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    phases_covered = ["source_discovery", "data_pack", "watershed_delineation", "hydrological_simulation"]
    required_steps = {"build_data_pack", "run_watershed_delineation", "run_hydrological_simulation"}
    planned_steps = set(preflight.get("planned_steps") or [])
    preflight_ok = bool(preflight.get("ok")) and not (preflight.get("missing_inputs") or []) and required_steps.issubset(planned_steps)
    status = "ready" if preflight_ok and evidence.get("all_present") else "not_ready"
    return {
        "schema_version": "p2.rollout_minimal_loop/v1",
        "case_id": case_id,
        "status": status,
        "ready": status == "ready",
        "phases_covered": phases_covered,
        "preflight": {
            "ok": preflight_ok,
            "missing_inputs": list(preflight.get("missing_inputs") or []),
            "planned_steps": list(preflight.get("planned_steps") or []),
        },
        "evidence": evidence,
    }


def write_case_summary(case_id: str, summary: dict[str, Any], workspace: Path = WORKSPACE) -> Path:
    path = _contracts_dir(case_id, workspace) / "rollout_minimal_loop.latest.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run_rollout_minimal_loop(case_ids: list[str], workspace: Path = WORKSPACE) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for case_id in case_ids:
        preflight = run_case_preflight(case_id, workspace)
        evidence = collect_case_evidence(case_id, workspace)
        summary = summarize_case(case_id, preflight, evidence)
        output = write_case_summary(case_id, summary, workspace)
        summary["output_contract"] = _workspace_rel(output)
        cases.append(summary)

    aggregate = {
        "schema_version": "p2.rollout_minimal_loop_summary/v1",
        "case_ids": case_ids,
        "ready_cases": [item["case_id"] for item in cases if item["ready"]],
        "not_ready_cases": [item["case_id"] for item in cases if not item["ready"]],
        "cases": cases,
    }
    summary_path = workspace / "cases" / "rollout_minimal_loop_summary.latest.json"
    summary_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    aggregate["summary_path"] = _workspace_rel(summary_path)
    return aggregate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build minimal rollout-loop evidence for five non-daduhe cases.")
    parser.add_argument("--case-id", action="append", dest="case_ids", help="Case id to include; repeatable.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    case_ids = args.case_ids or DEFAULT_CASE_IDS
    result = run_rollout_minimal_loop(case_ids)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
