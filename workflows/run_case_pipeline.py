"""开局 (KaiJu) — 案例初始化与配置生成

HydroMind 水智工坊 · Agent #2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
SCRIPTS_DIR = BASE_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from export_case_modeling_hints import derive_modeling_hints
from import_case_sourcebundle import import_case_sourcebundle
from workflows._shared import resolve_case_entry_inputs, run_python


WORKFLOWS_DIR = Path(__file__).resolve().parent
DEFAULT_HINTS_CONFIG = BASE_DIR / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
DEFAULT_HINTS_RULES = BASE_DIR / "configs" / "workflow_feasibility_rules.yaml"


def _canonical_contract_paths(case_manifest: str) -> dict[str, Path]:
    target = Path(case_manifest)
    try:
        manifest_path = target.resolve()
    except RuntimeError:
        manifest_path = target.absolute()
    if manifest_path.name == "case_manifest.json" and manifest_path.parent.name == "contracts":
        case_root = manifest_path.parent.parent
    else:
        case_root = manifest_path.parent
    contracts_dir = case_root / "contracts"
    return {
        "contracts_dir": contracts_dir,
        "data_pack": contracts_dir / "data_pack.latest.json",
        "parameter_governance": contracts_dir / "parameter_governance.latest.json",
        "modeling_hints": contracts_dir / "modeling_hints.latest.json",
        "workflow_run": contracts_dir / "workflow_run.json",
        "review_bundle": contracts_dir / "review_bundle.json",
        "release_manifest": contracts_dir / "release_manifest.json",
        "final_report": contracts_dir / "final_report.latest.json",
    }


def _workspace_rel_or_abs(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR.parent))
    except ValueError:
        return str(path)


def _safe_modeling_hints(case_id: str) -> dict:
    try:
        payload = derive_modeling_hints(case_id, DEFAULT_HINTS_CONFIG.resolve(), DEFAULT_HINTS_RULES.resolve())
        return payload.get("hints") or {"case_id": case_id}
    except Exception as error:
        return {
            "case_id": case_id,
            "error": str(error),
            "suggested_workflows": [],
            "graphify_supports_auto_modeling_hints": False,
            "graphify_modeling_signal_counts": {},
        }


def _command_preview(script_path: Path, args: list[str]) -> str:
    return " ".join([sys.executable, str(script_path), *[str(arg) for arg in args]])


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _display_path(path: str | Path | None) -> str | None:
    if not path:
        return None
    return _workspace_rel_or_abs(Path(path))


def _load_source_import_session_summary(case_id: str) -> dict:
    workspace = BASE_DIR.parent
    manifest_path = workspace / "cases" / case_id / "manifest.yaml"
    manifest_payload: dict = {}
    if manifest_path.is_file():
        manifest_payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    latest_block = manifest_payload.get("latest_source_import_session") or {}
    candidates: list[tuple[str, Path]] = []
    raw_latest = str(latest_block.get("path") or "").strip()
    if raw_latest:
        candidates.append(("manifest_latest", workspace / raw_latest))
    candidates.append(("contracts_default", workspace / "cases" / case_id / "contracts" / "source_import_session.latest.json"))

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
            return {
                "present": True,
                "source": source,
                "path": _workspace_rel_or_abs(path),
                "source_mode": payload.get("source_mode"),
                "record_count": payload.get("record_count"),
                "imported_at": payload.get("imported_at"),
                "scan_dirs": (((payload.get("inputs") or {}).get("scan_dirs")) or []),
                "web_seed_files": (((payload.get("inputs") or {}).get("web_seed_files")) or []),
                "sqlite_import_reason": (((payload.get("sqlite_import") or {}).get("reason"))),
                "station_topology_contract": payload.get("station_topology_contract") or ((payload.get("inputs") or {}).get("station_topology")),
                "station_topology_summary": dict(payload.get("station_topology_summary") or {}),
                "topology_status": payload.get("topology_status"),
                "station_geolocation_contract": payload.get("station_geolocation_contract") or ((payload.get("inputs") or {}).get("station_geolocation")),
                "station_geolocation_summary": dict(payload.get("station_geolocation_summary") or {}),
                "geolocation_status": payload.get("geolocation_status"),
                "station_geocode_candidates_contract": payload.get("station_geocode_candidates_contract") or ((payload.get("inputs") or {}).get("station_geocode_candidates")),
                "station_proxy_outlet_anchors_contract": payload.get("station_proxy_outlet_anchors_contract") or ((payload.get("inputs") or {}).get("station_proxy_outlet_anchors")),
                "station_proxy_outlet_anchors_summary": dict(payload.get("station_proxy_outlet_anchors_summary") or {}),
                "proxy_anchor_status": payload.get("proxy_anchor_status"),
                "station_outlet_candidates_contract": payload.get("station_outlet_candidates_contract") or ((payload.get("inputs") or {}).get("station_outlet_candidates")),
                "station_outlet_candidates_summary": dict(payload.get("station_outlet_candidates_summary") or {}),
                "outlet_candidate_status": payload.get("outlet_candidate_status"),
                "station_pre_delineation_review_contract": payload.get("station_pre_delineation_review_contract") or ((payload.get("inputs") or {}).get("station_pre_delineation_review")),
                "station_pre_delineation_review_summary": dict(payload.get("station_pre_delineation_review_summary") or {}),
                "pre_delineation_review_status": payload.get("pre_delineation_review_status"),
                "station_evidence_search_plan_contract": payload.get("station_evidence_search_plan_contract") or ((payload.get("inputs") or {}).get("station_evidence_search_plan")),
                "station_evidence_search_plan_summary": dict(payload.get("station_evidence_search_plan_summary") or {}),
                "evidence_search_plan_status": payload.get("evidence_search_plan_status"),
                "station_evidence_findings_contract": payload.get("station_evidence_findings_contract") or ((payload.get("inputs") or {}).get("station_evidence_findings")),
                "station_evidence_findings_summary": dict(payload.get("station_evidence_findings_summary") or {}),
                "evidence_findings_status": payload.get("evidence_findings_status"),
                "control_testing_readiness_contract": payload.get("control_testing_readiness_contract") or ((payload.get("inputs") or {}).get("control_testing_readiness")),
                "control_testing_readiness_summary": dict(payload.get("control_testing_readiness_summary") or {}),
                "control_testing_readiness_status": payload.get("control_testing_readiness_status"),
            }
    return {
        "present": False,
        "source": "missing",
        "path": None,
        "source_mode": None,
        "record_count": None,
        "imported_at": None,
        "scan_dirs": [],
        "web_seed_files": [],
        "sqlite_import_reason": None,
        "station_topology_contract": None,
        "station_topology_summary": {},
        "topology_status": None,
        "station_geolocation_contract": None,
        "station_geolocation_summary": {},
        "geolocation_status": None,
        "station_geocode_candidates_contract": None,
        "station_proxy_outlet_anchors_contract": None,
        "station_proxy_outlet_anchors_summary": {},
        "proxy_anchor_status": None,
        "station_outlet_candidates_contract": None,
        "station_outlet_candidates_summary": {},
        "outlet_candidate_status": None,
        "station_pre_delineation_review_contract": None,
        "station_pre_delineation_review_summary": {},
        "pre_delineation_review_status": None,
        "station_evidence_search_plan_contract": None,
        "station_evidence_search_plan_summary": {},
        "evidence_search_plan_status": None,
        "station_evidence_findings_contract": None,
        "station_evidence_findings_summary": {},
        "evidence_findings_status": None,
        "control_testing_readiness_contract": None,
        "control_testing_readiness_summary": {},
        "control_testing_readiness_status": None,
    }


def _load_web_source_session_summary(case_id: str) -> dict:
    workspace = BASE_DIR.parent
    manifest_path = workspace / "cases" / case_id / "manifest.yaml"
    manifest_payload: dict = {}
    if manifest_path.is_file():
        manifest_payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    latest_block = manifest_payload.get("latest_web_source_session") or {}
    candidates: list[tuple[str, Path]] = []
    raw_latest = str(latest_block.get("path") or "").strip()
    if raw_latest:
        candidates.append(("manifest_latest", workspace / raw_latest))
    candidates.append(("contracts_default", workspace / "cases" / case_id / "contracts" / "web_source_session.latest.json"))

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
            return {
                "present": True,
                "source": source,
                "path": _workspace_rel_or_abs(path),
                "status": payload.get("status"),
                "seed_query_count": payload.get("seed_query_count"),
                "seed_url_count": payload.get("seed_url_count"),
                "discovered_source_count": payload.get("discovered_source_count"),
                "download_file_count": payload.get("download_file_count"),
                "needs_web_fetch": payload.get("needs_web_fetch"),
                "public_data_inventory_contract": payload.get("public_data_inventory_contract"),
                "public_data_summary": dict(payload.get("public_data_summary") or {}),
            }
    return {
        "present": False,
        "source": "missing",
        "path": None,
        "status": None,
        "seed_query_count": 0,
        "seed_url_count": 0,
        "discovered_source_count": 0,
        "download_file_count": 0,
        "needs_web_fetch": False,
        "public_data_inventory_contract": None,
        "public_data_summary": {},
    }


def _load_outlets_health(outlets_path: str | Path | None) -> dict:
    if not outlets_path:
        return {"present": False, "count": None, "empty": False, "path": None}
    path = Path(outlets_path)
    if not path.is_file():
        return {"present": False, "count": None, "empty": False, "path": _workspace_rel_or_abs(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"present": True, "count": None, "empty": False, "path": _workspace_rel_or_abs(path), "invalid_json": True}
    if isinstance(payload, dict):
        raw_outlets = payload.get("outlets", payload)
        count = payload.get("count")
    else:
        raw_outlets = payload
        count = None
    if isinstance(raw_outlets, list):
        outlet_count = len(raw_outlets)
    elif isinstance(count, int):
        outlet_count = count
    else:
        outlet_count = None
    return {
        "present": True,
        "count": outlet_count,
        "empty": outlet_count == 0,
        "path": _workspace_rel_or_abs(path),
    }


def _recommended_public_data(project_type: str) -> list[str]:
    if project_type in {"canal", "pump_canal"}:
        return []
    return ["dem", "landuse", "soil", "hydrography"]


def _build_source_gap_hints(case_id: str, resolved_inputs: dict, source_import_session: dict, project_type: str) -> list[dict]:
    hints: list[dict] = []
    outlets_health = _load_outlets_health(resolved_inputs.get("outlets_json"))
    if outlets_health.get("empty"):
        public_data = _recommended_public_data(project_type)
        web_source_session = _load_web_source_session_summary(case_id)
        hints.append(
            {
                "kind": "outlets_empty",
                "summary": "Canonical outlets contract exists but contains zero delineation-ready outlets.",
                "source_contract": outlets_health.get("path"),
                "suggested_next_step": (
                    "补齐 case-local 原始资料或联网补齐公开资料后，重跑 source discovery / outlet normalization。"
                    if public_data
                    else "当前工程类型默认可先不做 hydrology；如需继续推进 outlet 相关链路，仍需补齐 case-local 或 web augmentation 资料。"
                ),
                "case_local_scan_dirs": source_import_session.get("scan_dirs") or [],
                "web_seed_files": source_import_session.get("web_seed_files") or [],
                "project_type": project_type,
                "recommended_public_data": public_data,
                "public_data_inventory_contract": web_source_session.get("public_data_inventory_contract"),
                "public_data_summary": dict(web_source_session.get("public_data_summary") or {}),
                "station_topology_contract": source_import_session.get("station_topology_contract"),
                "station_topology_summary": dict(source_import_session.get("station_topology_summary") or {}),
                "topology_status": source_import_session.get("topology_status"),
                "station_geolocation_contract": source_import_session.get("station_geolocation_contract"),
                "station_geolocation_summary": dict(source_import_session.get("station_geolocation_summary") or {}),
                "geolocation_status": source_import_session.get("geolocation_status"),
                "station_geocode_candidates_contract": source_import_session.get("station_geocode_candidates_contract"),
                "station_proxy_outlet_anchors_contract": source_import_session.get("station_proxy_outlet_anchors_contract"),
                "station_proxy_outlet_anchors_summary": dict(source_import_session.get("station_proxy_outlet_anchors_summary") or {}),
                "proxy_anchor_status": source_import_session.get("proxy_anchor_status"),
                "station_outlet_candidates_contract": source_import_session.get("station_outlet_candidates_contract"),
                "station_outlet_candidates_summary": dict(source_import_session.get("station_outlet_candidates_summary") or {}),
                "outlet_candidate_status": source_import_session.get("outlet_candidate_status"),
                "station_pre_delineation_review_contract": source_import_session.get("station_pre_delineation_review_contract"),
                "station_pre_delineation_review_summary": dict(source_import_session.get("station_pre_delineation_review_summary") or {}),
                "pre_delineation_review_status": source_import_session.get("pre_delineation_review_status"),
                "station_evidence_search_plan_contract": source_import_session.get("station_evidence_search_plan_contract"),
                "station_evidence_search_plan_summary": dict(source_import_session.get("station_evidence_search_plan_summary") or {}),
                "evidence_search_plan_status": source_import_session.get("evidence_search_plan_status"),
                "station_evidence_findings_contract": source_import_session.get("station_evidence_findings_contract"),
                "station_evidence_findings_summary": dict(source_import_session.get("station_evidence_findings_summary") or {}),
                "evidence_findings_status": source_import_session.get("evidence_findings_status"),
                "control_testing_readiness_contract": source_import_session.get("control_testing_readiness_contract"),
                "control_testing_readiness_summary": dict(source_import_session.get("control_testing_readiness_summary") or {}),
                "control_testing_readiness_status": source_import_session.get("control_testing_readiness_status"),
            }
        )
    return hints


def _preflight_stage_chain(
    *,
    args: argparse.Namespace,
    resolved_inputs: dict,
    source_import_session: dict,
    web_source_session: dict,
    paths: dict[str, Path],
) -> list[dict]:
    stage_specs: dict[str, dict] = {
        "source": {
            "kind": "entry",
            "command_step": "import_case_sourcebundle",
            "delivery_target": "锁定案例入口、标准化 source_bundle，并把 source import 会话显式暴露给主链。",
            "key_contracts": [
                {
                    "name": "case_manifest",
                    "path": _display_path(resolved_inputs.get("case_manifest")),
                    "role": "案例边界与主链入口定义",
                    "required": True,
                },
                {
                    "name": "source_bundle",
                    "path": _display_path(resolved_inputs.get("source_bundle_json")),
                    "role": "上游探源与资料聚合合同",
                    "required": True,
                },
                {
                    "name": "outlets_json",
                    "path": _display_path(resolved_inputs.get("outlets_json")),
                    "role": "流域出口/断面规范化输入",
                    "required": True,
                },
                {
                    "name": "simulation_config",
                    "path": _display_path(resolved_inputs.get("simulation_config")),
                    "role": "hydrology 阶段配置输入",
                    "required": args.phase in {"simulation", "full"},
                },
                {
                    "name": "source_import_session",
                    "path": source_import_session.get("path"),
                    "role": "记录 source 导入模式、批次与证据",
                    "required": False,
                },
            ],
        },
        "data_pack": {
            "kind": "contract",
            "command_step": "build_data_pack",
            "delivery_target": "生成统一 data_pack 合同，供 downstream 阶段稳定复用。",
            "key_contracts": [
                {
                    "name": "data_pack",
                    "path": _display_path(paths["data_pack"]),
                    "role": "source 到建模主链的标准化中枢合同",
                    "required": True,
                }
            ],
        },
        "watershed": {
            "kind": "workflow",
            "command_step": "run_watershed_delineation",
            "delivery_target": "补齐参数治理与流域工作流元数据，为 review/release 提供可追溯链路。",
            "key_contracts": [
                {
                    "name": "parameter_governance",
                    "path": _display_path(paths["parameter_governance"]),
                    "role": "多阶段参数治理合同",
                    "required": True,
                },
                {
                    "name": "workflow_run",
                    "path": _display_path(paths["workflow_run"]),
                    "role": "watershed 执行元数据与链路凭据",
                    "required": True,
                },
            ],
        },
        "hydrology": {
            "kind": "workflow",
            "command_step": "run_hydrological_simulation",
            "delivery_target": "运行 hydrology 仿真，为 review bundle 产出可审查结果。",
            "key_contracts": [
                {
                    "name": "simulation_config",
                    "path": _display_path(resolved_inputs.get("simulation_config")),
                    "role": "hydrology 仿真配置输入",
                    "required": True,
                },
                {
                    "name": "parameter_governance",
                    "path": _display_path(paths["parameter_governance"]),
                    "role": "驱动 hydrology 阶段的参数治理合同",
                    "required": True,
                },
            ],
        },
        "review": {
            "kind": "delivery",
            "command_step": "build_review_bundle",
            "delivery_target": "汇总 workflow 与仿真证据，形成 review-ready 交付包。",
            "key_contracts": [
                {
                    "name": "workflow_run",
                    "path": _display_path(paths["workflow_run"]),
                    "role": "review 汇总的流程元数据来源",
                    "required": True,
                },
                {
                    "name": "review_bundle",
                    "path": _display_path(paths["review_bundle"]),
                    "role": "审查与验收的核心交付合同",
                    "required": True,
                },
            ],
        },
        "release": {
            "kind": "delivery",
            "command_step": "build_release_manifest",
            "delivery_target": "基于 review 结论与关键治理证据生成最终 release_manifest。",
            "key_contracts": [
                {
                    "name": "review_bundle",
                    "path": _display_path(paths["review_bundle"]),
                    "role": "release 阶段复核输入",
                    "required": True,
                },
                {
                    "name": "release_manifest",
                    "path": _display_path(paths["release_manifest"]),
                    "role": "最终交付清单与归档入口",
                    "required": True,
                },
            ],
        },
        "final_report": {
            "kind": "delivery",
            "command_step": "build_final_report",
            "delivery_target": "把 readiness、review/release 结论与关键业务指标收束为统一 final_report。",
            "key_contracts": [
                {
                    "name": "review_bundle",
                    "path": _display_path(paths["review_bundle"]),
                    "role": "final report 的审查结论来源",
                    "required": True,
                },
                {
                    "name": "release_manifest",
                    "path": _display_path(paths["release_manifest"]),
                    "role": "final report 的发布结论来源",
                    "required": True,
                },
                {
                    "name": "final_report",
                    "path": _display_path(paths["final_report"]),
                    "role": "统一最终报告合同，供 HydroDesk 与验收链消费",
                    "required": True,
                },
                {
                    "name": "universal_report",
                    "path": _display_path(paths.get("universal_report", paths["contracts_dir"] / "universal_report.latest.html")),
                    "role": "动态可视化综合仿真报告",
                    "required": False,
                },
            ],
        },
    }
    phase_sequences = {
        "data-pack": ["source", "data_pack"],
        "watershed": ["source", "data_pack", "watershed"],
        "simulation": ["hydrology"],
        "hydrology_only": ["hydrology"],
        "review": ["review"],
        "release": ["release"],
        "full": ["source", "data_pack", "watershed", "hydrology", "review", "release", "final_report"],
    }
    return [
        {"stage": stage_name, **stage_specs[stage_name]}
        for stage_name in phase_sequences[args.phase]
    ]


def _flatten_critical_contracts(stage_chain: list[dict]) -> list[dict]:
    contracts: list[dict] = []
    seen: set[tuple[str, str | None]] = set()
    for stage in stage_chain:
        for contract in stage.get("key_contracts") or []:
            key = (str(contract.get("name")), contract.get("path"))
            if key in seen:
                continue
            seen.add(key)
            contracts.append(
                {
                    "name": contract.get("name"),
                    "path": contract.get("path"),
                    "role": contract.get("role"),
                    "required": bool(contract.get("required")),
                    "stage": stage.get("stage"),
                }
            )
    return contracts


def _delivery_targets(stage_chain: list[dict]) -> list[dict]:
    targets: list[dict] = []
    seen: set[str] = set()
    for stage in stage_chain:
        if stage.get("kind") != "delivery":
            continue
        stage_name = stage.get("stage")
        for contract in stage.get("key_contracts") or []:
            if contract.get("name") not in {"review_bundle", "release_manifest", "final_report", "universal_report"}:
                continue
            name = str(contract.get("name"))
            if name in seen:
                continue
            seen.add(name)
            targets.append(
                {
                    "name": name,
                    "path": contract.get("path"),
                    "stage": stage_name,
                    "goal": stage.get("delivery_target"),
                }
            )
    return targets


def _preflight_payload(
    *,
    args: argparse.Namespace,
    missing_inputs: list[str],
    sourcebundle_import: dict | None,
    source_import_session: dict,
    web_source_session: dict,
    resolved_inputs: dict,
    modeling_hints: dict,
    modeling_hints_path: Path,
    deferred_stages: list[str],
    planned_commands: list[dict[str, str]],
    stage_chain: list[dict],
    source_gap_hints: list[dict],
) -> dict:
    return {
        "ok": not missing_inputs,
        "case_id": args.case_id,
        "phase": args.phase,
        "missing_inputs": missing_inputs,
        "sourcebundle_import": sourcebundle_import,
        "source_import_session": source_import_session,
        "web_source_session": web_source_session,
        "resolved_inputs": resolved_inputs,
        "modeling_hints": modeling_hints,
        "modeling_hints_path": str(modeling_hints_path),
        "deferred_stages": deferred_stages,
        "entrypoint_scope": "source_to_delivery" if args.phase == "full" else "phase_preflight",
        "source_gap_hints": source_gap_hints,
        "stage_chain": stage_chain,
        "critical_contracts": _flatten_critical_contracts(stage_chain),
        "delivery_targets": _delivery_targets(stage_chain),
        "planned_commands": planned_commands,
    }


def _stage_guidance(modeling_hints: dict, stage: str) -> dict:
    return ((modeling_hints.get("workflow_recommendations") or {}).get("stage_activation_guidance") or {}).get(stage) or {}


def _should_import_sourcebundle(phase: str) -> bool:
    return phase in {"data-pack", "watershed", "simulation", "review", "release", "full"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic orchestrator for Hydrology case workflows.")
    parser.add_argument("--case-id", required=True, help="Case identifier")
    parser.add_argument("--case-manifest", default=None, help="Case manifest path")
    parser.add_argument("--source-bundle-json", default=None, help="SourceBundle contract JSON")
    parser.add_argument("--outlets-json", default=None, help="Canonical outlets JSON")
    parser.add_argument("--basin-validation-json", default=None, help="Strict basin validation report")
    parser.add_argument("--simulation-config", default=None, help="Simulation config for hydrological_simulation")
    parser.add_argument("--phase", choices=["data-pack", "watershed", "simulation", "review", "release", "full", "hydrology_only"], default="full")
    parser.add_argument("--version", default="v0.1.0", help="Release version for release/full phases")
    parser.add_argument("--strict", action="store_true", help="Enable strict data-pack checks")
    parser.add_argument("--dry-run", action="store_true", help="Emit non-blocking preflight JSON instead of executing")
    parser.add_argument("--respect-stage-guidance", action="store_true", help="Abort deferred stages when workflow recommendations explicitly mark them as deferred")
    parser.add_argument("--no-auto-import-sourcebundle", action="store_true", help="Skip the minimal P1 sourcebundle canonicalization step")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    sourcebundle_import = None
    if _should_import_sourcebundle(args.phase) and not args.no_auto_import_sourcebundle:
        sourcebundle_import = import_case_sourcebundle(args.case_id)
    source_import_session = _load_source_import_session_summary(args.case_id)
    web_source_session = _load_web_source_session_summary(args.case_id)
    resolved_inputs = resolve_case_entry_inputs(
        args.case_id,
        case_manifest=args.case_manifest,
        source_bundle_json=args.source_bundle_json,
        outlets_json=args.outlets_json,
        simulation_config=args.simulation_config,
    )
    modeling_hints = _safe_modeling_hints(args.case_id)
    deferred_stages = list(((modeling_hints.get("workflow_recommendations") or {}).get("deferred_stages") or []))
    missing_inputs: list[str] = []
    manifest_path = Path(resolved_inputs["case_manifest"]) if resolved_inputs.get("case_manifest") else BASE_DIR.parent / "cases" / args.case_id / "manifest.yaml"
    if not manifest_path.is_file():
        missing_inputs.append("manifest_yaml")
    if not resolved_inputs["source_bundle_json"]:
        missing_inputs.append("source_bundle")
    if not resolved_inputs["outlets_json"]:
        missing_inputs.append("outlets_json")
    project_type = str((modeling_hints or {}).get("project_type") or "").strip()
    source_gap_hints = _build_source_gap_hints(args.case_id, resolved_inputs, source_import_session, project_type)
    if source_gap_hints:
        missing_inputs.extend([hint["kind"] for hint in source_gap_hints if hint.get("kind") not in missing_inputs])
    if args.phase in {"simulation", "full"} and not resolved_inputs["simulation_config"]:
        missing_inputs.append("simulation_config")
    paths = _canonical_contract_paths(resolved_inputs["case_manifest"])
    contracts_dir = paths["contracts_dir"]
    data_pack = paths["data_pack"]
    parameter_governance = paths["parameter_governance"]
    modeling_hints_path = paths["modeling_hints"]
    workflow_run = paths["workflow_run"]
    review_bundle = paths["review_bundle"]
    release_manifest = paths["release_manifest"]
    final_report = paths["final_report"]
    stage_chain = _preflight_stage_chain(
        args=args,
        resolved_inputs=resolved_inputs,
        source_import_session=source_import_session,
        web_source_session=web_source_session,
        paths=paths,
    )
    planned_commands: list[dict[str, str]] = []

    if not args.dry_run:
        _write_json(modeling_hints_path, modeling_hints)

    if args.phase in {"data-pack", "watershed", "simulation", "review", "release", "full"}:
        cli_args = [
            "--case-manifest",
            resolved_inputs["case_manifest"],
            "--source-bundle-json",
            resolved_inputs["source_bundle_json"],
            "--outlets-json",
            resolved_inputs["outlets_json"],
            "--output",
            str(data_pack),
        ]
        if args.basin_validation_json:
            cli_args.extend(["--basin-validation-json", args.basin_validation_json])
        if resolved_inputs.get("simulation_config"):
            cli_args.extend(["--simulation-config", resolved_inputs["simulation_config"]])
        if args.strict:
            cli_args.append("--strict")
        planned_commands.append(
            {
                "step": "build_data_pack",
                "command": _command_preview(WORKFLOWS_DIR / "build_data_pack.py", cli_args),
            }
        )
        if not args.dry_run:
            run_python(WORKFLOWS_DIR / "build_data_pack.py", cli_args)
        if args.phase == "data-pack":
            if args.dry_run:
                print(
                    json.dumps(
                        _preflight_payload(
                            args=args,
                            missing_inputs=missing_inputs,
                            sourcebundle_import=sourcebundle_import,
                            source_import_session=source_import_session,
                            web_source_session=web_source_session,
                            resolved_inputs=resolved_inputs,
                            modeling_hints=modeling_hints,
                            modeling_hints_path=modeling_hints_path,
                            deferred_stages=deferred_stages,
                            planned_commands=planned_commands,
                            stage_chain=stage_chain,
                            source_gap_hints=source_gap_hints,
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return

    if args.phase in {"watershed", "simulation", "review", "release", "full"}:
        governance_args = [
            "--case-id",
            args.case_id,
            "--case-manifest",
            resolved_inputs["case_manifest"],
            "--data-pack-json",
            str(data_pack),
        ]
        planned_commands.append(
            {
                "step": "build_parameter_governance",
                "command": _command_preview(
                    WORKFLOWS_DIR / "build_parameter_governance.py",
                    governance_args,
                ),
            }
        )
        watershed_args = [
            "--case-id",
            args.case_id,
            "--data-pack-json",
            str(data_pack),
            "--parameter-governance-json",
            str(parameter_governance),
            "--metadata-out",
            str(workflow_run),
        ]
        planned_commands.append(
            {
                "step": "run_watershed_delineation",
                "command": _command_preview(
                    WORKFLOWS_DIR / "run_watershed_delineation.py",
                    watershed_args,
                ),
            }
        )
        if not args.dry_run:
            run_python(WORKFLOWS_DIR / "build_parameter_governance.py", governance_args)
            run_python(WORKFLOWS_DIR / "run_watershed_delineation.py", watershed_args)
        if args.phase == "watershed":
            if args.dry_run:
                print(
                    json.dumps(
                        _preflight_payload(
                            args=args,
                            missing_inputs=missing_inputs,
                            sourcebundle_import=sourcebundle_import,
                            source_import_session=source_import_session,
                            web_source_session=web_source_session,
                            resolved_inputs=resolved_inputs,
                            modeling_hints=modeling_hints,
                            modeling_hints_path=modeling_hints_path,
                            deferred_stages=deferred_stages,
                            planned_commands=planned_commands,
                            stage_chain=stage_chain,
                            source_gap_hints=source_gap_hints,
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return

    if args.phase in {"simulation", "full", "hydrology_only"}:
        if not resolved_inputs["simulation_config"]:
            raise ValueError("simulation config could not be resolved from args or case config")
        hydrology_guidance = _stage_guidance(modeling_hints, "hydrology")
        if args.respect_stage_guidance and hydrology_guidance.get("status") == "deferred":
            raise ValueError("hydrology stage deferred by stage guidance")
        simulation_args = [
            "--case-id",
            args.case_id,
            "--data-pack-json",
            str(data_pack),
            "--simulation-config",
            resolved_inputs["simulation_config"],
            "--parameter-governance-json",
            str(parameter_governance),
        ]
        planned_commands.append(
            {
                "step": "run_hydrological_simulation",
                "command": _command_preview(WORKFLOWS_DIR / "run_hydrological_simulation.py", simulation_args),
            }
        )
        if not args.dry_run:
            run_python(WORKFLOWS_DIR / "run_hydrological_simulation.py", simulation_args)
        if args.phase in {"simulation", "hydrology_only"}:
            if args.dry_run:
                print(
                    json.dumps(
                        _preflight_payload(
                            args=args,
                            missing_inputs=missing_inputs,
                            sourcebundle_import=sourcebundle_import,
                            source_import_session=source_import_session,
                            web_source_session=web_source_session,
                            resolved_inputs=resolved_inputs,
                            modeling_hints=modeling_hints,
                            modeling_hints_path=modeling_hints_path,
                            deferred_stages=deferred_stages,
                            planned_commands=planned_commands,
                            stage_chain=stage_chain,
                            source_gap_hints=source_gap_hints,
                        ),
                        ensure_ascii=False,
                        indent=2
                    )
                )
            return

    if args.phase in {"review", "release", "full"}:
        review_args = ["--case-id", args.case_id, "--run-id", f"{args.case_id}-watershed", "--review-output", str(review_bundle)]
        planned_commands.append(
            {
                "step": "build_review_bundle",
                "command": _command_preview(WORKFLOWS_DIR / "build_review_bundle.py", review_args),
            }
        )
        if not args.dry_run:
            run_python(WORKFLOWS_DIR / "build_review_bundle.py", review_args)
        if args.phase == "review":
            if args.dry_run:
                print(
                    json.dumps(
                        _preflight_payload(
                            args=args,
                            missing_inputs=missing_inputs,
                            sourcebundle_import=sourcebundle_import,
                            source_import_session=source_import_session,
                            web_source_session=web_source_session,
                            resolved_inputs=resolved_inputs,
                            modeling_hints=modeling_hints,
                            modeling_hints_path=modeling_hints_path,
                            deferred_stages=deferred_stages,
                            planned_commands=planned_commands,
                            stage_chain=stage_chain,
                            source_gap_hints=source_gap_hints,
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return

    if args.phase in {"release", "full"}:
        governance_artifacts = [
            contracts_dir / "parameter_inventory.latest.json",
            contracts_dir / "sensitivity_report.latest.json",
            contracts_dir / "candidate_set.latest.json",
            contracts_dir / "parameter_governance.latest.json",
            contracts_dir / "modeling_hints.latest.json",
            contracts_dir / "error_model_spec.latest.json",
            contracts_dir / "correction_parameter_catalog.latest.json",
            contracts_dir / "correction_activation_record.latest.json",
        ]
        release_args = [
            "--case-id",
            args.case_id,
            "--version",
            args.version,
            "--workflow-run",
            str(workflow_run),
            "--review-bundle",
            str(review_bundle),
        ]
        for artifact in governance_artifacts:
            release_args.extend(["--artifact", _workspace_rel_or_abs(artifact)])
        release_command_args = [*release_args, "--output", str(release_manifest)]
        planned_commands.append(
            {
                "step": "build_release_manifest",
                "command": _command_preview(WORKFLOWS_DIR / "build_release_manifest.py", release_command_args),
            }
        )
        final_report_args = [
            "--case-id",
            args.case_id,
            "--workflow-run",
            str(workflow_run),
            "--review-bundle",
            str(review_bundle),
            "--release-manifest",
            str(release_manifest),
            "--output",
            str(final_report),
        ]
        planned_commands.append(
            {
                "step": "build_final_report",
                "command": _command_preview(WORKFLOWS_DIR / "build_final_report.py", final_report_args),
            }
        )

        npz_path = BASE_DIR.parent / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / args.case_id / "sim_data.npz"
        universal_report_html = contracts_dir / "universal_report.latest.html"
        universal_report_args = [
            "--case-id",
            args.case_id,
            "--npz-path",
            str(npz_path),
            "--output-path",
            str(universal_report_html),
        ]
        planned_commands.append(
            {
                "step": "generate_universal_report",
                "command": _command_preview(WORKFLOWS_DIR / "generate_universal_report.py", universal_report_args),
            }
        )

        if args.dry_run:
            print(
                json.dumps(
                    _preflight_payload(
                        args=args,
                        missing_inputs=missing_inputs,
                        sourcebundle_import=sourcebundle_import,
                        source_import_session=source_import_session,
                        web_source_session=web_source_session,
                        resolved_inputs=resolved_inputs,
                        modeling_hints=modeling_hints,
                        modeling_hints_path=modeling_hints_path,
                        deferred_stages=deferred_stages,
                        planned_commands=planned_commands,
                        stage_chain=stage_chain,
                        source_gap_hints=source_gap_hints,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        run_python(WORKFLOWS_DIR / "build_release_manifest.py", release_command_args)
        run_python(WORKFLOWS_DIR / "build_final_report.py", final_report_args)
        run_python(WORKFLOWS_DIR / "generate_universal_report.py", universal_report_args)


if __name__ == "__main__":
    main()
