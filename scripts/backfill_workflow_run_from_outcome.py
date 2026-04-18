#!/usr/bin/env python3
"""Backfill workflow_run.json outputs from an existing outcome contract.

Used to upgrade rollout bootstrap triads into minimally evidence-bearing
workflow runs without fabricating domain results. This preserves the
existing run record where present and only injects output artifacts plus
light metadata linking the run to the outcome contract.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _artifact_record(case_id: str, workflow_key: str, artifact: dict[str, Any], index: int, outcome_path: str) -> dict[str, Any]:
    return {
        "artifact_id": f"{case_id}:{workflow_key}:outcome:{index}",
        "artifact_type": str(artifact.get("artifact_type") or "json"),
        "path": str(artifact.get("path") or ""),
        "uri": None,
        "checksum": None,
        "metadata": {
            "role": "outcome_artifact",
            "workflow_key": workflow_key,
            "exists": bool(artifact.get("exists")),
            "backfilled_from_outcome_contract": outcome_path,
        },
    }


def backfill_workflow_run(case_id: str, *, outcome_name: str = "source_to_delineation.latest.json") -> dict[str, Any]:
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    workflow_run_path = contracts_dir / "workflow_run.json"
    outcome_path = contracts_dir / "outcomes" / outcome_name

    if not workflow_run_path.is_file():
        raise FileNotFoundError(f"workflow_run not found: {workflow_run_path}")
    if not outcome_path.is_file():
        raise FileNotFoundError(f"outcome contract not found: {outcome_path}")

    workflow_run = _load_json(workflow_run_path)
    outcome = _load_json(outcome_path)
    workflow_key = str(outcome.get("workflow_key") or "unknown")
    artifacts = [item for item in (outcome.get("artifacts") or []) if isinstance(item, dict) and str(item.get("path") or "").strip()]
    if not artifacts:
        raise ValueError(f"outcome contract has no artifacts to backfill: {outcome_path}")

    workflow_run["workflow_type"] = workflow_key if workflow_run.get("_bootstrap") else workflow_run.get("workflow_type") or workflow_key
    workflow_run["status"] = str(outcome.get("status") or workflow_run.get("status") or "completed_with_review")
    workflow_run["outputs"] = [
        _artifact_record(case_id, workflow_key, artifact, index + 1, str(outcome_path.relative_to(WORKSPACE)))
        for index, artifact in enumerate(artifacts)
    ]

    if not isinstance(workflow_run.get("steps"), list) or not workflow_run["steps"]:
        workflow_run["steps"] = [
            {
                "step_id": workflow_key,
                "status": str(outcome.get("status") or "completed"),
                "inputs": [],
                "outputs": [record["path"] for record in workflow_run["outputs"]],
                "started_at": None,
                "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "metadata": {
                    "backfilled_from_outcome_contract": str(outcome_path.relative_to(WORKSPACE)),
                },
            }
        ]

    metadata = workflow_run.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        workflow_run["metadata"] = metadata
    metadata["backfilled_from_outcome_contract"] = str(outcome_path.relative_to(WORKSPACE))
    metadata["backfilled_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    metadata["_bootstrap_upgraded"] = True

    _write_json(workflow_run_path, workflow_run)
    return {
        "ok": True,
        "case_id": case_id,
        "workflow_run": str(workflow_run_path.relative_to(WORKSPACE)),
        "outcome_contract": str(outcome_path.relative_to(WORKSPACE)),
        "workflow_type": workflow_run.get("workflow_type"),
        "output_count": len(workflow_run["outputs"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill workflow_run.json outputs from an existing outcome contract")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--outcome-name", default="source_to_delineation.latest.json")
    args = parser.parse_args()
    payload = backfill_workflow_run(args.case_id.strip(), outcome_name=args.outcome_name.strip())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
