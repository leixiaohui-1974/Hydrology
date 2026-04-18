#!/usr/bin/env python3
"""
从 hydrodesk 闭环 YAML 的 case_selection 解析 case_id 列表，并从各案 case_manifest.json 取 display_name，
同时导出 hydrodesk_shell.full_spatial_hydro_evidence_case_ids（须为 rollout case_ids 子集）、
可选的 default_active_case_id（须在 case_ids 内），
生成 HydroDesk 与 Playwright 共用的 playwrightRollout.generated.json。

仓库根:
  python3 Hydrology/scripts/export_playwright_rollout_registry.py
  python3 Hydrology/scripts/export_playwright_rollout_registry.py --check   # 与已生成文件一致则 0，否则 1

变更闭环案例列表或案例显示名后须重跑本脚本并提交生成文件（CI 单测会校验）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from hydrodesk_loop_yaml_util import (  # noqa: E402
    load_loop_yaml,
    resolve_case_ids,
    resolve_default_active_case_id,
    resolve_full_spatial_hydro_evidence_case_ids,
)

DEFAULT_LOOP = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
DEFAULT_OUT = WORKSPACE / "HydroDesk" / "src" / "config" / "playwrightRollout.generated.json"


def _display_name_for_case(workspace: Path, case_id: str) -> str:
    man = workspace / "cases" / case_id / "contracts" / "case_manifest.json"
    if not man.is_file():
        return case_id
    try:
        data = json.loads(man.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return case_id
    if isinstance(data, dict):
        name = data.get("display_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return case_id


def compute_rollout_registry(workspace: Path, loop_config: Path) -> dict[str, Any]:
    cfg = load_loop_yaml(workspace, loop_config.resolve())
    case_ids = resolve_case_ids(cfg, workspace)
    if not case_ids:
        raise ValueError("no case_ids resolved from loop config")

    spatial_ids = resolve_full_spatial_hydro_evidence_case_ids(cfg)
    sid_set = set(case_ids)
    unknown = [x for x in spatial_ids if x not in sid_set]
    if unknown:
        raise ValueError(
            "hydrodesk_shell.full_spatial_hydro_evidence_case_ids must be subset of rollout case_ids; "
            f"unknown: {unknown}"
        )

    default_active = resolve_default_active_case_id(cfg)
    if default_active is not None and default_active not in sid_set:
        raise ValueError(
            "hydrodesk_shell.default_active_case_id must be in rollout case_ids; "
            f"got {default_active!r}, allowed {list(case_ids)}"
        )

    rel_loop = str(loop_config.resolve().relative_to(workspace))
    registry = []
    for cid in case_ids:
        registry.append(
            {
                "id": cid,
                "name": _display_name_for_case(workspace, cid),
                "caseId": cid,
                "status": "active",
                "stage": "V2_E2E",
                "source": "playwright_fixture",
            }
        )

    return {
        "_auto_generated": True,
        "generator": "Hydrology/scripts/export_playwright_rollout_registry.py",
        "loop_config": rel_loop.replace("\\", "/"),
        "case_ids": list(case_ids),
        "full_spatial_hydro_evidence_case_ids": list(spatial_ids),
        "default_active_case_id": default_active,
        "registry": registry,
    }


def _normalize_for_compare(payload: dict[str, Any]) -> dict[str, Any]:
    """比较用：去掉生成元数据。"""
    dac = payload.get("default_active_case_id")
    return {
        "case_ids": list(payload.get("case_ids") or []),
        "full_spatial_hydro_evidence_case_ids": list(
            payload.get("full_spatial_hydro_evidence_case_ids") or []
        ),
        "default_active_case_id": dac if dac is None else str(dac),
        "registry": list(payload.get("registry") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace", type=Path, default=WORKSPACE)
    parser.add_argument("--loop-config", type=Path, default=DEFAULT_LOOP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="仅校验已生成文件与当前闭环一致")
    args = parser.parse_args()

    ws = args.workspace.resolve()
    computed = compute_rollout_registry(ws, args.loop_config.resolve())
    out_path = args.output.resolve()

    if args.check:
        if not out_path.is_file():
            print(f"missing {out_path}", file=sys.stderr)
            return 1
        on_disk = json.loads(out_path.read_text(encoding="utf-8"))
        if _normalize_for_compare(computed) != _normalize_for_compare(on_disk):
            print(
                "playwrightRollout.generated.json is out of sync; run:\n"
                "  python3 Hydrology/scripts/export_playwright_rollout_registry.py",
                file=sys.stderr,
            )
            return 1
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(computed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_path.relative_to(ws)} ({len(computed['case_ids'])} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
