"""Backfill existing outcome contracts with contract_path and evidence bindings."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

_OUTCOME_CONTRACT_PATH = WORKSPACE / "Hydrology" / "workflows" / "outcome_contract.py"
_SPEC = importlib.util.spec_from_file_location("outcome_contract_module", _OUTCOME_CONTRACT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
generate_and_write_outcome = _MODULE.generate_and_write_outcome


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _exists(rel_path: str) -> bool:
    return (WORKSPACE / rel_path).exists()


def _default_artifacts(case_id: str, workflow_key: str) -> list[str]:
    defaults = {
        "hyd_cal": [
            f"cases/{case_id}/contracts/hydraulic_calibration.latest.json",
            f"cases/{case_id}/contracts/D2_hydraulic_report.md",
        ],
        "d1d4": [f"cases/{case_id}/contracts/d1d4_precision_report.latest.json"],
        "autonomy_assess": [
            f"cases/{case_id}/contracts/autonomy_assessment.latest.json",
            f"cases/{case_id}/contracts/autonomy_assessment.latest.md",
        ],
        "strict_revalidation_ext": ["reports/acceptance/strict_revalidation_summary.json"],
        "ensemble_forecast": [f"cases/{case_id}/contracts/ensemble_forecast.latest.json"],
    }
    return [item for item in defaults.get(workflow_key, []) if _exists(item)]


def _first_evidence(contract: dict[str, Any]) -> str:
    artifacts = contract.get("artifacts", [])
    for item in artifacts:
        if isinstance(item, dict) and item.get("path"):
            return str(item["path"])
    return str(contract.get("contract_path", ""))


def _is_result_asset(case_id: str, rel_path: str) -> bool:
    rel_path = str(rel_path or "").strip()
    return rel_path.startswith(
        (
            f"cases/{case_id}/contracts/",
            f"cases/{case_id}/source_selection/",
            "reports/acceptance/",
        )
    )


def _needs_regeneration(case_id: str, contract: dict[str, Any]) -> bool:
    artifacts = contract.get("artifacts", [])
    first_path = ""
    if isinstance(artifacts, list) and artifacts:
        first = artifacts[0]
        if isinstance(first, dict):
            first_path = str(first.get("path", ""))
    if not _is_result_asset(case_id, first_path):
        return True

    for dim_name in ("conclusion", "recommendation", "accuracy"):
        for item in (contract.get("dimensions", {}) or {}).get(dim_name, []) or []:
            if not isinstance(item, dict):
                continue
            evidence_path = str(item.get("evidence_path", ""))
            if evidence_path and not _is_result_asset(case_id, evidence_path):
                return True
    return False


def _ensure_dimensions(contract: dict[str, Any], fallback_path: str) -> None:
    dimensions = contract.setdefault("dimensions", {})
    for dim_name in ("conclusion", "recommendation", "accuracy"):
        items = dimensions.get(dim_name, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and not str(item.get("evidence_path", "")).strip():
                item["evidence_path"] = fallback_path
    if not contract.get("metrics"):
        accuracy_items = dimensions.get("accuracy")
        if isinstance(accuracy_items, list) and accuracy_items:
            first = accuracy_items[0]
            if isinstance(first, dict) and not first.get("value"):
                first["value"] = {"status": "pending_evaluation"}


def _status_to_outcome_status(status: str) -> str:
    return "completed" if status == "passed" else status


def _payload_from_excerpt(record: dict[str, Any]) -> dict[str, Any]:
    excerpt = record.get("excerpt")
    if not excerpt:
        return {
            "status": record.get("status"),
            "workflow_key": record.get("workflow_key"),
            "workflow_path": record.get("workflow_path"),
        }
    try:
        parsed = json.loads(excerpt)
        if isinstance(parsed, dict):
            return parsed.get("result") if isinstance(parsed.get("result"), dict) else parsed
    except Exception:
        pass
    return {
        "status": record.get("status"),
        "workflow_key": record.get("workflow_key"),
        "workflow_path": record.get("workflow_path"),
        "excerpt": excerpt,
    }


def backfill_case(case_id: str) -> dict[str, Any]:
    out_dir = WORKSPACE / "cases" / case_id / "contracts" / "outcomes"
    progress_path = WORKSPACE / "cases" / case_id / "contracts" / "e2e_live_progress.latest.json"
    progress = _load_json(progress_path) if progress_path.exists() else {}
    progress_records = {
        str(record.get("workflow_key", "")): record
        for record in progress.get("records", [])
        if record.get("workflow_key")
    }
    updated = 0
    generated = 0
    regenerated = 0
    for path in sorted(out_dir.glob("*.latest.json")):
        contract = _load_json(path)
        workflow_key = str(contract.get("workflow_key", path.stem.replace(".latest", "")))
        record = progress_records.get(workflow_key)
        if record and _needs_regeneration(case_id, contract):
            generate_and_write_outcome(
                workflow=workflow_key,
                case_id=case_id,
                result=_payload_from_excerpt(record),
                status=_status_to_outcome_status(str(record.get("status", "completed"))),
                execution_profile=str(progress.get("execution_profile", "default")),
            )
            regenerated += 1
            updated += 1
            continue
        rel_contract_path = str(path.relative_to(WORKSPACE))
        contract["contract_path"] = rel_contract_path

        artifacts = contract.setdefault("artifacts", [])
        artifact_paths = {
            str(item.get("path"))
            for item in artifacts
            if isinstance(item, dict) and item.get("path")
        }
        for rel_path in _default_artifacts(case_id, workflow_key):
            if rel_path not in artifact_paths:
                artifacts.insert(
                    0,
                    {
                        "path": rel_path,
                        "exists": True,
                        "artifact_type": Path(rel_path).suffix.lower().lstrip("."),
                    },
                )
                artifact_paths.add(rel_path)

        fallback_path = _first_evidence(contract) or rel_contract_path
        _ensure_dimensions(contract, fallback_path)
        _save_json(path, contract)
        updated += 1

    existing = {path.stem.replace(".latest", "") for path in out_dir.glob("*.latest.json")}
    for record in progress.get("records", []):
        workflow_key = str(record.get("workflow_key", ""))
        if not workflow_key or workflow_key in existing:
            continue
        generate_and_write_outcome(
            workflow=workflow_key,
            case_id=case_id,
            result=_payload_from_excerpt(record),
            status=_status_to_outcome_status(str(record.get("status", "completed"))),
            execution_profile=str(progress.get("execution_profile", "default")),
        )
        generated += 1

    return {
        "case_id": case_id,
        "updated_contracts": updated,
        "regenerated_contracts": regenerated,
        "generated_missing_contracts": generated,
        "outcomes_dir": str(out_dir.relative_to(WORKSPACE)),
        "_auto_generated": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()
    print(json.dumps(backfill_case(args.case_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
