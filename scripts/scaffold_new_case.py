#!/usr/bin/env python3
"""
在仓库内创建新案例骨架：cases/<case_id>/manifest.yaml、contracts、ingest/raw（Karpathy 式 raw 槽位，
与 hydrodesk_shell.knowledge_lint.raw_dir_rel 对齐）、最小 case_manifest.json、
Hydrology/configs/<case_id>.yaml；可选将 case_id 写入主闭环 YAML 的 case_selection.case_ids。

路径均相对 workspace root；禁止在代码中写死具体案例名（仅 CLI 传入）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from hydrodesk_loop_yaml_util import load_loop_yaml  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]
CASE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
DEFAULT_LOOP_CONFIG = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
STANDARD_WORKFLOW_TARGETS = [
    "source_discovery",
    "data_pack_build",
    "watershed_delineation",
    "hydrological_simulation",
    "acceptance_review",
    "release_publish",
]
STANDARD_WORKFLOW_VALIDATION_PRIORITY = [
    "watershed_delineation",
    "hydrological_simulation",
    "acceptance_review",
    "release_publish",
]


def _utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def rollout_workflow_baseline() -> dict[str, Any]:
    return {
        "entrypoint": "Hydrology/workflows/run_case_pipeline.py",
        "implementation": "Hydrology/workflows/run_watershed_delineation.py",
        "status": "contract_orchestrated",
        "updated_at": _utc_date(),
    }


def rollout_shell_entrypoints(case_id: str) -> dict[str, Any]:
    contracts_root = f"cases/{case_id}/contracts"
    return {
        "run": {
            "path": "Hydrology/workflows/run_case_pipeline.py",
            "phase": "watershed",
            "output_contract": f"{contracts_root}/workflow_run.json",
        },
        "review": {
            "path": "Hydrology/workflows/build_review_bundle.py",
            "phase": "review",
            "output_contract": f"{contracts_root}/review_bundle.json",
        },
        "release": {
            "path": "Hydrology/workflows/build_release_manifest.py",
            "phase": "release",
            "output_contract": f"{contracts_root}/release_manifest.json",
        },
    }


def rollout_release_handoff(case_id: str) -> dict[str, Any]:
    contracts_root = f"cases/{case_id}/contracts"
    return {
        "mode": "json_handoff",
        "producer_repo": "Hydrology",
        "consumer_repo": "pipedream-hydrology-integration-lab",
        "handoff_status": "shell_contract_ready",
        "artifacts": {
            "workflow_run": f"{contracts_root}/workflow_run.json",
            "review_bundle": f"{contracts_root}/review_bundle.json",
            "release_manifest": f"{contracts_root}/release_manifest.json",
        },
    }


def rollout_links(case_id: str, *, raw_root: str, raw_root_purpose: str = "原始资料入口") -> dict[str, Any]:
    contracts_root = f"cases/{case_id}/contracts"
    return {
        "raw_case_root": {
            "path": raw_root,
            "purpose": raw_root_purpose,
        },
        "hydrology_repo": {
            "path": "Hydrology",
            "purpose": "workflow 实现与报告模板",
        },
        "pipedream_repo": {
            "path": "pipedream-hydrology-integration-lab",
            "purpose": "数据接入、数据库治理与发布导入",
        },
        "release_handoff_index": {
            "path": "RELEASE_HANDOFF_INDEX.md",
            "purpose": "项目群 release handoff 总入口",
        },
        "hydrology_case_pipeline": {
            "path": "Hydrology/workflows/run_case_pipeline.py",
            "purpose": "Case / Data Pack / Run / Review / Release 的确定性总入口",
        },
        "hydrology_run_entry": {
            "path": "Hydrology/workflows/run_watershed_delineation.py",
            "purpose": "生成 WorkflowRun 的 Run 入口",
        },
        "hydrology_review_entry": {
            "path": "Hydrology/workflows/build_review_bundle.py",
            "purpose": "生成 ReviewBundle 的 Review 入口",
        },
        "hydrology_release_builder": {
            "path": "Hydrology/workflows/build_release_manifest.py",
            "purpose": "组装 ReleaseManifest 的 Release 入口",
        },
        "shell_workflow_run": {
            "path": f"{contracts_root}/workflow_run.json",
            "purpose": f"{case_id} shell 固定读取的 WorkflowRun",
        },
        "shell_review_bundle": {
            "path": f"{contracts_root}/review_bundle.json",
            "purpose": f"{case_id} shell 固定读取的 ReviewBundle",
        },
        "shell_release_manifest": {
            "path": f"{contracts_root}/release_manifest.json",
            "purpose": f"{case_id} shell 固定读取的 ReleaseManifest",
        },
        "program_state": {
            "path": ".planning/STATE.md",
            "purpose": "项目群当前推进状态",
        },
    }


def rollout_manifest_payload(case_id: str, display_name: str) -> dict[str, Any]:
    contracts_root = f"cases/{case_id}/contracts"
    return {
        "case": {
            "id": case_id,
            "display_name": display_name,
            "status": "draft",
            "priority": "rollout",
            "source_of_truth": True,
        },
        "workflow_targets": list(STANDARD_WORKFLOW_TARGETS),
        "workflow_validation_priority": list(STANDARD_WORKFLOW_VALIDATION_PRIORITY),
        "summary": {
            "description": "由 HydroDesk / scaffold_new_case 初始化；请补充 raw 资料、workflow 目标与验收标准。",
            "current_assessment": [
                "骨架已就绪，待接入数据源与 contracts 产物",
            ],
        },
        "locations": {
            "raw_root": "",
            "raw_ingest_dir": f"cases/{case_id}/ingest/raw",
            "workflow_repo": "Hydrology",
            "ingestion_repo": "pipedream-hydrology-integration-lab",
            "case_entry_root": f"cases/{case_id}",
        },
        "workflow_baseline": rollout_workflow_baseline(),
        "shell_entrypoints": rollout_shell_entrypoints(case_id),
        "release_handoff": rollout_release_handoff(case_id),
        "latest_source_bundle": {
            "path": f"{contracts_root}/source_bundle.contract.json",
            "status": "pending",
            "updated_at": _utc_date(),
        },
        "latest_outlets": {
            "path": f"{contracts_root}/outlets.normalized.json",
            "status": "pending",
            "updated_at": _utc_date(),
        },
        "latest_workflow_run": {
            "path": f"{contracts_root}/workflow_run.json",
            "run_id": f"{case_id}-hydrodesk-triad-bootstrap",
            "status": "pending",
            "updated_at": _utc_date(),
        },
        "latest_review_bundle": {
            "path": f"{contracts_root}/review_bundle.json",
            "review_id": f"review-{case_id}-hydrodesk-triad-bootstrap",
            "status": "pending",
            "updated_at": _utc_date(),
        },
        "latest_release_manifest": {
            "path": f"{contracts_root}/release_manifest.json",
            "release_id": f"release-{case_id}-hydrodesk-bootstrap",
            "status": "pending",
            "updated_at": _utc_date(),
        },
        "latest_source_import_session": {
            "path": f"{contracts_root}/source_import_session.latest.json",
            "status": "pending",
            "updated_at": _utc_date(),
        },
        "metadata": {
            "updated_at": _utc_date(),
            "owner_scope": "program",
            "notes": [
                f"编辑本文件与 Hydrology/configs/{case_id}.yaml 完成案例定义；勿在编排脚本中写死本案例分支",
            ],
        },
    }


def _manifest_yaml(case_id: str, display_name: str) -> str:
    payload = rollout_manifest_payload(case_id, display_name)
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _links_yaml(case_id: str, *, raw_root: str = "", raw_root_purpose: str = "原始资料入口") -> str:
    payload = {"links": rollout_links(case_id, raw_root=raw_root, raw_root_purpose=raw_root_purpose)}
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _hydrology_yaml(case_id: str, display_name: str, project_type: str) -> str:
    return f"""case_id: {case_id}
display_name: {display_name}
project_type: {project_type}
scan_dirs: []
target_stations: []
scan_extensions:
  - .json
  - .csv
  - .sqlite3
  - .db
  - .txt
  - .xlsx
dem_path: ''
river_network_path: ''
source_bundle_path: ''
case_manifest_path: cases/{case_id}/contracts/case_manifest.json
topology_json_paths: []
sqlite_paths: []
output_dir: cases/{case_id}/source_selection/product_outputs
validation:
  lat_range: []
  lon_range: []
  outlier_threshold_deg: 1.5
  min_precision_digits: 2
"""


def _case_manifest_json(case_id: str, display_name: str, project_type: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "display_name": display_name,
        "project_type": project_type,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "1.0",
        "notes": "scaffold_new_case.py bootstrap; replace with authoritative case manifest when data is ready",
    }


def register_case_in_loop_config(case_id: str, config_path: Path) -> bool:
    """将 case_id 追加到 case_selection.case_ids（若尚不存在）。返回是否写入文件。"""
    path = config_path.resolve()
    cfg = load_loop_yaml(WORKSPACE, path)
    sel = cfg.setdefault("case_selection", {})
    if not isinstance(sel, dict):
        sel = {}
        cfg["case_selection"] = sel
    ids = sel.get("case_ids")
    if not isinstance(ids, list):
        ids = []
    if case_id in ids:
        return False
    ids.append(case_id)
    sel["case_ids"] = ids
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return True


def run_scaffold(
    case_id: str,
    display_name: str,
    project_type: str,
    *,
    dry_run: bool,
    register_loop: bool,
    loop_config: Path,
    force: bool,
) -> dict[str, Any]:
    if not CASE_ID_RE.match(case_id):
        raise ValueError(f"invalid case_id {case_id!r}: use lowercase a-z, digits, underscore, 2–64 chars")

    case_root = WORKSPACE / "cases" / case_id
    contracts = case_root / "contracts"
    ingest_raw = case_root / "ingest" / "raw"
    outputs = case_root / "source_selection" / "product_outputs"
    hydrology_cfg = WORKSPACE / "Hydrology" / "configs" / f"{case_id}.yaml"

    planned = {
        "case_id": case_id,
        "paths": [
            str(case_root.relative_to(WORKSPACE) / "manifest.yaml"),
            str(case_root.relative_to(WORKSPACE) / "links.yaml"),
            str(contracts.relative_to(WORKSPACE) / "case_manifest.json"),
            str(ingest_raw.relative_to(WORKSPACE) / ".gitkeep"),
            str(hydrology_cfg.relative_to(WORKSPACE)),
        ],
        "dry_run": dry_run,
        "register_loop": register_loop,
    }

    if case_root.exists() and not force:
        raise FileNotFoundError(f"cases/{case_id} already exists (use --force to allow overwrite of scaffold files only)")

    if dry_run:
        return {**planned, "status": "dry_run"}

    case_root.mkdir(parents=True, exist_ok=True)
    contracts.mkdir(parents=True, exist_ok=True)
    ingest_raw.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)

    gitkeep = ingest_raw / ".gitkeep"
    if not gitkeep.is_file():
        gitkeep.write_text(
            "# Raw ingestion slot (see hydrodesk_shell.knowledge_lint.raw_dir_rel).\n"
            "# Uncompiled sources here; compiled / contract outputs → cases/<case_id>/contracts/.\n",
            encoding="utf-8",
        )

    manifest_path = case_root / "manifest.yaml"
    manifest_path.write_text(_manifest_yaml(case_id, display_name), encoding="utf-8")

    links_path = case_root / "links.yaml"
    links_path.write_text(_links_yaml(case_id), encoding="utf-8")

    cm_path = contracts / "case_manifest.json"
    cm_path.write_text(
        json.dumps(_case_manifest_json(case_id, display_name, project_type), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    hydrology_cfg.write_text(_hydrology_yaml(case_id, display_name, project_type), encoding="utf-8")

    reg_ok = False
    if register_loop:
        reg_ok = register_case_in_loop_config(case_id, loop_config)

    return {
        **planned,
        "status": "created",
        "loop_config_updated": reg_ok,
        "next_steps": [
            f"将原始剪藏/PDF/笔记放入 cases/{case_id}/ingest/raw/，再由 Agent 编译进 contracts/Markdown",
            f"编辑 cases/{case_id}/manifest.yaml 填写 raw_root、latest_source_bundle 等",
            f"完善 Hydrology/configs/{case_id}.yaml 中 scan_dirs、topology 等",
            "若未勾选 register-loop：手动将 case_id 加入 hydrodesk_autonomous_waternet_e2e_loop.yaml 的 case_selection.case_ids",
            "在 HydroDesk 项目中心刷新工程列表",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new Hydrology/HydroDesk case under cases/<id>/")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--display-name", required=True, help="案例中文或英文显示名")
    parser.add_argument(
        "--project-type",
        default="canal",
        choices=["canal", "cascade_hydro", "basin", "generic"],
        help="写入 case_manifest 与 Hydrology 配置（可后续手改）",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--register-loop",
        action="store_true",
        help=f"将 case_id 追加到主闭环 YAML case_selection.case_ids（默认文件 {DEFAULT_LOOP_CONFIG.name}）",
    )
    parser.add_argument("--loop-config", type=Path, default=DEFAULT_LOOP_CONFIG)
    parser.add_argument("--force", action="store_true", help="若目录已存在仍写入骨架文件（谨慎）")
    args = parser.parse_args()

    try:
        out = run_scaffold(
            args.case_id.strip(),
            args.display_name.strip(),
            args.project_type,
            dry_run=args.dry_run,
            register_loop=args.register_loop,
            loop_config=args.loop_config,
            force=args.force,
        )
    except (ValueError, FileNotFoundError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, **out}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
