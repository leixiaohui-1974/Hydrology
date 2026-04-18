#!/usr/bin/env python3
"""
Rollout 案例壳层门禁：与 hydrodesk_autonomous_waternet_e2e_loop.yaml 解析出的 case_id 一致，
校验 Hydrology/configs/<id>.yaml 存在且 workflows.load_case_config / resolve_case_entry_inputs 可加载，
并验证案例入口物（manifest.yaml、contracts/case_manifest.json）完整（不跑数值工作流）。

仓库根运行:
  python3 Hydrology/scripts/check_rollout_cases_loadable.py
  python3 Hydrology/scripts/check_rollout_cases_loadable.py --config Hydrology/configs/hydrodesk_autonomous_waternet_e2e_loop.yaml
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402
from scaffold_new_case import _case_manifest_json, _links_yaml, _manifest_yaml  # noqa: E402

HYDROLOGY_ROOT = WORKSPACE / "Hydrology"
DEFAULT_CONFIG = HYDROLOGY_ROOT / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"


def _git_head_file_text(relpath: str) -> str | None:
    proc = subprocess.run(
        ["git", "show", f"HEAD:{relpath}"],
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _repair_case_entry_files(case_id: str, *, display_name: str, project_type: str) -> list[str]:
    repaired: list[str] = []
    case_root = WORKSPACE / "cases" / case_id
    contracts = case_root / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)

    manifest_path = case_root / "manifest.yaml"
    manifest_rel = f"cases/{case_id}/manifest.yaml"
    if not manifest_path.is_file():
        if manifest_path.exists() or manifest_path.is_symlink():
            manifest_path.unlink(missing_ok=True)
        head_text = _git_head_file_text(manifest_rel)
        manifest_path.write_text(
            head_text if head_text is not None else _manifest_yaml(case_id, display_name),
            encoding="utf-8",
        )
        repaired.append(manifest_rel)

    links_path = case_root / "links.yaml"
    links_rel = f"cases/{case_id}/links.yaml"
    if not links_path.is_file():
        if links_path.exists() or links_path.is_symlink():
            links_path.unlink(missing_ok=True)
        head_text = _git_head_file_text(links_rel)
        links_path.write_text(
            head_text if head_text is not None else _links_yaml(case_id),
            encoding="utf-8",
        )
        repaired.append(links_rel)

    case_manifest_path = contracts / "case_manifest.json"
    case_manifest_rel = f"cases/{case_id}/contracts/case_manifest.json"
    if not case_manifest_path.is_file():
        if case_manifest_path.exists() or case_manifest_path.is_symlink():
            case_manifest_path.unlink(missing_ok=True)
        head_text = _git_head_file_text(case_manifest_rel)
        if head_text is not None:
            case_manifest_path.write_text(head_text, encoding="utf-8")
        else:
            case_manifest_path.write_text(
                json.dumps(_case_manifest_json(case_id, display_name, project_type), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        repaired.append(case_manifest_rel)
    return repaired


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Loop YAML（默认自主水网闭环）")
    parser.add_argument("--repair", action="store_true", help="缺失或坏链时自动修复入口物，再执行门禁")
    args = parser.parse_args()

    if str(HYDROLOGY_ROOT) not in sys.path:
        sys.path.insert(0, str(HYDROLOGY_ROOT))

    from workflows._shared import load_case_config, resolve_case_entry_inputs  # noqa: PLC0415

    cfg_path = args.config.resolve()
    cfg = load_loop_yaml(WORKSPACE, cfg_path)
    case_ids = resolve_case_ids(cfg, WORKSPACE)
    if not case_ids:
        print("no case_ids resolved (check case_selection)", file=sys.stderr)
        return 2

    errors: list[str] = []
    for cid in case_ids:
        yml = HYDROLOGY_ROOT / "configs" / f"{cid}.yaml"
        manifest = WORKSPACE / "cases" / cid / "manifest.yaml"
        links = WORKSPACE / "cases" / cid / "links.yaml"
        case_manifest = WORKSPACE / "cases" / cid / "contracts" / "case_manifest.json"
        if not yml.is_file():
            errors.append(f"missing {yml.relative_to(WORKSPACE)}")
            continue
        cfg_loaded = None
        try:
            cfg_loaded = load_case_config(cid)
        except Exception as exc:  # noqa: BLE001 — surface all load failures for CI
            errors.append(f"{cid}: load_case_config: {exc}")
            continue
        if args.repair and (not manifest.is_file() or not links.is_file() or not case_manifest.is_file()):
            repaired = _repair_case_entry_files(
                cid,
                display_name=str(cfg_loaded.get("display_name") or cid),
                project_type=str(cfg_loaded.get("project_type") or "generic"),
            )
            if repaired:
                print(f"repaired {cid}: {', '.join(repaired)}", file=sys.stderr)
        if not manifest.is_file():
            errors.append(f"{cid}: missing {manifest.relative_to(WORKSPACE)}")
        if not links.is_file():
            errors.append(f"{cid}: missing {links.relative_to(WORKSPACE)}")
        if not case_manifest.is_file():
            errors.append(f"{cid}: missing {case_manifest.relative_to(WORKSPACE)}")
        try:
            resolved = resolve_case_entry_inputs(cid)
        except Exception as exc:  # noqa: BLE001 — surface all load failures for CI
            errors.append(f"{cid}: resolve_case_entry_inputs: {exc}")
            continue
        for key in ("case_manifest", "source_bundle_json", "outlets_json", "simulation_config"):
            if not resolved.get(key):
                errors.append(f"{cid}: unresolved entry input: {key}")

    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1

    print(f"ok: {len(case_ids)} rollout case(s) loadable and entry-complete ({', '.join(case_ids)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
