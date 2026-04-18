#!/usr/bin/env python3
"""固知 (GuZhi) — 知识固化与资产管理

HydroMind 水智工坊 · Agent #10

知识固化工作流 — 把所有合约中发现的工程知识持久化到 case YAML。

三层架构：
  Layer 0  指针层（scan_dirs, sqlite_paths ...）     — 已有
  Layer 1  知识层（topology, turbines, calibration ...）— 本工作流写入
  Layer 2  会话层（每轮对话摘要、变更 diff）           — 本工作流追加

设计原则：
  - 只追加/更新，绝不清空
  - 多版本：YAML 备份 + 知识条目 updated_at
  - 通用：不依赖任何 case 名称，只依赖配置和合约路径
  - 幂等：相同输入多次运行结果一致
"""
from __future__ import annotations

import copy
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from workflows._shared import BASE_DIR, WORKSPACE, load_case_config


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _backup_yaml(yaml_path: Path, max_versions: int = 3) -> None:
    """保留最近 max_versions 个 YAML 备份。"""
    if not yaml_path.exists():
        return
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = yaml_path.with_suffix(f".v{ts}.yaml")
    shutil.copy2(yaml_path, backup)

    backups = sorted(yaml_path.parent.glob(f"{yaml_path.stem}.v*.yaml"))
    while len(backups) > max_versions:
        backups.pop(0).unlink()


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并 dict，override 优先。"""
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


# ─── 提取器：每个函数从特定合约中提取知识片段 ─────────────────────────────────

def _extract_topology(hp: dict) -> dict:
    """从 hydraulic_params.json 提取拓扑知识。"""
    now = _now_iso()
    src = "hydraulic_params.json"

    nodes = {}
    for name, info in hp.get("stations", {}).items():
        nodes[name] = {
            "zb": info.get("zb"),
            "lon": info.get("lon"),
            "lat": info.get("lat"),
            "type": {0: "junction", 1: "boundary_downstream", 2: "boundary_upstream"}
                .get(info.get("nodeType"), "unknown"),
            "Amin": info.get("Amin"),
            "source": src,
            "updated_at": now,
        }

    channels = []
    for ch in hp.get("channels", []):
        channels.append({
            "name": ch.get("name"),
            "node1": ch.get("node1"),
            "node2": ch.get("node2"),
            "manning_n": ch.get("manning_n"),
            "section_count": ch.get("section_count"),
            "source": src,
        })

    boundaries = {}
    for name, val in hp.get("boundaries", {}).items():
        node_info = hp.get("stations", {}).get(name, {})
        ntype = node_info.get("nodeType")
        btype = "flow" if ntype == 2 else "level"
        unit = "m3/s" if btype == "flow" else "m"
        boundaries[name] = {"type": btype, "value": val, "unit": unit}

    return {"nodes": nodes, "channels": channels, "boundaries": boundaries}


def _extract_reservoirs(hp: dict) -> dict:
    """从 hydraulic_params.json 提取水库参数。"""
    now = _now_iso()
    reservoirs = {}
    for sid, rp in hp.get("reservoir_properties", {}).items():
        if not rp.get("name"):
            continue
        has_data = any(
            rp.get(k) is not None
            for k in ("elevation", "normal_pool", "dead_pool", "installed_capacity_mw", "basin_area_km2")
        )
        if not has_data:
            continue
        reservoirs[sid] = {
            "name": rp["name"],
            "normal_pool_m": rp.get("normal_pool"),
            "dead_pool_m": rp.get("dead_pool"),
            "installed_capacity_mw": rp.get("installed_capacity_mw"),
            "basin_area_km2": rp.get("basin_area_km2"),
            "elevation_m": rp.get("elevation"),
            "source": "hydraulic_params.json",
            "updated_at": now,
        }
    return reservoirs


def _extract_turbines(hp: dict) -> dict:
    """从 hydraulic_params.json 提取水轮机。"""
    now = _now_iso()
    turbines = {}
    for station, units in hp.get("turbines", {}).items():
        turbines[station] = {
            "count": len(units),
            "units": [
                {"name": u["name"], "initial_flow_m3s": u.get("initial_value", 0.0)}
                for u in units
            ],
            "source": "hydraulic_params.json",
            "updated_at": now,
        }
    return turbines


def _extract_gates(hp: dict) -> dict:
    """从 hydraulic_params.json 提取闸门。"""
    now = _now_iso()
    gates = {}
    for station, units in hp.get("gates", {}).items():
        gates[station] = {
            "count": len(units),
            "units": [
                {"name": u["name"], "initial_opening": u.get("initial_opening", 0.0)}
                for u in units
            ],
            "source": "hydraulic_params.json",
            "updated_at": now,
        }
    return gates


def _extract_sections(hp: dict) -> dict:
    """从 hydraulic_params.json 提取断面几何汇总。"""
    total = hp.get("sections_count", 0)
    by_channel: dict[str, Any] = {}
    for ch in hp.get("channels", []):
        by_channel[ch["name"]] = {
            "count": ch.get("section_count", 0),
            "manning_n": ch.get("manning_n"),
            "source": "hydraulic_params.json",
        }
    return {"total_count": total, "by_channel": by_channel}


def _extract_basin_intervals(hp: dict) -> list:
    return hp.get("basin_intervals", [])


def _extract_calibration(contracts_dir: Path) -> dict:
    """从率定报告和精度提升报告提取 D1 率定知识。"""
    now = _now_iso()
    cal = _safe_load_json(contracts_dir / "calibration_report.latest.json")
    imp = _safe_load_json(contracts_dir / "precision_improvement.latest.json")
    d1d4 = _safe_load_json(contracts_dir / "d1d4_precision_report.latest.json")

    stations: dict[str, Any] = {}

    for s in cal.get("stations", []):
        sid = s.get("station_id", "")
        stations[sid] = {
            "name": s.get("station_name", ""),
            "model_type": s.get("model_type", ""),
            "best_params": s.get("best_params", {}),
            "cal_nse": s.get("calibration", {}).get("nse"),
            "val_nse": s.get("validation", {}).get("nse"),
            "peak_error_pct": s.get("calibration", {}).get("peak_error", {}).get("peak_error_pct"),
            "data_count": s.get("data_count"),
            "period": s.get("period", ""),
            "improved": False,
            "source": "calibration_report.latest.json",
            "updated_at": now,
        }

    for entry in imp.get("improvements", []):
        sid = entry.get("station_id", "")
        improved = entry.get("improved", {})
        if sid in stations and improved:
            stations[sid]["model_type"] = improved.get("model", stations[sid]["model_type"])
            stations[sid]["best_params"] = improved.get("best_params", stations[sid]["best_params"])
            stations[sid]["val_nse"] = improved.get("nse_val", stations[sid]["val_nse"])
            stations[sid]["improved"] = True
            stations[sid]["improvement_from"] = entry.get("original", {}).get("model", "")
            stations[sid]["source"] = "precision_improvement.latest.json"
            stations[sid]["updated_at"] = now

    for sid_key, info in d1d4.get("stations", {}).items():
        if sid_key in stations:
            if info.get("val_nse") is not None:
                stations[sid_key]["val_nse"] = info["val_nse"]
            if info.get("model"):
                stations[sid_key]["model_type"] = info["model"]
            if info.get("improved"):
                stations[sid_key]["improved"] = True
            stations[sid_key]["source"] = "d1d4_precision_report.latest.json"
            stations[sid_key]["updated_at"] = now

    overall_grade = cal.get("overall_grade", "")
    method = cal.get("model_type", "auto")

    return {
        "method": method,
        "overall_grade": overall_grade,
        "d1_score": d1d4.get("d1_score"),
        "stations": stations,
    }


def _extract_identification(contracts_dir: Path) -> dict:
    """从自主梯级报告提取 D3 辨识知识。"""
    cas = _safe_load_json(contracts_dir / "autonomous_cascade_report.latest.json")
    d1d4 = _safe_load_json(contracts_dir / "d1d4_precision_report.latest.json")

    ident_step = {}
    for step in cas.get("steps", []):
        if step.get("stage") == "identification":
            ident_step = step
            break

    stations = {}
    for name, params in ident_step.get("params", {}).items():
        stations[name] = {
            "params": params,
            "source": "autonomous_cascade_report.latest.json",
        }

    model_type = "FOPDT+IDZ"
    coverage = ident_step.get("coverage", len(stations) / max(len(stations), 1))

    return {
        "model_type": model_type,
        "coverage": coverage,
        "d3_score": d1d4.get("d3_score"),
        "stations": stations,
    }


def _extract_state_estimation(contracts_dir: Path) -> dict:
    """从 D1D4 报告提取 D4 状态估计知识。"""
    d1d4 = _safe_load_json(contracts_dir / "d1d4_precision_report.latest.json")
    return {
        "method": "EKF",
        "d4_score": d1d4.get("d4_score"),
        "sensor_coverage": 0.0,
        "rmse_m": None,
    }


def _extract_timeseries_inventory(hp: dict) -> dict:
    """从 hydraulic_params.json 提取时序数据清单。"""
    inv = hp.get("timeseries_inventory", [])
    total = len(inv)
    by_station: dict[str, list] = {}
    for entry in inv:
        sid = entry.get("station_id", "")
        by_station.setdefault(sid, []).append({
            "var": entry.get("variable"),
            "step": entry.get("time_step"),
            "n": entry.get("n_records"),
        })
    return {"total_variables": total, "by_station": by_station}


def _extract_hydro_coupling(reports_dir: Path) -> dict:
    """从水力耦合报告提取结果。"""
    hc = _safe_load_json(reports_dir / "hydro_coupling" / "hydro_coupling_summary.json")
    scenarios = {}
    raw_scenarios = hc.get("scenarios", {})
    if isinstance(raw_scenarios, dict):
        for name, info in raw_scenarios.items():
            if isinstance(info, dict):
                scenarios[name] = {
                    "peak_lateral_m3s": info.get("peak_lateral_m3s"),
                    "convergence": info.get("convergence"),
                }
    elif isinstance(raw_scenarios, list):
        for s in raw_scenarios:
            if isinstance(s, dict):
                scenarios[s.get("name", "unknown")] = {
                    "peak_lateral_m3s": s.get("peak_lateral_m3s"),
                    "convergence": s.get("convergence"),
                }
    return {
        "scenarios": scenarios,
        "data_gaps": hc.get("data_gaps", hc.get("next_steps", [])),
    }


# ─── 会话追踪 ────────────────────────────────────────────────────────────────

def _build_session_entry(
    old_knowledge: dict,
    new_knowledge: dict,
    agent: str = "cursor",
    summary: str = "",
    contracts_produced: list[str] | None = None,
    open_issues: list[str] | None = None,
) -> dict:
    """构建一条会话变更记录。"""
    key_changes = []
    for section in ["calibration", "identification", "state_estimation"]:
        old_s = old_knowledge.get(section, {}).get("stations", {})
        new_s = new_knowledge.get(section, {}).get("stations", {})
        for sid in new_s:
            for metric in ["val_nse", "cal_nse", "coverage"]:
                old_val = old_s.get(sid, {}).get(metric)
                new_val = new_s.get(sid, {}).get(metric)
                if old_val != new_val and new_val is not None:
                    key_changes.append({
                        "field": f"{section}.stations.{sid}.{metric}",
                        "old": old_val,
                        "new": new_val,
                    })

    return {
        "session_id": _now_iso().replace(":", "").replace("-", ""),
        "timestamp": _now_iso(),
        "agent": agent,
        "summary": summary or "知识固化工作流自动运行",
        "key_changes": key_changes,
        "contracts_produced": contracts_produced or [],
        "open_issues": open_issues or [],
    }


# ─── 主引擎 ──────────────────────────────────────────────────────────────────

def consolidate(
    case_id: str,
    *,
    config_path: str | None = None,
    agent: str = "cursor",
    summary: str = "",
    open_issues: list[str] | None = None,
    max_versions: int = 3,
    dry_run: bool = False,
) -> dict[str, Any]:
    """知识固化主入口。

    1. 读取 case YAML + 全部合约 JSON
    2. 通过提取器抽取各维度知识
    3. 深度合并到 YAML knowledge 层
    4. 追加会话记录
    5. 备份旧 YAML → 写入新 YAML
    """
    cfg = load_case_config(case_id, config_path)
    yaml_path = Path(config_path) if config_path else BASE_DIR / "configs" / f"{case_id}.yaml"

    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    product_dir = WORKSPACE / "cases" / case_id / "source_selection" / "product_outputs"
    pipedream_dir = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id

    hp = _safe_load_json(product_dir / "hydraulic_params.json")

    topology = _extract_topology(hp)
    reservoirs = _extract_reservoirs(hp)
    turbines = _extract_turbines(hp)
    gates = _extract_gates(hp)
    sections = _extract_sections(hp)
    basin_intervals = _extract_basin_intervals(hp)
    calibration = _extract_calibration(contracts_dir)
    identification = _extract_identification(contracts_dir)
    state_estimation = _extract_state_estimation(contracts_dir)
    ts_inventory = _extract_timeseries_inventory(hp)
    hydro_coupling = _extract_hydro_coupling(pipedream_dir)

    new_knowledge = {
        "_meta": {
            "schema_version": "2.0",
            "last_consolidated": _now_iso(),
            "consolidation_count": 0,
            "max_versions": max_versions,
        },
        "topology": topology,
        "reservoirs": reservoirs,
        "turbines": turbines,
        "gates": gates,
        "sections": sections,
        "basin_intervals": basin_intervals,
        "calibration": calibration,
        "identification": identification,
        "state_estimation": state_estimation,
        "timeseries_inventory": ts_inventory,
        "hydro_coupling": hydro_coupling,
    }

    raw_text = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""
    existing = yaml.safe_load(raw_text) or {} if raw_text else {}
    old_knowledge = existing.get("knowledge", {})

    merged_knowledge = _deep_merge(old_knowledge, new_knowledge)
    old_count = old_knowledge.get("_meta", {}).get("consolidation_count", 0)
    merged_knowledge["_meta"]["consolidation_count"] = old_count + 1

    existing_contracts = [
        p.name for p in contracts_dir.glob("*.latest.json")
    ] if contracts_dir.exists() else []

    session_entry = _build_session_entry(
        old_knowledge, merged_knowledge,
        agent=agent, summary=summary,
        contracts_produced=existing_contracts,
        open_issues=open_issues,
    )

    max_sessions = existing.get("sessions", {}).get("_meta", {}).get("max_sessions", 5)
    old_sessions = existing.get("sessions", {}).get("history", [])
    old_sessions.append(session_entry)
    while len(old_sessions) > max_sessions:
        old_sessions.pop(0)

    existing["knowledge"] = merged_knowledge
    existing["sessions"] = {
        "_meta": {"max_sessions": max_sessions},
        "history": old_sessions,
    }

    if "role_views" not in existing:
        existing["role_views"] = {
            "modeler": {
                "focus": ["calibration", "identification", "state_estimation", "hydro_coupling"],
                "detail_level": "full",
            },
            "operator": {
                "focus": ["reservoirs", "turbines", "gates", "boundaries"],
                "detail_level": "summary",
            },
            "admin": {
                "focus": ["sessions", "timeseries_inventory", "topology"],
                "detail_level": "overview",
            },
        }

    report = {
        "case_id": case_id,
        "consolidated_at": _now_iso(),
        "sections_extracted": {
            "topology_nodes": len(merged_knowledge.get("topology", {}).get("nodes", {})),
            "topology_channels": len(merged_knowledge.get("topology", {}).get("channels", [])),
            "reservoirs": len(merged_knowledge.get("reservoirs", {})),
            "turbines": sum(
                t.get("count", 0) for t in merged_knowledge.get("turbines", {}).values()
            ),
            "gates": sum(
                g.get("count", 0) for g in merged_knowledge.get("gates", {}).values()
            ),
            "sections_total": merged_knowledge.get("sections", {}).get("total_count", 0),
            "calibration_stations": len(merged_knowledge.get("calibration", {}).get("stations", {})),
            "identification_stations": len(merged_knowledge.get("identification", {}).get("stations", {})),
            "timeseries_variables": merged_knowledge.get("timeseries_inventory", {}).get("total_variables", 0),
            "basin_intervals": len(merged_knowledge.get("basin_intervals", [])),
        },
        "session_recorded": True,
        "consolidation_count": merged_knowledge["_meta"]["consolidation_count"],
        "key_changes": session_entry.get("key_changes", []),
        "yaml_path": str(yaml_path),
        "dry_run": dry_run,
    }

    if not dry_run:
        _backup_yaml(yaml_path, max_versions=max_versions)
        yaml_path.write_text(
            yaml.dump(existing, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
            encoding="utf-8",
        )
        contract_path = contracts_dir / "knowledge_consolidation.latest.json"
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    return report


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="知识固化工作流")
    parser.add_argument("--case-id", required=True, help="案例 ID")
    parser.add_argument("--config", help="YAML 配置路径")
    parser.add_argument("--agent", default="cursor", help="当前 agent 标识")
    parser.add_argument("--summary", default="", help="本轮会话摘要")
    parser.add_argument("--dry-run", action="store_true", help="仅预览不写入")
    parser.add_argument("--max-versions", type=int, default=3, help="YAML 备份版本数")
    args = parser.parse_args()

    result = consolidate(
        args.case_id,
        config_path=args.config,
        agent=args.agent,
        summary=args.summary,
        dry_run=args.dry_run,
        max_versions=args.max_versions,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
