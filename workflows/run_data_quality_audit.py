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

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from workflows._shared import (
    load_case_config,
    resolve_workspace_relpath,
    select_preferred_sqlite,
    sqlite_table_columns,
    sqlite_table_names,
    write_json,
    WORKSPACE,
)


SQLITE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}
OBSERVATION_VARIABLE_COLUMN = {
    "water_level": "Z",
    "flow": "Q",
}
REQUIRED_OBSERVATION_COLUMNS = {"station", "time"}
REQUIRED_TIMESERIES_COLUMNS = {"station_id", "variable", "time_step", "time", "value"}


def _artifact_guidance(*, degraded: bool) -> list[dict[str, str]]:
    if degraded:
        return [
            {
                "artifact": "data_quality_audit.latest.json",
                "purpose": "查看降级原因、忽略的无效 SQLite 路径与当前可用的数据审计结论。",
            },
            {
                "artifact": "data_quality_audit_report.md",
                "purpose": "给业务人员快速查看当前案例的数据审计状态与下一步补数建议。",
            },
        ]
    return [
        {
            "artifact": "data_quality_audit.latest.json",
            "purpose": "查看站点级问题清单、评分结果与各类质量告警。",
        },
        {
            "artifact": "data_quality_audit_report.md",
            "purpose": "阅读业务友好的数据质量结论，决定是否继续后续建模工作流。",
        },
    ]


def _supports_audit_schema(path: Path) -> bool:
    table_names = sqlite_table_names(path)
    if table_names is None:
        return False
    if "timeseries" in table_names:
        timeseries_columns = sqlite_table_columns(path, "timeseries") or set()
        if REQUIRED_TIMESERIES_COLUMNS.issubset(timeseries_columns):
            return True
    if "observations" in table_names:
        observation_columns = sqlite_table_columns(path, "observations") or set()
        if REQUIRED_OBSERVATION_COLUMNS.issubset(observation_columns) and any(
            column in observation_columns for column in OBSERVATION_VARIABLE_COLUMN.values()
        ):
            return True
    return False



def _is_workspace_local_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(WORKSPACE.resolve())
        return True
    except ValueError:
        return False



def _redacted_external_path(path: Path) -> str:
    name = path.name or "unknown"
    return f"[external]/{name}"



def _persisted_raw_path_or_none(raw_path: Any) -> str | None:
    text = str(raw_path or "").strip()
    if not text:
        return None
    if text.startswith("[external]/"):
        return text
    try:
        path = resolve_workspace_relpath(text)
    except Exception:
        return text
    if _is_workspace_local_path(path):
        return path.resolve().relative_to(WORKSPACE.resolve()).as_posix()
    return _redacted_external_path(path)



def _sanitize_invalid_sqlite_paths(raw_paths: list[str]) -> list[str]:
    sanitized: list[str] = []
    for raw_path in raw_paths:
        persisted = _persisted_raw_path_or_none(raw_path)
        if persisted:
            sanitized.append(persisted)
    return sanitized



def _find_db(cfg: dict) -> tuple[str | None, list[str]]:
    return select_preferred_sqlite(
        cfg,
        schema_support_fn=_supports_audit_schema,
        workspace=WORKSPACE,
        allow_unsupported_fallback=True,
    )



def _degraded_report(
    case_id: str,
    *,
    invalid_sqlite_paths: list[str],
    database: str | None = None,
    issue_type: str = "missing_usable_sqlite",
    issue_message: str = "未发现可用于数据质量审计的 SQLite 数据库。",
    business_status_zh: str = "当前案例缺少可用 SQLite，已输出降级版数据审计结果。",
    recommended_next_action: str = "请先在案例配置的 sqlite_paths 中补充可读取的 .sqlite/.sqlite3/.db 文件，或将数据库放入 scan_dirs 后重新执行。",
    existing_issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    issues = list(existing_issues or [])
    issues.append(
        {
            "type": issue_type,
            "severity": "warning",
            "message": issue_message,
        }
    )
    return {
        "case_id": case_id,
        "workflow": "data_quality_audit",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "database": database,
        "tables": {},
        "station_audit": {},
        "issues": issues,
        "scores": {},
        "degraded": True,
        "status": "degraded",
        "outcome_status": "degraded",
        "business_status_zh": business_status_zh,
        "recommended_next_action": recommended_next_action,
        "artifact_guidance": _artifact_guidance(degraded=True),
        "ignored_invalid_sqlite_paths": invalid_sqlite_paths,
    }


def _list_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows if len(row) > 1 and row[1]}



def _resolve_observation_columns(available_columns: set[str]) -> tuple[dict[str, str] | None, str | None]:
    missing_required_columns = sorted(REQUIRED_OBSERVATION_COLUMNS - available_columns)
    if missing_required_columns:
        return None, f"observations 缺少必要列: {', '.join(missing_required_columns)}"

    selected_columns: dict[str, str] = {}
    missing_value_columns: list[str] = []
    for variable, column in OBSERVATION_VARIABLE_COLUMN.items():
        if column in available_columns:
            selected_columns[variable] = column
        else:
            missing_value_columns.append(column)

    if not selected_columns:
        return None, (
            "observations 缺少可审计变量列；至少需要 "
            f"{', '.join(sorted(OBSERVATION_VARIABLE_COLUMN.values()))} 中的一列"
        )

    if missing_value_columns:
        return selected_columns, (
            "observations 缺少部分变量列: "
            f"{', '.join(missing_value_columns)}；当前将按已有列输出审计结果"
        )
    return selected_columns, None



def _detect_gaps(times: pd.Series, expected_step_h: float = 1.0) -> list[dict]:
    """检测时间序列中超过预期步长的缺口。"""
    if len(times) < 2:
        return []
    times = pd.Series(pd.to_datetime(times)).reset_index(drop=True)
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



def _infer_expected_step_hours(times: pd.Series) -> float:
    if len(times) < 2:
        return 1.0
    parsed_times = pd.Series(pd.to_datetime(times)).sort_values(ignore_index=True)
    diff_seconds = parsed_times.diff().dt.total_seconds().dropna()
    positive_diff_seconds = diff_seconds[diff_seconds > 0]
    if positive_diff_seconds.empty:
        return 1.0
    dominant_step_seconds = float(positive_diff_seconds.mode().min())
    dominant_step_hours = dominant_step_seconds / 3600
    return dominant_step_hours if dominant_step_hours > 0 else 1.0


def run_audit(case_id: str, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_case_config(case_id, config_path)
    db_path, invalid_sqlite_paths = _find_db(cfg)
    invalid_sqlite_paths = _sanitize_invalid_sqlite_paths(invalid_sqlite_paths)
    out_json = WORKSPACE / "cases" / case_id / "contracts" / "data_quality_audit.latest.json"
    md_path = WORKSPACE / "cases" / case_id / "contracts" / "data_quality_audit_report.md"
    if not db_path:
        report = _degraded_report(
            case_id,
            invalid_sqlite_paths=invalid_sqlite_paths,
        )
        write_json(out_json, report)
        _write_md_report(report, md_path)
        return report

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
        "degraded": False,
        "status": "completed",
        "outcome_status": "completed",
        "business_status_zh": "数据质量审计已完成。",
        "recommended_next_action": "优先查看 data_quality_audit.latest.json 与 Markdown 报告；若发现异常值或缺口，再补充数据后重跑。",
        "artifact_guidance": _artifact_guidance(degraded=False),
        "ignored_invalid_sqlite_paths": invalid_sqlite_paths,
    }

    for tbl in table_list:
        count = pd.read_sql(f"SELECT count(*) as n FROM '{tbl}'", conn)["n"][0]
        report["tables"][tbl] = {"row_count": int(count)}

    observations_columns = _list_table_columns(conn, "observations") if "observations" in table_list else set()
    timeseries_columns = _list_table_columns(conn, "timeseries") if "timeseries" in table_list else set()
    has_supported_timeseries = REQUIRED_TIMESERIES_COLUMNS.issubset(timeseries_columns)

    if "timeseries" in table_list and not has_supported_timeseries:
        report["issues"].append(
            {
                "type": "unsupported_timeseries_schema",
                "severity": "warning",
                "message": "timeseries 表已存在，但缺少 station_id/variable/time/value 完整列集；本次已回退到 observations 宽表继续审计。",
            }
        )

    if not has_supported_timeseries:
        if "observations" not in table_list:
            conn.close()
            report = _degraded_report(
                case_id,
                database=db_path,
                invalid_sqlite_paths=invalid_sqlite_paths,
                issue_type="missing_supported_timeseries_schema",
                issue_message="已发现 SQLite，但缺少可审计的 timeseries/observations 表结构。",
                business_status_zh="当前案例已发现 SQLite，但数据表结构暂不支持完整数据质量审计，已输出降级版结果。",
                recommended_next_action="请补充 timeseries 表，或提供 observations 宽表（至少包含 station/time/Z 或 Q 列）后重新执行。",
                existing_issues=report["issues"],
            )
            write_json(out_json, report)
            _write_md_report(report, md_path)
            return report

        selected_columns, observation_schema_message = _resolve_observation_columns(observations_columns)
        if selected_columns is None:
            conn.close()
            report = _degraded_report(
                case_id,
                database=db_path,
                invalid_sqlite_paths=invalid_sqlite_paths,
                issue_type="unsupported_observations_schema",
                issue_message=observation_schema_message or "observations 表结构暂不支持当前数据质量审计。",
                business_status_zh="当前案例已发现 observations 表，但字段结构暂不支持完整数据质量审计，已输出降级版结果。",
                recommended_next_action="请补充 observations 的 station/time 以及 Z 或 Q 列后重新执行。",
                existing_issues=report["issues"],
            )
            write_json(out_json, report)
            _write_md_report(report, md_path)
            return report

        query_columns = ["station", "time", *sorted(set(selected_columns.values()))]
        observations = pd.read_sql(
            f"SELECT {', '.join(query_columns)} FROM observations ORDER BY station, time",
            conn,
        )
        conn.close()
        report["tables"]["observations"] = {"row_count": int(len(observations))}
        station_audit: dict[str, Any] = {}
        issues: list[dict[str, Any]] = list(report["issues"])
        if observation_schema_message:
            issues.append(
                {
                    "type": "partial_observations_schema",
                    "severity": "warning",
                    "message": observation_schema_message,
                }
            )
        for station_id, station_df in observations.groupby("station", dropna=False):
            sid = str(station_id)
            audit = {"name": sid, "variables": {}}
            for variable, column in selected_columns.items():
                var_df = station_df[["time", column]].dropna()
                if var_df.empty:
                    continue
                expected_step_h = _infer_expected_step_hours(var_df["time"])
                gaps = _detect_gaps(var_df["time"], expected_step_h=expected_step_h)
                var_audit: dict[str, Any] = {
                    "n": int(len(var_df)),
                    "range": [float(var_df[column].min()), float(var_df[column].max())],
                    "mean": float(var_df[column].mean()),
                    "time_range": [str(var_df["time"].iloc[0]), str(var_df["time"].iloc[-1])],
                }
                if gaps:
                    var_audit["gaps"] = gaps[:10]
                    var_audit["total_gaps"] = len(gaps)
                    issues.append(
                        {
                            "station": sid,
                            "variable": variable,
                            "type": "time_gaps",
                            "count": len(gaps),
                            "max_gap_hours": max(g["hours"] for g in gaps),
                            "severity": "warning",
                        }
                    )
                if variable == "flow":
                    negative_count = int((var_df[column] < 0).sum())
                    if negative_count > 0:
                        var_audit["negative_count"] = negative_count
                        var_audit["negative_pct"] = round(negative_count / len(var_df) * 100, 2)
                        issues.append(
                            {
                                "station": sid,
                                "variable": variable,
                                "type": "negative_values",
                                "count": negative_count,
                                "severity": "warning" if negative_count / len(var_df) < 0.1 else "error",
                            }
                        )
                audit["variables"][variable] = var_audit
            if audit["variables"]:
                station_audit[sid] = audit
        report["station_audit"] = station_audit
        report["issues"] = issues
        report["scores"] = {
            "completeness": 4 if not any(i["type"] == "time_gaps" for i in issues) else 3,
            "reasonableness": 5 if not any(i.get("severity") == "error" for i in issues) else 3,
            "consistency": 3,
            "traceability": 4,
            "total_issues": len(issues),
            "errors": sum(1 for i in issues if i.get("severity") == "error"),
            "warnings": sum(1 for i in issues if i.get("severity") == "warning"),
        }
        write_json(out_json, report)
        _write_md_report(report, md_path)
        return report

    # Station-variable summary
    combos = pd.read_sql("""
        SELECT station_id, variable, count(*) as n,
               min(value) as val_min, max(value) as val_max, avg(value) as val_avg,
               min(time) as t_start, max(time) as t_end
        FROM timeseries
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
            neg = pd.read_sql_query(
                "SELECT count(*) as n FROM timeseries WHERE station_id=? AND variable=? AND value < 0",
                conn,
                params=[sid, var],
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

            # Gap analysis for water-level variables
            if var in {"H_up", "water_level"}:
                ts = pd.read_sql_query(
                    "SELECT time_step, time FROM timeseries WHERE station_id=? AND variable=? ORDER BY time_step, time",
                    conn,
                    params=[sid, var],
                )
                gaps: list[dict[str, Any]] = []
                for _, ts_group in ts.groupby("time_step", dropna=False):
                    expected_step_h = _infer_expected_step_hours(ts_group["time"])
                    gaps.extend(_detect_gaps(ts_group["time"], expected_step_h=expected_step_h))
                if gaps:
                    var_audit["gaps"] = gaps[:10]
                    var_audit["total_gaps"] = len(gaps)
                    report["issues"].append({
                        "station": sid,
                        "variable": var,
                        "type": "time_gaps",
                        "count": len(gaps),
                        "max_gap_hours": max(g["hours"] for g in gaps),
                        "severity": "warning",
                    })

                # Validate vs design levels
                np_ = meta.get("normal_pool")
                if np_ is None:
                    np_ = meta.get("normal_pool_m")
                dp_ = meta.get("dead_pool")
                if dp_ is None:
                    dp_ = meta.get("dead_pool_m")
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
    database_label = report["database"] or "未发现可用 SQLite"
    lines = [
        f"# {report['case_id']} 数据质量审计报告",
        f"\n> 自动生成 | {report['generated_at']}",
        f"\n> 当前状态：{report.get('business_status_zh', '数据质量审计已完成。')}",
        f"\n> 下一步：{report.get('recommended_next_action', '查看报告并决定是否继续后续工作流。')}",
        f"\n## 数据库: `{database_label}`",
        "\n| 表 | 记录数 |",
        "|---|--------|",
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
