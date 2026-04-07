#!/usr/bin/env python3
"""
通用自主运行水网建模 Agent 平台 — HydroDesk 端到端 E2E 编排（全配置驱动）。

「自主运行水网建模 Agent 平台」：以水网为对象、契约为边界，编排数据→建模→率定/控制→
HTML/报告→发布；案例仅通过 cases/<id>/ 与 configs 扩展，不在本脚本写案例分支。

用法（仓库根）:
  python3 Hydrology/scripts/run_hydrodesk_six_case_e2e_loop.py --list-cases
  python3 Hydrology/scripts/run_hydrodesk_six_case_e2e_loop.py --dry-run
  python3 Hydrology/scripts/run_hydrodesk_six_case_e2e_loop.py --case-id zhongxian

主配置: Hydrology/configs/hydrodesk_autonomous_waternet_e2e_loop.yaml
兼容:    Hydrology/configs/hydrodesk_six_case_e2e_loop.yaml（redirect）
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

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"


def _case_inputs_from_manifest(case_id: str) -> tuple[Path | None, Path | None, Path]:
    """manifest.latest_source_bundle / latest_outlets；outlets 可回退为与 bundle 同目录。"""
    man = WORKSPACE / "cases" / case_id / "manifest.yaml"
    case_manifest = WORKSPACE / "cases" / case_id / "contracts" / "case_manifest.json"
    if not man.is_file():
        return None, None, case_manifest

    data = yaml.safe_load(man.read_text(encoding="utf-8")) or {}

    def _pick(block_key: str) -> Path | None:
        block = data.get(block_key) or {}
        p = block.get("path")
        if not p:
            return None
        path = (WORKSPACE / str(p)).resolve()
        return path if path.is_file() else None

    source_bundle = _pick("latest_source_bundle")
    outlets = _pick("latest_outlets")
    if outlets is None and source_bundle is not None:
        cand = source_bundle.parent / "outlets.normalized.json"
        if cand.is_file():
            outlets = cand
    return source_bundle, outlets, case_manifest


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
    case_manifest: Path,
    source_bundle: Path,
    outlets_json: Path,
    cli_extra: dict[str, Any] | None,
) -> list[str]:
    script = WORKSPACE / script_rel
    cmd = [
        sys.executable,
        str(script),
        "--case-id",
        case_id,
        "--case-manifest",
        str(case_manifest),
        "--source-bundle-json",
        str(source_bundle),
        "--outlets-json",
        str(outlets_json),
        "--phase",
        phase,
    ]
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
    }
    exit_max = 0

    for case_id in case_ids:
        for st in stages:
            if not isinstance(st, dict):
                continue

            pipeline_phase = st.get("pipeline_phase")
            action = st.get("action")
            cont = bool(st.get("continue_on_error", False))
            cli_extra = st.get("cli") if isinstance(st.get("cli"), dict) else {}
            skip_if_inputs_missing = bool(st.get("skip_if_inputs_missing", True))

            cmd: list[str] | None = None
            row_base: dict[str, Any] = {
                "case_id": case_id,
                "stage_id": st.get("id", pipeline_phase or action or "unknown"),
                "continue_on_error": cont,
                "dry_run": args.dry_run,
            }

            if pipeline_phase:
                source_bundle, outlets, case_manifest = _case_inputs_from_manifest(case_id)
                missing = []
                if not case_manifest.is_file():
                    missing.append("case_manifest")
                if source_bundle is None:
                    missing.append("source_bundle")
                if outlets is None:
                    missing.append("outlets_json")
                if missing:
                    row = {
                        **row_base,
                        "runner": "case_pipeline",
                        "pipeline_phase": pipeline_phase,
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
                    case_manifest,
                    source_bundle,
                    outlets,
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
