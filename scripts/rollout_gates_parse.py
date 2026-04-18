"""解析 rollout_repo_artifact_gates.json（v2）。供 check_rollout_repo_contracts 与 tests 共用。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
GATES_PATH = WORKSPACE_ROOT / "Hydrology" / "configs" / "rollout_repo_artifact_gates.json"
PLATFORM_GOVERNANCE_INDEX_PATH = (
    WORKSPACE_ROOT / "Hydrology" / "configs" / "platform_governance_gates.index.json"
)


def load_rollout_gates(gates_path: Path | None = None) -> dict[str, Any]:
    path = gates_path or GATES_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 2:
        raise ValueError(f"rollout_repo_artifact_gates.json: expected version 2, got {data.get('version')}")
    return data


def profile_for_case(case_id: str, gates: dict[str, Any]) -> str:
    default_p = str(gates.get("default_artifact_profile") or "rollout_baseline").strip()
    cmap = gates.get("case_artifact_profile") or {}
    raw = cmap.get(case_id)
    return str(raw).strip() if raw is not None else default_p


def artifact_paths_for_case(case_id: str, gates: dict[str, Any]) -> list[str]:
    templates = gates.get("path_templates") or []
    prof = profile_for_case(case_id, gates)
    prof_body = (gates.get("artifact_profiles") or {}).get(prof) or {}
    extras = prof_body.get("extra_path_templates") or []
    cid = case_id.strip()
    base = [str(t).replace("{case_id}", cid) for t in templates]
    extra = [str(t).replace("{case_id}", cid) for t in extras]
    return [*base, *extra]


def rollout_json_shape_gate_cases(
    gates: dict[str, Any],
    *,
    case_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    展开 json 形状规则。case_ids 默认取 gates['case_artifact_profile'] 键排序；
    若传入则须与闭环 YAML 顺序一致（如 check_rollout_repo_contracts）。
    """
    shared = gates.get("shared_json_shape_gates") or []
    cmap = gates.get("case_artifact_profile") or {}
    order = case_ids if case_ids is not None else sorted(cmap.keys())
    out: list[dict[str, Any]] = []
    for case_id in order:
        prof = profile_for_case(case_id, gates)
        prof_rules = (gates.get("artifact_profiles") or {}).get(prof, {}).get("json_shape_gates") or []
        for rule in [*shared, *prof_rules]:
            pt = rule.get("path_template")
            rk = rule.get("required_keys")
            if not pt or not isinstance(rk, list):
                continue
            out.append(
                {
                    "case_id": case_id,
                    "path_template": str(pt),
                    "required_keys": list(rk),
                }
            )
    return out


def validate_platform_governance_index(
    index_path: Path | None = None,
) -> list[str]:
    """返回人类可读错误列表；空表示通过。"""
    path = index_path or PLATFORM_GOVERNANCE_INDEX_PATH
    errors: list[str] = []
    if not path.is_file():
        return [f"missing platform governance index: {path.relative_to(WORKSPACE_ROOT)}"]

    try:
        idx = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON ({exc})"]

    if idx.get("schema") != "platform_governance_gates.index":
        errors.append(f"{path.name}: schema must be 'platform_governance_gates.index'")
    if not isinstance(idx.get("version"), int):
        errors.append(f"{path.name}: version must be int")
    gates = idx.get("gates")
    if not isinstance(gates, list) or len(gates) != 3:
        errors.append(f"{path.name}: gates must be array of length 3")
    else:
        keys = sorted(str(g.get("key")) for g in gates if isinstance(g, dict))
        if keys != ["assimilation", "coupling", "hydraulics"]:
            errors.append(f"{path.name}: gate keys expected assimilation/coupling/hydraulics, got {keys}")
        for g in gates:
            if not isinstance(g, dict):
                continue
            chain = g.get("path_template_chain")
            if not isinstance(chain, list) or len(chain) == 0:
                errors.append(f"{path.name}: gate {g.get('key')!r} needs non-empty path_template_chain")
                continue
            for tpl in chain:
                if "{case_id}" not in str(tpl):
                    errors.append(f"{path.name}: gate {g.get('key')!r} template missing {{case_id}}: {tpl!r}")
    return errors
