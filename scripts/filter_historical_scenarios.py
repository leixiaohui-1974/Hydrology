#!/usr/bin/env python3
"""
Filter Historical Scenarios

Reads SQLite `observations` and filters out scenarios based on YAML rules in `cfg["knowledge"]["scenarios"]`.
Ensure zero hardcoding.
"""

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
_HYDROLOGY_DIR = _SCRIPTS_DIR.parent
_WORKSPACE = _HYDROLOGY_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
if str(_HYDROLOGY_DIR) not in sys.path:
    sys.path.insert(0, str(_HYDROLOGY_DIR))

from workflows._shared import load_case_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def _get_sqlite_path(case_id: str, cfg: dict[str, Any]) -> Path:
    sqlite_paths = cfg.get("sqlite_paths") or []
    if not sqlite_paths:
        sqlite_paths = [f"cases/{case_id}/data/observations.sqlite"]
    
    db_path = sqlite_paths[0]
    p = Path(db_path)
    if not p.is_absolute():
        p = (_WORKSPACE / p).resolve()
    return p

def _evaluate_rule(cursor: sqlite3.Cursor, rule: dict[str, Any]) -> tuple[bool, int, list[tuple]]:
    # Zero hardcoding: build WHERE clause dynamically based on rule dict
    where_clauses = []
    params = []
    
    if "start_time" in rule:
        where_clauses.append("time >= ?")
        params.append(rule["start_time"])
    if "end_time" in rule:
        where_clauses.append("time <= ?")
        params.append(rule["end_time"])
    
    if "station" in rule:
        where_clauses.append("station = ?")
        params.append(rule["station"])
        
    if "variable" in rule and "operator" in rule and "threshold" in rule:
        var = rule["variable"]  # e.g. "Z" or "Q"
        op = rule["operator"]   # e.g. ">", "<", "="
        thresh = rule["threshold"]
        # Simple validation to prevent obvious injection
        if var in ("Z", "Q") and op in (">", "<", ">=", "<=", "=", "!="):
            where_clauses.append(f"{var} {op} ?")
            params.append(thresh)
            
    if "where" in rule:
        # direct where clause if user wants it (advanced)
        where_clauses.append(f"({rule['where']})")
        
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    sql = f"SELECT time, station, Z, Q FROM observations WHERE {where_sql} ORDER BY time LIMIT 100"
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        count_sql = f"SELECT COUNT(*) FROM observations WHERE {where_sql}"
        cursor.execute(count_sql, params)
        count = cursor.fetchone()[0]
        
        return count > 0, count, rows
    except Exception as e:
        logger.error(f"Rule evaluation failed: {e} | SQL: {sql} | Params: {params}")
        return False, 0, []

def filter_historical_scenarios(case_id: str, config_path: str | None = None) -> list[dict[str, Any]]:
    cfg = load_case_config(case_id, config_path)
    scenarios_config = cfg.get("knowledge", {}).get("scenarios", [])
    
    if not scenarios_config:
        logger.warning(f"[{case_id}] No scenarios rules found in cfg['knowledge']['scenarios']")
        return []
        
    db_path = _get_sqlite_path(case_id, cfg)
    if not db_path.exists():
        logger.error(f"[{case_id}] SQLite database not found: {db_path}")
        return []
        
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    filtered_scenarios = []
    
    for scenario in scenarios_config:
        rule = scenario.get("rule", scenario)  # Support rule nested or flat
        
        is_valid, match_count, sample_rows = _evaluate_rule(cursor, rule)
        
        if is_valid:
            result = dict(scenario)
            result["match_count"] = match_count
            
            # Auto-infer time window if not explicitly provided but data matched
            if "start_time" not in result and sample_rows:
                result["inferred_start"] = sample_rows[0][0]
                result["inferred_end"] = sample_rows[-1][0]
                
            filtered_scenarios.append(result)
            logger.info(f"[{case_id}] Scenario matched: {scenario.get('id', 'unnamed')} ({match_count} records)")
        else:
            logger.info(f"[{case_id}] Scenario did not match any data: {scenario.get('id', 'unnamed')}")
            
    conn.close()
    
    # Save the filtered scenarios to a contract file
    out_dir = _WORKSPACE / "cases" / case_id / "contracts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "filtered_historical_scenarios.latest.json"
    out_file.write_text(json.dumps(filtered_scenarios, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return filtered_scenarios

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    
    res = filter_historical_scenarios(args.case_id, args.config)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
