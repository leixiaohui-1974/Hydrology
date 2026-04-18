"""
构建观测数据 SQLite (Build Observations SQLite)

此脚本为通用工作流组件。
它从案例的配置文件 (YAML) 中读取 `scada_timeseries.json_extraction_rules`，
将指定 JSON 文件中的嵌套时序数据解析、重命名并持久化为标准的 SQLite 数据库，
供下游的 `state_est` 和其他闭环同化工作流使用。
"""

import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from workflows._shared import load_case_config, WORKSPACE

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _get_nested_value(data: dict, keys: list[str]) -> Any:
    for k in keys:
        if isinstance(data, dict):
            data = data.get(k, {})
        else:
            return None
    return data


def build_observations_sqlite(case_id: str, config_path: Optional[str] = None) -> None:
    cfg = load_case_config(case_id, config_path)
    
    scada_cfg = cfg.get("knowledge", {}).get("scada_timeseries", {})
    extraction_rules = scada_cfg.get("json_extraction_rules")
    
    if not extraction_rules:
        logger.info(f"[{case_id}] 没有配置 json_extraction_rules，跳过观测数据构建。")
        return

    source_file = extraction_rules.get("source_file")
    root_key = extraction_rules.get("root_key", [])
    mapping = extraction_rules.get("mapping", {})
    
    if not source_file or not mapping:
        logger.error(f"[{case_id}] 提取规则不完整：缺少 source_file 或 mapping。")
        return

    full_source_path = WORKSPACE / source_file if not Path(source_file).is_absolute() else Path(source_file)
    if not full_source_path.exists():
        logger.error(f"[{case_id}] 源文件不存在: {full_source_path}")
        return

    logger.info(f"[{case_id}] 正在读取源数据文件: {full_source_path}")
    with open(full_source_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"[{case_id}] JSON 解析失败: {e}")
            return

    series_data = _get_nested_value(data, root_key)
    if not series_data or not isinstance(series_data, dict):
        logger.error(f"[{case_id}] 无法在根路径 {root_key} 下找到时序数据对象。")
        return

    # 获取或创建目标 sqlite 文件
    sqlite_paths = scada_cfg.get("files", [])
    if not sqlite_paths:
        default_db_path = f"cases/{case_id}/data/observations.sqlite"
        sqlite_paths.append(default_db_path)
        # Update config conceptually (in real workflow, config update is handled separately or we just write to default)
    
    target_db_rel = sqlite_paths[0]
    target_db = WORKSPACE / target_db_rel if not Path(target_db_rel).is_absolute() else Path(target_db_rel)
    target_db.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"[{case_id}] 正在写入 SQLite: {target_db}")
    
    # 我们将所有数据写入名为 'observations' 的通用表，带 station 字段
    conn = sqlite3.connect(str(target_db))
    cursor = conn.cursor()
    cursor.execute('DROP TABLE IF EXISTS observations')
    cursor.execute('''
        CREATE TABLE observations (
            name TEXT,
            station TEXT,
            time REAL,
            Z REAL,
            Q REAL
        )
    ''')

    inserted_count = 0
    for original_name, mapping_info in mapping.items():
        if original_name in series_data:
            points = series_data[original_name]
            
            # 解析映射配置 (支持纯字符串兼容老版本，或字典包含 station/variable)
            if isinstance(mapping_info, dict):
                station_name = mapping_info.get("station")
                variable = mapping_info.get("variable", "Z")
            else:
                station_name = mapping_info
                variable = "Z" # 默认缺省为水位 Z
            
            is_level = (variable.upper() == "Z")
            
            rows = []
            for pt in points:
                if len(pt) >= 2:
                    t, val = pt[0], pt[1]
                    z_val = val if is_level else None
                    q_val = val if not is_level else None
                    rows.append((station_name, station_name, float(t), z_val, q_val))
            
            cursor.executemany(
                'INSERT INTO observations (name, station, time, Z, Q) VALUES (?, ?, ?, ?, ?)',
                rows
            )
            inserted_count += len(rows)
            logger.info(f"[{case_id}] 成功映射: {original_name} -> {station_name} ({len(rows)} 条记录)")
        else:
            logger.warning(f"[{case_id}] 源数据中未找到指定的序列: {original_name}")

    conn.commit()
    conn.close()
    logger.info(f"[{case_id}] SQLite 构建完成，共写入 {inserted_count} 条记录。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 JSON 源提取时序数据并构建 SQLite 观测数据库")
    parser.add_argument("--case-id", required=True, help="Case ID (例如 xuhonghe)")
    parser.add_argument("--config", help="YAML 配置文件路径 (可选)")
    args = parser.parse_args()

    build_observations_sqlite(args.case_id, args.config)
