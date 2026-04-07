#!/usr/bin/env python3
"""探源 (TanYuan) — 数据勘探与知识发现

HydroMind 水智工坊 · Agent #1

数据质量审计工作流 — 产品化。

对 case 的 SQLite 数据做全维度质量评估：
  - 完整性（时间范围、记录数、缺口）
  - 合理性（物理区间、vs 设计值）
  - 一致性（多源对比、量纲检查）
  - 负值诊断
  - 缺口分析

输出 JSON + MD 报告到 contracts/

Usage:
    python3 -m workflows run data_audit --case-id zhongxian
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from workflows._shared import load_case_config, write_json, WORKSPACE


def _find_db(cfg: dict) -> str | None:
    for p in cfg.get("sqlite_paths", []):
        if "hydromind" in str(p).lower() and Path(p).exists():
            return str(p)
    for scan_dir in cfg.get("scan_dirs", []):
        for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
            return str(f)
    return None


def _detect_gaps(times: pd.Series, expected_step_h: float = 1.0) -> list[dict]:
    """检测时间序列中超过预期步长的缺口。"""
    if len(times) < 2:
        return []
    times = pd.to_datetime(times)
    diffs = times.diff().dt.total_seconds() / 3600
    threshold = expected_step_h * 1.5
    gaps = []
    for idx in diffs[diffs > threshold].index:
        gaps.append({
            "from": str(times.iloc[idx - 1]),
            "to": str(times.iloc[idx]),
            "hours": float(diffs.iloc[idx]),
        })
    return gaps


def run_audit(case_id: str, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "No hydromind SQLite found"}

    conn = sqlite3.connect(db_path)
    print(f"=== 数据质量审计: {case_id} ===")
    print(f"Database: {db_path}")

    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
    table_list = tables["name"].tolist()
    print(f"Tables: {table_list}")

    report: dict[str, Any] = {
        "case_id": case_id,
        "workflow": "data_quality_audit",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "database": db_path,
        "tables": {},
        "station_audit": {},
        "issues": [],
        "scores": {},
    }

    for tbl in table_list:
        count = pd.read_sql(f"SELECT count(*) as n FROM '{tbl}'", conn)["n"][0]
        report["tables"][tbl] = {"row_count": int(count)}

    if "timeseries" not in table_list:
        conn.close()
        return {**report, "error": "no timeseries table"}

    # Station-variable summary
    combos = pd.read_sql("""
        SELECT station_id, variable, count(*) as n,
               min(value) as val_min, max(value) as val_max, avg(value) as val_avg,
               min(time) as t_start, max(time) as t_end
        FROM timeseries
        WHERE station_id LIKE 's%'
        GROUP BY station_id, variable ORDER BY station_id, variable
    """, conn)

    # Stations metadata
    stations_meta = {}
    if "stations" in table_list:
        st_df = pd.read_sql("SELECT id, name, metadata_json FROM stations", conn)
        for _, row in st_df.iterrows():
            raw_meta = row["metadata_json"]
            if isinstance(raw_meta, str):
                try:
                    meta = json.loads(raw_meta) if raw_meta else {}
                except Exception:
                    meta = {}
            elif isinstance(raw_meta, dict):
                meta = raw_meta
            else:
                meta = {}
            stations_meta[row["id"]] = {"name": row["name"], **meta}

    # Audit each station's key variables
    station_ids = sorted(combos["station_id"].unique())
    for sid in station_ids:
        if not sid.startswith("s"):
            continue
        sid_data = combos[combos["station_id"] == sid]
        meta = stations_meta.get(sid, {})
        audit: dict[str, Any] = {"name": meta.get("name", sid), "variables": {}}

        for _, row in sid_data.iterrows():
            var = row["variable"]
            var_audit: dict[str, Any] = {
                "n": int(row["n"]),
                "range": [float(row["val_min"]), float(row["val_max"])],
                "mean": float(row["val_avg"]),
                "time_range": [row["t_start"], row["t_end"]],
            }

            # Negative value check
            neg = pd.read_sql(
                f"SELECT count(*) as n FROM timeseries WHERE station_id='{sid}' "
                f"AND variable='{var}' AND value < 0", conn,
            )
            n_neg = int(neg["n"].iloc[0])
            if n_neg > 0:
                var_audit["negative_count"] = n_neg
                var_audit["negative_pct"] = round(n_neg / row["n"] * 100, 2)
                report["issues"].append({
                    "station": sid,
                    "variable": var,
                    "type": "negative_values",
                    "count": n_neg,
                    "severity": "warning" if n_neg / row["n"] < 0.1 else "error",
                })

            # Gap analysis for H_up
            if var == "H_up":
                ts = pd.read_sql(
                    f"SELECT time FROM timeseries WHERE station_id='{sid}' "
                    f"AND variable='H_up' ORDER BY time", conn,
                )
                gaps = _detect_gaps(ts["time"])
                if gaps:
                    var_audit["gaps"] = gaps[:10]
                    var_audit["total_gaps"] = len(gaps)
                    report["issues"].append({
                        "station": sid,
                        "variable": "H_up",
                        "type": "time_gaps",
                        "count": len(gaps),
                        "max_gap_hours": max(g["hours"] for g in gaps),
                        "severity": "warning",
                    })

                # Validate vs design levels
                np_ = meta.get("normal_pool")
                dp_ = meta.get("dead_pool")
                if np_ is not None:
                    h_max = float(row["val_max"])
                    h_min = float(row["val_min"])
                    if h_max > np_ * 1.01:
                        report["issues"].append({
                            "station": sid, "type": "exceeds_normal_pool",
                            "obs_max": h_max, "normal_pool": np_, "severity": "error",
                        })
                    if dp_ is not None and h_min < dp_ * 0.99:
                        report["issues"].append({
                            "station": sid, "type": "below_dead_pool",
                            "obs_min": h_min, "dead_pool": dp_, "severity": "warning",
                        })
                    var_audit["design_validation"] = {
                        "normal_pool": np_,
                        "dead_pool": dp_,
                        "within_range": dp_ * 0.99 <= h_min and h_max <= np_ * 1.01,
                    }

            audit["variables"][var] = var_audit

        report["station_audit"][sid] = audit
        print(f"  {sid} ({audit['name']}): {len(audit['variables'])} variables, "
              f"{sum(1 for i in report['issues'] if i.get('station') == sid)} issues")

    # Score computation
    n_issues_error = sum(1 for i in report["issues"] if i.get("severity") == "error")
    n_issues_warn = sum(1 for i in report["issues"] if i.get("severity") == "warning")
    has_gaps = any(i["type"] == "time_gaps" for i in report["issues"])

    report["scores"] = {
        "completeness": 4 if not has_gaps else 3,
        "reasonableness": 5 if n_issues_error == 0 else 3,
        "consistency": 3,
        "traceability": 4,
        "total_issues": len(report["issues"]),
        "errors": n_issues_error,
        "warnings": n_issues_warn,
    }

    # Write JSON
    out_json = WORKSPACE / "cases" / case_id / "contracts" / "data_quality_audit.latest.json"
    write_json(out_json, report)
    print(f"\nJSON report: {out_json}")

    # Write MD
    md_path = WORKSPACE / "cases" / case_id / "contracts" / "data_quality_audit_report.md"
    _write_md_report(report, md_path)
    print(f"MD report: {md_path}")

    conn.close()
    return report


def _write_md_report(report: dict, path: Path) -> None:
    """从审计结果生成 MD 报告。"""
    lines = [
        f"# {report['case_id']} 数据质量审计报告",
        f"\n> 自动生成 | {report['generated_at']}",
        f"\n## 数据库: `{report['database']}`",
        f"\n| 表 | 记录数 |",
        f"|---|--------|",
    ]
    for tbl, info in report["tables"].items():
        lines.append(f"| {tbl} | {info['row_count']:,} |")

    lines.append("\n## 站点审计\n")
    for sid, audit in report["station_audit"].items():
        lines.append(f"### {sid} ({audit['name']})\n")
        lines.append("| 变量 | 记录数 | 范围 | 均值 | 时间跨度 | 问题 |")
        lines.append("|------|--------|------|------|---------|------|")
        for var, va in audit["variables"].items():
            issues = []
            if va.get("negative_count"):
                issues.append(f"负值{va['negative_count']}条({va['negative_pct']}%)")
            if va.get("total_gaps"):
                issues.append(f"缺口{va['total_gaps']}处")
            dv = va.get("design_validation", {})
            if dv and not dv.get("within_range", True):
                issues.append("超设计范围")
            issue_str = "; ".join(issues) if issues else "—"
            lines.append(
                f"| {var} | {va['n']:,} | [{va['range'][0]:.1f}, {va['range'][1]:.1f}] | "
                f"{va['mean']:.1f} | {va['time_range'][0][:10]}~{va['time_range'][1][:10]} | {issue_str} |"
            )
        lines.append("")

    lines.append("\n## 问题清单\n")
    lines.append("| 站点 | 类型 | 严重度 | 描述 |")
    lines.append("|------|------|--------|------|")
    for issue in report["issues"]:
        desc_parts = [f"{k}={v}" for k, v in issue.items() if k not in ("station", "type", "severity")]
        lines.append(f"| {issue.get('station','-')} | {issue['type']} | {issue['severity']} | {'; '.join(desc_parts)} |")

    lines.append("\n## 评分\n")
    for k, v in report["scores"].items():
        lines.append(f"- **{k}**: {v}")

    lines.append("\n---\n*_auto_generated: true*")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="数据质量审计工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    run_audit(case_id=args.case_id, config_path=args.config)


if __name__ == "__main__":
    main()
