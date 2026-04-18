#!/usr/bin/env python3
"""Export deterministic case modeling strategy recommendations.

This product answers a practical productization question:
"Given the current truth sources for a case, what model should we build now?"

It intentionally separates:
- what the case *could* become later
- what the current data truth actually supports today

No LLM is used. The decision is based on case config, control config, and
lightweight evidence signals already present in the workspace.
"""
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
from workflows._shared import load_case_config  # noqa: E402


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


def _exists(raw: Any) -> bool:
    text = str(raw or "").strip()
    return bool(text) and text.lower() != "none"


def _station_area_truth(stations: list[dict[str, Any]]) -> bool:
    for station in stations:
        if not isinstance(station, dict):
            continue
        for key in ("basin_area_km2", "control_area_km2", "drainage_area_km2", "area_km2"):
            value = station.get(key)
            if value not in (None, "", 0, 0.0):
                return True
    return False


def _source_bundle_truth(case_id: str) -> dict[str, bool]:
    bundle_path = _WORKSPACE / "cases" / case_id / "contracts" / "source_bundle.contract.json"
    if not bundle_path.is_file():
        return {
            "dem": False,
            "river_network": False,
            "wxq_model": False,
        }
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    dem = False
    river_network = False
    wxq_model = False
    for record in records:
        if not isinstance(record, dict):
            continue
        role = str(record.get("role") or "")
        artifact = record.get("artifact") or {}
        artifact_type = str(artifact.get("artifact_type") or "")
        path = str(artifact.get("path") or "").lower()
        if artifact_type in {"tif", "geotiff", "nc"} and ("dem" in role or "dem" in path):
            dem = True
        if "river" in role or "river" in path or "network" in path:
            river_network = True
        if artifact_type == "wxq_model_json":
            wxq_model = True
    return {
        "dem": dem,
        "river_network": river_network,
        "wxq_model": wxq_model,
    }


def _classify(case_id: str) -> dict[str, Any]:
    hydrology_cfg = load_case_config(case_id)
    control_json, control_yaml = _load_control_payload(case_id)
    source_bundle_truth = _source_bundle_truth(case_id)

    project_type = str(hydrology_cfg.get("project_type") or control_json.get("project_type") or "")
    stations = control_json.get("stations") or []
    model = control_yaml.get("model") or {}
    data_sources = control_yaml.get("data_sources") or {}

    reservoirs = model.get("reservoirs") or []
    actuators = model.get("actuators") or []
    catchment = ((data_sources.get("hydrology") or {}).get("catchment") or {})
    topology = ((data_sources.get("structures") or {}).get("topology") or {})
    terrain = ((data_sources.get("terrain") or {}).get("dem") or {})

    evidence = {
        "project_type": project_type,
        "has_dem_truth": _exists(hydrology_cfg.get("dem_path")) or _exists(terrain.get("path")) or source_bundle_truth["dem"],
        "has_river_network_truth": _exists(hydrology_cfg.get("river_network_path")) or _exists(topology.get("path")) or source_bundle_truth["river_network"],
        "has_catchment_truth": _exists(catchment.get("delineation_path")),
        "has_station_control_area_truth": _station_area_truth(stations),
        "has_control_topology": _exists(topology.get("path")) or source_bundle_truth["wxq_model"],
        "has_actuators": len(actuators) > 0,
        "has_reservoirs": len(reservoirs) > 0,
        "station_count": len(stations),
    }

    if evidence["has_catchment_truth"] and evidence["has_station_control_area_truth"] and evidence["has_dem_truth"]:
        strategy_key = "watershed_hydrology_hydrodynamics"
        display_name = "流域划分 + 水文模拟 + 水动力/梯级耦合"
        should_build_hydrology = True
        should_build_watershed = True
        should_build_control = evidence["has_reservoirs"] or evidence["has_actuators"]
        rationale = (
            "具备 catchment 真相、站点控制面积真相和 DEM/地形真相，当前可以建设真正的流域-水文-水动力主链。"
        )
    elif evidence["has_reservoirs"] and not evidence["has_catchment_truth"]:
        strategy_key = "cascade_hydrodynamic_operation"
        display_name = "梯级水动力 + 水库调度/运行模型"
        should_build_hydrology = False
        should_build_watershed = False
        should_build_control = True
        rationale = (
            "存在梯级/水库对象，但缺少 catchment 真相；当前应先做梯级水动力与运行调度，不应强行做流域水文模型。"
        )
    elif evidence["has_control_topology"] and evidence["has_actuators"]:
        strategy_key = "hydraulic_control_digital_twin"
        display_name = "渠道/泵闸水动力控制数字孪生"
        should_build_hydrology = False
        should_build_watershed = False
        should_build_control = True
        rationale = (
            "当前具备控制拓扑和执行器，但缺少 catchment 与站点控制面积真相；产品方向应是渠道/泵闸控制型水动力数字孪生。"
        )
    elif evidence["has_control_topology"]:
        strategy_key = "hydraulic_network_structural_model"
        display_name = "结构型水动力网络模型"
        should_build_hydrology = False
        should_build_watershed = False
        should_build_control = False
        rationale = "当前只有拓扑/结构真相，适合先做结构型水动力网络，不适合宣称已具备流域水文建模前提。"
    else:
        strategy_key = "case_entry_only"
        display_name = "案例入口整理阶段"
        should_build_hydrology = False
        should_build_watershed = False
        should_build_control = False
        rationale = "当前仅具备案例入口或零散资料，尚不足以进入模型建设。"

    blocked = []
    if not evidence["has_catchment_truth"]:
        blocked.append("缺 catchment/subbasin 真相")
    if not evidence["has_station_control_area_truth"]:
        blocked.append("缺站点控制范围/流域控制面积")
    if not evidence["has_dem_truth"]:
        blocked.append("缺 DEM/地形真相")

    return {
        "case_id": case_id,
        "strategy_key": strategy_key,
        "display_name": display_name,
        "should_build_watershed_model": should_build_watershed,
        "should_build_hydrology_model": should_build_hydrology,
        "should_build_control_model": should_build_control,
        "blocked_capabilities": blocked,
        "evidence": evidence,
        "rationale": rationale,
    }


def _batch(case_ids: list[str]) -> dict[str, Any]:
    rows = [_classify(case_id) for case_id in case_ids]
    rollup: dict[str, int] = {}
    for row in rows:
        key = str(row["strategy_key"])
        rollup[key] = rollup.get(key, 0) + 1
    return {
        "ok": True,
        "schema_version": "1.0",
        "case_ids": case_ids,
        "rollup": rollup,
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export deterministic case modeling strategy recommendations")
    parser.add_argument("--case-id", default="")
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    if args.batch:
        config_path = args.config if args.config.is_absolute() else _WORKSPACE / args.config
        cfg = load_loop_yaml(_WORKSPACE, config_path.resolve())
        case_ids = resolve_case_ids(cfg, _WORKSPACE)
        print(json.dumps(_batch(case_ids), ensure_ascii=False, indent=2))
        return 0

    case_id = str(args.case_id or "").strip()
    if not case_id:
        parser.error("请提供 --case-id，或使用 --batch")
    print(json.dumps({"ok": True, "schema_version": "1.0", "case": _classify(case_id)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
