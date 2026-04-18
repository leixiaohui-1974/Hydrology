"""自治策略合并：workflow_autonomy_policy.yaml + per_case + case YAML autonomy_policy 块。

供自提升管线、D1/D2 精度、DL 自学习、水力学自诊断、水文报告、auto_learning_loop 统一读取。
CLI 显式 flag 由各入口用 argv_has 自行判断，本模块只负责配置层合并。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

_BASE = Path(__file__).resolve().parents[1]
_POLICY_FILE = _BASE / "configs" / "workflow_autonomy_policy.yaml"


def argv_has(flag: str) -> bool:
    return flag in sys.argv


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def load_raw_autonomy_yaml() -> dict[str, Any]:
    return _load_yaml_file(_POLICY_FILE)


def load_merged_autonomy_policy(case_id: str, config_path: Optional[str] = None) -> Dict[str, Any]:
    """合并 defaults、per_case[case_id]、以及 case 配置中的 autonomy_policy（若存在）。"""
    from workflows._shared import load_case_config

    raw = load_raw_autonomy_yaml()
    defaults = raw.get("defaults") or {}
    per_all = raw.get("per_case") or {}
    per = (per_all.get(case_id) or {}) if isinstance(per_all, dict) else {}

    if not isinstance(defaults, dict):
        defaults = {}
    if not isinstance(per, dict):
        per = {}

    merged = _deep_merge(defaults, per)

    cfg = load_case_config(case_id, config_path)
    side = cfg.get("autonomy_policy")
    if isinstance(side, dict) and side:
        merged = _deep_merge(merged, side)

    # Legacy auto_learning_by_case.yaml：仅作兼容；与 workflow_autonomy_policy 冲突时以本策略文件为准
    try:
        from workflows._shared import WORKSPACE

        legacy = _load_yaml_file(WORKSPACE / "Hydrology" / "configs" / "auto_learning_by_case.yaml")
        defs_al = legacy.get("defaults") if isinstance(legacy.get("defaults"), dict) else {}
        per_al: dict[str, Any] = {}
        if isinstance(legacy.get("per_case"), dict):
            raw_per = legacy["per_case"].get(case_id)
            if isinstance(raw_per, dict):
                per_al = raw_per
        legacy_loop = _deep_merge(dict(defs_al), dict(per_al))
        if legacy_loop:
            cur = merged.get("auto_learning_loop") if isinstance(merged.get("auto_learning_loop"), dict) else {}
            merged["auto_learning_loop"] = _deep_merge(legacy_loop, cur)
    except Exception:
        pass

    return merged


def policy_section(policy: Dict[str, Any], name: str) -> Dict[str, Any]:
    v = policy.get(name)
    return dict(v) if isinstance(v, dict) else {}


def section(case_id: str, name: str, config_path: Optional[str] = None) -> Dict[str, Any]:
    """取合并后策略中的某一段（如 self_improving_pipeline、reporting）。"""
    return policy_section(load_merged_autonomy_policy(case_id, config_path), name)


def governance_source_relpath() -> str:
    try:
        from workflows._shared import WORKSPACE

        return str(_POLICY_FILE.resolve().relative_to(WORKSPACE)).replace("\\", "/")
    except ValueError:
        return str(_POLICY_FILE).replace("\\", "/")


def reporting_policy(case_id: str, config_path: Optional[str] = None) -> Dict[str, Any]:
    return section(case_id, "reporting", config_path)


def grade_nse(nse: Optional[float], rep: Dict[str, Any]) -> str:
    """按 reporting 段的 grade_order / grade_thresholds / grade_labels 分级。"""
    if nse is None:
        return str(rep.get("missing_label") or "无数据")
    order = rep.get("grade_order") or ["excellent", "good", "fair", "poor"]
    thresholds = rep.get("grade_thresholds") or {}
    labels = rep.get("grade_labels") or {}
    for key in order:
        thr = thresholds.get(key)
        if thr is None:
            continue
        if nse >= float(thr):
            return str(labels.get(key) or key)
    return str(labels.get("fail") or "不合格")


def apply_cli_overrides(
    base: Dict[str, Any],
    args: Any,
    mapping: List[Tuple[str, str, str]],
) -> Tuple[Dict[str, Any], List[str]]:
    """若 argv 中未出现对应 flag，则用 base 中的键覆盖 args 属性。

    mapping: (policy_key, args_attr, argv_flag)
    返回 (applied_dict, list of keys taken from base)
    """
    applied_keys: list[str] = []
    out = dict(base)
    for pol_key, attr, flag in mapping:
        if flag in sys.argv or pol_key not in base:
            continue
        if hasattr(args, attr):
            setattr(args, attr, base[pol_key])
            applied_keys.append(pol_key)
    return out, applied_keys
