#!/usr/bin/env python3
"""
从 hydrodesk_e2e_acceptance_rollout.yaml + 闭环 YAML 的 case_selection 生成
HydroDesk/src/config/playwrightE2eAcceptance.generated.json，供 six-case-e2e-loop 等 E2E 消费。

仓库根:
  python3 Hydrology/scripts/export_playwright_e2e_acceptance.py
  python3 Hydrology/scripts/export_playwright_e2e_acceptance.py --check   # 与已生成文件一致则 0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

WORKSPACE = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402

DEFAULT_LOOP = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
DEFAULT_ACCEPTANCE = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_e2e_acceptance_rollout.yaml"
DEFAULT_OUT = WORKSPACE / "HydroDesk" / "src" / "config" / "playwrightE2eAcceptance.generated.json"


def _display_name_from_case_manifest(workspace: Path, case_id: str) -> str | None:
    man = workspace / "cases" / case_id / "contracts" / "case_manifest.json"
    if not man.is_file():
        return None
    try:
        data = json.loads(man.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        name = data.get("display_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _display_name_from_pipedream(
    workspace: Path, template: str, case_id: str, json_key: str
) -> str | None:
    rel = template.format(case_id=case_id)
    p = workspace / rel
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get(json_key)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def compute_e2e_acceptance(
    workspace: Path, loop_config: Path, acceptance_config: Path
) -> dict[str, Any]:
    loop_cfg = load_loop_yaml(workspace, loop_config.resolve())
    case_ids = resolve_case_ids(loop_cfg, workspace)
    if not case_ids:
        raise ValueError("no case_ids resolved from loop config")

    with open(acceptance_config, encoding="utf-8") as fh:
        acc = yaml.safe_load(fh)
    if not isinstance(acc, dict):
        raise ValueError("invalid acceptance yaml root")

    pd = acc.get("pipedream") if isinstance(acc.get("pipedream"), dict) else {}
    case_tpl = str(pd.get("case_config_template") or "").strip()
    wnal_tpl = str(pd.get("wnal_path_template") or "").strip()
    pipe_sum_tpl = str(pd.get("pipeline_summary_template") or "").strip()
    dn_key = str(pd.get("display_name_json_key") or "display_name").strip()

    defaults = acc.get("defaults") if isinstance(acc.get("defaults"), dict) else {}
    per_case = acc.get("per_case") if isinstance(acc.get("per_case"), dict) else {}

    min_wnal_default = float(defaults.get("min_wnal_level", 0))
    min_nse_default = float(defaults.get("min_hydro_nse", 0.8))
    assert_when_present = bool(defaults.get("assert_hydro_nse_when_pipeline_summary_present", True))

    cases_out: dict[str, Any] = {}
    for cid in case_ids:
        ov = per_case.get(cid) if isinstance(per_case.get(cid), dict) else {}
        min_wnal = float(ov.get("min_wnal_level", min_wnal_default))
        min_nse = float(ov.get("min_hydro_nse", min_nse_default))
        assert_hydro = bool(ov.get("assert_hydro_nse_when_pipeline_summary_present", assert_when_present))

        display_name = None
        if case_tpl:
            display_name = _display_name_from_pipedream(workspace, case_tpl, cid, dn_key)
        if not display_name:
            display_name = _display_name_from_case_manifest(workspace, cid)
        if not display_name:
            display_name = cid

        wnal_rel = wnal_tpl.format(case_id=cid, display_name=display_name) if wnal_tpl else ""
        pipe_rel = pipe_sum_tpl.format(case_id=cid, display_name=display_name) if pipe_sum_tpl else ""
        pipedream_cfg_rel = case_tpl.format(case_id=cid) if case_tpl else ""

        cases_out[cid] = {
            "case_id": cid,
            "display_name": display_name,
            "min_wnal_level": min_wnal,
            "min_hydro_nse": min_nse,
            "assert_hydro_nse_when_pipeline_summary_present": assert_hydro,
            "pipedream_case_config_relpath": pipedream_cfg_rel.replace("\\", "/"),
            "wnal_json_relpath": wnal_rel.replace("\\", "/"),
            "pipeline_summary_relpath": pipe_rel.replace("\\", "/"),
        }

    rel_loop = str(loop_config.resolve().relative_to(workspace)).replace("\\", "/")
    rel_acc = str(acceptance_config.resolve().relative_to(workspace)).replace("\\", "/")

    return {
        "_auto_generated": True,
        "generator": "Hydrology/scripts/export_playwright_e2e_acceptance.py",
        "loop_config": rel_loop,
        "acceptance_config": rel_acc,
        "case_ids": list(case_ids),
        "cases": cases_out,
    }


def _normalize_for_compare(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_ids": list(payload.get("case_ids") or []),
        "cases": json.loads(json.dumps(payload.get("cases") or {}, sort_keys=True)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace", type=Path, default=WORKSPACE)
    parser.add_argument("--loop-config", type=Path, default=DEFAULT_LOOP)
    parser.add_argument("--acceptance-config", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    ws = args.workspace.resolve()
    computed = compute_e2e_acceptance(ws, args.loop_config.resolve(), args.acceptance_config.resolve())
    out_path = args.output.resolve()

    if args.check:
        if not out_path.is_file():
            print(f"missing {out_path}", file=sys.stderr)
            return 1
        on_disk = json.loads(out_path.read_text(encoding="utf-8"))
        if _normalize_for_compare(computed) != _normalize_for_compare(on_disk):
            print(
                "playwrightE2eAcceptance.generated.json is out of sync; run:\n"
                "  python3 Hydrology/scripts/export_playwright_e2e_acceptance.py",
                file=sys.stderr,
            )
            return 1
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(computed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path.relative_to(ws)} ({len(computed['case_ids'])} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
