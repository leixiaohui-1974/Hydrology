#!/usr/bin/env python3
"""探源 (TanYuan) — 数据勘探与知识发现

Hyd6: 1D水力学模型知识挖掘工作流 — 直接从原始模型 JSON 提取全量参数到 Case YAML。

与 run_knowledge_consolidate.py 的区别：
  consolidate  ← 从合约 JSON 提取（已运行模型产出的知识）
  1d_miner     ← 从原始模型文件提取（历史资产中的工程知识）

支持：
  - 多模型版本对比（同一案例可能有多个 .json 模型文件）
  - 自动提取：节点、河段、断面、水轮机（含特性曲线）、闸门（含过流参数）、泵站、虹吸管
  - 提取结果存入 case YAML knowledge.model_versions[] 层
  - 批量模式：一次处理一个案例的所有 topology_json_paths

Usage:
    python3 run_knowledge_miner.py --case-id zhongxian
    python3 run_knowledge_miner.py --case-id all
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

try:
    import rasterio
except ImportError:
    rasterio = None

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import load_case_config


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _backup_yaml(yaml_path: Path, max_versions: int = 3) -> None:
    if not yaml_path.exists():
        return
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = yaml_path.with_suffix(f".v{ts}.yaml")
    shutil.copy2(yaml_path, backup)
    backups = sorted(yaml_path.parent.glob(f"{yaml_path.stem}.v*.yaml"))
    while len(backups) > max_versions:
        backups.pop(0).unlink()


def _safe_load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


# ── 单模型文件提取 ────────────────────────────────────────────────────────────

def _unwrap_model_json(raw: Any) -> dict:
    """模型 JSON 可能被项目名包裹，自动解包。"""
    if isinstance(raw, dict):
        if "baseData" in raw:
            return raw
        for key, val in raw.items():
            if isinstance(val, dict) and "baseData" in val:
                return val
        return raw
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        for item in raw:
            if "baseData" in item:
                return item
            inner = item.get("model_info", item)
            if isinstance(inner, dict) and "baseData" in inner:
                return inner
    return {}


def extract_from_model_json(model_path: Path) -> dict[str, Any]:
    """从单个 1D模型 JSON 提取全量知识。"""
    raw = _safe_load_json(model_path)
    if not raw:
        return {"error": f"无法读取: {model_path}"}

    raw = _unwrap_model_json(raw)
    if not raw.get("baseData"):
        return {"error": f"非 1D模型 格式或无 baseData: {model_path.name}"}

    base = raw.get("baseData", {})
    init = raw.get("initialData", {})
    now = _now_iso()
    source = model_path.name

    nodes = _extract_nodes(base, init, source, now)
    channels = _extract_channels(base, source)
    turbines = _extract_turbines(base, init, source, now)
    gates = _extract_gates(base, init, source, now)
    pumps = _extract_pumps(base, init, source, now)
    siphons = _extract_siphons(base, source, now)
    sections_summary = _extract_sections_summary(base, source)
    boundaries = _extract_boundaries(base, init, source)
    curves = _extract_curves(base, source, now)

    return {
        "model_file": str(model_path.relative_to(WORKSPACE)) if model_path.is_relative_to(WORKSPACE) else str(model_path),
        "extracted_at": now,
        "source": source,
        "nodes": nodes,
        "channels": channels,
        "turbines": turbines,
        "gates": gates,
        "pumps": pumps,
        "siphons": siphons,
        "sections_summary": sections_summary,
        "boundaries": boundaries,
        "curves": curves,
        "stats": {
            "n_nodes": len(nodes),
            "n_channels": len(channels),
            "n_turbines": sum(t.get("count", 0) for t in turbines.values()),
            "n_gates": sum(g.get("count", 0) for g in gates.values()),
            "n_pumps": sum(p.get("count", 0) for p in pumps.values()),
            "n_siphons": len(siphons),
            "n_curves": len(curves),
        },
    }


def _extract_nodes(base: dict, init: dict, source: str, now: str) -> dict:
    nodes = {}
    raw_nodes = base.get("nodes", {})
    boundaries_init = init.get("boundaries", {})

    if isinstance(raw_nodes, dict):
        items = raw_nodes.items()
    elif isinstance(raw_nodes, list):
        items = ((n.get("name", f"node_{i}"), n) for i, n in enumerate(raw_nodes) if isinstance(n, dict))
    else:
        return nodes

    for name, n in items:
        if not isinstance(n, dict):
            continue
        ntype = n.get("nodeType", 0)
        nodes[name] = {
            "zb": n.get("zb"),
            "x": n.get("x"),
            "y": n.get("y"),
            "Amin": n.get("Amin"),
            "nodeType": ntype,
            "type_label": {0: "junction", 1: "boundary_downstream", 2: "boundary_upstream"}.get(ntype, "unknown"),
            "boundary_value": boundaries_init.get(name),
            "source": source,
            "updated_at": now,
        }
    return nodes


def _iter_items(raw, fallback_name_key="name") -> list[tuple[str, dict]]:
    """统一处理 dict 或 list 格式的 baseData 子集。"""
    if isinstance(raw, dict):
        return [(k, v) for k, v in raw.items() if isinstance(v, dict)]
    if isinstance(raw, list):
        return [(item.get(fallback_name_key, f"item_{i}"), item) for i, item in enumerate(raw) if isinstance(item, dict)]
    return []


def _extract_channels(base: dict, source: str) -> list:
    channels = []
    for name, ch in _iter_items(base.get("channels", {})):
        sec_names = ch.get("sec_names", [])
        channels.append({
            "name": name,
            "node1": ch.get("node1", ""),
            "node2": ch.get("node2", ""),
            "manning_n": ch.get("nc"),
            "section_count": len(sec_names),
            "source": source,
        })
    return channels


def _extract_turbines(base: dict, init: dict, source: str, now: str) -> dict:
    turbines_by_station: dict[str, Any] = {}
    init_turbines = init.get("turbines", {})

    for name, t in _iter_items(base.get("turbines", {})):
        station = _infer_station(name)
        if station not in turbines_by_station:
            turbines_by_station[station] = {"count": 0, "units": [], "source": source, "updated_at": now}

        unit_info: dict[str, Any] = {
            "name": name,
            "initial_flow_m3s": init_turbines.get(name, 0.0),
        }
        curve_ref = t.get("curve")
        if curve_ref:
            unit_info["curve_ref"] = curve_ref
        zb = t.get("zb")
        if zb is not None:
            unit_info["zb"] = zb

        turbines_by_station[station]["units"].append(unit_info)
        turbines_by_station[station]["count"] = len(turbines_by_station[station]["units"])

    return turbines_by_station


def _extract_gates(base: dict, init: dict, source: str, now: str) -> dict:
    gates_by_station: dict[str, Any] = {}
    init_gates = init.get("gates", {})

    for name, g in _iter_items(base.get("gates", {})):
        station = _infer_station(name)
        if station not in gates_by_station:
            gates_by_station[station] = {"count": 0, "units": [], "source": source, "updated_at": now}

        unit_info: dict[str, Any] = {
            "name": name,
            "initial_opening": init_gates.get(name, 0.0),
            "zb": g.get("zb"),
            "width": g.get("b"),
            "gate_type": g.get("type"),
        }
        for coeff in ("c1", "c2", "c3", "c4"):
            if g.get(coeff) is not None:
                unit_info[coeff] = g[coeff]

        gates_by_station[station]["units"].append(unit_info)
        gates_by_station[station]["count"] = len(gates_by_station[station]["units"])

    return gates_by_station


def _extract_pumps(base: dict, init: dict, source: str, now: str) -> dict:
    pumps_by_station: dict[str, Any] = {}
    init_pumps = init.get("pumps", {})

    for name, p in _iter_items(base.get("pumps", {})):
        station = _infer_station(name)
        if station not in pumps_by_station:
            pumps_by_station[station] = {"count": 0, "units": [], "source": source, "updated_at": now}

        unit_info: dict[str, Any] = {"name": name, "initial_value": init_pumps.get(name, 0.0)}
        curve_ref = p.get("curve")
        if curve_ref:
            unit_info["curve_ref"] = curve_ref

        pumps_by_station[station]["units"].append(unit_info)
        pumps_by_station[station]["count"] = len(pumps_by_station[station]["units"])

    return pumps_by_station


def _extract_siphons(base: dict, source: str, now: str) -> dict:
    siphons = {}
    for name, s in _iter_items(base.get("siphons", {})):
        siphons[name] = {"node1": s.get("node1", ""), "node2": s.get("node2", ""), "source": source, "updated_at": now}
        for field in ("diameter", "length", "roughness", "invert_up", "invert_down"):
            if s.get(field) is not None:
                siphons[name][field] = s[field]
    return siphons


def _extract_sections_summary(base: dict, source: str) -> dict:
    by_channel: dict[str, int] = {}
    sample_yz_sizes: dict[str, int] = {}

    for name, sec in _iter_items(base.get("sections", {})):
        ch = sec.get("channel", name)
        by_channel[ch] = by_channel.get(ch, 0) + 1
        yz = sec.get("yz", [])
        if yz:
            sample_yz_sizes[name] = len(yz)

    total = sum(by_channel.values()) if by_channel else len(base.get("sections", {}))

    return {
        "total_count": total,
        "by_channel": by_channel,
        "sample_yz_point_counts": dict(list(sample_yz_sizes.items())[:5]),
        "source": source,
    }


def _extract_boundaries(base: dict, init: dict, source: str) -> dict:
    boundaries = {}
    init_boundaries = init.get("boundaries", {})
    raw_nodes = base.get("nodes", {})
    if isinstance(raw_nodes, list):
        raw_nodes = {n.get("name", ""): n for n in raw_nodes if isinstance(n, dict)}

    for name, val in init_boundaries.items():
        ntype = raw_nodes.get(name, {}).get("nodeType", 0) if isinstance(raw_nodes.get(name), dict) else 0
        boundaries[name] = {
            "nodeType": ntype,
            "type_label": {1: "level", 2: "flow"}.get(ntype, "unknown"),
            "value": val,
            "unit": "m" if ntype == 1 else "m3/s",
            "source": source,
        }

    return boundaries


def _extract_curves(base: dict, source: str, now: str) -> dict:
    curves = {}
    for name, c in _iter_items(base.get("curves", {})):
        curve_type = c.get("type", "")
        data = c.get("data", [])
        header = c.get("header", [])

        curves[name] = {
            "type": curve_type,
            "header": header,
            "data_points": len(data),
            "source": source,
            "updated_at": now,
        }
        if data and len(data) <= 5:
            curves[name]["data_sample"] = data
        elif data:
            curves[name]["data_sample"] = data[:3] + [["..."]] + data[-2:]

    return curves


def _infer_station(name: str) -> str:
    """从设备名推断所属站点。如 '瀑布沟水轮机1' → '瀑布沟'。"""
    for suffix in ("水轮机", "闸", "泵", "站", "#"):
        idx = name.find(suffix)
        if idx > 0:
            return name[:idx]
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return name


# ── 扩展资料挖掘 ──────────────────────────────────────────────────────────────

def _mine_extra_sources(scan_dirs: list[str], case_id: str, step: str = "all") -> dict[str, Any]:
    """扫描 scan_dirs 发现并归类资产，构建知识图谱实体。分为 6 大类属性：
       geospatial, geometry, boundaries, parameters, initial, telemetry.
    """
    assets: dict[str, Any] = {
        "geospatial": [], "geometry": [], "boundaries": [],
        "parameters": [], "initial": [], "telemetry": []
    }
    
    for sd in scan_dirs:
        base = WORKSPACE / sd
        if not base.exists():
            continue
        
        for f in base.rglob("*"):
            if not f.is_file():
                continue
            rel = str(f.relative_to(WORKSPACE))
            size_mb = round(f.stat().st_size / 1e6, 2)
            name_lower = f.name.lower()
            entry = {"path": rel, "size_mb": size_mb, "name": f.name}
            
            # 1. Geospatial & Topography
            if name_lower.endswith(('.tif', '.nc', '.shp', '.geojson')):
                if step in ("all", "geospatial"):
                    if name_lower.endswith('.tif') and rasterio:
                        try:
                            with rasterio.open(f) as src:
                                entry["bounds"] = [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]
                                # Simple approximation for area in degree based tif
                                dx = src.bounds.right - src.bounds.left
                                dy = src.bounds.top - src.bounds.bottom
                                entry["estimated_area_deg2"] = round(dx * dy, 2)
                        except Exception:
                            pass
                    assets["geospatial"].append(entry)

            # 2. Topology & Geometry
            elif name_lower.endswith('.json') and ('topology' in name_lower or 'section' in name_lower):
                if step in ("all", "geometry"):
                    assets["geometry"].append(entry)
            elif 'section' in name_lower and name_lower.endswith('.csv'):
                if step in ("all", "geometry"):
                    assets["geometry"].append(entry)
                    
            # 3. Boundaries
            elif ('rain' in name_lower or 'inflow' in name_lower or 'boundary' in name_lower) and name_lower.endswith('.csv'):
                if step in ("all", "boundaries"):
                    assets["boundaries"].append(entry)
                    
            # 4. Parameters
            elif ('param' in name_lower or 'curve' in name_lower or 'manning' in name_lower) and name_lower.endswith(('.csv', '.json', '.yaml')):
                if step in ("all", "parameters"):
                    assets["parameters"].append(entry)
                    
            # 5. Initial
            elif 'init' in name_lower and name_lower.endswith(('.csv', '.json')):
                if step in ("all", "initial"):
                    assets["initial"].append(entry)
                    
            # 6. Telemetry & Observation
            elif name_lower.endswith(('.sqlite3', '.db')) or ('station' in name_lower and name_lower.endswith('.csv')):
                if step in ("all", "telemetry"):
                    if name_lower.endswith('.sqlite3'):
                        try:
                            conn = sqlite3.connect(f)
                            cursor = conn.cursor()
                            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                            tables = [r[0] for r in cursor.fetchall()]
                            entry["tables"] = tables
                            for tb in tables:
                                if 'station' in tb.lower():
                                    try:
                                        cursor.execute(f"PRAGMA table_info({tb});")
                                        cols = [r[1].lower() for r in cursor.fetchall()]
                                        
                                        name_col = next((c for c in cols if c in ['station_name', 'name', 'station_id', 'id']), None)
                                        area_col = next((c for c in cols if c in ['basin_area', 'catchment_area', 'area_km2', 'basin_area_km2']), None)
                                        
                                        if name_col and area_col:
                                            cursor.execute(f"SELECT {name_col}, {area_col} FROM {tb}")
                                            rows = cursor.fetchall()
                                            station_areas = {str(r[0]): float(r[1]) for r in rows if r[1] is not None}
                                            if station_areas:
                                                entry["station_expected_areas"] = station_areas
                                                entry["expected_basin_area"] = max(station_areas.values())
                                        elif area_col:
                                            cursor.execute(f"SELECT MAX({area_col}) FROM {tb}")
                                            val = cursor.fetchone()[0]
                                            if val:
                                                entry["expected_basin_area"] = float(val)
                                    except Exception:
                                        pass
                            conn.close()
                        except Exception:
                            pass
                    assets["telemetry"].append(entry)

    # 过滤掉空的类别
    result = {k: v for k, v in assets.items() if len(v) > 0}
    if result:
        result["total_files"] = sum(len(v) for v in result.values())
    return result


def _mine_pipedream_configs(case_id: str) -> dict[str, Any]:
    """从 pipedream 项目提取历史成功配置参数。"""
    result: dict[str, Any] = {}
    pip_root = WORKSPACE / "pipedream-hydrology-integration-lab"
    cfg = load_case_config(case_id)

    yaml_paths = [
        pip_root / "hydromind_control_server" / "configs" / "cases" / f"{case_id}.yaml",
        pip_root / "kb_pipeline" / "configs" / f"{case_id}.yaml",
    ]
    json_paths = [
        pip_root / "hydromind_control_server" / "configs" / "cases" / f"{case_id}.json",
        pip_root / "research" / "model_asset_registry" / f"{case_id}_inventory.json",
        pip_root / "research" / "e2e_reports" / case_id / f"{case_id}_pipeline_summary.json",
    ]
    csv_paths = [
        pip_root / "hydromind_control_server" / "configs" / "cases" / f"{case_id}_boundary_conditions.csv",
        pip_root / "hydromind_control_server" / "configs" / "cases" / f"{case_id}_inf_params.csv",
    ]

    for yp in yaml_paths:
        if yp.exists():
            try:
                data = yaml.safe_load(yp.read_text(encoding="utf-8")) or {}
                key = yp.stem + "_" + yp.parent.parent.name
                accuracy = data.get("accuracy", {})
                wnal = data.get("wnal", {}).get("dimensions", {})
                model = data.get("model", {})
                control = data.get("control", {})
                reservoirs = data.get("model", {}).get("reservoirs", data.get("stations", []))
                result[key] = {
                    "source": str(yp.relative_to(WORKSPACE)),
                    "accuracy": accuracy if accuracy else None,
                    "wnal_scores": wnal if wnal else None,
                    "solver_dt": model.get("solver", {}).get("dt"),
                    "manning_n": model.get("hydraulics", {}).get("manning_n", {}).get("default") if isinstance(model.get("hydraulics", {}).get("manning_n"), dict) else model.get("hydraulics", {}).get("manning_n"),
                    "ekf_params": control.get("kalman", {}),
                    "mpc_params": control.get("mpc", {}),
                    "n_reservoirs": len(reservoirs) if isinstance(reservoirs, list) else 0,
                }
            except Exception:
                pass

    for jp in json_paths:
        if jp.exists():
            try:
                data = json.loads(jp.read_text(encoding="utf-8"))
                key = jp.stem
                if isinstance(data, dict):
                    result[key] = {
                        "source": str(jp.relative_to(WORKSPACE)),
                        "ekf_process_noise": data.get("ekf_process_noise"),
                        "ekf_obs_noise": data.get("ekf_obs_noise"),
                        "mpc_horizon": data.get("mpc_horizon"),
                        "boundary_head_gain": data.get("boundary_head_gain"),
                        "model_response_factor": data.get("model_response_factor"),
                        "station_gate_area": data.get("station_gate_area"),
                        "station_discharge_coeff": data.get("station_discharge_coeff"),
                        "calibration_nse": data.get("calibration", {}).get("hydro_model", {}).get("NSE"),
                        "calibration_r2": data.get("calibration", {}).get("hydro_model", {}).get("R2"),
                        "n_stations": len(data.get("stations", [])),
                    }
            except Exception:
                pass

    for cp in csv_paths:
        if cp.exists():
            try:
                first_lines = cp.open(encoding="utf-8", errors="ignore").readlines()[:3]
                result[cp.stem] = {
                    "source": str(cp.relative_to(WORKSPACE)),
                    "header": first_lines[0].strip() if first_lines else "",
                    "sample": first_lines[1].strip() if len(first_lines) > 1 else "",
                    "n_lines": sum(1 for _ in cp.open()),
                }
            except Exception:
                pass

    # 从 case 扫描目录提取 catchment_areas.json（若存在）
    catchment_json = None
    for sd in cfg.get("scan_dirs", []):
        sd_path = Path(sd) if Path(sd).is_absolute() else WORKSPACE / sd
        for p in sd_path.rglob("catchment_areas.json"):
            catchment_json = p
            break
        if catchment_json:
            break

    if catchment_json and catchment_json.exists():
        try:
            ca = json.loads(catchment_json.read_text(encoding="utf-8"))
            result["catchment_areas"] = {
                "source": str(catchment_json.relative_to(WORKSPACE)),
                "intervals": ca,
            }
        except Exception:
            pass

    return result


# ── 批量挖掘 + 写入 YAML ──────────────────────────────────────────────────────

def mine_case(
    case_id: str,
    *,
    config_path: str | None = None,
    max_versions: int = 3,
    dry_run: bool = False,
    step: str = "all",
) -> dict[str, Any]:
    """对单个案例挖掘所有 topology_json_paths，结果存入 YAML knowledge.model_versions。"""
    cfg = load_case_config(case_id, config_path)
    yaml_path = Path(config_path) if config_path else BASE_DIR / "configs" / f"{case_id}.yaml"

    model_paths = cfg.get("topology_json_paths", [])
    if not model_paths:
        return {"case_id": case_id, "status": "skip", "reason": "no topology_json_paths"}

    versions = []
    if step in ("all", "model"):
        for mp in model_paths:
            full_path = WORKSPACE / mp if not Path(mp).is_absolute() else Path(mp)
            if not full_path.exists():
                versions.append({"model_file": mp, "error": "file not found"})
                continue
            extracted = extract_from_model_json(full_path)
            versions.append(extracted)
            if "error" in extracted:
                print(f"  ✗ {mp}: {extracted['error']}")
            else:
                s = extracted["stats"]
                print(f"  ✓ {mp}: {s['n_nodes']} nodes, "
                      f"{s['n_turbines']} turbines, {s['n_gates']} gates, "
                      f"{s['n_pumps']} pumps, {s['n_curves']} curves")

    manning_comparison = _compare_manning(versions) if step in ("all", "model") else []

    scan_dirs = cfg.get("scan_dirs", [])
    extra_sources = _mine_extra_sources(scan_dirs, case_id, step=step)

    raw_text = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""
    existing = yaml.safe_load(raw_text) or {} if raw_text else {}

    knowledge = existing.setdefault("knowledge", {})
    knowledge.setdefault("_meta", {
        "schema_version": "2.0",
        "last_consolidated": "",
        "consolidation_count": 0,
        "max_versions": max_versions,
    })
    if step in ("all", "model"):
        knowledge["model_versions"] = versions
    if manning_comparison:
        knowledge["manning_n_comparison"] = manning_comparison
    if extra_sources:
        knowledge["data_sources_discovered"] = extra_sources

    pipedream_params = _mine_pipedream_configs(case_id)
    if pipedream_params:
        knowledge["pipedream_historical"] = pipedream_params
        print(f"  ✓ pipedream 历史配置: {len(pipedream_params)} 个参数集")

    knowledge["_meta"]["last_consolidated"] = _now_iso()

    report = {
        "case_id": case_id,
        "mined_at": _now_iso(),
        "model_files_processed": len(versions),
        "versions_summary": [
            {
                "file": v.get("model_file", ""),
                "stats": v.get("stats", {}),
            }
            for v in versions if "error" not in v
        ],
        "manning_comparison": manning_comparison,
        "dry_run": dry_run,
    }

    if not dry_run:
        _backup_yaml(yaml_path, max_versions=max_versions)
        yaml_path.write_text(
            yaml.dump(existing, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
            encoding="utf-8",
        )
        contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        (contracts_dir / "knowledge_mining.latest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
        )

    return report


def _compare_manning(versions: list[dict]) -> list[dict]:
    """对比多个模型版本的 Manning 糙率差异。"""
    if len(versions) < 2:
        return []
    comparisons = []
    channel_data: dict[str, list] = {}
    for v in versions:
        if "error" in v:
            continue
        src = v.get("source", "")
        for ch in v.get("channels", []):
            ch_name = ch.get("name", "")
            channel_data.setdefault(ch_name, []).append({
                "source": src,
                "manning_n": ch.get("manning_n"),
            })

    for ch_name, entries in channel_data.items():
        values = [e["manning_n"] for e in entries if e["manning_n"] is not None]
        if len(values) >= 2 and len(set(values)) > 1:
            comparisons.append({
                "channel": ch_name,
                "values": entries,
                "range": [min(values), max(values)],
                "ratio": max(values) / min(values) if min(values) > 0 else None,
            })

    return comparisons


def mine_all_cases(dry_run: bool = False, step: str = "all") -> list[dict]:
    """批量处理所有案例。"""
    configs_dir = BASE_DIR / "configs"
    results = []
    for yaml_file in sorted(configs_dir.glob("*.yaml")):
        if yaml_file.name.startswith(("case_schema", "case_knowledge_schema", "batch_")):
            continue
        if ".v" in yaml_file.stem:
            continue
        case_id = yaml_file.stem
        print(f"\n{'='*60}")
        print(f"[挖掘] {case_id}")
        print(f"{'='*60}")
        result = mine_case(case_id, config_path=str(yaml_file), dry_run=dry_run, step=step)
        results.append(result)

    return results


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="1D模型知识挖掘")
    parser.add_argument("--case-id", required=True, help="案例 ID 或 'all'")
    parser.add_argument("--config", help="YAML 配置路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预览不写入")
    parser.add_argument("--max-versions", type=int, default=3)
    parser.add_argument("--step", type=str, default="all", help="指定单独运行的一步 (e.g., geospatial, telemetry, model)")
    args = parser.parse_args()

    if args.case_id == "all":
        results = mine_all_cases(dry_run=args.dry_run, step=args.step)
        print(f"\n批量挖掘完成，共 {len(results)} 个案例 (执行步骤: {args.step})")
        for r in results:
            status = r.get("status", "done")
            n_files = r.get("model_files_processed", 0)
            print(f"  {r['case_id']}: {status} ({n_files} files)")
    else:
        result = mine_case(args.case_id, config_path=args.config, dry_run=args.dry_run, step=args.step)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
