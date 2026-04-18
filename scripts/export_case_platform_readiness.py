#!/usr/bin/env python3
"""
单案例「平台就绪度」合并视图：主闭环 quality_loop + contracts 产物覆盖 + 工作流×数据信号矩阵。

stdout 单行 JSON，供 HydroDesk 评审与 CI；配置路径与案例 id 均参数化，零硬编码案例名。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_case_quality_artifacts import run_check  # noqa: E402
from export_case_workflow_feasibility import DEFAULT_RULES, run_export  # noqa: E402
from hydrodesk_loop_yaml_util import load_loop_yaml  # noqa: E402
from workflows._shared import (  # noqa: E402
    default_graphify_case_sidecar_dir,
    normalize_serialized_paths,
    resolve_case_entry_inputs,
)
from workflows.run_knowledge_miner import _load_graphify_sidecar  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]


def _feasibility_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        t = str(r.get("tier") or "unknown")
        out[t] = out.get(t, 0) + 1
    return out


def _workspace_rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE))
    except ValueError:
        return str(path.resolve())


def _load_case_manifest_payload(case_id: str) -> dict[str, Any]:
    manifest_path = WORKSPACE / "cases" / case_id / "manifest.yaml"
    if not manifest_path.is_file():
        return {}
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}


def _resolve_source_import_session(case_id: str, manifest_payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str, str | None]:
    latest_block = manifest_payload.get("latest_source_import_session") or {}
    candidates: list[tuple[str, Path]] = []
    raw_latest = str(latest_block.get("path") or "").strip()
    if raw_latest:
        candidates.append(("manifest_latest", WORKSPACE / raw_latest))
    candidates.append(("contracts_default", WORKSPACE / "cases" / case_id / "contracts" / "source_import_session.latest.json"))

    seen: set[str] = set()
    for source, path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload, source, _workspace_rel_or_abs(path)
    return None, "missing", None


def run_readiness(case_id: str, config_path: Path, rules_path: Path) -> dict[str, Any]:
    cid = case_id.strip()
    cfg = load_loop_yaml(WORKSPACE, config_path.resolve())
    try:
        cfg_rel = str(config_path.resolve().relative_to(WORKSPACE))
    except ValueError:
        cfg_rel = str(config_path.resolve())

    rubric: dict[str, Any] = {
        "config_path": cfg_rel,
        "version": cfg.get("version"),
        "platform": cfg.get("platform") or {},
        "quality_loop": cfg.get("quality_loop") or {},
        "html_contracts": cfg.get("html_contracts") or {},
    }

    artifact = run_check(cid, config_path)
    if not (WORKSPACE / "cases" / cid / "contracts").is_dir():
        artifact["error"] = artifact.get("error") or "contracts_directory_missing"

    feas = run_export(cid, rules_path.resolve() if not rules_path.is_absolute() else rules_path)
    tiers = _feasibility_counts(feas.get("workflows") or [])
    entry_inputs = resolve_case_entry_inputs(cid)
    manifest_payload = _load_case_manifest_payload(cid)
    source_import_session, source_import_session_source, source_import_session_path = _resolve_source_import_session(
        cid,
        manifest_payload,
    )
    graphify_sidecar = normalize_serialized_paths(
        _load_graphify_sidecar(str(default_graphify_case_sidecar_dir(cid)))
    )

    artifact_summary = artifact.get("summary") or {}
    summary = {
        "artifact_ratio": artifact_summary.get("ratio"),
        "artifact_dimensions_satisfied": artifact_summary.get("dimensions_satisfied"),
        "artifact_dimensions_total": artifact_summary.get("dimensions_total"),
        "workflow_outputs_count": artifact_summary.get("workflow_outputs_count"),
        "workflow_outputs_ready": artifact_summary.get("workflow_outputs_ready"),
        "data_pack_basin_validation_present": artifact_summary.get(
            "data_pack_basin_validation_present"
        ),
        "source_bundle_present": artifact_summary.get("source_bundle_present"),
        "pipeline_contract_ready": artifact_summary.get("pipeline_contract_ready"),
        "workflow_tier_counts": tiers,
        "workflow_data_ok": tiers.get("data_ok", 0),
        "workflow_data_gap": tiers.get("data_gap", 0),
        "case_config_signal": bool((feas.get("signals") or {}).get("case_config_file")),
        "entry_case_manifest_source": entry_inputs.get("case_manifest_source"),
        "entry_source_bundle_source": entry_inputs.get("source_bundle_source"),
        "entry_outlets_source": entry_inputs.get("outlets_source"),
        "entry_simulation_config_source": entry_inputs.get("simulation_config_source"),
        "entry_source_import_session_source": source_import_session_source,
        "source_import_session_present": bool(source_import_session),
        "source_import_session_path": source_import_session_path,
        "source_import_mode": (source_import_session or {}).get("source_mode"),
        "source_import_record_count": (source_import_session or {}).get("record_count"),
        "source_imported_at": (source_import_session or {}).get("imported_at"),
        "graphify_sidecar_status": graphify_sidecar.get("status", "missing") if graphify_sidecar else "missing",
        "graphify_supports_auto_modeling_hints": bool(graphify_sidecar.get("supports_auto_modeling_hints")) if graphify_sidecar else False,
        "graphify_modeling_signal_counts": graphify_sidecar.get("modeling_signal_counts", {}) if graphify_sidecar else {},
    }

    return {
        "ok": True,
        "schema_version": "1.0",
        "case_id": cid,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "loop_config_path": cfg_rel,
        "rules_path": feas.get("rules_path"),
        "summary": summary,
        "entry_inputs": entry_inputs,
        "source_import_session": normalize_serialized_paths(
            {
                "source": source_import_session_source,
                "path": source_import_session_path,
                "payload": source_import_session,
            }
        ),
        "graphify_sidecar": graphify_sidecar,
        "platform_rubric": rubric,
        "artifact_coverage": artifact,
        "workflow_feasibility": feas,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Export merged platform readiness for one case")
    p.add_argument("--case-id", required=True)
    p.add_argument(
        "--config",
        type=Path,
        default=WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml",
        help="主闭环 YAML（含 quality_loop）",
    )
    p.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES,
        help="workflow_feasibility_rules.yaml",
    )
    args = p.parse_args()
    rules = args.rules if args.rules.is_absolute() else WORKSPACE / args.rules
    if not rules.is_file():
        print(json.dumps({"ok": False, "error": f"rules not found: {rules}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    out = run_readiness(args.case_id, args.config, rules)
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
