#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
_BASE = _SCRIPTS_DIR.parent
_WORKSPACE = _BASE.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402
from workflows._shared import load_case_config, load_case_manifest  # noqa: E402


DEFAULT_CONFIG = _WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
CONTROL_CASE_DIR = _WORKSPACE / "pipedream-hydrology-integration-lab" / "hydromind_control_server" / "configs" / "cases"
CONTROL_CASE_ALIASES = {
    "yinchuojiliao": "yinchuo",
    "jiaodongtiaoshui": "jiaodong",
}


def _control_case_slug(case_id: str) -> str:
    return CONTROL_CASE_ALIASES.get(case_id, case_id)


def _load_control_payload(case_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    slug = _control_case_slug(case_id)
    json_payload: dict[str, Any] = {}
    yaml_payload: dict[str, Any] = {}

    json_path = CONTROL_CASE_DIR / f"{slug}.json"
    yaml_path = CONTROL_CASE_DIR / f"{slug}.yaml"
    if json_path.is_file():
        json_payload = json.loads(json_path.read_text(encoding="utf-8"))
    if yaml_path.is_file():
        yaml_payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return json_payload, yaml_payload


def _load_contract_json(case_id: str, filename: str) -> dict[str, Any]:
    path = _WORKSPACE / "cases" / case_id / "contracts" / filename
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_source_bundle(case_id: str) -> dict[str, Any]:
    return _load_contract_json(case_id, "source_bundle.contract.json")


def _load_source_import_session(case_id: str) -> dict[str, Any]:
    return _load_contract_json(case_id, "source_import_session.latest.json")


def _normalized_text(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text or text.lower() == "none":
        return ""
    return text


def _normalized_asset_path(raw: Any) -> str:
    return _normalized_text(raw).replace("\\", "/").lower()


def _path_aliases(raw: Any) -> set[str]:
    normalized = _normalized_asset_path(raw)
    if not normalized:
        return set()
    aliases = {normalized}
    for marker in ("${nas_root}/", "wxq-1d/", "cases/", "hydromind_control_server/", "research/"):
        if marker in normalized:
            suffix = normalized.split(marker, 1)[1]
            aliases.add(suffix)
            if marker != "${nas_root}/":
                aliases.add(marker + suffix)
    aliases.add(Path(normalized).name)
    return {alias for alias in aliases if alias}


def _index_source_bundle_records(source_bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in source_bundle.get("records") or []:
        if not isinstance(record, dict):
            continue
        artifact = record.get("artifact") or {}
        for path_key in _path_aliases(artifact.get("path")):
            index.setdefault(path_key, record)
    return index


def _add_path_asset(target: list[dict[str, Any]], asset_key: str, raw_path: Any, **extra: Any) -> None:
    path_text = _normalized_text(raw_path)
    if not path_text:
        return
    target.append({"asset_key": asset_key, "path": path_text, **extra})


def _add_count_asset(target: list[dict[str, Any]], asset_key: str, raw_count: Any, **extra: Any) -> None:
    if raw_count in (None, "", 0, 0.0):
        return
    target.append({"asset_key": asset_key, "count": raw_count, **extra})


def _add_list_asset(target: list[dict[str, Any]], asset_key: str, items: list[Any], **extra: Any) -> None:
    if not items:
        return
    target.append({"asset_key": asset_key, "count": len(items), **extra})


def _document_record(record: dict[str, Any]) -> bool:
    role = str(record.get("role") or "").lower()
    artifact = record.get("artifact") or {}
    artifact_type = str(artifact.get("artifact_type") or "").lower()
    path = str(artifact.get("path") or "").lower()
    return any(
        token in role or token in path or artifact_type == token
        for token in ("report", "doc", "pdf", "manual", "spec", "xlsx", "csv")
    )


def _category_payload(assets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "asset_count": len(assets),
        "available": bool(assets),
        "assets": assets,
    }


def _derive_authenticity(asset: dict[str, Any], source_bundle_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = str(asset.get("source") or "unknown")
    record = None
    for path_key in _path_aliases(asset.get("path") or ""):
        record = source_bundle_index.get(path_key)
        if record:
            break
    metadata = ((record or {}).get("artifact") or {}).get("metadata") or {}
    needs_review = bool((record or {}).get("needs_review"))
    semantic_status = str(metadata.get("semantic_status") or "")
    evidence = (record or {}).get("evidence") or []

    if record:
        authoritative = "authoritative" in semantic_status
        review_required = (needs_review and not authoritative) or "do_not_use" in semantic_status
        return {
            "source_type": (
                "authoritative_source"
                if authoritative
                else "review_required" if review_required else "referenced_source"
            ),
            "traceability": "evidence_backed" if evidence else "bundle_only",
            "freshness": "needs_review" if (needs_review and not authoritative) else "current",
            "coverage": "documented",
            "consistency": (
                "authoritative_with_review"
                if authoritative and needs_review
                else "review_required" if review_required else "not_checked"
            ),
            "model_readiness": "review_required" if review_required else "direct",
        }

    if source == "contracts":
        return {
            "source_type": "contract",
            "traceability": "repo_local",
            "freshness": "current",
            "coverage": "documented",
            "consistency": "not_checked",
            "model_readiness": "direct",
        }
    if source in {"manifest", "workspace"}:
        return {
            "source_type": source,
            "traceability": "repo_local",
            "freshness": "current",
            "coverage": "documented",
            "consistency": "not_checked",
            "model_readiness": "candidate",
        }
    return {
        "source_type": "configured_path",
        "traceability": "config_only",
        "freshness": "unknown",
        "coverage": "declared",
        "consistency": "not_checked",
        "model_readiness": "candidate",
    }


def _attach_authenticity(
    categories: dict[str, dict[str, Any]],
    source_bundle_index: dict[str, dict[str, Any]],
) -> None:
    for payload in categories.values():
        for asset in payload.get("assets") or []:
            asset["authenticity"] = _derive_authenticity(asset, source_bundle_index)


def _build_authenticity_summary(
    categories: dict[str, dict[str, Any]],
    source_bundle: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    configured_only_keys: set[str] = set()
    direct_keys: set[str] = set()
    review_required_keys: set[str] = set()
    risks: list[dict[str, Any]] = []
    seen_risk_keys: set[tuple[str, str, str]] = set()

    def risk_identity(asset: dict[str, Any], risk_type: str) -> tuple[str, str, str]:
        path_key = _normalized_asset_path(asset.get("path") or "")
        asset_key = str(asset.get("asset_key") or "")
        fallback = f"{asset_key}:{path_key}" if (asset_key or path_key) else json.dumps(asset, ensure_ascii=False, sort_keys=True)
        return risk_type, path_key, fallback

    def register_risk(asset: dict[str, Any], category_name: str, risk_type: str) -> None:
        identity = risk_identity(asset, risk_type)
        if identity in seen_risk_keys:
            return
        seen_risk_keys.add(identity)
        risks.append(
            {
                "risk_type": risk_type,
                "category": category_name,
                "asset_key": asset.get("asset_key"),
                "path": asset.get("path"),
            }
        )

    for category_name, payload in categories.items():
        for asset in payload.get("assets") or []:
            authenticity = asset.get("authenticity") or {}
            readiness = authenticity.get("model_readiness")
            source_type = authenticity.get("source_type")
            asset_identity = risk_identity(asset, "asset")[1:]  # path + stable fallback
            if readiness == "review_required":
                review_required_keys.add("|".join(asset_identity))
                register_risk(asset, category_name, "review_required_asset")
            elif readiness == "direct":
                direct_keys.add("|".join(asset_identity))
            else:
                configured_only_keys.add("|".join(asset_identity))
                if source_type == "configured_path":
                    register_risk(asset, category_name, "config_only_asset")

    bundle_gaps = source_bundle.get("gaps") or []
    for gap in bundle_gaps:
        register_risk({"asset_key": gap, "path": None}, "source_bundle", "missing_source_bundle_gap")

    summary = {
        "direct_assets": len(direct_keys),
        "configured_only_assets": len(configured_only_keys),
        "review_required_assets": len(review_required_keys),
        "missing_bundle_gaps": len(bundle_gaps),
    }
    return summary, risks


def _category_assets(categories: dict[str, dict[str, Any]], category_name: str) -> list[dict[str, Any]]:
    payload = categories.get(category_name) or {}
    return payload.get("assets") or []


def _has_direct_asset(categories: dict[str, dict[str, Any]], category_name: str, asset_key_fragment: str) -> bool:
    for asset in _category_assets(categories, category_name):
        if asset_key_fragment not in str(asset.get("asset_key") or ""):
            continue
        authenticity = asset.get("authenticity") or {}
        if authenticity.get("model_readiness") == "direct":
            return True
    return False


def _has_any_asset(categories: dict[str, dict[str, Any]], category_name: str) -> bool:
    payload = categories.get(category_name) or {}
    return bool(payload.get("available"))


def _has_review_required_asset(
    categories: dict[str, dict[str, Any]],
    category_name: str,
    asset_key_fragment: str,
) -> bool:
    for asset in _category_assets(categories, category_name):
        if asset_key_fragment not in str(asset.get("asset_key") or ""):
            continue
        authenticity = asset.get("authenticity") or {}
        if authenticity.get("model_readiness") == "review_required":
            return True
    return False


def _build_workflow_planning(
    categories: dict[str, dict[str, Any]],
    authenticity_summary: dict[str, Any],
    source_bundle: dict[str, Any],
    authenticity_risks: list[dict[str, Any]],
    project_type: str = "watershed",
    has_regulating_reservoir: bool = False,
) -> dict[str, Any]:
    missing_evidence: list[str] = list(source_bundle.get("gaps") or [])
    is_canal = "canal" in project_type.lower() and not has_regulating_reservoir
    if is_canal:
        missing_evidence = [gap for gap in missing_evidence if gap not in ("dem", "landuse", "rainfall", "catchment")]

    dem_ready = _has_direct_asset(categories, "terrain_and_spatial", "dem")
    catchment_ready = _has_direct_asset(categories, "hydrology", "catchment")
    rainfall_ready = _has_direct_asset(categories, "hydrology", "rainfall")
    hydraulics_ready = _has_any_asset(categories, "hydraulics")
    operation_ready = _has_any_asset(categories, "engineering_operation") or _has_any_asset(categories, "runtime_validation")

    if not is_canal:
        if not dem_ready and "dem" not in missing_evidence:
            missing_evidence.append("dem")
        if not rainfall_ready and "rainfall" not in missing_evidence:
            missing_evidence.append("rainfall")
        if not catchment_ready and "catchment" not in missing_evidence:
            missing_evidence.append("catchment")

    hydrology_ready = dem_ready and rainfall_ready and catchment_ready
    if is_canal:
        critical_hydrology_review = False
    else:
        critical_hydrology_review = any(
            [
                _has_review_required_asset(categories, "terrain_and_spatial", "dem"),
                _has_review_required_asset(categories, "hydrology", "rainfall"),
                _has_review_required_asset(categories, "hydrology", "catchment"),
            ]
        )

    recommended_path: list[str] = []
    risky_path: list[str] = []
    blocked_path: list[str] = []

    if not is_canal:
        if hydrology_ready:
            recommended_path.extend(["watershed_delineation", "hydrological_simulation"])
        else:
            blocked_path.extend(["watershed_delineation", "hydrological_simulation"])

    if hydraulics_ready or operation_ready:
        recommended_path.append("hydraulic_control_modeling")
    else:
        blocked_path.append("hydraulic_control_modeling")

    if critical_hydrology_review:
        if "watershed_delineation" in recommended_path:
            recommended_path.remove("watershed_delineation")
            risky_path.append("watershed_delineation")
        if "hydrological_simulation" in recommended_path:
            recommended_path.remove("hydrological_simulation")
            risky_path.append("hydrological_simulation")

    suggested_data_mining_tasks = [f"补充或核对 {item} 相关原始资料" for item in missing_evidence]
    model_change_advice: list[dict[str, Any]] = []
    if critical_hydrology_review:
        review_keys = [
            risk["asset_key"]
            for risk in authenticity_risks
            if risk.get("risk_type") == "review_required_asset"
            and risk.get("category") in {"terrain_and_spatial", "hydrology"}
        ]
        model_change_advice.append(
            {
                "advice_type": "data_authenticity",
                "priority": "high",
                "summary": "关键水文主链输入存在真实性复核需求，需先核对权威资料与语义口径。",
                "evidence_keys": sorted({key for key in review_keys if key}),
            }
        )

    if blocked_path and "hydraulic_control_modeling" in recommended_path:
        model_change_advice.append(
            {
                "advice_type": "workflow_strategy",
                "priority": "high",
                "summary": "当前更适合先走水动力/控制主链，待缺失的 DEM/雨量/catchment 真值补齐后再恢复流域+水文主链。",
                "evidence_keys": missing_evidence,
            }
        )

    return {
        "recommended_path": recommended_path,
        "risky_path": risky_path,
        "blocked_path": blocked_path,
        "missing_evidence": missing_evidence,
        "suggested_data_mining_tasks": suggested_data_mining_tasks,
        "model_change_advice": model_change_advice,
    }


def _build_learning_strategy(
    workflow_planning: dict[str, Any],
    is_canal: bool = False,
    has_scada: bool = False,
    case_id: str = ""
) -> dict[str, Any]:
    missing_evidence = workflow_planning.get("missing_evidence") or []
    blocked_path = workflow_planning.get("blocked_path") or []
    model_change_advice = workflow_planning.get("model_change_advice") or []
    parameter_status = "ready" if not missing_evidence and not blocked_path else "deferred"
    strategy_status = "recommended" if blocked_path else "steady"
    change_status = "required" if model_change_advice else "not_required"
    
    model_strategy_learning = {
        "status": strategy_status,
        "reason": "当前需要先调整工作流主链" if strategy_status == "recommended" else "当前工作流主链无需切换",
    }
    if is_canal:
        model_strategy_learning["calibration_strategy"] = [
            {"stage": 1, "name": "Steady-state simulation (稳态模拟)", "status": "pending"},
            {"stage": 2, "name": "Step response (阶跃响应)", "status": "pending"},
            {"stage": 3, "name": "Design condition simulation (设计工况模拟)", "status": "pending"},
            {"stage": 4, "name": "Historical condition calibration (历史工况率定)", "status": "pending"}
        ]

    filtered_scenarios_path = _WORKSPACE / "cases" / case_id / "contracts" / "filtered_historical_scenarios.latest.json"
    has_filtered_scenarios = False
    if filtered_scenarios_path.exists():
        try:
            scenarios = json.loads(filtered_scenarios_path.read_text(encoding="utf-8"))
            if isinstance(scenarios, list) and len(scenarios) > 0:
                has_filtered_scenarios = True
        except Exception:
            pass

    if has_scada and has_filtered_scenarios:
        advanced_reason = "SCADA数据与过滤后的历史场景均就绪，推荐进行高级学习"
        advanced_status = "ready"
    else:
        advanced_reason = "缺少SCADA数据或有效的历史过滤场景，暂不具备条件"
        advanced_status = "deferred"

    return {
        "parameter_learning": {
            "status": advanced_status if advanced_status == "ready" else parameter_status,
            "reason": advanced_reason if advanced_status == "ready" else ("存在关键缺数或主链阻断时，先不进入参数学习" if parameter_status == "deferred" else "关键输入已满足参数学习前提"),
        },
        "model_strategy_learning": model_strategy_learning,
        "model_change_advice": {
            "status": change_status,
            "reason": "当前存在需要显式处理的改模/改数据建议" if change_status == "required" else "当前没有新增改模建议",
        },
        "state_estimation": {
            "status": advanced_status,
            "reason": advanced_reason,
        },
        "data_assimilation": {
            "status": advanced_status,
            "reason": advanced_reason,
        },
        "parameter_estimation": {
            "status": advanced_status,
            "reason": advanced_reason,
        }
    }


def build_case_data_profile(case_id: str) -> dict[str, Any]:
    hydrology_cfg = load_case_config(case_id)
    project_type = str(hydrology_cfg.get("project_type") or "watershed").strip()
    has_regulating_reservoir = str(hydrology_cfg.get("has_regulating_reservoir", "false")).lower() == "true"
    is_canal = "canal" in project_type.lower() and not has_regulating_reservoir

    control_json, control_yaml = _load_control_payload(case_id)
    manifest_path, manifest_payload = load_case_manifest(case_id, hydrology_cfg.get("case_manifest_path"))
    source_bundle = _load_source_bundle(case_id)
    source_import_session = _load_source_import_session(case_id)
    source_bundle_index = _index_source_bundle_records(source_bundle)

    data_sources = hydrology_cfg.get("data_sources") or {}
    model = hydrology_cfg.get("model") or {}
    control_data_sources = control_yaml.get("data_sources") or {}

    terrain_assets: list[dict[str, Any]] = []
    hydrology_assets: list[dict[str, Any]] = []
    hydraulics_assets: list[dict[str, Any]] = []
    operation_assets: list[dict[str, Any]] = []
    runtime_assets: list[dict[str, Any]] = []
    document_assets: list[dict[str, Any]] = []

    terrain = data_sources.get("terrain") or {}
    hydrology = data_sources.get("hydrology") or {}
    structures = data_sources.get("structures") or {}
    scada = data_sources.get("scada") or {}
    control_terrain = control_data_sources.get("terrain") or {}
    control_hydrology = control_data_sources.get("hydrology") or {}
    control_scada = control_data_sources.get("scada") or {}
    control_structures = control_data_sources.get("structures") or {}

    _add_path_asset(terrain_assets, "dem", (terrain.get("dem") or {}).get("path"), source="case_config")
    _add_path_asset(terrain_assets, "landuse", (terrain.get("landuse") or {}).get("path"), source="case_config")
    _add_path_asset(terrain_assets, "river_network", (terrain.get("river_network") or {}).get("path"), source="case_config")
    _add_path_asset(terrain_assets, "topology_json", next(iter(hydrology_cfg.get("topology_json_paths") or []), None), source="case_config")
    _add_path_asset(terrain_assets, "catchment", (hydrology.get("catchment") or {}).get("delineation_path"), source="case_config")
    _add_path_asset(terrain_assets, "control_dem", (control_terrain.get("dem") or {}).get("path"), source="control_case")
    _add_path_asset(terrain_assets, "control_landuse", (control_terrain.get("landuse") or {}).get("path"), source="control_case")
    _add_path_asset(terrain_assets, "control_river_network", (control_terrain.get("river_network") or {}).get("path"), source="control_case")

    _add_path_asset(hydrology_assets, "rainfall", (hydrology.get("rainfall") or {}).get("path"), source="case_config")
    _add_path_asset(hydrology_assets, "evaporation", (hydrology.get("evaporation") or {}).get("path"), source="case_config")
    _add_path_asset(hydrology_assets, "soil", (hydrology.get("soil") or {}).get("path"), source="case_config")
    _add_path_asset(hydrology_assets, "catchment", (hydrology.get("catchment") or {}).get("delineation_path"), source="case_config")
    _add_path_asset(hydrology_assets, "control_rainfall", (control_hydrology.get("rainfall") or {}).get("path"), source="control_case")
    _add_path_asset(hydrology_assets, "control_evaporation", (control_hydrology.get("evaporation") or {}).get("path"), source="control_case")
    _add_path_asset(hydrology_assets, "control_soil", (control_hydrology.get("soil") or {}).get("path"), source="control_case")
    _add_path_asset(hydrology_assets, "control_catchment", (control_hydrology.get("catchment") or {}).get("delineation_path"), source="control_case")
    infiltration = hydrology.get("infiltration") or {}
    if _normalized_text(infiltration.get("model")):
        hydrology_assets.append(
            {
                "asset_key": "infiltration_model",
                "model": infiltration.get("model"),
                "params_path": _normalized_text(infiltration.get("params_path")),
                "source": "case_config",
            }
        )
    control_infiltration = control_hydrology.get("infiltration") or {}
    if _normalized_text(control_infiltration.get("model")):
        hydrology_assets.append(
            {
                "asset_key": "control_infiltration_model",
                "model": control_infiltration.get("model"),
                "params_path": _normalized_text(control_infiltration.get("params_path")),
                "source": "control_case",
            }
        )

    _add_path_asset(hydraulics_assets, "cross_sections", (structures.get("cross_sections") or {}).get("path"), source="case_config")
    _add_path_asset(hydraulics_assets, "topology", (structures.get("topology") or {}).get("path"), source="case_config")
    _add_path_asset(hydraulics_assets, "control_topology", (control_structures.get("topology") or {}).get("path"), source="control_case")
    boundary = model.get("boundary") or {}
    _add_path_asset(hydraulics_assets, "upstream_boundary_series", (boundary.get("upstream") or {}).get("series_path"), source="case_config")
    _add_path_asset(hydraulics_assets, "downstream_boundary_series", (boundary.get("downstream") or {}).get("series_path"), source="case_config")

    _add_path_asset(operation_assets, "gate_curves", (structures.get("gate_curves") or {}).get("path"), source="case_config")
    _add_count_asset(operation_assets, "gate_curve_count", (structures.get("gate_curves") or {}).get("count"), source="case_config")
    _add_count_asset(operation_assets, "control_gate_curve_count", (control_structures.get("gate_curves") or {}).get("count"), source="control_case")
    _add_path_asset(operation_assets, "pump_curves", (structures.get("pump_curves") or {}).get("path"), source="case_config")
    _add_path_asset(operation_assets, "turbine_curves", (structures.get("turbine_curves") or {}).get("path"), source="case_config")
    _add_path_asset(operation_assets, "control_turbine_curves", (control_structures.get("turbine_curves") or {}).get("path"), source="control_case")
    _add_count_asset(operation_assets, "reservoir_curve_count", (structures.get("reservoir_curves") or {}).get("count"), source="case_config")
    _add_list_asset(operation_assets, "reservoirs", model.get("reservoirs") or [], source="case_config")
    _add_list_asset(operation_assets, "actuators", model.get("actuators") or [], source="case_config")
    _add_list_asset(operation_assets, "control_stations", control_json.get("stations") or [], source="control_case")
    _add_count_asset(operation_assets, "station_gate_area", control_json.get("station_gate_area"), source="control_case")
    _add_count_asset(operation_assets, "station_discharge_coeff", control_json.get("station_discharge_coeff"), source="control_case")

    _add_path_asset(runtime_assets, "scada_database", (scada.get("database") or {}).get("path"), source="case_config")
    _add_path_asset(runtime_assets, "control_scada_database", (control_scada.get("database") or {}).get("path"), source="control_case")
    _add_path_asset(runtime_assets, "sqlite_path", next(iter(hydrology_cfg.get("sqlite_paths") or []), None), source="case_config")
    _add_path_asset(runtime_assets, "pipeline_summary", (hydrology_cfg.get("results") or {}).get("pipeline_summary"), source="case_config")
    runtime_assets.append(
        {
            "asset_key": "contracts_dir",
            "path": f"cases/{case_id}/contracts",
            "source": "workspace",
        }
    )
    if source_bundle:
        runtime_assets.append(
            {
                "asset_key": "source_bundle_contract",
                "path": f"cases/{case_id}/contracts/source_bundle.contract.json",
                "record_count": len(source_bundle.get("records") or []),
                "source": "contracts",
            }
        )
    if source_import_session:
        runtime_assets.append(
            {
                "asset_key": "source_import_session",
                "path": f"cases/{case_id}/contracts/source_import_session.latest.json",
                "record_count": source_import_session.get("record_count"),
                "imported_at": source_import_session.get("imported_at"),
                "source": "contracts",
            }
        )

    document_assets.append(
        {
            "asset_key": "case_manifest",
            "path": str(manifest_path),
            "source": "manifest",
            "has_payload": bool(manifest_payload),
        }
    )
    for raw_scan_dir in hydrology_cfg.get("scan_dirs") or []:
        _add_path_asset(document_assets, "scan_dir", raw_scan_dir, source="case_config")
    external_models = data_sources.get("external_models") or {}
    control_external_models = control_data_sources.get("external_models") or {}
    for model_name, payload in {**external_models, **control_external_models}.items():
        if not isinstance(payload, dict):
            continue
        _add_path_asset(
            document_assets,
            f"external_model:{model_name}",
            payload.get("path"),
            source="control_case" if model_name in control_external_models else "case_config",
        )
    for record in source_bundle.get("records") or []:
        if not isinstance(record, dict) or not _document_record(record):
            continue
        artifact = record.get("artifact") or {}
        _add_path_asset(
            document_assets,
            f"source_bundle:{record.get('role') or 'document'}",
            artifact.get("path"),
            source="source_bundle",
            artifact_type=artifact.get("artifact_type"),
        )

    categories = {
        "terrain_and_spatial": _category_payload(terrain_assets),
        "hydrology": _category_payload(hydrology_assets),
        "hydraulics": _category_payload(hydraulics_assets),
        "engineering_operation": _category_payload(operation_assets),
        "runtime_validation": _category_payload(runtime_assets),
        "document_knowledge": _category_payload(document_assets),
    }
    _attach_authenticity(categories, source_bundle_index)
    authenticity_summary, authenticity_risks = _build_authenticity_summary(categories, source_bundle)
    workflow_planning = _build_workflow_planning(
        categories,
        authenticity_summary,
        source_bundle,
        authenticity_risks,
        project_type,
        has_regulating_reservoir,
    )
    has_scada = any(
        asset.get("asset_key") in {"scada_database", "control_scada_database", "sqlite_path"}
        for asset in _category_assets(categories, "runtime_validation")
    )
    simulation_scenario = "historical_simulation" if has_scada else "design_scenario_simulation"

    learning_strategy = _build_learning_strategy(
        workflow_planning,
        is_canal=is_canal,
        has_scada=has_scada,
        case_id=case_id
    )
    available_categories = sum(1 for payload in categories.values() if payload["available"])

    return {
        "case_id": case_id,
        "case_characteristics": {
            "project_type": project_type,
            "simulation_scenario": simulation_scenario,
        },
        "asset_profile": {
            "categories": categories,
        },
        "authenticity_summary": authenticity_summary,
        "authenticity_risks": authenticity_risks,
        "workflow_planning": workflow_planning,
        "learning_strategy": learning_strategy,
        "coverage_summary": {
            "available_categories": available_categories,
            "total_categories": len(categories),
        },
    }


def run_export(case_id: str) -> dict[str, Any]:
    return build_case_data_profile(case_id)


def _batch(case_ids: list[str]) -> dict[str, Any]:
    return {
        "case_ids": case_ids,
        "profiles": [run_export(case_id) for case_id in case_ids],
    }


def _write_latest_profile(profile: dict[str, Any]) -> str | None:
    case_id = str(profile.get("case_id") or "").strip()
    if not case_id:
        return None
    target = _WORKSPACE / "cases" / case_id / "contracts" / "case_data_intelligence.latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target.relative_to(_WORKSPACE))


def _persist_latest(payload: dict[str, Any]) -> dict[str, Any]:
    if "profiles" in payload and isinstance(payload.get("profiles"), list):
        persisted = []
        for profile in payload["profiles"]:
            relative_path = _write_latest_profile(profile)
            if relative_path:
                profile["latest_output_path"] = relative_path
                persisted.append(relative_path)
        payload["latest_output_paths"] = persisted
        return payload

    relative_path = _write_latest_profile(payload)
    if relative_path:
        payload["latest_output_path"] = relative_path
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Export case data intelligence profile")
    parser.add_argument("--case-id")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--write-latest", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (_WORKSPACE / config_path).resolve()

    loop_yaml = load_loop_yaml(_WORKSPACE, config_path)
    case_ids = [args.case_id] if args.case_id else resolve_case_ids(loop_yaml, _WORKSPACE)
    payload = run_export(case_ids[0]) if len(case_ids) == 1 else _batch(case_ids)
    if args.write_latest:
        payload = _persist_latest(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
