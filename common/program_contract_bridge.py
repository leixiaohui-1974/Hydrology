"""Bridge helpers for HydroMind program-level contracts.

This module keeps Hydrology decoupled from the exact sibling-repo path while
making Case/Data Pack/Run/Review/Release contracts available when the shared
`hydromind-contracts` repo exists in the research workspace.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _contracts_repo_root() -> Path:
    return Path(__file__).resolve().parents[2] / "hydromind-contracts"


def ensure_contracts_importable() -> bool:
    repo_root = _contracts_repo_root()
    repo_root_str = str(repo_root)
    if repo_root.exists() and repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    return repo_root.exists()


CONTRACTS_AVAILABLE = ensure_contracts_importable()

if CONTRACTS_AVAILABLE:
    from hydromind_contracts.contract_index import (
        PROGRAM_SCHEMA_VERSION,
        ArtifactRef,
        CaseManifest,
        DataPack,
        ReleaseManifest,
        ReviewBundle,
        ReviewFinding,
        SourceBundle,
        WorkflowRun,
        WorkflowStepRun,
        load_and_validate_case_manifest,
        load_and_validate_data_pack,
        load_and_validate_release_manifest,
        load_and_validate_review_bundle,
        load_and_validate_source_bundle,
        load_and_validate_workflow_run,
    )
else:
    PROGRAM_SCHEMA_VERSION = "0.1.0"
    ArtifactRef = None
    CaseManifest = None
    DataPack = None
    ReleaseManifest = None
    ReviewBundle = None
    ReviewFinding = None
    SourceBundle = None
    WorkflowRun = None
    WorkflowStepRun = None
    load_and_validate_case_manifest = None
    load_and_validate_data_pack = None
    load_and_validate_release_manifest = None
    load_and_validate_review_bundle = None
    load_and_validate_source_bundle = None
    load_and_validate_workflow_run = None


def load_json_payload(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_payload(kind: str, payload: dict[str, Any]) -> tuple[Any, list[str]]:
    if not CONTRACTS_AVAILABLE:
        raise RuntimeError("hydromind-contracts repository is not available")

    mapping = {
        "case_manifest": load_and_validate_case_manifest,
        "source_bundle": load_and_validate_source_bundle,
        "data_pack": load_and_validate_data_pack,
        "workflow_run": load_and_validate_workflow_run,
        "review_bundle": load_and_validate_review_bundle,
        "release_manifest": load_and_validate_release_manifest,
    }
    loader = mapping.get(kind)
    if loader is None:
        raise ValueError(f"unsupported contract kind: {kind}")
    return loader(payload)


def load_and_validate_payload(kind: str, path: str | Path) -> tuple[Any, list[str]]:
    return validate_payload(kind, load_json_payload(path))


def program_contract_kinds() -> list[str]:
    return [
        "case_manifest",
        "source_bundle",
        "data_pack",
        "workflow_run",
        "review_bundle",
        "release_manifest",
    ]
