#!/usr/bin/env python3
"""筑模 (ZhuMo) — 模型构建与拓扑组装

HydroMind 水智工坊 · Agent #4

知识注册表 — 案例×资产×脚本×结果×精度 的全链路索引。

核心机制：
  1. 资产注册：扫描全部数据文件，记录路径、类型、大小、来源人
  2. 运行注册：每次工作流产出记录 input→script→output→metrics
  3. 精度索引：自动从合约 JSON 提取最优精度，按站×维度×方法索引
  4. 去重保护：运行前查询注册表，若已有更优结果则跳过
  5. 血缘追踪：知道某个参数从哪来、被哪些运行使用过

设计原则：
  - 注册表本身是一个 JSON 文件 cases/{case_id}/knowledge_registry.json
  - 每次 consolidate / mine / assimilate 等工作流运行后自动更新
  - 注册表是"真相的单一来源"——所有工作流先查注册表再决定是否运行

Usage:
    python3 run_knowledge_registry.py --case-id zhongxian --action scan
    python3 run_knowledge_registry.py --case-id zhongxian --action best-metrics
    python3 run_knowledge_registry.py --case-id zhongxian --action should-run --workflow improve --station s1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import load_case_config


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _file_hash(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()[:12]
    except Exception:
        return ""


def _registry_path(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "knowledge_registry.json"


def load_registry(case_id: str) -> dict:
    return _safe_load_json(_registry_path(case_id))


def save_registry(case_id: str, registry: dict) -> None:
    path = _registry_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


# ── 1. 资产扫描与注册 ─────────────────────────────────────────────────────────

DATA_EXTENSIONS = {
    ".json": "model_config",
    ".yaml": "config",
    ".yml": "config",
    ".sqlite3": "timeseries_db",
    ".db": "timeseries_db",
    ".csv": "timeseries",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".tif": "geospatial_raster",
    ".shp": "geospatial_vector",
    ".geojson": "geospatial_vector",
    ".py": "script",
    ".ipynb": "notebook",
    ".html": "report_viz",
    ".md": "documentation",
    ".docx": "documentation",
    ".pptx": "presentation",
    ".pdf": "document",
    ".nc": "netcdf",
    ".txt": "text_data",
}

CONTRIBUTOR_PATTERNS = {
    "张雷": "张雷",
    "施垚": "施垚",
    "shiyao": "施垚",
    "蒋老师": "蒋老师",
    "蒋": "蒋老师",
    "谭乔凤": "谭乔凤",
    "向小华": "向小华",
    "位士光": "位士光",
    "伍玉龙": "伍玉龙",
    "陈灵强": "陈灵强",
    "雷老师": "雷老师",
    "hydro_shiyao": "施垚",
}


def _infer_contributor(path_str: str) -> str | None:
    for pattern, name in CONTRIBUTOR_PATTERNS.items():
        if pattern in path_str:
            return name
    return None


def _infer_data_category(path: Path) -> str:
    name_lower = str(path).lower()
    if "断面" in name_lower or "section" in name_lower:
        return "cross_section"
    if "曲线" in name_lower or "curve" in name_lower:
        return "characteristic_curve"
    if "降雨" in name_lower or "rain" in name_lower:
        return "rainfall"
    if "水位" in name_lower or "level" in name_lower or "swll" in name_lower:
        return "water_level"
    if "流量" in name_lower or "flow" in name_lower or "discharge" in name_lower:
        return "flow"
    if "dem" in name_lower or "地形" in name_lower:
        return "terrain"
    if "超声波" in name_lower or "ultrasonic" in name_lower:
        return "ultrasonic_flow"
    if "负荷" in name_lower or "load" in name_lower:
        return "turbine_load"
    if "库容" in name_lower or "storage" in name_lower:
        return "storage_curve"
    if "地形" in name_lower or "河道" in name_lower:
        return "channel_geometry"
    return DATA_EXTENSIONS.get(path.suffix.lower(), "unknown")


def scan_assets(case_id: str, config_path: str | None = None) -> dict:
    """扫描案例关联的所有数据资产，生成资产清单。"""
    cfg = load_case_config(case_id, config_path)
    scan_dirs = cfg.get("scan_dirs", [])

    assets: dict[str, dict] = {}
    scripts: dict[str, dict] = {}

    all_scan_paths = []
    for sd in scan_dirs:
        p = WORKSPACE / sd if not Path(sd).is_absolute() else Path(sd)
        if p.exists():
            all_scan_paths.append(p)

    case_dir = WORKSPACE / "cases" / case_id
    if case_dir.exists():
        all_scan_paths.append(case_dir)

    pipedream_dir = WORKSPACE / "pipedream-hydrology-integration-lab"
    for sub in ["research/e2e_reports", "hydromind_control_server", "kb_pipeline", "hydroclaw_control_server"]:
        p = pipedream_dir / sub
        if p.exists():
            all_scan_paths.append(p)

    for scan_path in all_scan_paths:
        for root, dirs, files in os.walk(scan_path):
            dirs[:] = [d for d in dirs if not d.startswith((".git", "__pycache__", "node_modules", ".omc"))]
            for fname in files:
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()
                if ext not in DATA_EXTENSIONS:
                    continue

                try:
                    rel = str(fpath.relative_to(WORKSPACE))
                except ValueError:
                    rel = str(fpath)

                size_kb = round(fpath.stat().st_size / 1024, 1)
                category = _infer_data_category(fpath)
                contributor = _infer_contributor(rel)

                entry = {
                    "path": rel,
                    "type": DATA_EXTENSIONS.get(ext, "unknown"),
                    "category": category,
                    "size_kb": size_kb,
                    "contributor": contributor,
                    "registered_at": _now_iso(),
                }

                if ext == ".py":
                    scripts[rel] = entry
                else:
                    assets[rel] = entry

    return {"assets": assets, "scripts": scripts}


# ── 2. 精度索引 ───────────────────────────────────────────────────────────────

def extract_best_metrics(case_id: str) -> dict:
    """从所有合约中提取每站每维度的最优精度。"""
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    if not contracts_dir.exists():
        return {}

    best: dict[str, dict] = {}

    cal = _safe_load_json(contracts_dir / "calibration_report.latest.json")
    for s in cal.get("stations", []):
        sid = s.get("station_id", "")
        name = s.get("station_name", "")
        val_nse = s.get("validation", {}).get("nse")
        _update_best(best, sid, name, "D1_hydrology", "calibration",
                      s.get("model_type", ""), val_nse, s.get("validation", {}).get("rmse"),
                      "calibration_report.latest.json")

    scada = _safe_load_json(contracts_dir / "scada_calibration.latest.json")
    for s in scada.get("stations", []):
        sid = s.get("station_id", "")
        name = s.get("station_name", "")
        val_nse = s.get("validation", {}).get("nse")
        _update_best(best, sid, name, "D1_hydrology", "scada_calibration",
                      s.get("model_type", ""), val_nse, s.get("validation", {}).get("rmse"),
                      "scada_calibration.latest.json")

    imp = _safe_load_json(contracts_dir / "precision_improvement.latest.json")
    for entry in imp.get("improvements", []):
        sid = entry.get("station_id", "")
        name = entry.get("station_name", "")
        improved = entry.get("improved", {})
        if improved:
            _update_best(best, sid, name, "D1_hydrology", "precision_improvement",
                          improved.get("model", ""), improved.get("nse_val"),
                          None, "precision_improvement.latest.json")

    se = _safe_load_json(contracts_dir / "state_estimation.latest.json")
    for sid, sinfo in se.get("stations", {}).items():
        if isinstance(sinfo, dict) and sinfo.get("status") == "completed":
            _update_best(best, sid, sinfo.get("name", sid), "D4_state_est", "EKF",
                          "EKF", sinfo.get("nse"), sinfo.get("rmse_m"),
                          "state_estimation.latest.json")

    da = _safe_load_json(contracts_dir / "data_assimilation.latest.json")
    for target, stations in da.get("results", {}).items():
        for sname, sresult in stations.items():
            if not isinstance(sresult, dict):
                continue
            b = sresult.get("_best", {})
            if b:
                dim = {"hydrology": "D1_hydrology", "hydraulics": "D2_hydraulics",
                       "coupled": "D2_coupled"}.get(target, target)
                _update_best(best, sname, sname, dim, f"DA_{b['method']}",
                              b["method"], b.get("nse"), b.get("rmse"),
                              "data_assimilation.latest.json")

    return best


def _update_best(
    best: dict, sid: str, name: str, dimension: str, workflow: str,
    model: str, nse: float | None, rmse: float | None, source: str,
) -> None:
    if nse is None:
        return
    key = f"{sid}_{dimension}"
    existing = best.get(key, {})
    existing_nse = existing.get("nse")
    if existing_nse is None or nse > existing_nse:
        best[key] = {
            "station_id": sid,
            "station_name": name,
            "dimension": dimension,
            "workflow": workflow,
            "model": model,
            "nse": nse,
            "rmse": rmse,
            "source": source,
            "recorded_at": _now_iso(),
        }


# ── 3. 去重保护 ───────────────────────────────────────────────────────────────

def should_run(
    case_id: str,
    workflow: str,
    station_id: str | None = None,
    dimension: str = "D1_hydrology",
    target_nse: float = 0.85,
) -> dict[str, Any]:
    """查询注册表判断是否需要运行某工作流。"""
    registry = load_registry(case_id)
    best_metrics = registry.get("best_metrics", {})

    if station_id:
        key = f"{station_id}_{dimension}"
        existing = best_metrics.get(key, {})
        existing_nse = existing.get("nse")
        if existing_nse is not None and existing_nse >= target_nse:
            return {
                "should_run": False,
                "reason": f"已有更优结果: {existing['workflow']}→{existing['model']} NSE={existing_nse:.4f} "
                          f"(来源: {existing['source']})",
                "existing_best": existing,
            }
        return {
            "should_run": True,
            "reason": f"当前最优 NSE={existing_nse or 'N/A'}，未达目标 {target_nse}",
            "existing_best": existing,
        }

    all_stations_met = True
    station_status = {}
    for key, metric in best_metrics.items():
        if dimension in key:
            met = metric.get("nse", 0) >= target_nse
            station_status[metric.get("station_name", key)] = {
                "nse": metric.get("nse"),
                "met": met,
                "source": metric.get("source"),
            }
            if not met:
                all_stations_met = False

    if all_stations_met and station_status:
        return {
            "should_run": False,
            "reason": f"所有 {len(station_status)} 个站点已达目标 NSE≥{target_nse}",
            "station_status": station_status,
        }

    return {
        "should_run": True,
        "reason": f"部分站点未达目标",
        "station_status": station_status,
    }


# ── 4. 血缘追踪 ───────────────────────────────────────────────────────────────

def record_run(
    case_id: str,
    workflow: str,
    inputs: list[str],
    outputs: list[str],
    metrics: dict[str, float] | None = None,
    params: dict | None = None,
) -> None:
    """记录一次工作流运行到注册表。"""
    registry = load_registry(case_id)
    runs = registry.setdefault("runs", [])

    max_runs = 50
    while len(runs) >= max_runs:
        runs.pop(0)

    runs.append({
        "workflow": workflow,
        "timestamp": _now_iso(),
        "inputs": inputs,
        "outputs": outputs,
        "metrics": metrics or {},
        "params": params or {},
    })

    save_registry(case_id, registry)


# ── 5. 主入口：全量注册 ───────────────────────────────────────────────────────

def build_registry(case_id: str, config_path: str | None = None) -> dict:
    """构建/更新案例的完整知识注册表。"""
    print(f"\n[知识注册表] 构建: {case_id}")

    print("  扫描资产...")
    scan_result = scan_assets(case_id, config_path)
    n_assets = len(scan_result["assets"])
    n_scripts = len(scan_result["scripts"])
    print(f"  → 发现 {n_assets} 数据资产, {n_scripts} 脚本")

    print("  提取精度索引...")
    best_metrics = extract_best_metrics(case_id)
    print(f"  → {len(best_metrics)} 个站×维度精度记录")

    contributors = set()
    categories: dict[str, int] = {}
    for asset in scan_result["assets"].values():
        if asset.get("contributor"):
            contributors.add(asset["contributor"])
        cat = asset.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    registry = {
        "_meta": {
            "case_id": case_id,
            "built_at": _now_iso(),
            "schema_version": "1.0",
        },
        "summary": {
            "total_assets": n_assets,
            "total_scripts": n_scripts,
            "contributors": sorted(contributors),
            "categories": dict(sorted(categories.items(), key=lambda x: -x[1])),
            "best_overall_nse": {},
        },
        "assets": scan_result["assets"],
        "scripts": scan_result["scripts"],
        "best_metrics": best_metrics,
        "runs": load_registry(case_id).get("runs", []),
    }

    for key, metric in best_metrics.items():
        dim = metric.get("dimension", "")
        existing_best = registry["summary"]["best_overall_nse"].get(dim, {}).get("nse", -999)
        if metric.get("nse", -999) > existing_best:
            registry["summary"]["best_overall_nse"][dim] = {
                "station": metric.get("station_name"),
                "nse": metric.get("nse"),
                "workflow": metric.get("workflow"),
            }

    save_registry(case_id, registry)

    unintegrated = _find_unintegrated(registry)
    if unintegrated:
        registry["unintegrated_assets"] = unintegrated
        save_registry(case_id, registry)
        print(f"  ⚠ 发现 {len(unintegrated)} 个尚未整合的高价值资产")
        for u in unintegrated[:5]:
            print(f"    - {u['path']} ({u['reason']})")

    print(f"\n  [完成] 注册表已保存: cases/{case_id}/knowledge_registry.json")
    return registry


def _find_unintegrated(registry: dict) -> list[dict]:
    """识别尚未被工作流使用过的高价值资产。"""
    unintegrated = []
    used_paths = set()
    for run in registry.get("runs", []):
        used_paths.update(run.get("inputs", []))
        used_paths.update(run.get("outputs", []))

    high_value_categories = {"cross_section", "characteristic_curve", "storage_curve",
                             "water_level", "flow", "ultrasonic_flow", "turbine_load",
                             "timeseries_db", "channel_geometry"}

    for path, info in registry.get("assets", {}).items():
        if path in used_paths:
            continue
        cat = info.get("category", "")
        size = info.get("size_kb", 0)

        is_high_value = (
            cat in high_value_categories
            or size > 1000
            or info.get("type") == "timeseries_db"
        )
        if is_high_value:
            unintegrated.append({
                "path": path,
                "category": cat,
                "size_kb": size,
                "contributor": info.get("contributor"),
                "reason": f"{cat} 未被任何工作流使用" if cat in high_value_categories
                          else f"大文件({size:.0f}KB) 未被使用",
            })

    unintegrated.sort(key=lambda x: -x.get("size_kb", 0))
    return unintegrated


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="知识注册表")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--action", default="scan",
                        choices=["scan", "best-metrics", "should-run", "build"])
    parser.add_argument("--config", help="YAML 配置路径")
    parser.add_argument("--workflow", help="工作流名称 (should-run)")
    parser.add_argument("--station", help="站点 ID (should-run)")
    parser.add_argument("--dimension", default="D1_hydrology")
    parser.add_argument("--target-nse", type=float, default=0.85)
    args = parser.parse_args()

    if args.action == "build":
        result = build_registry(args.case_id, args.config)
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    elif args.action == "best-metrics":
        best = extract_best_metrics(args.case_id)
        for key, m in sorted(best.items()):
            print(f"  {m['station_name']:10s} {m['dimension']:15s} NSE={m['nse']:.4f} "
                  f"via {m['workflow']} ({m['source']})")
    elif args.action == "should-run":
        result = should_run(args.case_id, args.workflow or "", args.station,
                            args.dimension, args.target_nse)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = scan_assets(args.case_id, args.config)
        print(f"Assets: {len(result['assets'])}, Scripts: {len(result['scripts'])}")


if __name__ == "__main__":
    main()
