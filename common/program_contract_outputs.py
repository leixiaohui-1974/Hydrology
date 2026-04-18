"""Helpers to emit contract-aware workflow and review metadata files."""

from __future__ import annotations

import json
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from common.program_contract_bridge import CONTRACTS_AVAILABLE, PROGRAM_SCHEMA_VERSION, validate_payload
except Exception:
    _bridge_path = Path(__file__).resolve().with_name("program_contract_bridge.py")
    _spec = importlib.util.spec_from_file_location("program_contract_bridge", _bridge_path)
    _module = importlib.util.module_from_spec(_spec)
    assert _spec is not None and _spec.loader is not None
    _spec.loader.exec_module(_module)
    CONTRACTS_AVAILABLE = _module.CONTRACTS_AVAILABLE
    PROGRAM_SCHEMA_VERSION = _module.PROGRAM_SCHEMA_VERSION
    validate_payload = _module.validate_payload


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_contract_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        return str(candidate)
    resolved = candidate.resolve()
    try:
        return str(resolved.relative_to(_workspace_root()))
    except ValueError:
        return str(resolved)


def default_workflow_run_output(config_path: str | Path) -> Path:
    path = Path(config_path)
    return path.with_name(f"{path.stem}.workflow_run.json")


def default_review_bundle_output(report_path: str | Path) -> Path:
    path = Path(report_path)
    return path.with_name(f"{path.stem}.review_bundle.json")


def default_release_manifest_output(base_path: str | Path) -> Path:
    path = Path(base_path)
    if path.suffix:
        return path.with_name(f"{path.stem}.release_manifest.json")
    return path / "release_manifest.json"


def build_workflow_run_payload(
    *,
    run_id: str,
    case_id: str,
    workflow_type: str,
    status: str,
    config_path: str | Path,
    components: list[str],
    dt_seconds: float,
    num_steps: int,
    started_at: str,
    completed_at: str,
    output_artifacts: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "run_id": run_id,
        "case_id": case_id,
        "workflow_type": workflow_type,
        "status": status,
        "inputs": [
            {
                "artifact_id": f"{run_id}:config",
                "artifact_type": "config",
                "path": _normalize_contract_path(config_path),
                "metadata": {},
            }
        ],
        "outputs": output_artifacts or [],
        "steps": [],
        "started_at": started_at,
        "completed_at": completed_at,
        "metadata": {
            "components": components,
            "dt_seconds": dt_seconds,
            "num_steps": num_steps,
            **(metadata or {}),
        },
        "schema_version": PROGRAM_SCHEMA_VERSION,
    }
    return payload


def build_artifact_payload(
    *,
    artifact_id: str,
    artifact_type: str,
    path: str | Path | None = None,
    uri: str | None = None,
    checksum: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "path": _normalize_contract_path(path),
        "uri": uri,
        "checksum": checksum,
        "metadata": metadata or {},
    }


def build_workflow_step_payload(
    *,
    step_id: str,
    status: str,
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "status": status,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "started_at": started_at,
        "completed_at": completed_at,
        "metadata": metadata or {},
    }


def write_workflow_run_metadata(output_path: str | Path, payload: dict[str, Any]) -> Path:
    _, errors = validate_payload("workflow_run", payload)
    if errors:
        raise ValueError(errors)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_review_bundle_payload(
    *,
    review_id: str,
    run_id: str,
    case_id: str,
    verdict: str,
    report_path: str | Path,
    findings: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report_artifact = {
        "artifact_id": f"{review_id}:report",
        "artifact_type": "html_report",
        "path": _normalize_contract_path(report_path),
        "metadata": {"role": "acceptance_report"},
    }
    payload = {
        "review_id": review_id,
        "run_id": run_id,
        "case_id": case_id,
        "verdict": verdict,
        "findings": findings or [],
        "report_artifacts": [report_artifact],
        "metadata": metadata or {},
        "schema_version": PROGRAM_SCHEMA_VERSION,
    }
    return payload


def write_review_bundle_metadata(output_path: str | Path, payload: dict[str, Any]) -> Path:
    _, errors = validate_payload("review_bundle", payload)
    if errors:
        raise ValueError(errors)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def default_governance_gates_ref_for_release() -> dict[str, Any]:
    """P0 治理门：release 侧可追溯的索引指针（与 HydroDesk / Hydrology/configs 共用）。"""
    index_rel = "Hydrology/configs/platform_governance_gates.index.json"
    root = _workspace_root()
    index_path = root / index_rel
    version = 1
    if index_path.is_file():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            v = data.get("version")
            if isinstance(v, int):
                version = v
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return {
        "index_rel": index_rel,
        "index_version": version,
        "note": "Review 三道治理门路径索引；按 case_id 解析 path_template_chain；与 HydroDesk 共用。",
    }


def build_release_manifest_payload(
    *,
    release_id: str,
    case_id: str,
    version: str,
    channel: str,
    status: str,
    included_runs: list[str],
    review_refs: list[str],
    artifacts: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    governance_gates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "release_id": release_id,
        "case_id": case_id,
        "version": version,
        "channel": channel,
        "status": status,
        "included_runs": included_runs,
        "artifacts": artifacts,
        "review_refs": review_refs,
        "metadata": metadata or {},
        "schema_version": PROGRAM_SCHEMA_VERSION,
        "governance_gates": dict(governance_gates)
        if governance_gates is not None
        else default_governance_gates_ref_for_release(),
    }
    return payload


def write_release_manifest_metadata(output_path: str | Path, payload: dict[str, Any]) -> Path:
    _, errors = validate_payload("release_manifest", payload)
    if errors:
        raise ValueError(errors)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
