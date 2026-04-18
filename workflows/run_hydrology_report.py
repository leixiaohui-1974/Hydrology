#!/usr/bin/env python3
"""撰报 (ZhuanBao) — 成果报告自动生成

HydroMind 水智工坊 · Agent #9

D1 水文模型精度评价报告自动生成器。

从 calibration_report / precision_improvement / data_assimilation / scada_calibration
读取率定验证结果，自动择优生成结构化 Markdown 报告。

产品化：零硬编码，通用于所有案例。

Usage:
    python3 -m workflows.run_hydrology_report --case-id zhongxian
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflows._shared import (
    WORKSPACE,
    load_case_config,
    save_knowledge_file,
    build_name_to_sid,
)
from workflows._autonomy_policy import grade_nse, load_merged_autonomy_policy


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def generate_report(case_id: str, config_path: str | None = None) -> dict[str, Any]:
    """生成 D1 水文模型精度报告（MD + JSON），自动从多源择优。"""
    cfg = load_case_config(case_id, config_path)
    autonomy = load_merged_autonomy_policy(case_id, config_path)
    rep = autonomy.get("reporting") if isinstance(autonomy.get("reporting"), dict) else {}
    contracts = WORKSPACE / "cases" / case_id / "contracts"

    cal_report = _load_json(contracts / "calibration_report.latest.json")
    scada_report = _load_json(contracts / "scada_calibration.latest.json")
    improve_report = _load_json(contracts / "precision_improvement.latest.json")
    assim_report = _load_json(contracts / "data_assimilation.latest.json")

    # Build per-station best metrics across all sources
    stations: dict[str, dict[str, Any]] = {}

    # Source 1: calibration_report (list of station dicts)
    if cal_report:
        for sm in cal_report.get("stations", []):
            if not isinstance(sm, dict):
                continue
            sid = sm.get("station_id", "")
            if not sid:
                continue
            stations.setdefault(sid, {"sources": {}})
            stations[sid]["name"] = sm.get("station_name", sid)
            cal_m = sm.get("calibration", {})
            val_m = sm.get("validation", {})
            stations[sid]["sources"]["calibrate"] = {
                "cal_nse": cal_m.get("nse"),
                "val_nse": val_m.get("nse"),
                "cal_rmse": cal_m.get("rmse"),
                "val_rmse": val_m.get("rmse"),
                "cal_kge": cal_m.get("kge"),
                "val_kge": val_m.get("kge"),
            }

    # Source 2: scada_calibration (list of station dicts)
    if scada_report:
        for sm in scada_report.get("stations", []):
            if not isinstance(sm, dict):
                continue
            sid = sm.get("station_id", "")
            if not sid:
                continue
            stations.setdefault(sid, {"sources": {}})
            stations[sid].setdefault("name", sm.get("station_name", sid))
            cal_m = sm.get("calibration", {})
            val_m = sm.get("validation", {})
            stations[sid]["sources"]["scada"] = {
                "cal_nse": cal_m.get("nse"),
                "val_nse": val_m.get("nse"),
                "cal_rmse": cal_m.get("rmse"),
                "val_rmse": val_m.get("rmse"),
            }

    # Source 3: precision_improvement (list under 'improvements')
    if improve_report:
        for sm in improve_report.get("improvements", []):
            if not isinstance(sm, dict):
                continue
            sid = sm.get("station_id", "")
            if not sid:
                continue
            stations.setdefault(sid, {"sources": {}})
            stations[sid].setdefault("name", sm.get("station_name", sid))
            improved = sm.get("improved") or {}
            original = sm.get("original") or {}
            if not isinstance(improved, dict):
                improved = {}
            if not isinstance(original, dict):
                original = {}
            stations[sid]["sources"]["improve"] = {
                "val_nse": improved.get("nse_val"),
                "baseline_nse": original.get("nse_val"),
                "strategy": improved.get("model"),
            }

    # Source 4: data_assimilation (best method per Chinese station name)
    if assim_report:
        results = assim_report.get("results") or {}
        if not isinstance(results, dict):
            results = {}
        hydro = results.get("hydrology") or {}
        if not isinstance(hydro, dict):
            hydro = {}
        name_to_sid = build_name_to_sid(cfg)
        for cn, methods in hydro.items():
            sid = name_to_sid.get(cn, cn)
            if not isinstance(methods, dict):
                continue
            best_m = methods.get("_best", {})
            stations.setdefault(sid, {"sources": {}})
            stations[sid].setdefault("name", cn)
            stations[sid]["sources"]["assimilate"] = {
                "val_nse": best_m.get("nse"),
                "val_rmse": best_m.get("rmse"),
                "method": best_m.get("method", "EnKF"),
            }

    # Determine best validation NSE per station
    for sid, sdata in stations.items():
        best_val_nse = None
        best_source = None
        for src_name, src_data in sdata.get("sources", {}).items():
            v = src_data.get("val_nse")
            if v is not None and (best_val_nse is None or v > best_val_nse):
                best_val_nse = v
                best_source = src_name
        sdata["best_val_nse"] = best_val_nse
        sdata["best_source"] = best_source
        cal_nses = [s.get("cal_nse") for s in sdata["sources"].values() if s.get("cal_nse")]
        sdata["best_cal_nse"] = max(cal_nses) if cal_nses else None

    # Generate MD
    lines = [
        f"# D1 水文模型精度评价报告 — {case_id}",
        "",
        f"> 自动生成 | case_id: {case_id} | {_now_iso()}",
        "",
        "## 1. 概述",
        "",
        f"对 {case_id} 流域所有控制站点进行水文模型率定验证精度评价。"
        "本报告自动从多个工作流（率定、SCADA、精度改进、数据同化）中择优汇总。",
        "",
        "## 2. 逐站精度汇总（择优后）",
        "",
        "| 站点 | 名称 | 最优验证 NSE | 最优来源 | 等级 | 最优率定 NSE |",
        "|------|------|-------------|---------|------|------------|",
    ]

    sorted_sids = sorted(stations.keys())
    for sid in sorted_sids:
        sd = stations[sid]
        v_nse = sd.get("best_val_nse")
        v_str = f"{v_nse:.4f}" if v_nse is not None else "N/A"
        c_nse = sd.get("best_cal_nse")
        c_str = f"{c_nse:.4f}" if c_nse is not None else "N/A"
        lines.append(
            f"| {sid} | {sd.get('name', '')} "
            f"| {v_str} "
            f"| {sd.get('best_source', '')} "
            f"| {grade_nse(v_nse, rep)} "
            f"| {c_str} |"
        )

    # Per-source detail tables
    lines.extend(["", "## 3. 分源详情", ""])

    # 3.1 Calibrate
    lines.extend(["### 3.1 基础率定 (`calibrate`)", ""])
    if cal_report:
        lines.extend([
            "| 站点 | 名称 | cal NSE | val NSE | cal RMSE | val RMSE | cal KGE | val KGE |",
            "|------|------|---------|---------|----------|----------|---------|---------|",
        ])
        for sid in sorted_sids:
            src = stations.get(sid, {}).get("sources", {}).get("calibrate")
            if not src:
                continue
            name = stations[sid].get("name", "")
            def _f(v):
                return f"{v:.4f}" if v is not None else "—"
            lines.append(
                f"| {sid} | {name} "
                f"| {_f(src.get('cal_nse'))} "
                f"| {_f(src.get('val_nse'))} "
                f"| {_f(src.get('cal_rmse'))} "
                f"| {_f(src.get('val_rmse'))} "
                f"| {_f(src.get('cal_kge'))} "
                f"| {_f(src.get('val_kge'))} |"
            )
    else:
        lines.append("*无数据*")

    # 3.2 SCADA
    lines.extend(["", "### 3.2 SCADA 率定 (`scada`)", ""])
    if scada_report:
        lines.extend([
            "| 站点 | cal NSE | val NSE | cal RMSE | val RMSE |",
            "|------|---------|---------|----------|----------|",
        ])
        for sid in sorted_sids:
            src = stations.get(sid, {}).get("sources", {}).get("scada")
            if not src:
                continue
            def _f(v):
                return f"{v:.4f}" if v is not None else "—"
            lines.append(
                f"| {sid} | {_f(src.get('cal_nse'))} "
                f"| {_f(src.get('val_nse'))} "
                f"| {_f(src.get('cal_rmse'))} "
                f"| {_f(src.get('val_rmse'))} |"
            )
    else:
        lines.append("*无数据*")

    # 3.3 Improve
    lines.extend(["", "### 3.3 精度自提升 (`improve`)", ""])
    if improve_report:
        lines.extend([
            "| 站点 | val NSE (改进后) | 最优策略 |",
            "|------|-----------------|---------|",
        ])
        for sid in sorted_sids:
            src = stations.get(sid, {}).get("sources", {}).get("improve")
            if not src:
                continue
            v = src.get("val_nse")
            v_str = f"{v:.4f}" if v is not None else "—"
            lines.append(f"| {sid} | {v_str} | {src.get('strategy', '')} |")
    else:
        lines.append("*无数据*")

    # 3.4 Assimilate
    lines.extend(["", "### 3.4 数据同化 (`assimilate`)", ""])
    if assim_report:
        lines.extend([
            "| 站点 | 名称 | NSE | RMSE | 最优方法 |",
            "|------|------|-----|------|---------|",
        ])
        for sid in sorted_sids:
            src = stations.get(sid, {}).get("sources", {}).get("assimilate")
            if not src:
                continue
            v = src.get("val_nse")
            r = src.get("val_rmse")
            v_s = f"{v:.4f}" if v is not None else "—"
            r_s = f"{r:.4f}" if r is not None else "—"
            lines.append(
                f"| {sid} | {stations[sid].get('name', '')} "
                f"| {v_s} | {r_s} | {src.get('method', '')} |"
            )
    else:
        lines.append("*无数据*")

    # 4. Model architecture
    lines.extend([
        "", "## 4. 模型架构说明", "",
        "### 水文模型可独立运行，也支持与流域划分耦合", "",
        "- **独立模式**：用 SCADA 实测入流/出流直接率定，快速验证",
        "- **耦合模式**：流域划分（DEM → 子流域面积/坡度/河网）→ 产汇流模型 → 出流序列",
        "- DEM 数据支持双来源：",
        "  1. **公开下载**：SRTM 30m / ASTER GDEM / ALOS 12.5m",
        "  2. **case 本地**：`cases/{case_id}/source_selection/dem/` 目录",
        "",
        "### 水文→水力学耦合路径", "",
        "水文模型的站点出流序列 `Q_out(t)` 作为一维水力学模型的上游边界入流：",
        "",
        "```",
        "水文模型 (D1)           水力学模型 (D2)",
        "┌──────────┐           ┌──────────────┐",
        "│ 降雨产流   │ Q_out(t) │ 水库水量平衡   │",
        "│ 汇流演算   │────────→│ 梯级水位模拟   │",
        "│ 站点出流   │           │ 水位过程      │",
        "└──────────┘           └──────────────┘",
        "```",
        "",
        "耦合接口在 `workflows/run_coupled_hydro_hydraulic.py` 中实现。",
    ])

    # 5. Summary
    val_nses = [sd["best_val_nse"] for sd in stations.values() if sd.get("best_val_nse") is not None]
    cal_nses = [sd["best_cal_nse"] for sd in stations.values() if sd.get("best_cal_nse") is not None]
    pass_val = float(rep.get("pass_val_nse", 0.80))
    n_pass = sum(1 for v in val_nses if v >= pass_val)

    lines.extend([
        "", "## 5. 总结", "",
        f"- 站点数: **{len(stations)}**",
        f"- 平均最优验证 NSE: **{sum(val_nses)/len(val_nses):.4f}**" if val_nses else "- 平均验证 NSE: N/A",
        f"- 达标站点 (NSE ≥ {pass_val:.2f}): **{n_pass}/{len(val_nses)}**",
        "",
        "---",
        "",
        f"*数据来源: `cases/{case_id}/contracts/` 下多个合约文件*",
        f"*工作流: `Hydrology/workflows/run_hydrology_report.py`*",
        "*_auto_generated: true*",
    ])

    md_content = "\n".join(lines)
    md_path = contracts / "D1_hydrology_precision_report.md"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"报告: {md_path}")

    # Knowledge fixation
    precision_entry = {
        "dimension": "D1_hydrology",
        "generated_at": _now_iso(),
        "stations": {},
    }
    for sid in sorted_sids:
        sd = stations[sid]
        precision_entry["stations"][sid] = {
            "name": sd.get("name"),
            "best_val_nse": sd.get("best_val_nse"),
            "best_source": sd.get("best_source"),
            "best_cal_nse": sd.get("best_cal_nse"),
        }

    save_knowledge_file(case_id, "precision/d1_hydrology.yaml", precision_entry)
    print(f"知识固化: knowledge/{case_id}/precision/d1_hydrology.yaml")

    summary = {
        "n_stations": len(stations),
        "avg_val_nse": sum(val_nses) / len(val_nses) if val_nses else None,
        "n_pass_val_target": n_pass,
        "pass_val_nse": pass_val,
        "n_pass_80": n_pass,
    }
    return {"report_path": str(md_path), "summary": summary}


def main():
    parser = argparse.ArgumentParser(description="D1 水文精度报告生成")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    generate_report(args.case_id, args.config)


if __name__ == "__main__":
    main()
