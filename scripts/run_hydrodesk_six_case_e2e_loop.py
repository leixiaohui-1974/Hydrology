#!/usr/bin/env python3
"""
通用自主运行水网建模 Agent 平台 — HydroDesk rollout 端到端 E2E 编排（全配置驱动）。

「自主运行水网建模 Agent 平台」：以水网为对象、契约为边界，编排数据→建模→率定/控制→
HTML/报告→发布；案例仅通过 cases/<id>/ 与 configs 扩展，不在本脚本写案例分支。

用法（仓库根）:
  python3 Hydrology/scripts/run_hydrodesk_six_case_e2e_loop.py --list-cases
  python3 Hydrology/scripts/run_hydrodesk_six_case_e2e_loop.py --dry-run
  python3 Hydrology/scripts/run_hydrodesk_six_case_e2e_loop.py --case-id zhongxian
  python3 Hydrology/scripts/run_hydrodesk_rollout_e2e_loop.py --list-cases

主配置: Hydrology/configs/hydrodesk_autonomous_waternet_e2e_loop.yaml
兼容:    Hydrology/configs/hydrodesk_six_case_e2e_loop.yaml（redirect）

说明：
  当前默认 rollout cohort 使用六个验证案例，但脚本语义是“rollout case set”，
  不是把产品边界固定为六案。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_HYDROLOGY_ROOT = _SCRIPTS_DIR.parent
if str(_HYDROLOGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_HYDROLOGY_ROOT))

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402
from export_case_modeling_hints import derive_modeling_hints  # noqa: E402
from workflows._shared import resolve_case_entry_inputs  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
DEFAULT_RULES = WORKSPACE / "Hydrology" / "configs" / "workflow_feasibility_rules.yaml"


def _safe_modeling_hints(case_id: str, config_path: Path, rules_path: Path) -> dict[str, Any]:
    try:
        payload = derive_modeling_hints(case_id, config_path, rules_path)
        return payload.get("hints") or {"case_id": case_id}
    except Exception as error:
        return {
            "case_id": case_id,
            "error": str(error),
            "suggested_workflows": [],
            "graphify_supports_auto_modeling_hints": False,
            "graphify_modeling_signal_counts": {},
        }


def _workspace_rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE))
    except ValueError:
        return str(path.resolve())


def _load_source_import_session(case_id: str) -> dict[str, Any]:
    manifest_path = WORKSPACE / "cases" / case_id / "manifest.yaml"
    manifest_payload: dict[str, Any] = {}
    if manifest_path.is_file():
        manifest_payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    latest_block = manifest_payload.get("latest_source_import_session") or {}
    candidates: list[tuple[str, Path]] = []
    raw_latest = str(latest_block.get("path") or "").strip()
    if raw_latest:
        candidates.append(("manifest_latest", WORKSPACE / raw_latest))
    candidates.append(("contracts_default", WORKSPACE / "cases" / case_id / "contracts" / "source_import_session.latest.json"))

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
        if not isinstance(payload, dict):
            continue
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


def _build_hydrodesk_cmd(
    script_rel: str,
    case_id: str,
    action: str,
    cli_extra: dict[str, Any] | None,
) -> list[str]:
    script = WORKSPACE / script_rel
    cmd = [sys.executable, str(script), "--case-id", case_id, "--action", action]
    for k, v in sorted((cli_extra or {}).items()):
        k_str = str(k)
        flag = k_str if k_str.startswith("--") else f"--{k_str.replace('_', '-')}"
        cmd.extend([flag, str(v)])
    return cmd


def _build_case_pipeline_cmd(
    script_rel: str,
    case_id: str,
    phase: str,
    respect_stage_guidance: bool,
    cli_extra: dict[str, Any] | None,
) -> list[str]:
    script = WORKSPACE / script_rel
    cmd = [sys.executable, str(script), "--case-id", case_id, "--phase", phase]
    if respect_stage_guidance:
        cmd.append("--respect-stage-guidance")
    for k, v in sorted((cli_extra or {}).items()):
        k_str = str(k)
        flag = k_str if k_str.startswith("--") else f"--{k_str.replace('_', '-')}"
        cmd.extend([flag, str(v)])
    return cmd


def _scada_sqlite_path_for_skip(case_id: str) -> Path:
    """与 hydrodesk_e2e_actions.resolve_scada_replay_config 一致，用于 live 跳过无库案例。"""
    hyd = WORKSPACE / "Hydrology"
    if str(hyd) not in sys.path:
        sys.path.insert(0, str(hyd))
    from workflows.hydrodesk_e2e_actions import resolve_scada_replay_config  # noqa: PLC0415

    _qs, _qe, sqlite_path, _sid = resolve_scada_replay_config(case_id)
    return sqlite_path


def _run_one(cmd: list[str], dry_run: bool) -> tuple[int, str]:
    if dry_run:
        return 0, " ".join(cmd)
    proc = subprocess.run(
        cmd,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        timeout=7200,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous water-network modeling agent platform — HydroDesk E2E loop (config-driven)",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Loop YAML path")
    parser.add_argument("--case-id", default="", help="仅跑单案例；默认跑配置解析后的全部")
    parser.add_argument("--list-cases", action="store_true", help="打印解析后的 case_id 列表（JSON）并退出")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的命令（不调用子进程）")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="dry-run 时不逐行打印命令，仅输出最终摘要",
    )
    parser.add_argument("--json-summary", action="store_true", help="结束时打印一行 JSON 摘要")
    args = parser.parse_args()

    cfg = load_loop_yaml(WORKSPACE, args.config.resolve())
    case_ids = resolve_case_ids(cfg, WORKSPACE)
    if not case_ids:
        print("no case_ids resolved (check case_selection or case_ids)", file=sys.stderr)
        return 2

    if args.list_cases:
        print(json.dumps({"case_ids": case_ids, "count": len(case_ids)}, ensure_ascii=False))
        return 0

    if args.case_id:
        if args.case_id not in case_ids:
            print(f"case_id {args.case_id!r} not in resolved case list", file=sys.stderr)
            return 2
        case_ids = [args.case_id]

    stages = cfg.get("stages") or []
    hydrodesk_script = str(cfg.get("hydrodesk_e2e_script") or "Hydrology/workflows/hydrodesk_e2e_actions.py")
    pipeline_script = str(cfg.get("case_pipeline_script") or "Hydrology/workflows/run_case_pipeline.py")

    summary: list[dict[str, Any]] = []
    preflight_report: dict[str, Any] = {
        "case_count": len(case_ids),
        "missing_inputs": {},
        "modeling_hints": {},
        "source_import_sessions": {},
    }
    exit_max = 0

    for case_id in case_ids:
        case_modeling_hints = _safe_modeling_hints(case_id, args.config.resolve(), DEFAULT_RULES.resolve())
        case_source_import_session = _load_source_import_session(case_id)
        preflight_report["modeling_hints"][case_id] = case_modeling_hints
        preflight_report["source_import_sessions"][case_id] = case_source_import_session
        for st in stages:
            if not isinstance(st, dict):
                continue

            pipeline_phase = st.get("pipeline_phase")
            action = st.get("action")
            cont = bool(st.get("continue_on_error", False))
            cli_extra = st.get("cli") if isinstance(st.get("cli"), dict) else {}
            skip_if_inputs_missing = bool(st.get("skip_if_inputs_missing", True))
            respect_stage_guidance = bool(st.get("respect_stage_guidance", False))

            cmd: list[str] | None = None
            row_base: dict[str, Any] = {
                "case_id": case_id,
                "stage_id": st.get("id", pipeline_phase or action or "unknown"),
                "continue_on_error": cont,
                "dry_run": args.dry_run,
                "respect_stage_guidance": respect_stage_guidance,
            }

            if pipeline_phase:
                resolved = resolve_case_entry_inputs(case_id)
                missing = []
                case_manifest = Path(resolved["case_manifest"]) if resolved.get("case_manifest") else WORKSPACE / "cases" / case_id / "manifest.yaml"
                if not case_manifest.is_file():
                    missing.append("manifest_yaml")
                if not resolved.get("source_bundle_json"):
                    missing.append("source_bundle")
                if not resolved.get("outlets_json"):
                    missing.append("outlets_json")
                if missing:
                    row = {
                        **row_base,
                        "runner": "case_pipeline",
                        "pipeline_phase": pipeline_phase,
                        "modeling_hints": case_modeling_hints,
                        "source_import_session": case_source_import_session,
                        "skipped": True,
                        "skip_reason": f"missing_inputs: {','.join(missing)}",
                    }
                    preflight_report["missing_inputs"].setdefault(case_id, [])
                    preflight_report["missing_inputs"][case_id].append(
                        {
                            "stage_id": row_base["stage_id"],
                            "pipeline_phase": pipeline_phase,
                            "missing": missing,
                        }
                    )
                    summary.append(row)
                    if not args.quiet:
                        msg = f"# skip {row['stage_id']}: {row['skip_reason']} (case_id={case_id})"
                        print(msg, flush=True)
                    if not skip_if_inputs_missing:
                        exit_max = max(exit_max, 1)
                        print(json.dumps(row, ensure_ascii=False), file=sys.stderr)
                        if not cont:
                            if args.json_summary:
                                print(
                                    json.dumps(
                                        {
                                            "ok": False,
                                            "summary": summary,
                                            "preflight_report": preflight_report,
                                        },
                                        ensure_ascii=False,
                                    )
                                )
                            return 1
                    continue

                cmd = _build_case_pipeline_cmd(
                    pipeline_script,
                    case_id,
                    str(pipeline_phase),
                    respect_stage_guidance,
                    cli_extra,
                )
                row_base["runner"] = "case_pipeline"
                row_base["pipeline_phase"] = pipeline_phase
            elif action:
                act = str(action)
                if (
                    not args.dry_run
                    and act == "run-scada-replay"
                    and bool(st.get("skip_if_sqlite_missing", False))
                ):
                    sp = _scada_sqlite_path_for_skip(case_id)
                    if not sp.is_file():
                        row = {
                            **row_base,
                            "runner": "hydrodesk_e2e",
                            "action": act,
                            "skipped": True,
                            "skip_reason": f"sqlite_not_found:{sp.name}",
                        }
                        summary.append(row)
                        if not args.quiet:
                            print(
                                f"# skip {row['stage_id']}: {row['skip_reason']} (case_id={case_id})",
                                flush=True,
                            )
                        continue
                cmd = _build_hydrodesk_cmd(hydrodesk_script, case_id, act, cli_extra)
                row_base["runner"] = "hydrodesk_e2e"
                row_base["action"] = action
            else:
                continue

            assert cmd is not None
            rc, out = _run_one(cmd, args.dry_run)
            row = {
                **row_base,
                "modeling_hints": case_modeling_hints if row_base.get("runner") == "case_pipeline" else None,
                "source_import_session": case_source_import_session if row_base.get("runner") == "case_pipeline" else None,
                "returncode": rc,
                "skipped": False,
            }
            if args.dry_run:
                row["command"] = out
                if not args.quiet:
                    print(out, flush=True)
            else:
                row["output_tail"] = out[-2000:] if out else ""
            summary.append(row)
            if rc != 0:
                exit_max = max(exit_max, rc)
                print(json.dumps(row, ensure_ascii=False), file=sys.stderr)
                if not cont:
                    if args.json_summary:
                        print(
                            json.dumps(
                                {
                                    "ok": False,
                                    "summary": summary,
                                    "preflight_report": preflight_report,
                                },
                                ensure_ascii=False,
                            )
                        )
                    return min(rc, 125) if rc > 0 else 1

    if args.json_summary:
        print(
            json.dumps(
                {
                    "ok": exit_max == 0,
                    "summary": summary,
                    "preflight_report": preflight_report,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(json.dumps({"ok": exit_max == 0, "steps": len(summary)}, ensure_ascii=False))
    return exit_max if exit_max != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
