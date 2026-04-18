#!/usr/bin/env python3
"""探源 (TanYuan) — 数据勘探与知识发现

HydroMind 水智工坊 · Agent #1

深度资产记录器 — 一次扫描全部数据资产，永久写入 Case YAML。

确保所有已发现的资料路径、参数、精度记录、历史配置都被持久化，
后续对话不需要重复挖掘。

扫描范围：
  1. wxq-1d/{case}/ 全子目录（模型JSON、地形TXT、CSV、SQL、XLS等）
  2. pipedream-hydrology-integration-lab/ 定制脚本中的硬编码参数
  3. pipedream e2e_reports/ 历史精度记录
  4. .team/ 上下文包中的发现

写入目标：
  case YAML → knowledge.discovered_assets
  case YAML → knowledge.pipedream_scripts
  case YAML → knowledge.historical_precision
  case YAML → knowledge.terrain_sections
  case YAML → knowledge.zv_curves (水位-库容)
  case YAML → knowledge.boundary_conditions
  case YAML → knowledge.horton_params

Usage:
    python3 run_deep_asset_recorder.py --case-id zhongxian
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflows._shared import load_case_config
from workflows.run_knowledge_miner import _load_graphify_sidecar


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE))
    except ValueError:
        return str(path)


def _backup_yaml(yaml_path: Path, max_versions: int = 3) -> None:
    if not yaml_path.exists():
        return
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = yaml_path.with_suffix(f".v{ts}.yaml")
    shutil.copy2(yaml_path, backup)
    backups = sorted(yaml_path.parent.glob(f"{yaml_path.stem}.v*.yaml"))
    while len(backups) > max_versions:
        backups.pop(0).unlink()


# ── 资产扫描 ──────────────────────────────────────────────────────────────────

def scan_all_assets(scan_dirs: list[str]) -> dict[str, list]:
    """扫描所有数据文件，按类型分组。"""
    assets: dict[str, list] = {}
    ext_map = {
        ".json": "model_json",
        ".csv": "csv_data",
        ".txt": "text_data",
        ".sql": "sql_script",
        ".xlsx": "excel",
        ".xls": "excel",
        ".tsv": "tsv_data",
        ".sqlite3": "sqlite",
        ".db": "sqlite",
        ".tif": "raster",
        ".shp": "shapefile",
        ".prj": "projection",
        ".canal": "canal_model",
        ".xml": "xml_data",
    }

    for sd in scan_dirs:
        scan_path = WORKSPACE / sd if not Path(sd).is_absolute() else Path(sd)
        if not scan_path.exists():
            continue
        for f in scan_path.rglob("*"):
            if f.is_dir() or f.name.startswith("."):
                continue
            ext = f.suffix.lower()
            category = ext_map.get(ext, "other")
            assets.setdefault(category, []).append({
                "path": _rel(f),
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "parent": f.parent.name,
            })

    return assets


def scan_terrain_sections(scan_dirs: list[str]) -> list[dict]:
    """扫描实测河道断面地形文件。"""
    sections = []
    patterns = ["*地形*.txt", "*断面*.txt", "*.canal"]

    for sd in scan_dirs:
        scan_path = WORKSPACE / sd if not Path(sd).is_absolute() else Path(sd)
        if not scan_path.exists():
            continue
        for pattern in patterns:
            for f in scan_path.rglob(pattern):
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    n_lines = len(text.strip().split("\n"))
                    sections.append({
                        "path": _rel(f),
                        "name": f.name,
                        "n_lines": n_lines,
                        "size_kb": round(f.stat().st_size / 1024, 1),
                    })
                except Exception:
                    sections.append({"path": _rel(f), "name": f.name, "error": "read_failed"})

    return sections


def scan_zv_curves(scan_dirs: list[str]) -> list[dict]:
    """扫描水位-库容/面积曲线文件。"""
    curves = []
    patterns = ["*库容*.txt", "*水位*.txt", "*修正*.txt"]

    for sd in scan_dirs:
        scan_path = WORKSPACE / sd if not Path(sd).is_absolute() else Path(sd)
        if not scan_path.exists():
            continue
        for pattern in patterns:
            for f in scan_path.rglob(pattern):
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
                    curves.append({
                        "path": _rel(f),
                        "name": f.name,
                        "n_lines": len(lines),
                        "preview": lines[:3] if lines else [],
                    })
                except Exception:
                    pass

    return curves


def scan_scada_data(scan_dirs: list[str]) -> list[dict]:
    """扫描 SCADA / 时序数据文件。"""
    scada = []
    patterns = ["*5MINLY*.tsv", "*水位*.csv", "*流量*.txt", "*数据*.txt"]

    for sd in scan_dirs:
        scan_path = WORKSPACE / sd if not Path(sd).is_absolute() else Path(sd)
        if not scan_path.exists():
            continue
        for pattern in patterns:
            for f in scan_path.rglob(pattern):
                scada.append({
                    "path": _rel(f),
                    "name": f.name,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                })

    return scada


def scan_boundary_csv(cfg: dict) -> dict:
    """扫描边界条件 CSV。"""
    candidates = [
        WORKSPACE / "pipedream-hydrology-integration-lab" / "hydromind_control_server" / "configs" / "cases",
    ]
    for c in candidates:
        bc_file = c / f"{cfg.get('case_id', '')}_boundary_conditions.csv"
        if bc_file.exists():
            try:
                lines = bc_file.read_text().strip().split("\n")
                header = lines[0] if lines else ""
                return {
                    "path": _rel(bc_file),
                    "n_records": len(lines) - 1,
                    "columns": header.split(","),
                    "preview_row": lines[1] if len(lines) > 1 else "",
                }
            except Exception:
                pass
    return {}


def scan_horton_params(cfg: dict) -> list[dict]:
    """扫描 Horton 下渗参数。"""
    candidates = [
        WORKSPACE / "pipedream-hydrology-integration-lab" / "hydromind_control_server" / "configs" / "cases"
        / f"{cfg.get('case_id', '')}_inf_params.csv",
    ]
    params = []
    for f in candidates:
        if not f.exists():
            continue
        try:
            reader = csv.DictReader(f.open())
            for row in reader:
                params.append({k: v for k, v in row.items() if v})
        except Exception:
            pass
    return params


def scan_pipedream_scripts(case_id: str) -> list[dict]:
    """扫描 pipedream 中该案例的定制脚本。"""
    scripts = []
    pipedream = WORKSPACE / "pipedream-hydrology-integration-lab"
    if not pipedream.exists():
        return scripts

    for f in pipedream.rglob(f"*{case_id}*.py"):
        scripts.append({
            "path": _rel(f),
            "name": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
        })

    for subdir in ["hydromind_control_server/src", "hydroclaw_control_server/src", "universal_autonomous_architecture"]:
        src_dir = pipedream / subdir
        if not src_dir.exists():
            continue
        for f in src_dir.rglob(f"*{case_id}*.py"):
            entry = {"path": _rel(f), "name": f.name, "size_kb": round(f.stat().st_size / 1024, 1)}
            if entry not in scripts:
                scripts.append(entry)

    return scripts


def extract_historical_precision(case_id: str, cfg: dict | None = None) -> dict:
    """从 pipedream e2e 和 wnal 报告中提取历史最佳精度。"""
    precision = {}
    cfg = cfg or {}
    display_name = cfg.get("display_name", case_id)
    wnal_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "wnal_evaluation" / f"{display_name}梯级_wnal_evaluation.json"
    if wnal_path.exists():
        try:
            wnal = json.loads(wnal_path.read_text())
            precision["wnal"] = {
                "path": _rel(wnal_path),
                "wnal_score": wnal.get("wnal_score"),
                "wnal_level": wnal.get("wnal_level"),
                "bottleneck": wnal.get("bottleneck_dim"),
            }
        except Exception:
            pass

    eval_md = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id / f"{case_id}_evaluation_report.md"
    if eval_md.exists():
        try:
            text = eval_md.read_text(encoding="utf-8", errors="ignore")
            nse_match = re.search(r"NSE\s*[=:]\s*([\d.]+)", text)
            rmse_match = re.search(r"RMSE\s*[=:]\s*([\d.]+)", text)
            precision["evaluation_report"] = {
                "path": _rel(eval_md),
                "best_nse": float(nse_match.group(1)) if nse_match else None,
                "best_rmse_m": float(rmse_match.group(1)) if rmse_match else None,
            }
        except Exception:
            pass

    pipeline_summary = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id / "full_pipeline" / "pipeline_summary.json"
    if pipeline_summary.exists():
        try:
            summary = json.loads(pipeline_summary.read_text())
            precision["pipeline_summary"] = {
                "path": _rel(pipeline_summary),
                "hydrology_nse": summary.get("hydrology", {}).get("nse"),
                "hydraulics_converged": summary.get("hydraulics", {}).get("steady_state_status"),
                "sil_pass_rate": summary.get("sil", {}).get("pass_rate"),
                "odd_match": summary.get("odd_evaluation", {}).get("odd_validation_match"),
            }
        except Exception:
            pass

    wnal_sim = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id / "wnal_from_simulation.json"
    if wnal_sim.exists():
        try:
            data = json.loads(wnal_sim.read_text())
            d2 = data.get("D2_hydraulics", {})
            precision["wnal_d2_stations"] = d2.get("stations", {})
            precision["wnal_d2_avg_rmse"] = d2.get("avg_rmse")
            precision["wnal_d2_manning_n"] = d2.get("manning_n")
        except Exception:
            pass

    return precision


def extract_pipedream_hardcoded_params(case_id: str) -> dict:
    """从 pipedream YAML/JSON 配置中提取核心参数。"""
    params = {}

    json_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "hydromind_control_server" / "configs" / "cases" / f"{case_id}.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text())
            params["control_server_json"] = {
                "path": _rel(json_path),
                "mpc_horizon": data.get("mpc_horizon"),
                "mpc_dt": data.get("mpc_dt"),
                "ekf_process_noise": data.get("ekf_process_noise"),
                "ekf_obs_noise": data.get("ekf_obs_noise"),
                "boundary_head_gain": data.get("boundary_head_gain"),
                "model_response_factor": data.get("model_response_factor"),
                "station_gate_area": data.get("station_gate_area"),
                "station_discharge_coeff": data.get("station_discharge_coeff"),
                "default_start": data.get("default_start"),
                "default_end": data.get("default_end"),
                "default_freq": data.get("default_freq"),
                "stations": [
                    {k: v for k, v in s.items() if k in ("name", "elevation", "normal_pool", "dead_pool", "installed_mw", "basin_area_km2")}
                    for s in data.get("stations", [])
                ],
            }
        except Exception:
            pass

    yaml_paths = [
        WORKSPACE / "pipedream-hydrology-integration-lab" / "hydromind_control_server" / "configs" / "cases" / f"{case_id}.yaml",
        WORKSPACE / "pipedream-hydrology-integration-lab" / "kb_pipeline" / "configs" / f"{case_id}.yaml",
    ]
    for yp in yaml_paths:
        if yp.exists():
            try:
                data = yaml.safe_load(yp.read_text())
                label = yp.parent.parent.name
                params[f"{label}_yaml"] = {
                    "path": _rel(yp),
                    "manning_n": data.get("hydraulics", {}).get("manning_n"),
                    "dt_seconds": data.get("hydraulics", {}).get("time_step_seconds"),
                    "channel_geometry": data.get("hydraulics", {}).get("channel_geometry"),
                    "muskingum": data.get("calibration", {}).get("muskingum", data.get("hydrology", {}).get("muskingum")),
                    "accuracy": data.get("accuracy"),
                    "mpc": data.get("control", {}).get("mpc"),
                    "kalman": data.get("control", {}).get("kalman"),
                }
            except Exception:
                pass

    return params


# ── 主入口 ────────────────────────────────────────────────────────────────────

def record_assets(
    case_id: str,
    *,
    config_path: str | None = None,
    max_versions: int = 3,
    dry_run: bool = False,
    graphify_sidecar_dir: str | None = None,
) -> dict[str, Any]:
    """一次扫描、永久记录所有数据资产。"""
    cfg = load_case_config(case_id, config_path)
    yaml_path = Path(config_path) if config_path else BASE_DIR / "configs" / f"{case_id}.yaml"
    scan_dirs = cfg.get("scan_dirs", [])

    print(f"\n{'='*60}")
    print(f"[深度资产记录] {case_id}")
    print(f"  扫描目录: {scan_dirs}")
    print(f"{'='*60}")

    all_assets = scan_all_assets(scan_dirs)
    terrain = scan_terrain_sections(scan_dirs)
    zv_curves = scan_zv_curves(scan_dirs)
    scada = scan_scada_data(scan_dirs)
    boundary = scan_boundary_csv(cfg)
    horton = scan_horton_params(cfg)
    scripts = scan_pipedream_scripts(case_id)
    precision = extract_historical_precision(case_id, cfg)
    hardcoded = extract_pipedream_hardcoded_params(case_id)
    graphify_sidecar = _load_graphify_sidecar(graphify_sidecar_dir)

    asset_counts = {cat: len(files) for cat, files in all_assets.items()}
    total_files = sum(asset_counts.values())

    print(f"\n  扫描结果:")
    print(f"    总文件数: {total_files}")
    for cat, count in sorted(asset_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")
    print(f"    实测断面地形: {len(terrain)} 个文件")
    print(f"    水位-库容曲线: {len(zv_curves)} 个文件")
    print(f"    SCADA时序: {len(scada)} 个文件")
    print(f"    边界条件: {'有' if boundary else '无'} ({boundary.get('n_records', 0)} 行)")
    print(f"    Horton参数: {len(horton)} 个地类")
    print(f"    定制脚本: {len(scripts)} 个")
    print(f"    历史精度记录: {len(precision)} 个来源")

    recorded_at = _now_iso()

    knowledge_update = {
        "discovered_assets": {
            "_recorded_at": recorded_at,
            "_total_files": total_files,
            "by_type": {cat: [{"path": f["path"], "name": f["name"]} for f in files[:50]]
                        for cat, files in all_assets.items()},
            "counts": asset_counts,
        },
        "terrain_sections": {
            "_recorded_at": recorded_at,
            "files": terrain,
        },
        "zv_curves": {
            "_recorded_at": recorded_at,
            "files": zv_curves,
        },
        "scada_timeseries": {
            "_recorded_at": recorded_at,
            "files": scada,
        },
        "boundary_conditions_csv": boundary,
        "horton_params": {
            "_recorded_at": recorded_at,
            "_source": cfg.get("infiltration_params_path", f"{case_id}_inf_params.csv"),
            "land_classes": horton,
        },
        "pipedream_scripts": {
            "_recorded_at": recorded_at,
            "files": scripts,
        },
        "historical_precision": {
            "_recorded_at": recorded_at,
            **precision,
        },
        "pipedream_hardcoded_params": {
            "_recorded_at": recorded_at,
            **hardcoded,
        },
    }
    if graphify_sidecar:
        knowledge_update["graphify_sidecar"] = graphify_sidecar

    raw_text = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""
    existing = yaml.safe_load(raw_text) or {} if raw_text else {}
    knowledge = existing.setdefault("knowledge", {})
    knowledge.update(knowledge_update)
    knowledge.setdefault("_meta", {})["last_consolidated"] = recorded_at

    report = {
        "case_id": case_id,
        "recorded_at": recorded_at,
        "total_files_discovered": total_files,
        "asset_counts": asset_counts,
        "terrain_files": len(terrain),
        "zv_curve_files": len(zv_curves),
        "scada_files": len(scada),
        "boundary_records": boundary.get("n_records", 0),
        "horton_classes": len(horton),
        "pipedream_scripts": len(scripts),
        "historical_precision_sources": len(precision),
        "dry_run": dry_run,
        "graphify_sidecar": graphify_sidecar,
    }

    if not dry_run:
        _backup_yaml(yaml_path, max_versions=max_versions)
        yaml_path.write_text(
            yaml.dump(existing, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
            encoding="utf-8",
        )
        contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        (contracts_dir / "deep_asset_recording.latest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
        )
        print(f"\n  ✓ 已写入 {yaml_path.name} 和 deep_asset_recording.latest.json")
    else:
        print(f"\n  [DRY-RUN] 未写入")

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="深度资产记录器")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", help="YAML 配置路径")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-versions", type=int, default=3)
    parser.add_argument("--graphify-sidecar-dir", help="可选 Graphify sidecar 目录（只读候选层）")
    args = parser.parse_args()

    result = record_assets(
        args.case_id,
        config_path=args.config,
        dry_run=args.dry_run,
        max_versions=args.max_versions,
        graphify_sidecar_dir=args.graphify_sidecar_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
