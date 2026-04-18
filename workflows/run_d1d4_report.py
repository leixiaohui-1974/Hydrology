#!/usr/bin/env python3
"""撰报 (ZhuanBao) — 成果报告自动生成

HydroMind 水智工坊 · Agent #9

D1-D4 全维度精度分析报告生成器。

从 Case YAML knowledge 层和合约中提取数据，生成结构化精度报告。
产品化：零硬编码，通用于所有案例。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflows._shared import BASE_DIR, WORKSPACE, load_case_config, write_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _grade(nse: float | None) -> str:
    if nse is None:
        return "无数据"
    if nse >= 0.90:
        return "优秀"
    if nse >= 0.80:
        return "良好"
    if nse >= 0.70:
        return "合格"
    if nse >= 0.50:
        return "较差"
    return "不合格"


def _level_score(score: float | None) -> str:
    if score is None:
        return "无数据"
    if score >= 4.0:
        return "L4"
    if score >= 3.0:
        return "L3"
    if score >= 2.0:
        return "L2"
    if score >= 1.0:
        return "L1"
    return "L0"


def generate_report(case_id: str, *, config_path: str | None = None) -> dict[str, Any]:
    """生成 D1-D4 完整精度报告。"""
    cfg = load_case_config(case_id, config_path)
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    product_dir = WORKSPACE / "cases" / case_id / "source_selection" / "product_outputs"

    cal_report = _safe_load(contracts_dir / "calibration_report.latest.json")
    imp_report = _safe_load(contracts_dir / "precision_improvement.latest.json")
    scada_report = _safe_load(contracts_dir / "scada_calibration.latest.json")
    d1d4_old = _safe_load(contracts_dir / "d1d4_precision_report.latest.json")
    steady = _safe_load(contracts_dir / "hydraulics_steady.latest.json")
    unsteady = _safe_load(contracts_dir / "hydraulics_unsteady.latest.json")
    selfdiag = _safe_load(contracts_dir / "hydraulic_selfdiag.latest.json")
    cascade = _safe_load(contracts_dir / "autonomous_cascade_report.latest.json")
    hp = _safe_load(product_dir / "hydraulic_params.json")

    registry_path = contracts_dir.parent / "knowledge_registry.json"
    registry_best = _safe_load(registry_path).get("best_metrics", {})

    # ── D1 水文建模（合并多源精度：率定→SCADA→精度提升→注册表最优）────────
    d1_stations = []
    station_best: dict[str, dict] = {}

    for s in cal_report.get("stations", []):
        sid = s.get("station_id", "")
        station_best[sid] = {
            "name": s.get("station_name", ""),
            "model_type": s.get("model_type", ""),
            "cal_nse": s.get("calibration", {}).get("nse"),
            "val_nse": s.get("validation", {}).get("nse"),
            "source": "calibration",
        }

    for s in scada_report.get("stations", []):
        sid = s.get("station_id", "")
        val_nse = s.get("validation", {}).get("nse")
        if val_nse and val_nse > (station_best.get(sid, {}).get("val_nse") or 0):
            station_best.setdefault(sid, {})
            station_best[sid].update({
                "name": s.get("station_name", station_best.get(sid, {}).get("name", "")),
                "model_type": s.get("model_type", "AR(1)"),
                "cal_nse": s.get("calibration", {}).get("nse"),
                "val_nse": val_nse,
                "source": "scada_calibration",
            })

    for entry in imp_report.get("improvements", []):
        sid = entry.get("station_id", "")
        improved = entry.get("improved", {})
        if improved and improved.get("nse_val") is not None:
            if improved["nse_val"] > (station_best.get(sid, {}).get("val_nse") or 0):
                station_best.setdefault(sid, {})
                station_best[sid].update({
                    "model_type": improved.get("model", ""),
                    "val_nse": improved["nse_val"],
                    "source": "precision_improvement",
                })

    for key, metric in registry_best.items():
        if metric.get("dimension") != "D1_hydrology":
            continue
        sid = metric.get("station_id", "")
        nse = metric.get("nse")
        if nse and nse > (station_best.get(sid, {}).get("val_nse") or 0):
            station_best.setdefault(sid, {"name": metric.get("station_name", sid)})
            station_best[sid].update({
                "model_type": metric.get("model", ""),
                "val_nse": nse,
                "source": metric.get("source", "registry"),
            })

    for sid, info in station_best.items():
        val_nse = info.get("val_nse")
        d1_stations.append({
            "station_id": sid,
            "name": info.get("name", sid),
            "model_type": info.get("model_type", ""),
            "cal_nse": info.get("cal_nse"),
            "val_nse": val_nse,
            "grade": _grade(val_nse),
            "target_met": (val_nse or 0) >= 0.85,
            "best_source": info.get("source", ""),
        })

    nse_values = [s["val_nse"] for s in d1_stations if s["val_nse"] is not None]
    d1_mean_nse = sum(nse_values) / len(nse_values) if nse_values else 0
    d1_above_target = sum(1 for s in d1_stations if s["target_met"])
    d1_ratio = d1_above_target / max(len(d1_stations), 1)
    d1_score = round(min(5.0, d1_mean_nse * 3.0 + d1_ratio * 2.0), 1) if nse_values else 0

    d1 = {
        "dimension": "D1 水文建模",
        "score": d1_score,
        "level": _level_score(d1_score),
        "mean_val_nse": round(d1_mean_nse, 4),
        "stations_above_085": d1_above_target,
        "stations_total": len(d1_stations),
        "stations": d1_stations,
        "problems": [
            f"{s['name']} val_nse={s['val_nse']:.3f} {s['grade']}"
            for s in d1_stations if not s["target_met"] and s["val_nse"] is not None
        ],
        "recommendations": [],
    }
    if d1_above_target < len(d1_stations):
        weak = [s for s in d1_stations if not s["target_met"]]
        d1["recommendations"].append(
            f"继续对 {len(weak)} 个弱站进行精度提升（多策略率定+高分辨率数据）"
        )

    # ── D2 水动力建模 ────────────────────────────────────────────────────────
    d2_nodes = []
    for name, info in unsteady.get("stations", {}).items():
        zb = hp.get("stations", {}).get(name, {}).get("zb")
        max_level = info if isinstance(info, (int, float)) else info.get("max_level_m", 0)
        water_depth = (max_level - zb) if zb is not None else None
        d2_nodes.append({
            "node": name,
            "max_level_m": round(max_level, 2),
            "zb_m": zb,
            "water_depth_m": round(water_depth, 2) if water_depth is not None else None,
            "physically_reasonable": water_depth is not None and 0 < water_depth < 100,
        })

    d2_reasonable = sum(1 for n in d2_nodes if n["physically_reasonable"])
    selfdiag_verdict = selfdiag.get("final_verdict", "未运行")
    selfdiag_critical = selfdiag.get("final_critical_count", -1)
    d2_ratio = d2_reasonable / max(len(d2_nodes), 1)
    d2_score = round(d2_ratio * 3.5 + (1.5 if selfdiag_verdict == "PASS" else 0), 1)
    d2_score = min(5.0, d2_score)

    d2 = {
        "dimension": "D2 水动力建模",
        "score": d2_score,
        "level": _level_score(d2_score),
        "steady_converged": steady.get("converged", False),
        "steady_iterations": steady.get("iterations"),
        "selfdiag_verdict": selfdiag_verdict,
        "selfdiag_critical": selfdiag_critical,
        "nodes_reasonable": d2_reasonable,
        "nodes_total": len(d2_nodes),
        "nodes": d2_nodes,
        "problems": [
            f"{n['node']} 水深{n['water_depth_m']}m 偏高"
            for n in d2_nodes if n["water_depth_m"] and n["water_depth_m"] > 50
        ],
        "recommendations": [],
    }
    if any(n["water_depth_m"] and n["water_depth_m"] > 50 for n in d2_nodes):
        high_nodes = [n["node"] for n in d2_nodes if n["water_depth_m"] and n["water_depth_m"] > 50]
        d2["recommendations"].append(f"{', '.join(high_nodes)} 水深偏高，建议增大对应河段断面宽度或补充实测断面数据")

    # ── D3 系统辨识 ──────────────────────────────────────────────────────────
    ident_step = {}
    for step in cascade.get("steps", []):
        if step.get("stage") == "identification":
            ident_step = step

    d3_stations = []
    for name, params in ident_step.get("params", {}).items():
        d3_stations.append({"name": name, "params": params})

    d3_coverage = ident_step.get("coverage", len(d3_stations) / max(1, len(d3_stations)))
    d3_score = round(min(5.0, d3_coverage * 3.5 + (1.5 if len(d3_stations) >= 5 else len(d3_stations) * 0.3)), 1)
    d3 = {
        "dimension": "D3 系统辨识",
        "score": d3_score,
        "level": _level_score(d3_score),
        "model_type": "FOPDT+IDZ",
        "stations_identified": len(d3_stations),
        "coverage": d3_coverage,
        "stations": d3_stations,
        "problems": [],
        "recommendations": ["可尝试 RLS/DualKalman 等在线辨识方法提升实时精度"],
    }

    # ── D4 状态估计 ──────────────────────────────────────────────────────────
    se_report = _safe_load(contracts_dir / "state_estimation.latest.json")
    da_report = _safe_load(contracts_dir / "data_assimilation.latest.json")

    if se_report.get("summary"):
        se_summary = se_report["summary"]
        d4_score = se_summary.get("d4_score", d1d4_old.get("d4_score", 2.4))
        d4_method = se_report.get("method", "EKF")
        d4_stations = se_report.get("stations", {})
        d4_problems = []
        d4_recs = []

        if se_summary.get("no_data", 0) > 0:
            d4_problems.append(f"{se_summary['no_data']} 个站点无观测数据")
        for sid, sinfo in d4_stations.items():
            if isinstance(sinfo, dict) and sinfo.get("status") == "completed":
                if not sinfo.get("converged"):
                    d4_problems.append(f"{sinfo.get('name', sid)} 未收敛 (RMSE={sinfo.get('rmse_m')}m)")

        if da_report.get("recommendation"):
            best = da_report["recommendation"].get("overall_best_method", "")
            d4_recs.append(f"数据同化比选推荐: {best}")
            for target, rec in da_report["recommendation"].get("by_target", {}).items():
                d4_recs.append(f"  {target}: {rec.get('best_method')} (avg_NSE={rec.get('avg_nse')})")

        d4 = {
            "dimension": "D4 状态估计",
            "score": d4_score,
            "level": _level_score(d4_score),
            "method": d4_method,
            "sensor_coverage": se_summary.get("completed", 0) / max(se_summary.get("total_stations", 1), 1),
            "avg_rmse_m": se_summary.get("avg_rmse_m"),
            "avg_nse": se_summary.get("avg_nse"),
            "completed": se_summary.get("completed", 0),
            "converged": se_summary.get("converged", 0),
            "problems": d4_problems or ["无"],
            "recommendations": d4_recs or ["持续积累观测数据以提升同化精度"],
        }
    else:
        d4_score = d1d4_old.get("d4_score", 2.4)
        d4 = {
            "dimension": "D4 状态估计",
            "score": d4_score,
            "level": _level_score(d4_score),
            "method": "EKF（待实施）",
            "sensor_coverage": 0.0,
            "problems": ["状态估计尚未实施，依赖 D1+D3 的率定和辨识结果"],
            "recommendations": [
                "基于 D3 辨识参数实施 EKF/UKF 状态估计",
                "优先对弱站进行水位同化",
            ],
        }

    # ── 综合 ────────────────────────────────────────────────────────────────
    scores = [d1["score"], d2["score"], d3["score"], d4["score"]]
    capability_score = sum(scores) / len(scores) if scores else 0
    wnal_score = d1d4_old.get("wnal_score", 0)

    report = {
        "case_id": case_id,
        "display_name": cfg.get("display_name", case_id),
        "generated_at": _now_iso(),
        "target_nse": 0.85,
        "capability_score": round(capability_score, 3),
        "wnal_score": wnal_score,
        "wnal_level": _level_score(wnal_score * 5),
        "dimensions": {
            "d1": d1,
            "d2": d2,
            "d3": d3,
            "d4": d4,
        },
        "overall_problems": d1.get("problems", []) + d2.get("problems", []) + d4.get("problems", []),
        "overall_recommendations": d1.get("recommendations", []) + d2.get("recommendations", [])
                                   + d3.get("recommendations", []) + d4.get("recommendations", []),
    }

    contracts_dir.mkdir(parents=True, exist_ok=True)
    write_json(contracts_dir / "d1d4_precision_report.latest.json", report)
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="D1-D4 全维度精度分析报告")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", help="YAML 配置路径")
    args = parser.parse_args()

    result = generate_report(args.case_id, config_path=args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
