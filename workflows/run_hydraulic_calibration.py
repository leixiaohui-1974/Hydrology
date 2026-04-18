#!/usr/bin/env python3
"""率定 (LuDing) — 参数校准与自学习

HydroMind 水智工坊 · Agent #5

水力学历史率定验证 + 自提升工作流 (产品化)。

调用通用产品模块完成：
  - hydro_model.reservoir_balance: 逐站水库水量平衡率定
  - hydro_model.report_md: 自动生成 D2 精度报告 (Markdown)

配置驱动，零硬编码。新案例只需 YAML + 数据，零代码修改。

Usage:
    python3 -m workflows run hyd_cal --case-id zhongxian
    python3 workflows/run_hydraulic_calibration.py --case-id zhongxian
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from hydro_model.reservoir_balance import calibrate_station
from hydro_model.report_md import ReportGenerator
from workflows._shared import (
    load_case_config,
    select_preferred_sqlite,
    sqlite_table_columns,
    sqlite_table_names,
    write_json,
    WORKSPACE,
    build_station_meta,
    build_name_to_sid,
)


MIN_REQUIRED_CALIBRATION_STEPS = 200
REQUIRED_TIMESERIES_COLUMNS = {"station_id", "variable", "time", "value"}
REQUIRED_OBSERVATION_COLUMNS = {"station", "time", "Z", "Q_in", "Q_out"}


def _is_sqlite_path_str(path_str: str) -> bool:
    low = path_str.lower()
    return low.endswith(".sqlite3") or low.endswith(".sqlite") or low.endswith(".db")


def _db_has_supported_tables(db_path: Path) -> bool:
    table_names = sqlite_table_names(db_path)
    if table_names is None:
        return False
    if "timeseries" in table_names:
        timeseries_columns = sqlite_table_columns(db_path, "timeseries") or set()
        if REQUIRED_TIMESERIES_COLUMNS.issubset(timeseries_columns):
            return True
    if "observations" in table_names:
        observation_columns = sqlite_table_columns(db_path, "observations") or set()
        return REQUIRED_OBSERVATION_COLUMNS.issubset(observation_columns)
    return False



def _db_has_recognized_tables(db_path: Path) -> bool:
    table_names = sqlite_table_names(db_path)
    if table_names is None:
        return False
    return bool({"timeseries", "observations"} & set(table_names))


def _resolve_local_workspace_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (WORKSPACE / path).resolve()



def _first_supported_db(candidates: list[Path]) -> str | None:
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if _db_has_supported_tables(path):
            return str(path)
    return None



def _find_db(cfg: dict) -> str | None:
    selected_db, _ = select_preferred_sqlite(
        cfg,
        schema_support_fn=_db_has_supported_tables,
        workspace=WORKSPACE,
    )
    if selected_db:
        return selected_db
    fallback_db, _ = select_preferred_sqlite(
        cfg,
        schema_support_fn=_db_has_recognized_tables,
        workspace=WORKSPACE,
    )
    return fallback_db


def _normalize_station_id(raw_station_id: str) -> str:
    station_text = str(raw_station_id).strip()
    if not station_text:
        return ""
    parts = [part for part in station_text.replace("\\", "/").split("/") if part]
    return parts[-1] if parts else station_text


def _resolve_observation_station_aliases(conn: sqlite3.Connection, station_id: str) -> list[str]:
    exact_match = conn.execute(
        "SELECT DISTINCT station FROM observations WHERE station=? AND station IS NOT NULL",
        (station_id,),
    ).fetchall()
    if exact_match:
        return [str(exact_match[0][0])]

    normalized_station_id = _normalize_station_id(station_id)
    if not normalized_station_id:
        return []

    candidate_rows = conn.execute(
        "SELECT DISTINCT station FROM observations WHERE station IS NOT NULL ORDER BY station"
    ).fetchall()
    return [
        str(candidate)
        for (candidate,) in candidate_rows
        if _normalize_station_id(str(candidate)) == normalized_station_id
    ]


def _list_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows if len(row) > 1 and row[1]}


def _resolve_observation_value_column(variable: str, available_columns: set[str]) -> tuple[str | None, str | None]:
    normalized_variable = str(variable).strip()
    upper_variable = normalized_variable.upper()

    if normalized_variable in available_columns:
        return normalized_variable, None

    if ("H" in upper_variable or "Z" in upper_variable) and "Z" in available_columns:
        return "Z", None

    return None, "unsupported_observation_variable"


def _empty_timeseries() -> pd.Series:
    return pd.Series(dtype=float)



def _series_from_frame(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return _empty_timeseries()
    series = pd.Series(
        df["value"].astype(float).to_numpy(),
        index=pd.Index(df["time"].astype(str), name="time"),
    )
    return series[~series.index.duplicated(keep="last")].sort_index()



def _load_ts_with_metadata(db_path: str, station_id: str, variable: str) -> tuple[pd.Series, dict[str, Any] | None]:
    try:
        with sqlite3.connect(db_path) as conn:
            table_names = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }

            timeseries_columns = _list_table_columns(conn, "timeseries") if "timeseries" in table_names else set()
            if REQUIRED_TIMESERIES_COLUMNS.issubset(timeseries_columns):
                df = pd.read_sql_query(
                    "SELECT time, value FROM timeseries WHERE station_id=? AND variable=? ORDER BY time",
                    conn,
                    params=[station_id, variable],
                )
                if not df.empty:
                    return _series_from_frame(df), None

            if "observations" in table_names:
                available_columns = _list_table_columns(conn, "observations")
                observation_column, observation_error = _resolve_observation_value_column(
                    variable,
                    available_columns,
                )
                if observation_error:
                    return _empty_timeseries(), {
                        "reason": observation_error,
                        "station_id": station_id,
                        "variable": variable,
                        "available_columns": sorted(available_columns),
                    }

                station_aliases = _resolve_observation_station_aliases(conn, station_id)
                if len(station_aliases) > 1:
                    return _empty_timeseries(), {
                        "reason": "ambiguous_observation_station_aliases",
                        "station_id": station_id,
                        "aliases": station_aliases,
                        "variable": variable,
                    }
                if len(station_aliases) == 1 and observation_column is not None:
                    df = pd.read_sql_query(
                        f"SELECT time, {observation_column} as value FROM observations WHERE station=? AND {observation_column} IS NOT NULL ORDER BY time",
                        conn,
                        params=[station_aliases[0]],
                    )
                    if not df.empty:
                        return _series_from_frame(df), None
    except (sqlite3.Error, pd.errors.DatabaseError) as exc:
        return _empty_timeseries(), {
            "reason": "sqlite_read_error",
            "station_id": station_id,
            "variable": variable,
            "error": str(exc),
        }

    return _empty_timeseries(), None



def _load_ts(db_path: str, station_id: str, variable: str) -> np.ndarray:
    values, _ = _load_ts_with_metadata(db_path, station_id, variable)
    return values.to_numpy(dtype=float)


def _default_station_vars(project_type: str) -> list[str]:
    base_vars = ["H_up", "Q_in", "Q_out"]
    if "transfer" in project_type:
        base_vars.append("Q_transfer")
    return base_vars


def _strip_topology_station_suffix(station_name: str) -> str:
    normalized = str(station_name).strip()
    if not normalized:
        return ""
    for suffix in ("前", "后", "入流", "出流"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].strip()
    return normalized



def _is_aliasable_topology_node(node_info: Any) -> bool:
    if not isinstance(node_info, dict):
        return False
    node_type = node_info.get("nodeType")
    if node_type is not None:
        return node_type == 0
    node_label = str(node_info.get("type", "")).strip().lower()
    if node_label:
        return node_label in {"junction", "reservoir", "station"}
    return False



def _resolve_target_station_ids(cfg: dict) -> list[str]:
    target_stations = cfg.get("target_stations", []) or []
    if not target_stations:
        return []

    knowledge = cfg.get("knowledge", {}) or {}
    topology_nodes = knowledge.get("topology", {}).get("nodes", {}) or {}
    name_to_sid = build_name_to_sid(cfg)
    has_reservoir_meta = bool(knowledge.get("reservoirs", {}))
    resolved_ids: list[str] = []
    for raw_station in target_stations:
        station_text = str(raw_station).strip()
        if not station_text:
            continue
        resolved_id = name_to_sid.get(station_text)
        topology_node = topology_nodes.get(station_text)
        if not resolved_id and topology_node is not None and _is_aliasable_topology_node(topology_node):
            bare_station = _strip_topology_station_suffix(station_text)
            resolved_id = name_to_sid.get(bare_station)
        if not resolved_id and not has_reservoir_meta:
            resolved_id = station_text
        if resolved_id and resolved_id not in resolved_ids:
            resolved_ids.append(resolved_id)
    return resolved_ids


def _get_station_meta(cfg: dict) -> dict[str, dict]:
    """从配置获取站点元信息，优先 target_stations 与 reservoirs 的规范映射交集。"""
    meta = build_station_meta(cfg)
    has_reservoir_meta = bool(meta)
    target_stations = cfg.get("target_stations", []) or []
    target_station_ids = _resolve_target_station_ids(cfg)
    if meta and target_stations:
        meta = {
            sid: meta[sid]
            for sid in target_station_ids
            if sid in meta
        }

    if not meta and not has_reservoir_meta:
        fallback_vars = _default_station_vars(str(cfg.get("project_type", "cascade_hydro")))
        fallback_station_ids = target_station_ids or [
            str(sid)
            for sid in cfg.get("target_stations", []) or []
            if str(sid).strip()
        ]
        meta = {
            str(sid): {
                "name": str(sid),
                "vars": list(fallback_vars),
            }
            for sid in fallback_station_ids
            if str(sid).strip()
        }

    result = {}
    for sid, m in meta.items():
        v = m.get("vars", ["H_up", "Q_in", "Q_out"])
        result[sid] = {
            "name": m.get("name", sid),
            "h_var": v[0] if len(v) > 0 else "H_up",
            "q_in_var": v[1] if len(v) > 1 else "Q_in",
            "q_out_var": v[2] if len(v) > 2 else "Q_out",
        }
    return result


def _align_timeseries(h: pd.Series, q_in: pd.Series, q_out: pd.Series) -> tuple[pd.DataFrame, str | None]:
    aligned = pd.concat(
        [
            h.rename("h"),
            q_in.rename("q_in"),
            q_out.rename("q_out"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    if aligned.empty:
        return aligned, "missing_timeseries"
    return aligned.sort_index(), None



def calibrate_and_validate(
    case_id: str,
    config_path: str | None = None,
    cal_ratio: float = 0.7,
    target_nse: float = 0.85,
    generate_report: bool = True,
) -> dict[str, Any]:
    """水力学历史率定验证主入口（产品化）。"""
    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    station_meta = _get_station_meta(cfg)
    if not db_path:
        contract = {
            "case_id": case_id,
            "workflow": "hydraulic_calibration_validation",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "outcome_status": "no_data",
            "quality_gate_passed": False,
            "quality_reason": "未找到支持 timeseries/observations 的 SQLite 数据源",
            "station_results": {},
            "steady_metrics": {},
            "summary": {
                "n_stations_calibrated": 0,
                "avg_cal_nse": None,
                "avg_val_nse": None,
                "avg_cal_rmse": None,
                "n_candidate_stations": len(station_meta),
                "n_station_results": 0,
                "n_insufficient_data_stations": 0,
                "n_missing_timeseries_stations": 0,
                "n_ambiguous_observation_stations": 0,
                "n_unsupported_observation_variable_stations": 0,
                "n_sqlite_read_error_stations": 0,
            },
            "_auto_generated": True,
        }
        json_path = WORKSPACE / "cases" / case_id / "contracts" / "hydraulic_calibration.latest.json"
        write_json(json_path, contract)
        print(f"  合约: {json_path}")
        return contract

    # 1. Load data
    print("=== 加载历史数据 ===")
    data: dict[str, dict] = {}
    station_results: dict[str, dict] = {}
    for sid, meta in station_meta.items():
        h, h_meta = _load_ts_with_metadata(db_path, sid, meta["h_var"])
        q_in, q_in_meta = _load_ts_with_metadata(db_path, sid, meta["q_in_var"])
        q_out, q_out_meta = _load_ts_with_metadata(db_path, sid, meta["q_out_var"])

        load_errors = [item for item in (h_meta, q_in_meta, q_out_meta) if item]
        if load_errors:
            primary_error = load_errors[0]
            station_result = {
                "name": meta["name"],
                "status": primary_error["reason"],
                "n": 0,
                "required_steps": MIN_REQUIRED_CALIBRATION_STEPS,
                "variables": sorted({
                    str(item.get("variable"))
                    for item in load_errors
                    if item.get("variable")
                }),
            }
            if primary_error.get("aliases"):
                station_result["aliases"] = list(primary_error["aliases"])
                print(f"  {sid} ({meta['name']}): 观测站别名歧义")
            elif primary_error.get("available_columns"):
                station_result["available_columns"] = list(primary_error["available_columns"])
                print(f"  {sid} ({meta['name']}): observations 缺少变量列 {primary_error.get('variable')}")
            elif primary_error.get("error"):
                station_result["error"] = str(primary_error["error"])
                print(f"  {sid} ({meta['name']}): SQLite 读取失败")
            else:
                print(f"  {sid} ({meta['name']}): 数据加载失败")
            station_results[sid] = station_result
            continue

        aligned, alignment_error = _align_timeseries(h, q_in, q_out)
        if alignment_error:
            print(f"  {sid} ({meta['name']}): 缺少有效时序")
            station_results[sid] = {
                "name": meta["name"],
                "status": alignment_error,
                "n": 0,
                "required_steps": MIN_REQUIRED_CALIBRATION_STEPS,
            }
            continue

        h_values = aligned["h"].to_numpy(dtype=float)
        q_in_values = aligned["q_in"].to_numpy(dtype=float)
        q_out_values = aligned["q_out"].to_numpy(dtype=float)
        data[sid] = {"h": h_values, "q_in": q_in_values, "q_out": q_out_values, **meta}
        print(f"  {sid} ({meta['name']}): H=[{h_values.min():.1f},{h_values.max():.1f}]m "
              f"Q_in={len(q_in_values)} Q_out={len(q_out_values)}")

    # 2. Per-station calibration using product module
    print("\n=== 逐站水库水量平衡率定 ===")
    for sid, sdata in data.items():
        h, q_in, q_out = sdata["h"], sdata["q_in"], sdata["q_out"]
        print(f"\n  {sid} ({sdata['name']}):")

        result = calibrate_station(
            Q_in=q_in, Q_out=q_out, H_obs=h,
            cal_ratio=cal_ratio,
            target_nse=target_nse,
            auto_improve=True,
        )

        if result["status"] != "completed":
            print(f"    失败: {result.get('status')}")
            station_results[sid] = {
                "name": sdata["name"],
                **result,
                "required_steps": MIN_REQUIRED_CALIBRATION_STEPS,
            }
            continue

        cal_m = result["cal_metrics"]
        val_m = result["val_metrics"]
        print(f"    率定: NSE={cal_m['nse']:.4f} RMSE={cal_m['rmse']:.3f}m ({result['phases_used']})")
        print(f"    验证: NSE={val_m['nse']:.4f} RMSE={val_m['rmse']:.3f}m")
        print(f"    ★ 参数: {result['model_params']}")

        station_results[sid] = {
            "name": sdata["name"],
            "calibration": {"best": {**result["cal_metrics"], **result["model_params"]}},
            "validation": result["val_metrics"],
            "model_params": result["model_params"],
            "phases_used": result["phases_used"],
            "n_cal": result["n_cal"],
            "n_val": result["n_val"],
        }

    # 3. Steady-state summary
    print("\n=== 稳态水位统计 ===")
    steady_metrics: dict[str, dict] = {}
    for sid, sdata in data.items():
        h_mean = float(np.mean(sdata["h"]))
        q_mean = float(np.mean(np.abs(sdata["q_in"][:len(sdata["h"])])))
        steady_metrics[sid] = {
            "name": sdata["name"],
            "obs_mean_level": h_mean,
            "obs_mean_Q": q_mean,
            "obs_range": [float(sdata["h"].min()), float(sdata["h"].max())],
        }
        print(f"  {sid} ({sdata['name']}): H_mean={h_mean:.1f}m Q_mean={q_mean:.0f}m³/s")

    # 4. Build summary
    cal_nses = [sr["calibration"]["best"]["nse"]
                for sr in station_results.values()
                if isinstance(sr, dict) and "calibration" in sr]
    val_nses = [sr["validation"]["nse"]
                for sr in station_results.values()
                if isinstance(sr, dict) and "validation" in sr
                and isinstance(sr["validation"].get("nse"), (int, float))]

    insufficient_station_ids = [
        sid
        for sid, sr in station_results.items()
        if isinstance(sr, dict) and sr.get("status") == "insufficient_data"
    ]
    missing_timeseries_station_ids = [
        sid
        for sid, sr in station_results.items()
        if isinstance(sr, dict) and sr.get("status") == "missing_timeseries"
    ]
    ambiguous_observation_station_ids = [
        sid
        for sid, sr in station_results.items()
        if isinstance(sr, dict) and sr.get("status") == "ambiguous_observation_station_aliases"
    ]
    unsupported_observation_variable_station_ids = [
        sid
        for sid, sr in station_results.items()
        if isinstance(sr, dict) and sr.get("status") == "unsupported_observation_variable"
    ]
    sqlite_read_error_station_ids = [
        sid
        for sid, sr in station_results.items()
        if isinstance(sr, dict) and sr.get("status") == "sqlite_read_error"
    ]

    summary = {
        "n_stations_calibrated": len(cal_nses),
        "avg_cal_nse": float(np.mean(cal_nses)) if cal_nses else None,
        "avg_val_nse": float(np.mean(val_nses)) if val_nses else None,
        "avg_cal_rmse": float(np.mean([
            sr["calibration"]["best"]["rmse"]
            for sr in station_results.values()
            if isinstance(sr, dict) and "calibration" in sr
        ])) if cal_nses else None,
        "n_candidate_stations": len(station_meta),
        "n_station_results": len(station_results),
        "n_insufficient_data_stations": len(insufficient_station_ids),
        "n_missing_timeseries_stations": len(missing_timeseries_station_ids),
        "n_ambiguous_observation_stations": len(ambiguous_observation_station_ids),
        "n_unsupported_observation_variable_stations": len(unsupported_observation_variable_station_ids),
        "n_sqlite_read_error_stations": len(sqlite_read_error_station_ids),
    }

    has_failed_stations = len(station_results) > len(cal_nses)
    outcome_status = "completed"
    quality_gate_passed = True
    quality_reasons: list[str] = []
    if not db_path:
        outcome_status = "no_data"
        quality_gate_passed = False
        quality_reasons.append("未找到支持 timeseries/observations 的 SQLite 数据源")
    elif summary["n_candidate_stations"] == 0:
        outcome_status = "no_data"
        quality_gate_passed = False
        quality_reasons.append("未识别到可率定站点")
    elif summary["n_stations_calibrated"] == 0:
        outcome_status = "no_data"
        quality_gate_passed = False
        if summary["n_insufficient_data_stations"] == summary["n_station_results"] and summary["n_station_results"] > 0:
            quality_reasons.append("所有候选站点有效时序不足，无法完成水力率定")
        elif summary["n_missing_timeseries_stations"] == summary["n_station_results"] and summary["n_station_results"] > 0:
            quality_reasons.append("所有候选站点均缺少有效时序，无法完成水力率定")
        elif summary["n_ambiguous_observation_stations"] == summary["n_station_results"] and summary["n_station_results"] > 0:
            quality_reasons.append("所有候选站点均存在观测站别名歧义，无法安全完成水力率定")
        elif summary["n_unsupported_observation_variable_stations"] == summary["n_station_results"] and summary["n_station_results"] > 0:
            quality_reasons.append("所有候选站点均缺少 observations 所需变量列，无法安全完成水力率定")
        elif summary["n_sqlite_read_error_stations"] == summary["n_station_results"] and summary["n_station_results"] > 0:
            quality_reasons.append("所有候选站点在读取 SQLite 时失败，无法完成水力率定")
        else:
            quality_reasons.append("没有任何站点完成水力率定")
    elif has_failed_stations:
        outcome_status = "degraded"
        quality_gate_passed = False
        quality_reasons.append("部分候选站点完成率定，部分站点失败；请检查 station_results 明细")
    elif summary.get("avg_val_nse") is None or float(summary["avg_val_nse"]) < 0.5:
        outcome_status = "quality_failed"
        quality_gate_passed = False
        quality_reasons.append(f"验证集平均 NSE 未达标（avg_val_nse={summary.get('avg_val_nse')}）")

    print(f"\n=== 总结 ===")
    print(f"  站点数: {summary['n_stations_calibrated']}")
    print(f"  平均率定 NSE: {summary.get('avg_cal_nse')}")
    print(f"  平均验证 NSE: {summary.get('avg_val_nse')}")

    # 5. Write JSON contract
    contract = {
        "case_id": case_id,
        "workflow": "hydraulic_calibration_validation",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "outcome_status": outcome_status,
        "quality_gate_passed": quality_gate_passed,
        "quality_reason": "；".join(quality_reasons) or None,
        "station_results": station_results,
        "steady_metrics": steady_metrics,
        "summary": summary,
        "_auto_generated": True,
    }
    json_path = WORKSPACE / "cases" / case_id / "contracts" / "hydraulic_calibration.latest.json"
    write_json(json_path, contract)
    print(f"  合约: {json_path}")

    # 6. Generate D2 Markdown report
    if generate_report:
        gen = ReportGenerator(case_id=case_id, dimension="D2",
                              title=f"D2 水力学精度评价报告 — {case_id}")
        gen.build(
            station_results=station_results,
            steady_metrics=steady_metrics,
            summary=summary,
            methodology="",
        )
        md_path = WORKSPACE / "cases" / case_id / "contracts" / "D2_hydraulic_report.md"
        gen.write(md_path)
        print(f"  MD报告: {md_path}")

    return contract


def main():
    parser = argparse.ArgumentParser(description="水力学历史率定验证工作流 (产品化)")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--cal-ratio", type=float, default=0.7)
    parser.add_argument("--target-nse", type=float, default=0.85)
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()

    calibrate_and_validate(
        case_id=args.case_id,
        config_path=args.config,
        cal_ratio=args.cal_ratio,
        target_nse=args.target_nse,
        generate_report=not args.no_report,
    )


if __name__ == "__main__":
    main()
