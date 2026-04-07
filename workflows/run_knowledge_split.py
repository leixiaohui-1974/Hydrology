#!/usr/bin/env python3
"""筑模 (ZhuMo) — 模型构建与拓扑组装

HydroMind 水智工坊 · Agent #4

知识分层迁移器 — 将膨胀的单文件 YAML 拆分为知识目录。

设计原则：
  1. config 是 config，knowledge 是 knowledge —— 分离关注点
  2. 每个参数有溯源 —— value, sources[], conflicts, recommended
  3. 每个模型版本一张卡片 —— 数据 → 参数 → 精度 自闭环
  4. manifest 做索引 —— 快速查找不需要读全部文件
  5. config YAML ≤150 行

Usage:
    python3 -m workflows.run_knowledge_split --case-id zhongxian
"""
from __future__ import annotations

import argparse
import json
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
        encoding="utf-8",
    )


def _safe_get(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d


def _dict_items(obj) -> list[tuple[str, dict]]:
    """Safely iterate over dict or list-of-dict, always returning (name, dict) pairs."""
    if isinstance(obj, dict):
        return [(k, v) for k, v in obj.items() if isinstance(v, dict)]
    if isinstance(obj, list):
        return [(v.get("name", f"item_{i}"), v) for i, v in enumerate(obj) if isinstance(v, dict)]
    return []


# ── 参数溯源构建 ──────────────────────────────────────────────────────────────

def _build_param_provenance(knowledge: dict, cfg: dict) -> dict[str, dict]:
    """为每个关键参数构建溯源链。"""

    hydraulics_params = {}
    hydrology_params = {}
    control_params = {}

    # Manning n — 从多个来源收集
    manning_sources = []
    manning_conflicts = []

    modeling = cfg.get("modeling", {})
    if modeling.get("hydraulics", {}).get("manning_n"):
        manning_sources.append({
            "value": modeling["hydraulics"]["manning_n"],
            "source": f"configs/{cfg['case_id']}.yaml → modeling.hydraulics.manning_n",
            "context": "运行时配置值",
            "status": "active",
        })

    model_versions = knowledge.get("model_versions", [])
    mv_items: list[tuple[str, dict]] = []
    if isinstance(model_versions, dict):
        mv_items = [(k, v) for k, v in model_versions.items() if isinstance(v, dict)]
    elif isinstance(model_versions, list):
        mv_items = [(f"v{i}", v) for i, v in enumerate(model_versions) if isinstance(v, dict)]

    for ver_name, mv in mv_items:
        channels = mv.get("channels", {})
        if not isinstance(channels, dict):
            continue
        for ch_name, ch_info in channels.items():
            if isinstance(ch_info, dict) and ch_info.get("manning_n"):
                manning_sources.append({
                    "value": ch_info["manning_n"],
                    "source": mv.get("source_file", f"model_version:{ver_name}"),
                    "context": f"河段 {ch_name}",
                    "status": "reference",
                })

    # 从 manning_n_comparison 补充
    for comp in knowledge.get("manning_n_comparison", []):
        if isinstance(comp, dict):
            vals = comp.get("values", {})
            if isinstance(vals, dict):
                for src, val in vals.items():
                    if val is not None:
                        manning_sources.append({
                            "value": val,
                            "source": src,
                            "context": comp.get("channel", "unknown"),
                            "status": "historical",
                        })
            elif isinstance(vals, list):
                for v in vals:
                    if isinstance(v, dict):
                        manning_sources.append({
                            "value": v.get("value"),
                            "source": v.get("source", "unknown"),
                            "context": comp.get("channel", "unknown"),
                            "status": "historical",
                        })

    # 从 pipedream_hardcoded 补充
    pip_params = knowledge.get("pipedream_hardcoded_params", {})
    for cfg_key, cfg_val in pip_params.items():
        if isinstance(cfg_val, dict) and cfg_val.get("manning_n"):
            manning_sources.append({
                "value": cfg_val["manning_n"],
                "source": cfg_val.get("path", cfg_key),
                "context": "pipedream 配置",
                "status": "reference",
            })

    unique_vals = set()
    for s in manning_sources:
        if s["value"] is not None:
            unique_vals.add(float(s["value"]) if not isinstance(s["value"], str) else s["value"])

    if len(unique_vals) > 1:
        manning_conflicts.append(f"存在 {len(unique_vals)} 个不同取值: {sorted(unique_vals)}")

    hydraulics_params["manning_n"] = {
        "recommended": modeling.get("hydraulics", {}).get("manning_n", 0.025),
        "unit": "s/m^(1/3)",
        "provenance": manning_sources,
        "conflicts": manning_conflicts or ["无冲突"],
        "resolution": "分河段优化" if len(unique_vals) > 1 else "统一值",
    }

    # dt_seconds
    dt_sources = []
    if modeling.get("hydraulics", {}).get("dt_seconds"):
        dt_sources.append({
            "value": modeling["hydraulics"]["dt_seconds"],
            "source": f"configs/{cfg['case_id']}.yaml",
            "context": "运行时配置",
            "accuracy": cfg.get("historical_accuracy", {}).get("note", ""),
        })
    # pipedream 中的 dt
    cs_json = pip_params.get("control_server_json", {})
    if cs_json.get("mpc_dt"):
        dt_sources.append({
            "value": cs_json["mpc_dt"],
            "source": cs_json.get("path", f"{cfg['case_id']}.json"),
            "context": "MPC控制步长",
        })

    hydraulics_params["dt_seconds"] = {
        "recommended": modeling.get("hydraulics", {}).get("dt_seconds", 60),
        "unit": "s",
        "provenance": dt_sources,
        "note": "dt=60s 用于高精度仿真，dt=3600s 用于MPC控制步长",
    }

    # channel geometry from topology
    topo_channels = knowledge.get("topology", {}).get("channels", {})
    if isinstance(topo_channels, dict):
        for ch_name, ch_info in topo_channels.items():
            if isinstance(ch_info, dict):
                hydraulics_params[f"channel_{ch_name}"] = {
                    "length_m": ch_info.get("length"),
                    "width": ch_info.get("width") or ch_info.get("g2"),
                    "manning_n": ch_info.get("manning_n"),
                    "source": ch_info.get("source", "unknown"),
                    "updated_at": ch_info.get("updated_at"),
                }
    elif isinstance(topo_channels, list):
        for i, ch_info in enumerate(topo_channels):
            if isinstance(ch_info, dict):
                ch_name = ch_info.get("name", f"ch_{i}")
                hydraulics_params[f"channel_{ch_name}"] = {
                    "length_m": ch_info.get("length"),
                    "width": ch_info.get("width") or ch_info.get("g2"),
                    "manning_n": ch_info.get("manning_n"),
                    "source": ch_info.get("source", "unknown"),
                }

    # Muskingum parameters
    musk_sources = []
    pip_hist = knowledge.get("pipedream_historical", {})
    for key, val in pip_hist.items():
        if isinstance(val, dict):
            musk = val.get("muskingum")
            if musk:
                musk_sources.append({"params": musk, "source": val.get("path", key)})
            hydro = val.get("hydrology")
            if isinstance(hydro, dict) and hydro.get("muskingum"):
                musk_sources.append({"params": hydro["muskingum"], "source": val.get("path", key)})

    musk_defaults = cfg.get("modeling", {}).get("hydrology", {}).get("muskingum", {"K": 1.2, "X": 0.2, "dt_days": 1.0})
    hydrology_params["muskingum"] = {
        "recommended": musk_defaults,
        "unit": "K=days, X=dimensionless",
        "provenance": musk_sources or [{"note": "配置默认值，需率定优化"}],
    }

    hydrology_params["catchment_areas_km2"] = cfg.get("catchment_areas", {})

    # Control params
    if cs_json:
        control_params["mpc"] = {
            "horizon": cs_json.get("mpc_horizon"),
            "dt": cs_json.get("mpc_dt"),
            "source": cs_json.get("path", f"{cfg['case_id']}.json"),
        }
        control_params["ekf"] = {
            "process_noise": cs_json.get("ekf_process_noise"),
            "obs_noise": cs_json.get("ekf_obs_noise"),
            "source": cs_json.get("path", f"{cfg['case_id']}.json"),
        }
        control_params["gate"] = {
            "area": cs_json.get("station_gate_area"),
            "discharge_coeff": cs_json.get("station_discharge_coeff"),
            "model_response_factor": cs_json.get("model_response_factor"),
            "source": cs_json.get("path", f"{cfg['case_id']}.json"),
        }
        control_params["stations"] = cs_json.get("stations", [])

    return {
        "hydraulics": hydraulics_params,
        "hydrology": hydrology_params,
        "control": control_params,
    }


# ── 模型版本卡片 ─────────────────────────────────────────────────────────────

def _build_model_cards(knowledge: dict) -> dict[str, dict]:
    """为每个模型版本构建独立卡片。"""
    cards = {}

    model_versions = knowledge.get("model_versions", {})
    items = model_versions if isinstance(model_versions, dict) else {}
    if isinstance(model_versions, list):
        items = {f"v{i}": mv for i, mv in enumerate(model_versions) if isinstance(mv, dict)}

    for ver_name, mv in items.items():
        if not isinstance(mv, dict):
            continue
        card_id = ver_name.replace("/", "_").replace(" ", "_").replace(".", "_")

        card = {
            "model_id": card_id,
            "source_file": mv.get("source_file", "unknown"),
            "mined_at": mv.get("mined_at"),
            "topology": {
                "nodes": len(mv.get("nodes", {})),
                "channels": len(mv.get("channels", {})),
                "turbines": len(mv.get("turbines", {})),
                "gates": len(mv.get("gates", {})),
                "pumps": len(mv.get("pumps", {})),
                "siphons": len(mv.get("siphons", {})),
            },
            "key_params": {},
            "data_sources": [],
            "accuracy_achieved": {},
        }

        for ch_name, ch_info in _dict_items(mv.get("channels", {})):
            card["key_params"][f"channel_{ch_name}"] = {
                "manning_n": ch_info.get("manning_n"),
                "length": ch_info.get("length"),
                "width": ch_info.get("width") or ch_info.get("g2"),
            }

        for t_name, t_info in _dict_items(mv.get("turbines", {})):
            card["key_params"][f"turbine_{t_name}"] = {
                "max_flow": t_info.get("max_flow") or t_info.get("designQ"),
                "n_units": t_info.get("n_units") or t_info.get("number"),
                "efficiency": t_info.get("efficiency"),
            }

        for g_name, g_info in _dict_items(mv.get("gates", {})):
            card["key_params"][f"gate_{g_name}"] = {
                "max_flow": g_info.get("max_flow") or g_info.get("designQ"),
                "n_gates": g_info.get("n_gates") or g_info.get("number"),
                "width": g_info.get("width") or g_info.get("gateWidth"),
            }

        cards[card_id] = card

    # pipedream 实验版本
    pip_hist = knowledge.get("pipedream_historical", {})
    for key, val in pip_hist.items():
        if not isinstance(val, dict):
            continue
        card_id = f"pipedream_{key}"
        card = {
            "model_id": card_id,
            "source_file": val.get("path", key),
            "mined_at": val.get("_recorded_at", val.get("mined_at")),
            "topology": {},
            "key_params": {},
            "data_sources": [val.get("path", key)],
            "accuracy_achieved": {},
        }
        for param_key in ["muskingum", "hydrology", "hydraulics", "control", "mpc", "ekf", "accuracy"]:
            if val.get(param_key):
                card["key_params"][param_key] = val[param_key]
        if val.get("accuracy"):
            card["accuracy_achieved"] = val["accuracy"]
        elif val.get("nse"):
            card["accuracy_achieved"]["nse"] = val["nse"]

        cards[card_id] = card

    return cards


# ── 精度历史 ──────────────────────────────────────────────────────────────────

def _build_precision_history(knowledge: dict, cfg: dict) -> dict:
    """汇总所有历史精度记录。"""
    history = {
        "records": [],
        "best_overall": {},
    }

    if cfg.get("historical_accuracy"):
        history["records"].append({
            "label": "pipedream_scada_实测边界",
            "source": cfg["historical_accuracy"].get("source", ""),
            "metrics": {
                "flow_nse": cfg["historical_accuracy"].get("flow_nse"),
                "flow_r2": cfg["historical_accuracy"].get("flow_r2"),
                "water_level_rmse_m": cfg["historical_accuracy"].get("water_level_rmse_m"),
                "grade": cfg["historical_accuracy"].get("grade"),
            },
            "note": cfg["historical_accuracy"].get("note"),
        })

    hp = knowledge.get("historical_precision", {})
    if hp.get("wnal"):
        history["records"].append({
            "label": "WNAL综合评价",
            "source": hp["wnal"].get("path", ""),
            "metrics": {
                "wnal_score": hp["wnal"].get("wnal_score"),
                "wnal_level": hp["wnal"].get("wnal_level"),
            },
        })
    if hp.get("evaluation_report"):
        history["records"].append({
            "label": "e2e评估报告",
            "source": hp["evaluation_report"].get("path", ""),
            "metrics": {
                "best_nse": hp["evaluation_report"].get("best_nse"),
                "best_rmse_m": hp["evaluation_report"].get("best_rmse_m"),
            },
        })
    if hp.get("pipeline_summary"):
        history["records"].append({
            "label": "pipeline综合",
            "source": hp["pipeline_summary"].get("path", ""),
            "metrics": hp["pipeline_summary"],
        })

    # 当前 D1-D4
    cal = knowledge.get("calibration", {})
    ident = knowledge.get("identification", {})
    se = knowledge.get("state_estimation", {})

    history["current_d1d4"] = {
        "D1_hydrology": {"score": cal.get("d1_score"), "grade": cal.get("overall_grade")},
        "D2_hydraulics": {"score": knowledge.get("topology", {}).get("d2_score")},
        "D3_identification": {"score": ident.get("d3_score"), "coverage": ident.get("coverage")},
        "D4_state_estimation": {"score": se.get("d4_score"), "rmse_m": se.get("rmse_m")},
    }

    best_nse = max(
        (r["metrics"].get("flow_nse") or r["metrics"].get("best_nse") or 0
         for r in history["records"]),
        default=0,
    )
    history["best_overall"] = {"best_nse": best_nse}

    return history


# ── 主迁移逻辑 ────────────────────────────────────────────────────────────────

def split_knowledge(
    case_id: str,
    *,
    config_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """将膨胀 YAML 拆分为知识目录结构。"""
    cfg_file = Path(config_path) if config_path else BASE_DIR / "configs" / f"{case_id}.yaml"
    if not cfg_file.exists():
        return {"error": f"{cfg_file} not found"}

    full_cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
    knowledge = full_cfg.pop("knowledge", {})
    if not knowledge:
        return {"error": "no knowledge section found", "note": "YAML may already be split"}

    kb_dir = BASE_DIR / "knowledge" / case_id
    now = _now_iso()

    # 1. 构建参数溯源
    params = _build_param_provenance(knowledge, full_cfg)

    # 2. 构建模型版本卡片
    model_cards = _build_model_cards(knowledge)

    # 3. 构建精度历史
    precision = _build_precision_history(knowledge, full_cfg)

    # 4. 资产清单（只保留路径索引，不重复存内容）
    assets_inventory = knowledge.get("discovered_assets", {})
    terrain_index = knowledge.get("terrain_sections", {})
    zv_curves = knowledge.get("zv_curves", {})
    scada_index = knowledge.get("scada_timeseries", {})
    boundary = knowledge.get("boundary_conditions_csv", {})

    # 5. Horton 参数（独立文件）
    horton = knowledge.get("horton_params", {})

    # 6. 拓扑快照（保留关键结构，但不再冗余存在 config 中）
    topology = {
        "nodes": knowledge.get("topology", {}).get("nodes", {}),
        "channels": knowledge.get("topology", {}).get("channels", {}),
        "boundaries": knowledge.get("topology", {}).get("boundaries", {}),
    }
    reservoirs = knowledge.get("reservoirs", {})
    turbines = knowledge.get("turbines", {})
    gates = knowledge.get("gates", {})
    sections = knowledge.get("sections", {})

    # 7. 构建 manifest
    manifest = {
        "_schema_version": "3.0",
        "_migrated_at": now,
        "_architecture": "knowledge-directory",
        "case_id": case_id,
        "files": {
            "params/hydraulics.yaml": "水力学参数（含溯源链）",
            "params/hydrology.yaml": "水文参数（含溯源链）",
            "params/control.yaml": "控制参数（MPC/EKF/闸门）",
            "params/horton.yaml": "Horton下渗参数",
            "topology/topology.yaml": "拓扑结构（节点/河段/边界）",
            "topology/reservoirs.yaml": "水库参数",
            "topology/turbines.yaml": "水轮机参数",
            "topology/gates.yaml": "闸门参数",
            "topology/sections.yaml": "断面统计",
            "terrain/index.yaml": "实测断面文件注册",
            "curves/zv_curves.yaml": "水位-库容曲线注册",
            "precision/history.yaml": "精度历史记录",
            "assets/inventory.yaml": "全部文件清单",
            "assets/scada.yaml": "SCADA数据索引",
            "assets/boundary.yaml": "边界条件元数据",
        },
        "model_cards": {card_id: f"models/{card_id}.yaml" for card_id in model_cards},
    }

    report = {
        "case_id": case_id,
        "migrated_at": now,
        "knowledge_dir": str(kb_dir),
        "files_written": 0,
        "original_yaml_lines": len(cfg_file.read_text().split("\n")),
        "slim_yaml_lines": 0,
        "dry_run": dry_run,
    }

    if dry_run:
        print(f"[DRY-RUN] Would write {len(manifest['files']) + len(model_cards) + 1} files to {kb_dir}")
        report["files_written"] = len(manifest["files"]) + len(model_cards) + 1
        return report

    # 写入知识目录
    _write_yaml(kb_dir / "manifest.yaml", manifest)
    _write_yaml(kb_dir / "params" / "hydraulics.yaml", params["hydraulics"])
    _write_yaml(kb_dir / "params" / "hydrology.yaml", params["hydrology"])
    _write_yaml(kb_dir / "params" / "control.yaml", params["control"])
    _write_yaml(kb_dir / "params" / "horton.yaml", horton)
    _write_yaml(kb_dir / "topology" / "topology.yaml", topology)
    _write_yaml(kb_dir / "topology" / "reservoirs.yaml", reservoirs)
    _write_yaml(kb_dir / "topology" / "turbines.yaml", turbines)
    _write_yaml(kb_dir / "topology" / "gates.yaml", gates)
    _write_yaml(kb_dir / "topology" / "sections.yaml", sections)
    _write_yaml(kb_dir / "terrain" / "index.yaml", terrain_index)
    _write_yaml(kb_dir / "curves" / "zv_curves.yaml", zv_curves)
    _write_yaml(kb_dir / "precision" / "history.yaml", precision)
    _write_yaml(kb_dir / "assets" / "inventory.yaml", assets_inventory)
    _write_yaml(kb_dir / "assets" / "scada.yaml", scada_index)
    _write_yaml(kb_dir / "assets" / "boundary.yaml", boundary)

    for card_id, card_data in model_cards.items():
        _write_yaml(kb_dir / "models" / f"{card_id}.yaml", card_data)

    files_written = len(manifest["files"]) + len(model_cards) + 1
    report["files_written"] = files_written

    # 瘦身 config YAML：只保留 knowledge_dir 引用
    full_cfg["knowledge_dir"] = f"knowledge/{case_id}"
    full_cfg.pop("role_views", None)

    # 备份原 YAML
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = cfg_file.with_suffix(f".pre_split_{ts}.yaml")
    shutil.copy2(cfg_file, backup)

    cfg_file.write_text(
        yaml.dump(full_cfg, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
        encoding="utf-8",
    )

    slim_lines = len(cfg_file.read_text().split("\n"))
    report["slim_yaml_lines"] = slim_lines

    print(f"\n{'='*60}")
    print(f"[知识分层迁移] {case_id}")
    print(f"  原 YAML: {report['original_yaml_lines']} 行")
    print(f"  新 YAML: {slim_lines} 行 (瘦身 {report['original_yaml_lines'] - slim_lines} 行)")
    print(f"  知识目录: {kb_dir}")
    print(f"  写入文件: {files_written} 个")
    print(f"  模型卡片: {len(model_cards)} 个")
    print(f"  备份: {backup.name}")
    print(f"{'='*60}")

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="知识分层迁移器")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", help="YAML 配置路径")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = split_knowledge(args.case_id, config_path=args.config, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
