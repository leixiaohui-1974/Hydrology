#!/usr/bin/env python3
"""
导出「工作流注册表 × 案例数据信号」可运行性矩阵（stdout 单行 JSON）。

路径相对 workspace root；规则见 Hydrology/configs/workflow_feasibility_rules.yaml。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
_BASE = _SCRIPTS_DIR.parent
_WORKSPACE = _BASE.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

from workflows import WORKFLOW_REGISTRY  # noqa: E402
from workflows._shared import build_station_meta, load_case_config  # noqa: E402

DEFAULT_RULES = _BASE / "configs" / "workflow_feasibility_rules.yaml"


def _coerce_path_str(raw: Any) -> str:
    if isinstance(raw, dict):
        for key in ("path", "sqlite_path", "value"):
            value = raw.get(key)
            if value:
                return str(value).strip()
        return ""
    if raw is None:
        return ""
    return str(raw).strip()


def _resolve_workspace_path(raw: str | Path) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path.resolve()
    return (_WORKSPACE / path).resolve()


def _is_sqlite_path(path: Path) -> bool:
    return path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}


def _sqlite_has_supported_tables(path: Path) -> bool:
    try:
        with sqlite3.connect(str(path)) as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
    except sqlite3.Error:
        return False
    return bool({"timeseries", "observations"} & tables)


def _iter_candidate_sqlite_paths(cfg: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []

    for raw in cfg.get("sqlite_paths", []) or []:
        path_str = _coerce_path_str(raw)
        if not path_str:
            continue
        path = _resolve_workspace_path(path_str)
        if path.is_file() and _is_sqlite_path(path):
            candidates.append(path)

    knowledge = cfg.get("knowledge") or {}
    scada_files = (knowledge.get("scada_timeseries") or {}).get("files") or []
    for raw in scada_files:
        path_str = _coerce_path_str(raw)
        if not path_str:
            continue
        path = _resolve_workspace_path(path_str)
        if path.is_file() and _is_sqlite_path(path):
            candidates.append(path)

    for scan_dir in cfg.get("scan_dirs", []) or []:
        base = _resolve_workspace_path(str(scan_dir))
        if not base.is_dir():
            continue
        for pattern in ("*.sqlite", "*.sqlite3", "*.db"):
            candidates.extend(path.resolve() for path in sorted(base.glob(pattern)) if path.is_file())

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(path)
    return unique_candidates


def _inventory_by_station(cfg: dict[str, Any]) -> dict[str, set[str]]:
    knowledge = cfg.get("knowledge") or {}
    inventory = knowledge.get("timeseries_inventory") or {}
    by_station = inventory.get("by_station") or {}
    if not isinstance(by_station, dict):
        return {}

    normalized: dict[str, set[str]] = {}
    for station_id, station_payload in by_station.items():
        station_key = str(station_id).strip()
        if not station_key:
            continue
        variables: set[str] = set()
        if isinstance(station_payload, dict):
            for key, value in station_payload.items():
                if value:
                    variables.add(str(key).strip())
        elif isinstance(station_payload, list):
            for item in station_payload:
                if isinstance(item, dict):
                    var_name = item.get("var") or item.get("variable") or item.get("name")
                    if var_name:
                        variables.add(str(var_name).strip())
                elif item:
                    variables.add(str(item).strip())
        elif station_payload:
            variables.add(str(station_payload).strip())
        if variables:
            normalized[station_key] = variables
    return normalized


def _timeseries_inventory_ready(cfg: dict[str, Any]) -> bool:
    knowledge = cfg.get("knowledge") or {}
    inventory = knowledge.get("timeseries_inventory") or {}
    total_variables = inventory.get("total_variables")
    if isinstance(total_variables, (int, float)) and total_variables > 0:
        return True
    return bool(_inventory_by_station(cfg))


def _has_candidate_station_meta(cfg: dict[str, Any]) -> bool:
    if build_station_meta(cfg):
        return True
    target_stations = cfg.get("target_stations") or []
    return any(str(station_id).strip() for station_id in target_stations)


def _closure_binding_present(cfg: dict[str, Any]) -> bool:
    hydrology_cfg = ((cfg.get("modeling") or {}).get("hydrology") or {})
    closure_binding = hydrology_cfg.get("closure_binding") or {}
    return isinstance(closure_binding, dict) and bool(closure_binding)


def _hydraulic_station_series_ready(cfg: dict[str, Any]) -> bool:
    inventory_by_station = _inventory_by_station(cfg)
    if not inventory_by_station:
        return False
    station_meta = build_station_meta(cfg)
    for station_id, meta in station_meta.items():
        variables = inventory_by_station.get(str(station_id).strip()) or set()
        required = {
            str(meta.get("h_var") or "H_up").strip(),
            str(meta.get("q_in_var") or "Q_in").strip(),
            str(meta.get("q_out_var") or "Q_out").strip(),
        }
        if required.issubset(variables):
            return True
    return False


_REPORT_SERIES_PAIRS: tuple[tuple[str, str], ...] = (
    ("Q_in_reservoir", "Q_out_reservoir"),
    ("Q_in", "Q_out"),
    ("flow", "water_level"),
    ("flow", "velocity"),
)


def _report_pairable_series_ready(cfg: dict[str, Any]) -> bool:
    if _closure_binding_present(cfg):
        return True
    inventory_by_station = _inventory_by_station(cfg)
    for variables in inventory_by_station.values():
        for input_variable, observed_variable in _REPORT_SERIES_PAIRS:
            if input_variable in variables and observed_variable in variables:
                return True
    return False


def _scan_dirs_have_data(cfg: dict[str, Any]) -> bool:
    exts = cfg.get("scan_extensions") or [
        ".json",
        ".csv",
        ".sqlite3",
        ".db",
        ".txt",
        ".xlsx",
    ]
    exts_l = {str(e).lower() if e.startswith(".") else f".{str(e).lower()}" for e in exts}
    for d in cfg.get("scan_dirs") or []:
        root = Path(d)
        if not root.is_dir():
            continue
        try:
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts_l:
                    return True
        except OSError:
            continue
    return False


def _hydrology_outputs_hint(case_id: str) -> bool:
    c = _WORKSPACE / "cases" / case_id / "contracts"
    if not c.is_dir():
        return False
    try:
        for p in c.glob("*.json"):
            n = p.name.lower()
            if "hydrology" in n or "hyd_sim" in n or "rainfall" in n or "runoff" in n:
                return True
        oc = c / "outcomes"
        if oc.is_dir() and any(oc.glob("*.json")):
            return True
    except OSError:
        return False
    return False


def _workspace_rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_WORKSPACE))
    except ValueError:
        return str(path.resolve())


def _load_source_import_session(case_id: str) -> dict[str, Any]:
    manifest_path = _WORKSPACE / "cases" / case_id / "manifest.yaml"
    manifest_payload: dict[str, Any] = {}
    if manifest_path.is_file():
        manifest_payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    latest_block = manifest_payload.get("latest_source_import_session") or {}
    candidates: list[tuple[str, Path]] = []
    raw_latest = str(latest_block.get("path") or "").strip()
    if raw_latest:
        candidates.append(("manifest_latest", _WORKSPACE / raw_latest))
    candidates.append(("contracts_default", _WORKSPACE / "cases" / case_id / "contracts" / "source_import_session.latest.json"))

    seen: set[str] = set()
    for source, path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return {
                "present": True,
                "source": source,
                "path": _workspace_rel_or_abs(path),
                "source_mode": payload.get("source_mode"),
                "record_count": payload.get("record_count"),
                "imported_at": payload.get("imported_at"),
            }

    return {
        "present": False,
        "source": "missing",
        "path": None,
        "source_mode": None,
        "record_count": None,
        "imported_at": None,
    }


def compute_signals(case_id: str, cfg: dict[str, Any]) -> dict[str, bool]:
    cfg_path = _BASE / "configs" / f"{case_id}.yaml"
    case_config_file = cfg_path.is_file()

    dem = cfg.get("dem_path") or ""
    dem_file = bool(dem) and Path(str(dem)).is_file()

    rn = cfg.get("river_network_path") or ""
    river_network_file = bool(rn) and Path(str(rn)).is_file()

    topo = cfg.get("topology_json_paths") or []
    topology_files = any(Path(str(p)).is_file() for p in topo if p)

    candidate_sqlite_paths = _iter_candidate_sqlite_paths(cfg)
    sqlite_files = bool(candidate_sqlite_paths)
    supported_sqlite_files = any(_sqlite_has_supported_tables(path) for path in candidate_sqlite_paths)

    cm = cfg.get("case_manifest_path") or ""
    case_manifest_file = bool(cm) and Path(str(cm)).is_file()

    sb = cfg.get("source_bundle_path") or ""
    source_bundle_file = bool(sb) and Path(str(sb)).is_file()

    scan_dirs_data = _scan_dirs_have_data(cfg)

    contracts_dir = (_WORKSPACE / "cases" / case_id / "contracts").is_dir()
    source_import_session_file = (_WORKSPACE / "cases" / case_id / "contracts" / "source_import_session.latest.json").is_file()

    return {
        "case_config_file": case_config_file,
        "dem_file": dem_file,
        "river_network_file": river_network_file,
        "topology_files": topology_files,
        "sqlite_files": sqlite_files,
        "supported_sqlite_files": supported_sqlite_files,
        "timeseries_inventory_ready": _timeseries_inventory_ready(cfg),
        "candidate_station_meta": _has_candidate_station_meta(cfg),
        "hydraulic_station_series_ready": _hydraulic_station_series_ready(cfg),
        "report_pairable_series_ready": _report_pairable_series_ready(cfg),
        "closure_binding_present": _closure_binding_present(cfg),
        "case_manifest_file": case_manifest_file,
        "source_bundle_file": source_bundle_file,
        "scan_dirs_data": scan_dirs_data,
        "contracts_dir": contracts_dir,
        "source_import_session_file": source_import_session_file,
        "hydrology_outputs_hint": _hydrology_outputs_hint(case_id),
    }


def _tier_for_rule(signals: dict[str, bool], rule: dict[str, Any]) -> tuple[str, list[str]]:
    matched: list[str] = []
    if "data_ready_if_all" in rule:
        req = rule["data_ready_if_all"] or []
        for s in req:
            if signals.get(s):
                matched.append(s)
        ok = bool(req) and all(signals.get(s, False) for s in req)
    else:
        req = rule.get("data_ready_if_any") or []
        if not req:
            ok = True
        else:
            for s in req:
                if signals.get(s):
                    matched.append(s)
            ok = any(signals.get(s, False) for s in req)
    tier = "data_ok" if ok else "data_gap"
    return tier, matched


def run_export(case_id: str, rules_path: Path) -> dict[str, Any]:
    cid = case_id.strip()
    raw_rules = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    wf_rules: dict[str, Any] = raw_rules.get("workflows") or {}
    default_note = raw_rules.get("default_note_zh") or ""
    methodology = raw_rules.get("methodology_note_zh") or ""

    try:
        cfg = load_case_config(cid) if (_BASE / "configs" / f"{cid}.yaml").is_file() else {"case_id": cid}
    except Exception:
        cfg = {"case_id": cid}

    project_type = str(cfg.get("project_type") or "watershed").strip()
    signals = compute_signals(cid, cfg)
    source_import_session = _load_source_import_session(cid)

    rows: list[dict[str, Any]] = []
    for key in sorted(WORKFLOW_REGISTRY.keys()):
        meta = WORKFLOW_REGISTRY[key]
        desc = str(meta.get("description") or "")
        req_args = meta.get("required_args") or []

        if not signals["case_config_file"]:
            rows.append(
                {
                    "key": key,
                    "description": desc,
                    "registry_required_args": req_args,
                    "tier": "no_case_config",
                    "matched_signals": [],
                    "rule_note_zh": "缺少 Hydrology/configs/<case_id>.yaml，请先新建案例骨架或初始化配置。",
                }
            )
            continue

        rule = wf_rules.get(key)
        if not rule:
            rows.append(
                {
                    "key": key,
                    "description": desc,
                    "registry_required_args": req_args,
                    "tier": "registry_only",
                    "matched_signals": [],
                    "rule_note_zh": default_note,
                }
            )
            continue

        unsupported_types = rule.get("unsupported_project_types") or []
        has_regulating_reservoir = str(cfg.get("has_regulating_reservoir", "false")).lower() == "true"

        is_unsupported = False
        for ut in unsupported_types:
            if ut in project_type.lower():
                is_unsupported = True
                break
                
        if is_unsupported and has_regulating_reservoir and "canal" in project_type.lower():
            is_unsupported = False

        if is_unsupported:
            rows.append(
                {
                    "key": key,
                    "description": desc,
                    "registry_required_args": req_args,
                    "tier": "unsupported",
                    "matched_signals": [],
                    "rule_note_zh": f"当前案例类型为 {project_type}，该工作流不支持此类型项目。",
                }
            )
            continue

        tier, matched = _tier_for_rule(signals, rule)
        note = str(rule.get("note_zh") or default_note)
        rows.append(
            {
                "key": key,
                "description": desc,
                "registry_required_args": req_args,
                "tier": tier,
                "matched_signals": matched,
                "rule_note_zh": note,
            }
        )

    return {
        "schema_version": raw_rules.get("schema_version") or "1.0",
        "case_id": cid,
        "rules_path": str(rules_path.relative_to(_WORKSPACE)),
        "methodology_note_zh": methodology,
        "signals": signals,
        "source_import_session": source_import_session,
        "workflow_count": len(rows),
        "workflows": rows,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Export case workflow feasibility matrix as JSON")
    p.add_argument("--case-id", required=True)
    p.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES,
        help="workflow_feasibility_rules.yaml",
    )
    args = p.parse_args()
    rules_path = args.rules if args.rules.is_absolute() else _WORKSPACE / args.rules
    if not rules_path.is_file():
        print(json.dumps({"ok": False, "error": f"rules not found: {rules_path}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    out = run_export(args.case_id, rules_path)
    print(json.dumps({"ok": True, **out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
