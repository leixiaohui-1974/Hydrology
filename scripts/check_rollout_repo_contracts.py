#!/usr/bin/env python3
"""
Rollout 仓库契约门禁：必达文件存在 + JSON 顶层键；完全由 rollout_repo_artifact_gates.json 驱动。
并校验 platform_governance_gates.index.json（与 HydroDesk 平台治理门索引一致）。

- case_id 列表来自 hydrodesk 闭环 YAML（与 HydroDesk rollout 五案例一致）
- 每案例制品档位来自 JSON 的 case_artifact_profile → artifact_profiles[...]
- 脚本内无案例名、无 if/elif 分支

仓库根:
    python3 Hydrology/scripts/check_rollout_repo_contracts.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402
from rollout_gates_parse import (  # noqa: E402
    artifact_paths_for_case,
    load_rollout_gates,
    profile_for_case,
    rollout_json_shape_gate_cases,
    validate_platform_governance_index,
)

DEFAULT_GATES = WORKSPACE / "Hydrology" / "configs" / "rollout_repo_artifact_gates.json"
DEFAULT_LOOP = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gates", type=Path, default=DEFAULT_GATES)
    parser.add_argument("--loop-config", type=Path, default=DEFAULT_LOOP)
    args = parser.parse_args()

    gates_path = args.gates.resolve()
    if not gates_path.is_file():
        print(f"missing gates file: {gates_path}", file=sys.stderr)
        return 2

    try:
        gates = load_rollout_gates(gates_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"gates file invalid: {exc}", file=sys.stderr)
        return 2

    cfg = load_loop_yaml(WORKSPACE, args.loop_config.resolve())
    case_ids = resolve_case_ids(cfg, WORKSPACE)
    if not case_ids:
        print("no case_ids from loop config", file=sys.stderr)
        return 2

    errors: list[str] = []

    cmap = gates.get("case_artifact_profile")
    if not isinstance(cmap, dict):
        errors.append("case_artifact_profile must be an object")
    else:
        ids_set = set(case_ids)
        keys_set = set(cmap.keys())
        if keys_set != ids_set:
            only_loop = sorted(ids_set - keys_set)
            only_map = sorted(keys_set - ids_set)
            if only_loop:
                errors.append(
                    "case_artifact_profile missing entries for loop case_ids: "
                    + ", ".join(only_loop),
                )
            if only_map:
                errors.append(
                    "case_artifact_profile has unknown case_ids (not in loop): "
                    + ", ".join(only_map),
                )

    profiles = gates.get("artifact_profiles")
    if not isinstance(profiles, dict):
        errors.append("artifact_profiles must be an object")

    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1

    for cid in case_ids:
        prof = profile_for_case(cid, gates)
        if prof not in profiles:
            errors.append(f"unknown artifact_profile {prof!r} for case_id={cid}")
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1

    for cid in case_ids:
        for rel in artifact_paths_for_case(cid, gates):
            p = WORKSPACE / rel
            if not p.is_file():
                errors.append(f"missing file: {rel}")

    shape_rows = rollout_json_shape_gate_cases(gates, case_ids=case_ids)
    rule_count = 0
    for row in shape_rows:
        cid = row["case_id"]
        tmpl = row["path_template"]
        keys = row["required_keys"]
        rule_count += 1
        rel = tmpl.replace("{case_id}", cid)
        p = WORKSPACE / rel
        if not p.is_file():
            errors.append(f"missing json for shape gate: {rel}")
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{rel}: invalid JSON ({exc})")
            continue
        if not isinstance(data, dict):
            errors.append(f"{rel}: JSON root must be object")
            continue
        for k in keys:
            if k not in data:
                errors.append(f"{rel}: missing top-level key {k!r}")

    errors.extend(validate_platform_governance_index())

    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1

    print(
        f"ok: rollout repo contracts ({len(case_ids)} cases, {rule_count} json shape check(s), "
        "platform governance index ok)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
