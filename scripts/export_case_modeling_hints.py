#!/usr/bin/env python3
"""Export deterministic modeling hints for one case.

This bridge composes existing readiness truth with Graphify sidecar-derived
signals into a non-authoritative, reviewable hints object. It never modifies
contracts or workflow truth; it only emits structured suggestions.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from export_case_platform_readiness import run_readiness  # noqa: E402
from workflows._shared import load_case_config  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
DEFAULT_RULES = WORKSPACE / "Hydrology" / "configs" / "workflow_feasibility_rules.yaml"


def _prioritize_workflows(summary: dict[str, Any]) -> list[str]:
    counts = summary.get("graphify_modeling_signal_counts") or {}
    suggestions: list[str] = []

    if int(counts.get("terrain", 0)) > 0:
        suggestions.extend(["source_to_delineation", "section_analysis"])
    if int(counts.get("topology", 0)) > 0:
        suggestions.extend(["model", "source_to_delineation"])
    if int(counts.get("geometry", 0)) > 0:
        suggestions.extend(["section_analysis", "hyd_sim"])
    if int(counts.get("boundary", 0)) > 0:
        suggestions.extend(["model", "hydro_report"])
    if int(counts.get("control", 0)) > 0:
        suggestions.extend(["cascade", "state_est", "assimilate"])

    ordered: list[str] = []
    seen: set[str] = set()
    for name in suggestions:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _workflow_recommendations(hints: dict[str, Any], project_type: str) -> dict[str, Any]:
    suggested = [str(x) for x in (hints.get("suggested_workflows") or []) if str(x).strip()]
    supports = bool(hints.get("graphify_supports_auto_modeling_hints"))
    stage_map = {
        "watershed_delineation": {"source_to_delineation", "section_analysis"},
        "hydrology": {"model", "hyd_sim", "hydro_report"},
        "hydraulics": {"section_analysis"},
        "coupling": {"cascade"},
        "assimilation": {"state_est", "assimilate"},
    }
    suggested_set = set(suggested)
    guidance = {}
    deferred = []
    for stage, names in stage_map.items():
        if project_type in {"canal", "pump_canal"} and stage == "hydrology":
            guidance[stage] = {
                "status": "deferred",
                "matched_workflows": [],
                "reason": f"project_type {project_type} defers hydrology in early productization phases",
            }
            deferred.append(stage)
            continue
        matched = sorted(suggested_set & names)
        if matched:
            status = "recommended"
        elif supports:
            status = "deferred"
            deferred.append(stage)
        else:
            status = "default"
        guidance[stage] = {
            "status": status,
            "matched_workflows": matched,
        }
    return {
        "supports_auto_modeling_hints": supports,
        "suggested_workflows": suggested,
        "deferred_stages": deferred,
        "stage_activation_guidance": guidance,
    }


def derive_modeling_hints(case_id: str, config_path: Path, rules_path: Path) -> dict[str, Any]:
    readiness = run_readiness(case_id, config_path, rules_path)
    case_cfg = load_case_config(case_id)
    project_type = str(case_cfg.get("project_type") or "").strip()
    summary = readiness.get("summary") or {}
    graphify = readiness.get("graphify_sidecar") or {}

    hints = {
        "case_id": case_id,
        "project_type": project_type,
        "entry_sources": {
            "case_manifest": summary.get("entry_case_manifest_source"),
            "source_bundle": summary.get("entry_source_bundle_source"),
            "outlets": summary.get("entry_outlets_source"),
            "simulation_config": summary.get("entry_simulation_config_source"),
            "import_session": summary.get("entry_source_import_session_source"),
        },
        "source_import_session": {
            "present": summary.get("source_import_session_present"),
            "path": summary.get("source_import_session_path"),
            "source_mode": summary.get("source_import_mode"),
            "record_count": summary.get("source_import_record_count"),
            "imported_at": summary.get("source_imported_at"),
        },
        "graphify_supports_auto_modeling_hints": bool(summary.get("graphify_supports_auto_modeling_hints")),
        "graphify_modeling_signal_counts": summary.get("graphify_modeling_signal_counts") or {},
        "pipeline_contract_ready": summary.get("pipeline_contract_ready"),
        "workflow_data_ok": summary.get("workflow_data_ok"),
        "workflow_data_gap": summary.get("workflow_data_gap"),
        "suggested_workflows": _prioritize_workflows(summary),
        "graphify_artifacts": graphify.get("artifacts") or [],
    }
    hints["workflow_recommendations"] = _workflow_recommendations(hints, project_type)
    return {
        "ok": True,
        "schema_version": "1.0",
        "case_id": case_id,
        "hints": hints,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export deterministic modeling hints for one case")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()

    config = args.config if args.config.is_absolute() else WORKSPACE / args.config
    rules = args.rules if args.rules.is_absolute() else WORKSPACE / args.rules
    payload = derive_modeling_hints(args.case_id.strip(), config.resolve(), rules.resolve())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
