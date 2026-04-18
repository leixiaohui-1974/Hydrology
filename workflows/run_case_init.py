#!/usr/bin/env python3
"""开局 (KaiJu) — 案例初始化与配置生成

HydroMind 水智工坊 · Agent #2

通用案例初始化工作流 — 从 wxq-1d 数据自动生成配置与目录结构。

设计原则：
  - 零硬编码：所有参数从数据文件自动提取
  - 通用性：同一脚本处理渠道/梯级/泵站等任意工程类型
  - 可重跑：幂等，重复运行只更新不覆盖人工修改

用法：
    # 从 wxq-1d 数据自动初始化
    python3 run_case_init.py --case-id jiaodong --wxq-dir wxq-1d/胶东调水王耨-胶莱河 --display-name 胶东调水

    # 批量初始化
    python3 run_case_init.py --batch batch_cases.yaml

    # 仅更新拓扑（不覆盖已有配置）
    python3 run_case_init.py --case-id zhongxian --wxq-dir wxq-1d/中线 --display-name 中线工程 --no-overwrite
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

sys.path.insert(0, str(BASE_DIR))
from workflows._shared import load_case_config, resolve_config_paths


# ── wxq 模型 JSON 解析 ────────────────────────────────────────────────────

def _find_wxq_model_jsons(wxq_dir: Path) -> list[Path]:
    """在 wxq 数据目录中查找模型 JSON 文件。"""
    results = []
    for p in sorted(wxq_dir.rglob("*.json")):
        if p.name.startswith(".") or "/.omc/" in str(p) or "/.claude/" in str(p):
            continue
        if "model_" in p.name and "wxq" in p.name:
            results.append(p)
    if not results:
        for p in sorted(wxq_dir.rglob("*智能体*.json")):
            results.append(p)
    return results


def _parse_wxq_model(model_path: Path) -> dict[str, Any]:
    """解析 wxq 一维模型 JSON，提取拓扑和工程参数。"""
    raw = json.loads(model_path.read_text(encoding="utf-8"))

    root_key = None
    for k, v in raw.items():
        if isinstance(v, dict) and ("baseData" in v or "solver" in v):
            root_key = k
            break
    if root_key is None:
        return {"source": str(model_path), "parse_error": "no baseData found"}

    model = raw[root_key]
    base = model.get("baseData", {})

    nodes = base.get("nodes", {})
    channels = base.get("channels", {})
    sections = base.get("sections", {})
    gates = base.get("gates", {})
    turbines = base.get("turbines", {})
    pumps = base.get("pumps", {})
    siphons = base.get("siphons", {})
    valves = base.get("valves", {})
    diversion = base.get("diversion", {})
    curves = base.get("curves", {})

    node_names = []
    node_coords = {}
    for nid, ndata in nodes.items():
        name = ndata.get("name", nid)
        node_names.append(name)
        x, y = ndata.get("x"), ndata.get("y")
        if x is not None and y is not None:
            node_coords[name] = {"lon": float(x), "lat": float(y)}
        zb = ndata.get("zb")
        if zb is not None:
            node_coords.setdefault(name, {})["zb"] = float(zb)

    has_turbines = len(turbines) > 0
    has_pumps = len(pumps) > 0
    has_gates = len(gates) > 0

    if has_turbines:
        project_type = "cascade_hydro"
    elif has_pumps:
        project_type = "pump_canal"
    else:
        project_type = "canal"

    return {
        "source": str(model_path),
        "root_key": root_key,
        "display_name": root_key,
        "project_type": project_type,
        "topology_summary": {
            "n_nodes": len(nodes),
            "n_channels": len(channels),
            "n_sections": len(sections),
            "n_gates": len(gates),
            "n_turbines": len(turbines),
            "n_pumps": len(pumps),
            "n_siphons": len(siphons),
            "n_valves": len(valves),
            "n_diversion": len(diversion),
            "n_curves": len(curves),
        },
        "station_names": node_names,
        "node_coords": node_coords,
    }


# ── 数据资产扫描 ──────────────────────────────────────────────────────────

def _scan_data_assets(wxq_dir: Path) -> dict[str, Any]:
    """扫描 wxq 目录下所有可用数据资产。"""
    assets = {
        "sqlite": [],
        "json_models": [],
        "xlsx": [],
        "shp": [],
        "tif": [],
    }
    for p in sorted(wxq_dir.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        suffix = p.suffix.lower()
        rel = str(p.relative_to(WORKSPACE))
        if suffix == ".sqlite3":
            assets["sqlite"].append(rel)
        elif suffix == ".json" and ("model_" in p.name or "智能体" in p.name):
            assets["json_models"].append(rel)
        elif suffix == ".xlsx":
            assets["xlsx"].append(rel)
        elif suffix == ".shp":
            assets["shp"].append(rel)
        elif suffix == ".tif":
            assets["tif"].append(rel)
    return assets


# ── 配置生成 ──────────────────────────────────────────────────────────────

def generate_config(
    case_id: str,
    display_name: str,
    wxq_rel_dir: str,
    models: list[dict],
    assets: dict,
) -> dict[str, Any]:
    """从解析结果生成 case_schema 兼容的 YAML 配置。"""
    all_stations = []
    for m in models:
        all_stations.extend(m.get("station_names", []))
    unique_stations = list(dict.fromkeys(all_stations))

    scan_dirs = [wxq_rel_dir]

    topology_json_paths = assets.get("json_models", [])
    sqlite_paths = assets.get("sqlite", [])

    dem_candidates = assets.get("tif", [])
    dem_path = dem_candidates[0] if dem_candidates else ""

    river_candidates = [s for s in assets.get("shp", []) if "river" in s.lower()]
    river_network_path = river_candidates[0] if river_candidates else ""

    project_type = "canal"
    for m in models:
        pt = m.get("project_type", "canal")
        if pt == "cascade_hydro":
            project_type = "cascade_hydro"
            break
        if pt == "pump_canal":
            project_type = "pump_canal"

    coords = {}
    for m in models:
        coords.update(m.get("node_coords", {}))
    lats = [c["lat"] for c in coords.values() if "lat" in c]
    lons = [c["lon"] for c in coords.values() if "lon" in c]

    if lats and lons:
        lat_range = [round(min(lats) - 1, 1), round(max(lats) + 1, 1)]
        lon_range = [round(min(lons) - 1, 1), round(max(lons) + 1, 1)]
    else:
        lat_range = [15.0, 55.0]
        lon_range = [70.0, 140.0]

    manning_n = 0.015 if project_type == "canal" else 0.025

    topo_summary = {}
    for m in models:
        s = m.get("topology_summary", {})
        for k, v in s.items():
            topo_summary[k] = topo_summary.get(k, 0) + v

    cfg = {
        "case_id": case_id,
        "display_name": display_name,
        "project_type": project_type,
        "scan_dirs": scan_dirs,
        "target_stations": unique_stations[:30],
        "scan_extensions": [".json", ".csv", ".sqlite3", ".db", ".txt", ".xlsx"],
        "dem_path": dem_path,
        "river_network_path": river_network_path,
        "source_bundle_path": "",
        "case_manifest_path": f"cases/{case_id}/contracts/case_manifest.json",
        "topology_json_paths": topology_json_paths,
        "sqlite_paths": sqlite_paths,
        "output_dir": f"cases/{case_id}/source_selection/product_outputs",
        "validation": {
            "lat_range": lat_range,
            "lon_range": lon_range,
            "outlier_threshold_deg": 1.5,
            "min_precision_digits": 2,
        },
        "modeling": {
            "delineation": {
                "snap_distance": 5000.0,
                "stream_threshold": 100.0,
            },
            "hydrology": {
                "runoff_model": "xinanjiang",
                "routing_model": "muskingum",
                "dt_hours": 1.0,
                "simulation_hours": 720,
            },
            "hydraulics": {
                "dt_seconds": 10,
                "manning_n": manning_n,
                "steady_state_max_iter": 5000,
                "steady_state_tolerance": 0.05,
            },
        },
        "_auto_generated": {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
            "topology_summary": topo_summary,
            "data_asset_counts": {
                "sqlite": len(sqlite_paths),
                "json_models": len(topology_json_paths),
                "xlsx": len(assets.get("xlsx", [])),
                "shp": len(assets.get("shp", [])),
                "tif": len(assets.get("tif", [])),
            },
        },
    }
    return cfg


# ── 目录结构创建 ──────────────────────────────────────────────────────────

def _ensure_case_dir(path: Path) -> None:
    """确保目录可用，并修复指向缺失目标的坏符号链接。"""
    if path.is_symlink():
        if path.exists() and path.is_dir():
            return
        path.unlink()
    elif path.exists() and not path.is_dir():
        raise NotADirectoryError(f"expected directory path but found file: {path}")

    path.mkdir(parents=True, exist_ok=True)


def create_case_directory(case_id: str, display_name: str, config: dict) -> Path:
    """创建标准 case 目录结构。"""
    case_dir = WORKSPACE / "cases" / case_id
    contracts_dir = case_dir / "contracts"
    product_dir = case_dir / "source_selection" / "product_outputs"

    _ensure_case_dir(contracts_dir)
    _ensure_case_dir(product_dir)

    manifest = {
        "case_id": case_id,
        "display_name": display_name,
        "project_type": config.get("project_type", "canal"),
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "schema_version": "1.0",
    }
    manifest_path = contracts_dir / "case_manifest.json"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    readme_path = case_dir / "README.md"
    if not readme_path.exists():
        topo = config.get("_auto_generated", {}).get("topology_summary", {})
        topo_lines = "\n".join(f"  - {k}: {v}" for k, v in topo.items() if v > 0)
        readme_path.write_text(
            f"# {display_name} ({case_id})\n\n"
            f"项目类型: {config.get('project_type', 'unknown')}\n\n"
            f"## 拓扑规模\n{topo_lines}\n\n"
            f"## 数据来源\n"
            + "\n".join(f"- {d}" for d in config.get("scan_dirs", []))
            + "\n",
            encoding="utf-8",
        )

    return case_dir


# ── 知识引擎集成 ──────────────────────────────────────────────────────────

def _run_knowledge_engine(
    case_id: str, config_path: Path | None = None,
) -> dict[str, Any] | None:
    """运行知识引擎全流程（discover → evaluate → consolidate）。"""
    try:
        from hydro_model.knowledge_engine import run_full_pipeline
        return run_full_pipeline(
            case_id,
            config_path=str(config_path) if config_path else None,
        )
    except Exception as exc:
        print(f"       知识引擎错误: {exc}")
        return None


# ── 主流程 ────────────────────────────────────────────────────────────────

def init_case(
    case_id: str,
    wxq_dir: str,
    display_name: str,
    no_overwrite: bool = False,
) -> dict[str, Any]:
    """初始化单个案例：扫描数据→解析拓扑→生成配置→创建目录。"""
    wxq_abs = (WORKSPACE / wxq_dir).resolve()
    if not wxq_abs.exists():
        return {"case_id": case_id, "status": "error", "error": f"wxq dir not found: {wxq_abs}"}

    print(f"[1/4] 扫描数据资产: {wxq_dir}")
    assets = _scan_data_assets(wxq_abs)

    print(f"[2/4] 解析模型拓扑 ({len(assets['json_models'])} 个模型)")
    models = []
    for jp in _find_wxq_model_jsons(wxq_abs):
        parsed = _parse_wxq_model(jp)
        models.append(parsed)
        ts = parsed.get("topology_summary", {})
        print(f"       {parsed.get('root_key', '?')}: {ts.get('n_nodes',0)}节点 {ts.get('n_channels',0)}渠段 {ts.get('n_sections',0)}断面")

    if not models:
        print("       警告: 未找到模型JSON，将生成空拓扑配置")

    print("[3/4] 生成配置")
    wxq_rel = str(Path(wxq_dir))
    config = generate_config(case_id, display_name, wxq_rel, models, assets)

    config_path = BASE_DIR / "configs" / f"{case_id}.yaml"
    if config_path.exists() and no_overwrite:
        print(f"       跳过（已存在且 --no-overwrite）: {config_path.name}")
    else:
        auto_meta = config.pop("_auto_generated", {})
        config_text = (
            f"# {display_name} Case Configuration\n"
            f"# Auto-generated by run_case_init.py at {auto_meta.get('timestamp', '')}\n"
            f"# All paths are relative to workspace root.\n"
        )
        config_text += yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)
        config_text += (
            f"\n# ── Auto-generated metadata (do not edit) ──\n"
            f"_auto_generated:\n"
            f"  timestamp: \"{auto_meta.get('timestamp', '')}\"\n"
        )
        topo_s = auto_meta.get("topology_summary", {})
        if topo_s:
            config_text += "  topology_summary:\n"
            for k, v in topo_s.items():
                config_text += f"    {k}: {v}\n"
        asset_c = auto_meta.get("data_asset_counts", {})
        if asset_c:
            config_text += "  data_asset_counts:\n"
            for k, v in asset_c.items():
                config_text += f"    {k}: {v}\n"

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(config_text, encoding="utf-8")
        print(f"       写入: {config_path.relative_to(WORKSPACE)}")

    print("[4/5] 创建案例目录")
    config["_auto_generated"] = auto_meta
    case_dir = create_case_directory(case_id, display_name, config)
    print(f"       目录: {case_dir.relative_to(WORKSPACE)}")

    print("[5/5] 知识挖掘-评价-固化")
    ke_result = _run_knowledge_engine(case_id, config_path if config_path.exists() else None)
    if ke_result:
        print(f"       发现 {ke_result.get('discovery', {}).get('files_scanned', 0)} 文件")
        print(f"       写入 {len(ke_result.get('consolidation', {}).get('files_written', {}))} 知识文件")
    else:
        print("       跳过（知识引擎未安装或配置不完整）")

    return {
        "case_id": case_id,
        "status": "completed",
        "config_path": str(config_path.relative_to(WORKSPACE)),
        "case_dir": str(case_dir.relative_to(WORKSPACE)),
        "models_found": len(models),
        "project_type": config.get("project_type", "unknown"),
        "topology_summary": auto_meta.get("topology_summary", {}),
        "knowledge_engine": ke_result,
    }


def run_init(
    case_id: str,
    wxq_dir: str | None = None,
    display_name: str | None = None,
    no_overwrite: bool = True,
    skip_if_exists: bool = True,
) -> dict[str, Any]:
    """MCP 友好入口：仅给 case_id 时也可运行。"""
    config_path = BASE_DIR / "configs" / f"{case_id}.yaml"

    # fast/e2e 场景下优先复用现有配置，避免重复扫描大目录。
    if skip_if_exists and config_path.exists() and not wxq_dir and not display_name:
        cfg = load_case_config(case_id)
        return {
            "case_id": case_id,
            "status": "completed",
            "reused_existing": True,
            "config_path": str(config_path.relative_to(WORKSPACE)),
            "case_dir": f"cases/{case_id}",
            "display_name": cfg.get("display_name", case_id),
            "_auto_generated": datetime.utcnow().isoformat() + "Z",
        }

    cfg = load_case_config(case_id)
    inferred_wxq_dir = wxq_dir
    if not inferred_wxq_dir:
        scan_dirs = cfg.get("scan_dirs", [])
        if scan_dirs:
            inferred_wxq_dir = str(scan_dirs[0])
    if not inferred_wxq_dir:
        raise ValueError(
            "wxq_dir is required when no existing config/scan_dirs is available. "
            "Pass params.wxq_dir explicitly."
        )

    inferred_display_name = display_name or cfg.get("display_name") or case_id
    return init_case(
        case_id=case_id,
        wxq_dir=inferred_wxq_dir,
        display_name=inferred_display_name,
        no_overwrite=no_overwrite,
    )


def init_batch(batch_path: str) -> list[dict]:
    """从批量配置 YAML 初始化多个案例。"""
    with open(batch_path, encoding="utf-8") as f:
        batch = yaml.safe_load(f)
    results = []
    for item in batch.get("cases", []):
        print(f"\n{'='*60}")
        print(f"初始化: {item['case_id']} ({item.get('display_name', '')})")
        print(f"{'='*60}")
        r = init_case(
            case_id=item["case_id"],
            wxq_dir=item["wxq_dir"],
            display_name=item.get("display_name", item["case_id"]),
            no_overwrite=item.get("no_overwrite", False),
        )
        results.append(r)
    return results


def main():
    parser = argparse.ArgumentParser(description="通用案例初始化工作流")
    parser.add_argument("--case-id", help="案例 ID")
    parser.add_argument("--wxq-dir", help="wxq-1d 数据目录（相对 workspace）")
    parser.add_argument("--display-name", help="显示名称")
    parser.add_argument("--batch", help="批量配置 YAML 路径")
    parser.add_argument("--no-overwrite", action="store_true", help="不覆盖已有配置")
    args = parser.parse_args()

    if args.batch:
        results = init_batch(args.batch)
    elif args.case_id and args.wxq_dir:
        results = [init_case(
            case_id=args.case_id,
            wxq_dir=args.wxq_dir,
            display_name=args.display_name or args.case_id,
            no_overwrite=args.no_overwrite,
        )]
    else:
        parser.error("需要 --case-id + --wxq-dir 或 --batch")
        return

    print(f"\n{'='*60}")
    print("初始化结果汇总")
    print(f"{'='*60}")
    for r in results:
        status = r.get("status", "?")
        topo = r.get("topology_summary", {})
        n = topo.get("n_nodes", 0)
        ch = topo.get("n_channels", 0)
        sec = topo.get("n_sections", 0)
        print(f"  {r['case_id']:20s} {status:10s} {r.get('project_type',''):15s} {n}节点 {ch}渠段 {sec}断面")

    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
