"""加载自主运行水网闭环 YAML（支持 redirect_config 桩文件）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_MAX_REDIRECT = 5


def load_loop_yaml(workspace: Path, config_path: Path, depth: int = 0) -> dict[str, Any]:
    with open(config_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"invalid yaml root: {config_path}")
    redirect = data.get("redirect_config")
    if redirect:
        if depth >= _MAX_REDIRECT:
            raise ValueError("redirect_config chain too deep")
        nxt = (workspace / str(redirect)).resolve()
        if not nxt.is_file():
            raise FileNotFoundError(f"redirect target missing: {nxt}")
        return load_loop_yaml(workspace, nxt, depth + 1)
    return data


def resolve_case_ids(cfg: dict[str, Any], workspace: Path) -> list[str]:
    """按 case_selection.mode 解析案例列表（explicit | manifest_glob）。"""
    sel = cfg.get("case_selection") if isinstance(cfg.get("case_selection"), dict) else {}
    mode = str(sel.get("mode") or "explicit").strip().lower()

    if mode == "manifest_glob":
        pattern = str(sel.get("manifest_glob") or "cases/*/manifest.yaml")
        paths = sorted(workspace.glob(pattern))
        ids = [p.parent.name for p in paths if p.is_file()]
        exclude = {str(x) for x in (sel.get("exclude_case_ids") or []) if x is not None}
        ids = [i for i in ids if i not in exclude]
        order = str(sel.get("sort") or "asc").lower()
        ids.sort(reverse=(order == "desc"))
        return ids

    ids = sel.get("case_ids")
    if isinstance(ids, list) and all(isinstance(c, str) for c in ids):
        return list(ids)
    legacy = cfg.get("case_ids") or []
    if isinstance(legacy, list) and all(isinstance(c, str) for c in legacy):
        return list(legacy)
    return []


def resolve_full_spatial_hydro_evidence_case_ids(cfg: dict[str, Any]) -> list[str]:
    """hydrodesk_shell.full_spatial_hydro_evidence_case_ids：须为字符串列表。"""
    shell = cfg.get("hydrodesk_shell")
    if not isinstance(shell, dict):
        return []
    ids = shell.get("full_spatial_hydro_evidence_case_ids")
    if not isinstance(ids, list):
        return []
    out: list[str] = []
    for c in ids:
        if isinstance(c, str) and c.strip():
            out.append(c.strip())
    return out


def resolve_default_active_case_id(cfg: dict[str, Any]) -> str | None:
    """hydrodesk_shell.default_active_case_id：可选；须在 rollout case_ids 内（由调用方校验）。"""
    shell = cfg.get("hydrodesk_shell")
    if not isinstance(shell, dict):
        return None
    raw = shell.get("default_active_case_id")
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None
