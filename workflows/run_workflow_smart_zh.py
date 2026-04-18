#!/usr/bin/env python3
"""中文友好的工作流目录、端到端范围说明与自动选流编排。

- plan：根据案例数据就绪度（feasibility）+ 建模提示（modeling_hints）生成有序执行计划
- run：按计划调用 run_workflow（默认遇错即停；``--continue-on-error`` 才继续）
- 进度：终端显示 [i/N] 与耗时；默认写入 ``contracts/workflow_smart_progress.latest.ndjson``（一行一 JSON，便于外部 tail/采集）
- Agent：`meta` 打印契约 JSON；`plan` / `run` / `menu` / `refresh-reports` 可用 ``--json-summary``（或 ``HYDRO_SMART_JSON_SUMMARY=1``）写入当前命令作用域摘要；正式 ``run --profile smart`` 还会刷新共享 ``workflow_smart_cli_result.latest.json``
- menu：交互式选择端到端类型后展示计划

配置：
  - Hydrology/configs/workflow_catalog_zh.yaml（目录与选流）
  - Hydrology/configs/workflow_smart_reporting.yaml（跑后报告 / refresh-reports / md_regeneration）
  - 案例 YAML 可选顶层 ``smart_reporting:`` 覆盖上述默认（零案例硬编码）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SCRIPTS_DIR = BASE_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from workflows import WORKFLOW_REGISTRY, list_workflows, run_workflow  # noqa: E402
from workflows._shared import load_case_config  # noqa: E402

DEFAULT_CATALOG = BASE_DIR / "configs" / "workflow_catalog_zh.yaml"
DEFAULT_RULES = BASE_DIR / "configs" / "workflow_feasibility_rules.yaml"
DEFAULT_LOOP = BASE_DIR / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"


def _contracts_dir(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id.strip() / "contracts"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _append_ndjson(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def _resolve_run_report_level(args: argparse.Namespace) -> str:
    """默认 detailed；--no-reports / --no-detailed-reports → none；--simple-report → simple。"""
    if getattr(args, "no_reports", False) or getattr(args, "no_detailed_reports", False):
        return "none"
    if getattr(args, "simple_report", False):
        return "simple"
    lvl = getattr(args, "report_level", "detailed") or "detailed"
    if str(lvl).strip().lower() not in ("detailed", "simple", "none"):
        return "detailed"
    return str(lvl).strip().lower()


def _resolve_plan_report_level(args: argparse.Namespace) -> str:
    if getattr(args, "no_plan_reports", False):
        return "none"
    return _resolve_run_report_level(args)


def _optional_workspace_path(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _agent_json_summary_requested(args: argparse.Namespace) -> bool:
    if getattr(args, "json_summary", False):
        return True
    v = (os.environ.get("HYDRO_SMART_JSON_SUMMARY") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _parse_restrict_workflow_keys(raw: str | None) -> set[str] | None:
    value = str(raw or "").strip()
    if not value:
        return None
    keys = {part.strip() for part in value.split(",") if part.strip()}
    return keys or None


PROFILE_BUSINESS_LABELS: dict[str, str] = {
    "smart": "一键建模",
    "modeling": "建模分析",
    "control": "调度控制",
    "evaluation": "结果审查",
    "full": "全流程复核",
}


NON_SUCCESS_OUTCOME_STATUSES = {
    "degraded",
    "error",
    "failed",
    "insufficient_data",
    "no_data",
    "partial",
    "quality_failed",
    "skipped",
}

QUALITY_DEGRADED_OUTCOME_STATUSES = {
    "degraded",
    "insufficient_data",
    "no_data",
    "partial",
    "quality_failed",
    "skipped",
}

ALLOWED_OUTCOME_STATUSES = {"completed", *NON_SUCCESS_OUTCOME_STATUSES}


def _standard_smart_artifact_relpaths(case_id: str) -> dict[str, str]:
    cid = case_id.strip()
    base = f"cases/{cid}/contracts"
    return {
        "run_summary": f"{base}/workflow_smart_run_summary.latest.json",
        "plan": f"{base}/workflow_smart_plan.latest.json",
        "progress_ndjson": f"{base}/workflow_smart_progress.latest.ndjson",
        "cli_result": f"{base}/workflow_smart_cli_result.latest.json",
    }


def _normalize_cli_result_component(value: str | None, *, fallback: str) -> str:
    raw = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return normalized or fallback


def _scoped_cli_result_relpath(case_id: str, *, command: str, profile: str, dry_run: bool) -> str:
    cid = case_id.strip()
    base = f"cases/{cid}/contracts"
    command_slug = _normalize_cli_result_component(command, fallback="command")
    profile_slug = _normalize_cli_result_component(profile, fallback="no_profile")
    dry_run_suffix = ".dry_run" if dry_run else ""
    return (
        f"{base}/workflow_smart_cli_result."
        f"{command_slug}.{profile_slug}{dry_run_suffix}.latest.json"
    )


def _should_refresh_shared_cli_result(*, command: str, profile: str, dry_run: bool) -> bool:
    return command == "run" and str(profile or "").strip().lower() == "smart" and not dry_run


def _profile_business_label(profile: str) -> str:
    key = str(profile or "").strip().lower()
    return PROFILE_BUSINESS_LABELS.get(key, key or "未指定模式")


def _format_scope_labels(scopes: list[str] | None) -> str:
    labels: list[str] = []
    for scope in scopes or []:
        normalized_scope = str(scope or "").strip()
        if not normalized_scope:
            continue
        label = _profile_business_label(normalized_scope)
        if label not in labels:
            labels.append(label)
    return " / ".join(labels) if labels else "未标注"


def _recommended_commands_for_business(*, command: str, case_id: str, profile: str) -> list[str]:
    cid = case_id.strip()
    selected_profile = str(profile or "smart").strip().lower() or "smart"
    commands_by_command = {
        "plan": [
            f"python3 -m workflows.run_workflow_smart_zh run --case-id {cid} --profile {selected_profile} --dry-run --json-summary",
            f"python3 -m workflows.run_workflow_smart_zh run --case-id {cid} --profile {selected_profile} --json-summary",
        ],
        "run": [
            f"python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id {cid} --json-summary",
            f"python3 -m workflows.run_workflow_smart_zh plan --case-id {cid} --json-summary",
        ],
        "refresh-reports": [
            f"python3 -m workflows.run_workflow_smart_zh plan --case-id {cid} --json-summary",
            f"python3 -m workflows.run_workflow_smart_zh run --case-id {cid} --profile {selected_profile} --json-summary",
        ],
    }
    return commands_by_command.get(
        command,
        [f"python3 -m workflows.run_workflow_smart_zh plan --case-id {cid} --json-summary"],
    )


def _print_business_next_steps(*, command: str, case_id: str, profile: str) -> None:
    next_commands = _recommended_commands_for_business(
        command=command,
        case_id=case_id,
        profile=profile,
    )
    if not next_commands:
        return
    print("建议下一步：")
    for item in next_commands:
        print(f"  · {item}")
    print()


def _print_cli_result_guidance(payload: dict[str, Any]) -> None:
    business_status = str(payload.get("business_status_zh") or "").strip()
    recommended_next_action = str(payload.get("recommended_next_action") or "").strip()
    recommended_next_commands = payload.get("recommended_next_commands") or []
    if business_status:
        print(f"业务状态：{business_status}")
    if recommended_next_action:
        print(f"建议处理：{recommended_next_action}")
    if recommended_next_commands:
        print("建议命令：")
        for item in recommended_next_commands:
            print(f"  · {item}")
    if business_status or recommended_next_action or recommended_next_commands:
        print()


def _recommended_artifacts(
    *,
    command: str,
    arts: dict[str, str],
    report_paths: dict[str, Any],
    progress_relpath: str | None,
) -> list[str]:
    ordered: list[str] = []

    def add(path: str | None) -> None:
        p = str(path or "").strip()
        if p and p not in ordered:
            ordered.append(p)

    add(arts.get("plan"))
    if command in {"run", "refresh-reports"}:
        add(arts.get("run_summary"))
        add(progress_relpath or arts.get("progress_ndjson"))
    if command == "plan":
        add("cases/<case_id>/contracts/workflow_smart_plan_report.latest.md")
        add("cases/<case_id>/contracts/workflow_smart_plan_report.latest.html")
    for key in (
        "smart_report_md",
        "smart_report_html",
        "business_run_digest_md",
        "business_run_digest_html",
        "e2e_dashboard_html",
        "final_report_json",
        "universal_report_html",
    ):
        add(report_paths.get(key))
    add(arts.get("cli_result_scoped"))
    add(arts.get("cli_result"))
    return ordered


def _normalize_outcome_status(value: Any) -> str:
    status = str(value or "completed").strip().lower()
    return status or "completed"


def _coerce_status_to_outcome_status(value: Any) -> str | None:
    status = str(value or "").strip().lower()
    if not status:
        return None
    if status == "completed" or status in NON_SUCCESS_OUTCOME_STATUSES:
        return status
    if status.startswith("skipped"):
        return "skipped"
    if status in {"blocked", "failed_convergence"}:
        return "partial"
    if status in {"failure", "failed"}:
        return "failed"
    return None


def _summarize_workflow_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "ok": True,
            "outcome_status": "completed",
            "quality_gate_passed": None,
            "quality_reason": None,
        }

    quality_gate_passed = result.get("quality_gate_passed")
    quality_reason = str(
        result.get("quality_reason") or result.get("reason") or result.get("error") or ""
    ).strip() or None
    raw_outcome_status = result.get("outcome_status")
    if raw_outcome_status is None:
        if result.get("error"):
            raw_outcome_status = "error"
        else:
            raw_outcome_status = _coerce_status_to_outcome_status(result.get("status"))
    outcome_status = _normalize_outcome_status(raw_outcome_status)
    ok = outcome_status not in NON_SUCCESS_OUTCOME_STATUSES and quality_gate_passed is not False
    return {
        "ok": ok,
        "outcome_status": outcome_status,
        "quality_gate_passed": quality_gate_passed,
        "quality_reason": quality_reason,
    }


def _build_workflow_failure_message(workflow_key: str, summary: dict[str, Any]) -> str:
    parts = [workflow_key]
    outcome_status = summary.get("outcome_status")
    quality_gate_passed = summary.get("quality_gate_passed")
    quality_reason = summary.get("quality_reason")
    if outcome_status and outcome_status != "completed":
        parts.append(str(outcome_status))
    elif quality_gate_passed is False:
        parts.append("quality_failed")
    if quality_reason:
        parts.append(str(quality_reason))
    return ": ".join(parts)


def _quality_degraded_steps(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        step
        for step in results
        if str(step.get("outcome_status") or "") in QUALITY_DEGRADED_OUTCOME_STATUSES
    ]


def _continued_quality_degraded_steps(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [step for step in _quality_degraded_steps(results) if bool(step.get("continued"))]


def _has_hard_failures(results: list[dict[str, Any]], failures: list[str]) -> bool:
    if any(
        (not bool(step.get("ok")))
        and str(step.get("outcome_status") or "") not in QUALITY_DEGRADED_OUTCOME_STATUSES
        for step in results
    ):
        return True
    return any(
        not any(token in str(message or "").lower() for token in QUALITY_DEGRADED_OUTCOME_STATUSES)
        for message in failures
    )


def _classify_cli_result(
    *,
    command: str,
    ok: bool,
    exit_code: int,
    results: list[dict[str, Any]],
    failures: list[str],
    report_paths: dict[str, Any],
    dry_run: bool,
    profile: str,
) -> dict[str, str | None]:
    profile_zh = _profile_business_label(profile)
    if command == "plan":
        if ok:
            return {
                "business_status_zh": f"{profile_zh}计划已生成",
                "error_code": None,
                "error_category": None,
                "recommended_next_action": "确认计划后执行 run；如果只调整文案或报告策略，可后续使用 refresh-reports。",
            }
        return {
            "business_status_zh": f"{profile_zh}计划生成失败",
            "error_code": "smart_plan_failed",
            "error_category": "planning",
            "recommended_next_action": "先检查案例输入、可行性导出和建模提示，再重新执行 plan。",
        }

    if command == "refresh-reports":
        if ok:
            return {
                "business_status_zh": "报告链已刷新",
                "error_code": None,
                "error_category": None,
                "recommended_next_action": "优先查看 smart_report、business_run_digest 与 final_report；如需重跑建模再执行 run。",
            }
        return {
            "business_status_zh": "报告链刷新失败",
            "error_code": "smart_refresh_reports_failed",
            "error_category": "reporting",
            "recommended_next_action": "检查 workflow_smart_run_summary、plan 与报告配置后重试 refresh-reports。",
        }

    if command == "run" and dry_run:
        return {
            "business_status_zh": f"{profile_zh}执行预览已生成",
            "error_code": None,
            "error_category": None,
            "recommended_next_action": "确认计划无误后去掉 --dry-run 执行正式建模；也可先查看计划说明和推荐产物。",
        }

    has_hard_failures = _has_hard_failures(results, failures)
    continued_degraded_steps = _continued_quality_degraded_steps(results)
    if (
        not has_hard_failures
        and continued_degraded_steps
        and len(continued_degraded_steps) == len(_quality_degraded_steps(results))
    ):
        return {
            "business_status_zh": f"{profile_zh}执行已继续完成，但存在可继续的降级步骤",
            "error_code": "smart_run_non_blocking_degraded",
            "error_category": "quality",
            "recommended_next_action": "优先查看 continued_quality_degraded_steps、run_summary 与相关 contracts，补齐降级步骤输入后重新执行 run。",
        }

    if ok:
        return {
            "business_status_zh": f"{profile_zh}执行完成",
            "error_code": None,
            "error_category": None,
            "recommended_next_action": "优先查看 business_run_digest、E2E 看板与 final_report；如只需重出文档可执行 refresh-reports。",
        }

    if failures:
        first_failure = str(failures[0] or "").lower()
        if any(token in first_failure for token in QUALITY_DEGRADED_OUTCOME_STATUSES):
            error_code = "smart_run_quality_degraded"
            error_category = "quality"
            business_status = f"{profile_zh}执行已落盘，但未达到业务质量门槛"
            next_action = "优先查看 run_summary、progress_ndjson 与相关 contracts，修复降级或质量失败步骤后重新执行 run。"
        elif "filenotfound" in first_failure or "不存在" in first_failure or "missing" in first_failure:
            error_code = "smart_run_missing_input"
            error_category = "input"
            business_status = f"{profile_zh}执行未完成"
            next_action = "补齐缺失输入或 contracts 后重试 run；必要时先执行 plan 确认可用步骤。"
        else:
            error_code = "smart_run_workflow_failed"
            error_category = "workflow_execution"
            business_status = f"{profile_zh}执行未完成"
            next_action = "查看 progress_ndjson 与 run_summary 中首个失败步骤，修复后重新执行 run；如仅需重出报告再执行 refresh-reports。"
        return {
            "business_status_zh": business_status,
            "error_code": error_code,
            "error_category": error_category,
            "recommended_next_action": next_action,
        }

    if exit_code != 0 and report_paths:
        return {
            "business_status_zh": f"{profile_zh}主体完成，但报告链存在错误",
            "error_code": "smart_run_reporting_degraded",
            "error_category": "reporting",
            "recommended_next_action": "建模主链已完成，请先查看已有报告；修复报告配置后执行 refresh-reports。",
        }

    return {
        "business_status_zh": f"{profile_zh}执行失败",
        "error_code": "smart_run_failed",
        "error_category": "runtime",
        "recommended_next_action": "查看 cli_result 与 run_summary，定位失败原因后重试。",
    }


def _build_cli_result_payload(
    *,
    command: str,
    case_id: str,
    profile: str,
    exit_code: int,
    ok: bool,
    results: list[dict[str, Any]],
    failures: list[str],
    total_elapsed_sec: float | None,
    plan: dict[str, Any] | None,
    report_bundle: dict[str, Any] | None,
    dry_run: bool = False,
    progress_relpath: str | None = None,
    md_refresh: dict[str, Any] | None = None,
) -> dict[str, Any]:
    arts = _standard_smart_artifact_relpaths(case_id)
    arts["cli_result_scoped"] = _scoped_cli_result_relpath(
        case_id,
        command=command,
        profile=profile,
        dry_run=dry_run,
    )
    if progress_relpath:
        arts["progress_ndjson"] = progress_relpath
    report_paths = {}
    reporting_src = None
    if report_bundle and isinstance(report_bundle, dict):
        report_paths = dict(report_bundle.get("report_paths") or {})
        reporting_src = report_bundle.get("reporting_config_source")
    steps_ok = sum(1 for r in results if r.get("ok"))
    quality_degraded_steps = _quality_degraded_steps(results)
    continued_quality_degraded = _continued_quality_degraded_steps(results)
    classification = _classify_cli_result(
        command=command,
        ok=ok,
        exit_code=exit_code,
        results=results,
        failures=failures,
        report_paths=report_paths,
        dry_run=dry_run,
        profile=profile,
    )
    return {
        "schema_version": "workflow_smart_cli_result.v1",
        "_generator": "workflows.run_workflow_smart_zh",
        "command": command,
        "case_id": case_id.strip(),
        "profile": profile,
        "profile_label_zh": _profile_business_label(profile),
        "business_goal": f"{_profile_business_label(profile)}（{command}）",
        "exit_code": exit_code,
        "ok": ok,
        "dry_run": dry_run,
        "generated_at": _utc_now_iso(),
        "total_elapsed_sec": round(total_elapsed_sec, 3) if total_elapsed_sec is not None else None,
        "steps_planned": len(plan.get("workflows") or []) if isinstance(plan, dict) else None,
        "steps_executed": len(results),
        "steps_ok": steps_ok,
        "steps_failed": len(results) - steps_ok,
        "continued_step_count": len(continued_quality_degraded),
        "quality_degraded_steps": quality_degraded_steps,
        "continued_quality_degraded_steps": continued_quality_degraded,
        "failure_messages": list(failures),
        "business_status_zh": classification["business_status_zh"],
        "error_code": classification["error_code"],
        "error_category": classification["error_category"],
        "recommended_next_action": classification["recommended_next_action"],
        "recommended_next_commands": _recommended_commands_for_business(
            command=command,
            case_id=case_id,
            profile=profile,
        ),
        "recommended_artifacts": _recommended_artifacts(
            command=command,
            arts=arts,
            report_paths=report_paths,
            progress_relpath=progress_relpath,
        ),
        "ready_for_review": bool(
            ok
            and command in {"run", "refresh-reports"}
            and not continued_quality_degraded
        ),
        "ready_for_release": bool(ok and command == "refresh-reports" and not continued_quality_degraded),
        "artifacts": arts,
        "report_paths": report_paths,
        "reporting_config_source": reporting_src,
        "md_refresh": md_refresh,
    }


def _write_and_maybe_print_cli_result(
    args: argparse.Namespace,
    case_id: str,
    payload: dict[str, Any],
) -> None:
    if not _agent_json_summary_requested(args):
        return

    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    scoped_rel = str(
        artifacts.get("cli_result_scoped")
        or _scoped_cli_result_relpath(
            case_id,
            command=str(payload.get("command") or ""),
            profile=str(payload.get("profile") or ""),
            dry_run=bool(payload.get("dry_run")),
        )
    )
    scoped_path = WORKSPACE / scoped_rel
    scoped_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    scoped_path.write_text(encoded, encoding="utf-8")
    print(f"\n[cli] 机器摘要已写入: {scoped_rel}")

    if _should_refresh_shared_cli_result(
        command=str(payload.get("command") or ""),
        profile=str(payload.get("profile") or ""),
        dry_run=bool(payload.get("dry_run")),
    ):
        shared_rel = str(artifacts.get("cli_result") or _standard_smart_artifact_relpaths(case_id)["cli_result"])
        shared_path = WORKSPACE / shared_rel
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(encoded, encoding="utf-8")
        print(f"[cli] 共享 latest 已刷新: {shared_rel}")

    if getattr(args, "print_json_summary", False):
        print(json.dumps(payload, ensure_ascii=False), flush=True)


def _maybe_emit_run_reports(
    args: argparse.Namespace,
    case_slug: str,
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    failures: list[str],
) -> dict[str, Any] | None:
    """按 --report-level 生成跑后报告（默认 detailed）。返回 emit bundle 供 CLI 摘要。"""
    level = _resolve_run_report_level(args)
    if level == "none":
        return None
    if not results:
        return None
    try:
        from workflows.smart_run_reporting import emit_post_run_artifacts

        skip_univ = bool(getattr(args, "skip_universal_report", False))
        bundle = emit_post_run_artifacts(
            case_slug,
            args.profile,
            plan,
            results,
            failures,
            report_level=level,
            skip_universal=skip_univ,
            case_config_path=_optional_workspace_path(getattr(args, "case_config", None)),
            reporting_yaml=_optional_workspace_path(getattr(args, "smart_reporting_config", None)),
        )
        label_zh = {"detailed": "详细", "simple": "简单"}.get(level, level)
        print(f"\n=== 已自动生成{label_zh}报告（--report-level {level}）===\n")
        for label, rel in sorted((bundle.get("report_paths") or {}).items()):
            print(f"  · {label}: {rel}")
        idx = (bundle.get("steps") or {}).get("smart_index") or {}
        if idx.get("md"):
            print(f"\n  本轮总览 MD: {idx['md']}")
        if idx.get("html"):
            print(f"  本轮总览 HTML: {idx['html']}")
        if bundle.get("errors"):
            print("\n  （部分子步骤非零退出，已尽力继续；请查看上方 tail 或日志）")
            for e in bundle["errors"][:8]:
                print(f"    · {e}")
        print()
        return bundle
    except Exception as exc:
        print(f"\n【警告】自动生成报告失败（工作流结果仍已落盘）: {exc}\n")
        return None


def cmd_meta(args: argparse.Namespace) -> int:
    """供 Cursor / Agent / CI 发现的稳定 CLI 契约（JSON）。"""
    cat_path = str(Path(args.catalog).resolve()) if getattr(args, "catalog", None) and str(args.catalog).strip() else str(DEFAULT_CATALOG.resolve())
    meta = {
        "schema_version": "workflow_smart_cli_meta.v1",
        "_generator": "workflows.run_workflow_smart_zh",
        "cli_module": "workflows.run_workflow_smart_zh",
        "workspace_root_relative": "repository root (cd Hydrology; paths in artifacts are relative to workspace root)",
        "exit_codes": {
            "0": "success (all steps ok for run; refresh without blocking errors)",
            "1": "run: at least one workflow failed, or refresh/md 失败；仍可能已写 contracts",
            "2": "argparse / 前置校验失败（预留，当前多用 1）",
        },
        "environment": {
            "HYDRO_SMART_JSON_SUMMARY": "若设为 1/true/yes/on，等价于为 plan/run/menu/refresh-reports 开启 --json-summary",
        },
        "subcommands": [
            {
                "name": "meta",
                "requires_case_id": False,
                "purpose": "打印本 JSON；大模型应先调用以获知 flags 与产物路径",
            },
            {
                "name": "plan",
                "requires_case_id": True,
                "purpose": "生成 workflow_smart_plan.latest.json",
            },
            {
                "name": "run",
                "requires_case_id": True,
                "purpose": "按计划执行 WORKFLOW_REGISTRY；写 run_summary / progress ndjson",
            },
            {
                "name": "refresh-reports",
                "requires_case_id": True,
                "purpose": "仅刷新跑后报告链，依赖已有 workflow_smart_run_summary",
            },
            {"name": "list", "requires_case_id": False},
            {"name": "legend", "requires_case_id": False},
            {"name": "menu", "requires_case_id": True, "note": "交互式，不适合无人 Agent"},
        ],
        "agent_friendly_flags": {
            "plan_run_menu_refresh_shared": [
                "--json-summary：总是写入当前命令/模式的 scoped 摘要；正式 run --profile smart 还会刷新共享 latest",
                "--print-json-summary：额外向 stdout 打一行 JSON（便于管道）",
                "--smart-reporting-config PATH",
                "--case-config PATH",
                "--report-level detailed|simple|none",
                "--skip-universal-report",
            ],
            "run_only": ["--dry-run", "--continue-on-error", "-v", "--no-progress-file", "--progress-file PATH"],
        },
        "configs": {
            "workflow_catalog_zh": "Hydrology/configs/workflow_catalog_zh.yaml",
            "workflow_smart_reporting": "Hydrology/configs/workflow_smart_reporting.yaml",
            "case_yaml": "Hydrology/configs/<case_id>.yaml",
            "case_smart_reporting_override": "案例 YAML 顶层 smart_reporting: 合并入 workflow_smart_reporting",
        },
        "artifacts_relative": {
            "cli_result": "cases/<case_id>/contracts/workflow_smart_cli_result.latest.json",
            "cli_result_scoped": "cases/<case_id>/contracts/workflow_smart_cli_result.<command>.<profile>[.dry_run].latest.json",
            "run_summary": "cases/<case_id>/contracts/workflow_smart_run_summary.latest.json",
            "plan_json": "cases/<case_id>/contracts/workflow_smart_plan.latest.json",
            "progress_ndjson": "cases/<case_id>/contracts/workflow_smart_progress.latest.ndjson",
        },
        "catalog_path_resolved": cat_path,
        "invocation_examples": [
            "cd Hydrology && python3 -m workflows.run_workflow_smart_zh meta",
            "cd Hydrology && python3 -m workflows.run_workflow_smart_zh plan --case-id <case_id> --json-summary",
            "cd Hydrology && python3 -m workflows.run_workflow_smart_zh run --case-id <case_id> --profile smart --json-summary",
            "cd Hydrology && python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id <case_id> --report-level detailed --json-summary",
        ],
    }
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


def cmd_refresh_reports(args: argparse.Namespace) -> int:
    """从 contracts 中的 smart 摘要 + 计划重跑报告链；可选先重生成 D1/D2/D1–D4 MD（吃新策略）。"""
    from workflows.smart_run_reporting import (
        emit_post_run_artifacts,
        load_smart_run_context_from_contracts,
        regenerate_md_dimension_reports,
    )

    cid = args.case_id.strip()
    cc = _optional_workspace_path(getattr(args, "case_config", None))
    src = _optional_workspace_path(getattr(args, "smart_reporting_config", None))
    md_failed = False
    md_refresh_out: dict[str, Any] | None = None
    if getattr(args, "regenerate_md_reports", False):
        print("\n=== 重生成 Markdown（配置项 md_regeneration.workflow_keys）===\n")
        md_out = regenerate_md_dimension_reports(
            cid,
            case_config_path=cc,
            reporting_yaml=src,
        )
        md_refresh_out = md_out
        for st in md_out.get("steps", []):
            mark = "✓" if st.get("ok") else "✗"
            print(f"  {mark} {st.get('workflow_key')} — {st.get('label', '')}")
        for err in md_out.get("errors", []):
            print(f"  · {err}")
            md_failed = True
        print()

    level = _resolve_run_report_level(args)
    profile = ""
    plan: dict[str, Any] | None = None
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    bundle: dict[str, Any] | None = None

    if level == "none":
        print("（--report-level none：未刷新 E2E / final / 索引）\n")
        rc = 1 if md_failed else 0
        prog_p = _contracts_dir(cid) / "workflow_smart_progress.latest.ndjson"
        prog_rel = str(prog_p.relative_to(WORKSPACE)) if prog_p.is_file() else None
        payload = _build_cli_result_payload(
            command="refresh-reports",
            case_id=cid,
            profile="",
            exit_code=rc,
            ok=(rc == 0),
            results=results,
            failures=failures,
            total_elapsed_sec=None,
            plan=plan,
            report_bundle=bundle,
            dry_run=False,
            progress_relpath=prog_rel,
            md_refresh=md_refresh_out,
        )
        _print_business_next_steps(command="refresh-reports", case_id=cid, profile="")
        _write_and_maybe_print_cli_result(args, cid, payload)
        return rc

    try:
        profile, plan, results, failures = load_smart_run_context_from_contracts(
            cid,
            case_config_path=cc,
            reporting_yaml=src,
        )
    except FileNotFoundError as exc:
        print(f"【错误】{exc}\n")
        payload = _build_cli_result_payload(
            command="refresh-reports",
            case_id=cid,
            profile="",
            exit_code=1,
            ok=False,
            results=[],
            failures=[str(exc)],
            total_elapsed_sec=None,
            plan=None,
            report_bundle=None,
            dry_run=False,
            progress_relpath=None,
            md_refresh=md_refresh_out,
        )
        _write_and_maybe_print_cli_result(args, cid, payload)
        return 1
    except ValueError as exc:
        print(f"【错误】{exc}\n")
        payload = _build_cli_result_payload(
            command="refresh-reports",
            case_id=cid,
            profile="",
            exit_code=1,
            ok=False,
            results=[],
            failures=[str(exc)],
            total_elapsed_sec=None,
            plan=None,
            report_bundle=None,
            dry_run=False,
            progress_relpath=None,
            md_refresh=md_refresh_out,
        )
        _write_and_maybe_print_cli_result(args, cid, payload)
        return 1

    skip_univ = bool(getattr(args, "skip_universal_report", False))
    bundle = emit_post_run_artifacts(
        cid,
        profile,
        plan,
        results,
        failures,
        report_level=level,
        skip_universal=skip_univ,
        case_config_path=cc,
        reporting_yaml=src,
    )
    label_zh = {"detailed": "详细", "simple": "简单"}.get(level, level)
    print(f"\n=== 已刷新{label_zh}报告（refresh-reports --report-level {level}）===\n")
    for label, rel in sorted((bundle.get("report_paths") or {}).items()):
        print(f"  · {label}: {rel}")
    idx = (bundle.get("steps") or {}).get("smart_index") or {}
    if idx.get("md"):
        print(f"\n  本轮总览 MD: {idx['md']}")
    if idx.get("html"):
        print(f"  本轮总览 HTML: {idx['html']}")
    if bundle.get("errors"):
        print("\n  （部分子步骤非零退出，已尽力继续）")
        for e in bundle["errors"][:8]:
            print(f"    · {e}")
    print()
    rc = 1 if (bundle.get("errors") or md_failed) else 0
    prog_p = _contracts_dir(cid) / "workflow_smart_progress.latest.ndjson"
    prog_rel = str(prog_p.relative_to(WORKSPACE)) if prog_p.is_file() else None
    payload = _build_cli_result_payload(
        command="refresh-reports",
        case_id=cid,
        profile=profile,
        exit_code=rc,
        ok=(rc == 0),
        results=results,
        failures=list(failures),
        total_elapsed_sec=None,
        plan=plan,
        report_bundle=bundle,
        dry_run=False,
        progress_relpath=prog_rel,
        md_refresh=md_refresh_out,
    )
    _write_and_maybe_print_cli_result(args, cid, payload)
    return rc


def _print_run_footer(results: list[dict[str, Any]], *, failures: list[str]) -> None:
    print("\n" + "═" * 60)
    print("步骤结果一览")
    print("═" * 60)
    for i, r in enumerate(results, start=1):
        ok = r.get("ok")
        key = r.get("workflow_key", "")
        es = r.get("elapsed_sec")
        es_s = f"{es:.1f}s" if isinstance(es, (int, float)) else "—"
        mark = "OK " if ok else "FAIL"
        err = (r.get("error") or "")[:72]
        extra = f"  |  {err}" if err and not ok else ""
        print(f"  {i:>2}. [{mark}] {key:<22}  {es_s:>8}{extra}")
    print("═" * 60)
    if failures:
        print("\n失败明细（共 {} 条）:".format(len(failures)))
        for line in failures:
            print(f"  · {line}")


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_CATALOG
    if not p.is_file():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _coerce_catalog_string_list(
    raw: Any,
    *,
    field_name: str,
    normalizer: callable | None = None,
) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        raise ValueError(f"workflow catalog 字段 {field_name} 必须是字符串或字符串列表")

    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        out.append(normalizer(text) if normalizer else text)
    return out


def _coerce_continue_on_outcome_statuses(raw: Any) -> list[str]:
    statuses = _coerce_catalog_string_list(
        raw,
        field_name="continue_on_outcome_statuses",
        normalizer=_normalize_outcome_status,
    )
    invalid_statuses = [status for status in statuses if status not in ALLOWED_OUTCOME_STATUSES]
    if invalid_statuses:
        invalid_list = ", ".join(sorted(set(invalid_statuses)))
        raise ValueError(
            "workflow catalog 字段 continue_on_outcome_statuses 包含未知状态: "
            f"{invalid_list}"
        )
    return statuses


def _workflow_meta_from_catalog(catalog: dict[str, Any], key: str) -> dict[str, Any]:
    w = (catalog.get("workflows") or {}).get(key) or {}
    defaults = catalog.get("defaults") or {}
    raw_continue_on_outcome_statuses = (
        w.get("continue_on_outcome_statuses")
        if "continue_on_outcome_statuses" in w
        else defaults.get("continue_on_outcome_statuses")
    )
    continue_on_outcome_statuses = _coerce_continue_on_outcome_statuses(
        raw_continue_on_outcome_statuses
    )
    return {
        "display_zh": w.get("display_zh") or key,
        "category_zh": w.get("category_zh") or "其他",
        "scopes": w.get("scopes") or defaults.get("scopes") or ["modeling"],
        "priority": int(w.get("priority", defaults.get("priority", 100))),
        "auto_select": bool(w.get("auto_select", defaults.get("auto_select", True))),
        "external": bool(w.get("external", False)),
        "long_running": bool(w.get("long_running", False)),
        "run_after": _coerce_catalog_string_list(
            w.get("run_after"),
            field_name="run_after",
        ),
        "continue_on_outcome_statuses": continue_on_outcome_statuses,
        "smart_relax_external": bool(
            w.get("smart_relax_external", defaults.get("smart_relax_external", False))
        ),
        "smart_require_contract": str(
            w.get("smart_require_contract") or defaults.get("smart_require_contract") or ""
        ).strip(),
    }


def _is_alias_key(key: str) -> bool:
    spec = WORKFLOW_REGISTRY.get(key) or {}
    return bool(spec.get("alias_of"))


def _is_external_key(key: str) -> bool:
    spec = WORKFLOW_REGISTRY.get(key) or {}
    return "external_script" in spec


def run_feasibility_export(case_id: str, rules_path: Path) -> dict[str, Any]:
    from export_case_workflow_feasibility import run_export

    return run_export(case_id.strip(), rules_path)


def run_modeling_hints(case_id: str, config_path: Path, rules_path: Path) -> dict[str, Any]:
    from export_case_modeling_hints import derive_modeling_hints

    return derive_modeling_hints(case_id.strip(), config_path.resolve(), rules_path.resolve())


def heuristic_suggestions(case_id: str, feasible: set[str], hints_payload: dict[str, Any]) -> list[str]:
    """当 Graphify 未给出 suggested_workflows 时，用语义与就绪度做保守推荐。"""
    h = hints_payload.get("hints") or {}
    if h.get("suggested_workflows"):
        return [str(x).strip() for x in h["suggested_workflows"] if str(x).strip()]

    project_type = str(h.get("project_type") or "").strip().lower()
    out: list[str] = []
    if "data_audit" in feasible:
        out.append("data_audit")
    if "model" in feasible:
        out.append("model")
    if "section_analysis" in feasible:
        out.append("section_analysis")
    if "calibrate" in feasible:
        out.append("calibrate")
    if "hydro_report" in feasible:
        out.append("hydro_report")
    if "hyd_report" in feasible:
        out.append("hyd_report")
    if "coupled" in feasible:
        out.append("coupled")
    if "hyd_sim" in feasible and (_contracts_dir(case_id) / "parameter_governance.latest.json").is_file():
        out.append("hyd_sim")
    if "d1d4" in feasible:
        out.append("d1d4")
    # 梯级/水网类：控制链放在建模启发之后
    if "cascade" in feasible and ("cascade" in project_type or "hydro" in project_type):
        out.append("cascade")
    # 去重保序
    seen: set[str] = set()
    ordered: list[str] = []
    for k in out:
        if k in seen:
            continue
        seen.add(k)
        ordered.append(k)
    return ordered


def _priority_key(catalog: dict[str, Any], key: str) -> tuple[int, str]:
    return (_workflow_meta_from_catalog(catalog, key)["priority"], key)


def _topo_sort_selected(keys: set[str], catalog: dict[str, Any]) -> tuple[list[str], list[str]]:
    """按 catalog run_after 拓扑排序；成环或无法排全时回退为 priority 排序。"""
    nodes = list(keys)
    succ: dict[str, set[str]] = {n: set() for n in nodes}
    pred_count: dict[str, int] = {n: 0 for n in nodes}
    for k in nodes:
        for dep in _workflow_meta_from_catalog(catalog, k).get("run_after") or []:
            if dep in keys:
                succ[dep].add(k)
                pred_count[k] = pred_count.get(k, 0) + 1
    roots = sorted([n for n in nodes if pred_count.get(n, 0) == 0], key=lambda x: _priority_key(catalog, x))
    out: list[str] = []
    q: deque[str] = deque(roots)
    while q:
        u = q.popleft()
        out.append(u)
        for v in sorted(succ[u], key=lambda x: _priority_key(catalog, x)):
            pred_count[v] -= 1
            if pred_count[v] == 0:
                q.append(v)
    warnings: list[str] = []
    if len(out) != len(keys):
        warnings.append("run_after 存在环或未覆盖全部节点，已回退为 priority 字典序")
        out = sorted(keys, key=lambda x: _priority_key(catalog, x))
    return out, warnings


def build_auto_plan(
    case_id: str,
    *,
    catalog: dict[str, Any],
    feasibility: dict[str, Any],
    hints_payload: dict[str, Any],
    profile: str,
    include_external: bool,
    include_long_running: bool,
    max_workflows: int,
    allow_registry_only: bool = False,
    restrict_workflow_keys: set[str] | None = None,
) -> dict[str, Any]:
    rows = feasibility.get("workflows") or []
    allowed_keys = set(restrict_workflow_keys or set()) if restrict_workflow_keys else None
    feasible: set[str] = set()
    registry_only_keys: list[str] = []
    data_ok_count = 0
    for r in rows:
        t = r.get("tier")
        k = str(r.get("key") or "")
        if not k:
            continue
        if allowed_keys is not None and k not in allowed_keys:
            continue
        if t == "data_ok":
            feasible.add(k)
            data_ok_count += 1
        elif allow_registry_only and t == "registry_only":
            feasible.add(k)
            registry_only_keys.append(k)

    hints = hints_payload.get("hints") or {}
    raw_suggested = [str(x).strip() for x in (hints.get("suggested_workflows") or []) if str(x).strip()]
    suggested = list(raw_suggested)
    heuristic_used = not bool(raw_suggested)
    if not suggested:
        suggested = heuristic_suggestions(case_id, feasible, hints_payload)

    profile = (profile or "smart").strip().lower()

    def scope_ok(key: str) -> bool:
        meta = _workflow_meta_from_catalog(catalog, key)
        scopes = set(meta.get("scopes") or [])
        if profile == "full":
            return True
        if profile in ("smart", "modeling"):
            if "control" in scopes and "modeling" not in scopes:
                return False
            return bool(scopes & {"modeling", "data", "evaluation"})
        if profile == "control":
            return "control" in scopes
        if profile == "evaluation":
            return "evaluation" in scopes
        return True

    def selection_allowed(key: str, *, dependency_mode: bool) -> bool:
        if key not in WORKFLOW_REGISTRY or _is_alias_key(key):
            return False
        if key not in feasible:
            return False
        if not scope_ok(key):
            return False
        meta = _workflow_meta_from_catalog(catalog, key)
        if not dependency_mode:
            if profile == "full":
                if not meta["auto_select"] and meta["long_running"] and not include_long_running:
                    return False
            elif not meta["auto_select"]:
                return False
        if meta["external"] or _is_external_key(key):
            if not include_external:
                req = meta.get("smart_require_contract") or ""
                if not (
                    profile == "smart"
                    and meta.get("smart_relax_external")
                    and req
                    and (_contracts_dir(case_id) / req).is_file()
                ):
                    return False
        if meta["long_running"] and not include_long_running:
            return False
        return True

    selected: set[str] = set()

    def try_select(key: str, *, dependency_mode: bool) -> None:
        if selection_allowed(key, dependency_mode=dependency_mode):
            selected.add(key)

    for key in suggested:
        try_select(key, dependency_mode=True)

    for key in sorted(feasible, key=lambda k: _priority_key(catalog, k)):
        if len(selected) >= max_workflows:
            break
        try_select(key, dependency_mode=False)

    dependency_warnings: list[str] = []
    pending: deque[str] = deque(sorted(selected, key=lambda k: _priority_key(catalog, k)))
    while pending:
        key = pending.popleft()
        for dep in _workflow_meta_from_catalog(catalog, key).get("run_after") or []:
            if dep in selected:
                continue
            if selection_allowed(dep, dependency_mode=True):
                selected.add(dep)
                pending.append(dep)
            else:
                dependency_warnings.append(f"{key} 缺少可纳入计划的前置依赖 {dep}")

    unsatisfied_dependency_warnings: list[str] = []
    changed = True
    while changed:
        changed = False
        for key in sorted(list(selected), key=lambda k: _priority_key(catalog, k), reverse=True):
            missing = [dep for dep in (_workflow_meta_from_catalog(catalog, key).get("run_after") or []) if dep not in selected]
            if not missing:
                continue
            selected.remove(key)
            unsatisfied_dependency_warnings.append(
                f"{key} 因缺少前置依赖 {', '.join(missing)} 已从计划移除"
            )
            changed = True

    ordered, topo_warnings = _topo_sort_selected(selected, catalog)
    ordered = ordered[:max_workflows]

    plan_rows: list[dict[str, Any]] = []
    for key in ordered:
        meta = _workflow_meta_from_catalog(catalog, key)
        tier = next((r.get("tier") for r in rows if r.get("key") == key), "")
        plan_rows.append(
            {
                "workflow_key": key,
                "display_zh": meta["display_zh"],
                "category_zh": meta["category_zh"],
                "tier": tier,
                "priority": meta["priority"],
                "scopes": meta["scopes"],
                "run_after": meta.get("run_after") or [],
                "external": meta["external"] or _is_external_key(key),
            }
        )

    notes = [
        "智能选流：候选 = tier∈{data_ok}（可加 --allow-registry-only 含 registry_only）∩ profile 过滤 ∩ auto_select 规则；"
        "建模提示优先入集，并自动补齐 run_after 前置依赖，再按 catalog.run_after 拓扑排序，最后截断 max-workflows。",
        "外部脚本默认跳过；catalog 中 smart_relax_external + smart_require_contract 且契约文件存在时，profile=smart 仍会纳入（如 hyd_sim）。",
        "长时任务（improve/pipeline/DL）仍默认跳过，使用 --include-long-running；其它外部脚本用 --include-external。",
        "run 结束后默认 --report-level detailed：完整 E2E 看板 + 验证 MD/JSON + final_report + 通用 HTML + 索引；"
        "--report-level simple / --simple-report 仅看板与索引；--report-level none / --no-reports 不生成。"
        "detailed 下可用 --skip-universal-report 跳过通用仿真 HTML。",
        "plan 默认写 workflow_smart_plan_report；--no-plan-reports 或与上述 none 类开关一致时不写计划说明 MD/HTML。",
    ]
    if allowed_keys is not None:
        notes.append(f"已应用工作流白名单约束（{len(allowed_keys)} 个键）。")
    if dependency_warnings:
        notes.extend(sorted(set(dependency_warnings)))
    if unsatisfied_dependency_warnings:
        notes.extend(sorted(set(unsatisfied_dependency_warnings)))
    if topo_warnings:
        notes.extend(topo_warnings)
    if allow_registry_only and registry_only_keys:
        notes.append(f"registry_only 已纳入候选（共 {len(registry_only_keys)} 个键，详见 feasibility 矩阵）。")

    return {
        "case_id": case_id.strip(),
        "profile": profile,
        "allow_registry_only": allow_registry_only,
        "feasible_eligible_count": len(feasible),
        "feasible_data_ok_count": data_ok_count,
        "registry_only_keys_included": registry_only_keys,
        "suggested_from_hints": raw_suggested,
        "suggested_effective": suggested,
        "graphify_supports_auto": bool(hints.get("graphify_supports_auto_modeling_hints")),
        "heuristic_used": heuristic_used,
        "topo_warnings": topo_warnings,
        "workflows": plan_rows,
        "notes_zh": notes,
    }


def print_plan_table(plan: dict[str, Any]) -> None:
    print("\n=== 工作流执行计划（中文）===\n")
    print(f"案例: {plan['case_id']}  |  profile: {plan['profile']}")
    print(
        f"候选池: data_ok={plan.get('feasible_data_ok_count', 0)}，"
        f"合计 eligible={plan.get('feasible_eligible_count', 0)}"
        + ("（含 registry_only）" if plan.get("allow_registry_only") else "")
    )
    if plan.get("topo_warnings"):
        for w in plan["topo_warnings"]:
            print(f"  [拓扑] {w}")
    if plan.get("heuristic_used"):
        print(f"启发式推荐（建模提示为空时按案例类型+data_ok）: {plan.get('suggested_effective') or []}")
    else:
        print(f"建模提示优先: {plan.get('suggested_from_hints') or []}")
    print(f"Graphify 自动提示: {'是' if plan['graphify_supports_auto'] else '否'}")
    print()
    for i, row in enumerate(plan.get("workflows") or [], start=1):
        ext = " [外部脚本]" if row.get("external") else ""
        print(
            f"  {i:2}. [{row['workflow_key']}] {row['display_zh']}{ext}\n"
            f"      分类: {row['category_zh']} | 优先级: {row['priority']} | tier: {row.get('tier')}"
        )
    print("\n--- 说明 ---")
    for line in plan.get("notes_zh") or []:
        print(f"  · {line}")
    print()


def print_scope_legend(catalog: dict[str, Any]) -> None:
    scopes = catalog.get("e2e_scopes_zh") or {}
    profiles = catalog.get("profiles_help_zh") or {}
    print("\n=== 端到端范围（中文）===\n")
    for k, v in scopes.items():
        print(f"  · {k}: {v}")
    print("\n=== profile 说明 ===\n")
    for k, v in profiles.items():
        print(f"  · {k}: {v}")
    print()


def list_workflows_zh(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """合并注册表 description 与中文目录。"""
    cat = catalog or load_catalog()
    out: list[dict[str, Any]] = []
    for item in list_workflows(include_hidden=False):
        key = item["name"]
        meta = _workflow_meta_from_catalog(cat, key)
        out.append(
            {
                "name": key,
                "description": item["description"],
                "display_zh": meta["display_zh"],
                "category_zh": meta["category_zh"],
                "scopes": meta["scopes"],
                "args": item.get("args"),
            }
        )
    return out


def _save_plan_json(case_id: str, plan: dict[str, Any]) -> Path:
    path = _contracts_dir(case_id) / "workflow_smart_plan.latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **plan,
        "_auto_generated": True,
        "generator": "workflows.run_workflow_smart_zh",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _save_run_summary(
    case_id: str,
    profile: str,
    results: list[dict[str, Any]],
    failures: list[str],
) -> Path:
    path = _contracts_dir(case_id) / "workflow_smart_run_summary.latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    continued_degraded_steps = [
        step
        for step in results
        if bool(step.get("continued"))
        and str(step.get("outcome_status") or "") in QUALITY_DEGRADED_OUTCOME_STATUSES
    ]
    has_non_blocking_degraded = bool(continued_degraded_steps)
    payload = {
        "case_id": case_id.strip(),
        "profile": profile,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": not failures and not has_non_blocking_degraded,
        "has_non_blocking_degraded": has_non_blocking_degraded,
        "continued_degraded_step_count": len(continued_degraded_steps),
        "continued_degraded_steps": continued_degraded_steps,
        "failure_count": len(failures),
        "steps": results,
        "failure_messages": failures,
        "_auto_generated": True,
        "generator": "workflows.run_workflow_smart_zh",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def cmd_plan(args: argparse.Namespace) -> int:
    t0 = time.monotonic()
    catalog = load_catalog(Path(args.catalog) if args.catalog else None)
    restrict_workflow_keys = _parse_restrict_workflow_keys(
        getattr(args, "restrict_workflow_keys", None) or os.environ.get("HYDRO_SMART_RESTRICT_WORKFLOW_KEYS")
    )
    rules = Path(args.rules) if args.rules else DEFAULT_RULES
    if not rules.is_file():
        rules = WORKSPACE / args.rules if args.rules else DEFAULT_RULES
    loop_cfg = Path(args.config) if args.config else DEFAULT_LOOP
    if not loop_cfg.is_file():
        loop_cfg = WORKSPACE / args.config if args.config else DEFAULT_LOOP

    feasibility = run_feasibility_export(args.case_id, rules)
    hints_payload = run_modeling_hints(args.case_id, loop_cfg, rules)
    plan = build_auto_plan(
        args.case_id,
        catalog=catalog,
        feasibility=feasibility,
        hints_payload=hints_payload,
        profile=args.profile,
        include_external=args.include_external,
        include_long_running=args.include_long_running,
        max_workflows=args.max_workflows,
        allow_registry_only=args.allow_registry_only,
        restrict_workflow_keys=restrict_workflow_keys,
    )
    print_scope_legend(catalog)
    print_plan_table(plan)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not args.no_save:
        p = _save_plan_json(args.case_id, plan)
        print(f"已写入: {p.relative_to(WORKSPACE)}\n")
        if _resolve_plan_report_level(args) != "none":
            try:
                from workflows.smart_run_reporting import (
                    load_workflow_smart_reporting_config,
                    write_plan_index,
                )

                rep_cfg = load_workflow_smart_reporting_config(
                    args.case_id.strip(),
                    config_path=_optional_workspace_path(getattr(args, "case_config", None)),
                    reporting_yaml=_optional_workspace_path(getattr(args, "smart_reporting_config", None)),
                )
                md_p, h_p = write_plan_index(
                    args.case_id.strip(), args.profile, plan, reporting_cfg=rep_cfg
                )
                print(f"计划说明 MD: {md_p.relative_to(WORKSPACE)}")
                print(f"计划说明 HTML: {h_p.relative_to(WORKSPACE)}\n")
            except Exception as exc:
                print(f"【警告】计划说明 MD/HTML 生成失败: {exc}\n")
    _print_business_next_steps(command="plan", case_id=args.case_id, profile=args.profile)
    if _agent_json_summary_requested(args):
        elapsed = time.monotonic() - t0
        payload = _build_cli_result_payload(
            command="plan",
            case_id=args.case_id,
            profile=args.profile,
            exit_code=0,
            ok=True,
            results=[],
            failures=[],
            total_elapsed_sec=elapsed,
            plan=plan,
            report_bundle=None,
            dry_run=False,
            progress_relpath=None,
            md_refresh=None,
        )
        _write_and_maybe_print_cli_result(args, args.case_id, payload)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    catalog = load_catalog(Path(args.catalog) if args.catalog else None)
    restrict_workflow_keys = _parse_restrict_workflow_keys(
        getattr(args, "restrict_workflow_keys", None) or os.environ.get("HYDRO_SMART_RESTRICT_WORKFLOW_KEYS")
    )
    rules = Path(args.rules) if args.rules else DEFAULT_RULES
    if not rules.is_file():
        rules = WORKSPACE / args.rules if args.rules else DEFAULT_RULES
    loop_cfg = Path(args.config) if args.config else DEFAULT_LOOP
    if not loop_cfg.is_file():
        loop_cfg = WORKSPACE / args.config if args.config else DEFAULT_LOOP
    feasibility = run_feasibility_export(args.case_id, rules)
    hints_payload = run_modeling_hints(args.case_id, loop_cfg, rules)
    plan = build_auto_plan(
        args.case_id,
        catalog=catalog,
        feasibility=feasibility,
        hints_payload=hints_payload,
        profile=args.profile,
        include_external=args.include_external,
        include_long_running=args.include_long_running,
        max_workflows=args.max_workflows,
        allow_registry_only=args.allow_registry_only,
        restrict_workflow_keys=restrict_workflow_keys,
    )
    if not args.no_save:
        _save_plan_json(args.case_id, plan)

    print_plan_table(plan)
    if args.dry_run:
        print("(--dry-run 已指定，不执行 run_workflow)\n")
        _print_business_next_steps(command="run", case_id=args.case_id, profile=args.profile)
        if _agent_json_summary_requested(args):
            payload = _build_cli_result_payload(
                command="run",
                case_id=args.case_id,
                profile=args.profile,
                exit_code=0,
                ok=True,
                results=[],
                failures=[],
                total_elapsed_sec=0.0,
                plan=plan,
                report_bundle=None,
                dry_run=True,
                progress_relpath=None,
                md_refresh=None,
            )
            _write_and_maybe_print_cli_result(args, args.case_id, payload)
        return 0

    rows = plan.get("workflows") or []
    n = len(rows)
    case_slug = args.case_id.strip()

    progress_path: Path | None = None
    if not getattr(args, "no_progress_file", False):
        rel = (getattr(args, "progress_file", None) or "").strip()
        progress_path = Path(rel) if rel else _contracts_dir(case_slug) / "workflow_smart_progress.latest.ndjson"
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text("", encoding="utf-8")

    if args.continue_on_error:
        print(
            "\n【警告】已启用 --continue-on-error：某步失败后仍会执行后续步骤；"
            "若后续依赖失败步的产物，结果可能不完整或误导。默认行为为遇错即停（不加本参数）。\n"
        )
    else:
        print("\n（遇错即停：任一步失败将中止，并写入已执行步骤的摘要与进度。加 --continue-on-error 可改为继续。）\n")

    verbose = bool(getattr(args, "verbose", False))
    run_t0 = time.monotonic()
    if progress_path is not None:
        _append_ndjson(
            progress_path,
            {
                "event": "run_begin",
                "ts": _utc_now_iso(),
                "case_id": case_slug,
                "profile": args.profile,
                "total_steps": n,
                "continue_on_error": bool(args.continue_on_error),
            },
        )

    failures: list[str] = []
    results: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        key = row["workflow_key"]
        display = row.get("display_zh") or key
        workflow_meta = _workflow_meta_from_catalog(catalog, key)
        continueable_outcome_statuses = set(workflow_meta.get("continue_on_outcome_statuses") or [])
        step_t0 = time.monotonic()
        elapsed_so_far = time.monotonic() - run_t0

        if verbose:
            print(f"    [verbose] 开始 {_utc_now_iso()}  step={i}/{n}")
        print(f"\n{'─' * 60}")
        print(f"  [{i:>2}/{n}]  {key}  —  {display}")
        print(f"      自启动以来: {_format_elapsed(elapsed_so_far)}")
        print(f"{'─' * 60}\n")

        if progress_path is not None:
            _append_ndjson(
                progress_path,
                {
                    "event": "step_begin",
                    "ts": _utc_now_iso(),
                    "case_id": case_slug,
                    "step": i,
                    "total": n,
                    "workflow_key": key,
                    "display_zh": display,
                },
            )

        step_started_wall = _utc_now_iso()
        try:
            workflow_result = run_workflow(key, case_id=case_slug)
            result_summary = _summarize_workflow_result(workflow_result)
            step_elapsed = time.monotonic() - step_t0
            step_ended_wall = _utc_now_iso()
            step_record = {
                "workflow_key": key,
                "ok": result_summary["ok"],
                "error": "",
                "elapsed_sec": round(step_elapsed, 2),
                "started_at": step_started_wall,
                "ended_at": step_ended_wall,
                "outcome_status": result_summary["outcome_status"],
                "quality_gate_passed": result_summary["quality_gate_passed"],
                "quality_reason": result_summary["quality_reason"],
                "continued": False,
                "continue_reason": None,
            }
            if isinstance(workflow_result, dict):
                if workflow_result.get("business_status_zh"):
                    step_record["business_status_zh"] = str(workflow_result.get("business_status_zh"))
                if workflow_result.get("recommended_next_action"):
                    step_record["recommended_next_action"] = str(workflow_result.get("recommended_next_action"))
                artifact_guidance = workflow_result.get("artifact_guidance")
                if isinstance(artifact_guidance, list):
                    step_record["artifact_guidance"] = artifact_guidance
            progress_record = {
                "event": "step_end",
                "ts": _utc_now_iso(),
                "case_id": case_slug,
                "step": i,
                "total": n,
                "workflow_key": key,
                "ok": result_summary["ok"],
                "elapsed_sec": round(step_elapsed, 3),
                "outcome_status": result_summary["outcome_status"],
            }
            if result_summary["quality_gate_passed"] is not None:
                progress_record["quality_gate_passed"] = result_summary["quality_gate_passed"]
            if result_summary["quality_reason"]:
                progress_record["quality_reason"] = result_summary["quality_reason"]
            outcome_status = str(result_summary.get("outcome_status") or "")
            is_continueable_degraded = outcome_status in continueable_outcome_statuses
            if result_summary["ok"]:
                print(f"    ✓ 完成: {key}  （本步 {_format_elapsed(step_elapsed)}）")
            else:
                msg = _build_workflow_failure_message(key, result_summary)
                is_non_blocking_failure = bool(is_continueable_degraded and not args.continue_on_error)
                if not is_non_blocking_failure:
                    failures.append(msg)
                step_record["error"] = msg[:800]
                progress_record["error"] = msg[:500]
                print(f"    ✗ 未达标: {msg}  （本步 {_format_elapsed(step_elapsed)}）")
            results.append(step_record)
            if progress_path is not None:
                _append_ndjson(progress_path, progress_record)
            if not result_summary["ok"]:
                if args.continue_on_error:
                    step_record["continued"] = True
                    step_record["continue_reason"] = "continue_on_error"
                    print("    → 因 --continue-on-error，继续下一步。\n")
                elif is_continueable_degraded:
                    step_record["continued"] = True
                    step_record["continue_reason"] = "catalog_non_blocking_status"
                    print(
                        "    → 当前步骤未达标，但目录已声明该状态可继续；"
                        f"继续下一步（outcome_status={outcome_status}）。\n"
                    )
                else:
                    total_elapsed = time.monotonic() - run_t0
                    ok_n = sum(1 for r in results if r.get("ok"))
                    print(f"\n已中止：总耗时 {_format_elapsed(total_elapsed)}，已成功 {ok_n} 步后失败。\n")
                    _print_run_footer(results, failures=failures)
                    if not args.no_save:
                        sp = _save_run_summary(args.case_id, args.profile, results, failures)
                        print(f"执行摘要已写入: {sp.relative_to(WORKSPACE)}")
                        if progress_path is not None:
                            print(f"进度 NDJSON: {progress_path.relative_to(WORKSPACE)}")
                    if progress_path is not None:
                        _append_ndjson(
                            progress_path,
                            {
                                "event": "run_end",
                                "ts": _utc_now_iso(),
                                "case_id": case_slug,
                                "ok": False,
                                "failure_count": len(failures),
                                "total_elapsed_sec": round(time.monotonic() - run_t0, 3),
                                "aborted": True,
                            },
                        )
                    bundle = _maybe_emit_run_reports(args, case_slug, plan, results, failures)
                    prog_rel = (
                        str(progress_path.relative_to(WORKSPACE))
                        if progress_path is not None and progress_path.is_file()
                        else None
                    )
                    payload = _build_cli_result_payload(
                        command="run",
                        case_id=args.case_id,
                        profile=args.profile,
                        exit_code=1,
                        ok=False,
                        results=results,
                        failures=failures,
                        total_elapsed_sec=time.monotonic() - run_t0,
                        plan=plan,
                        report_bundle=bundle,
                        dry_run=False,
                        progress_relpath=prog_rel,
                        md_refresh=None,
                    )
                    _print_cli_result_guidance(payload)
                    _write_and_maybe_print_cli_result(args, args.case_id, payload)
                    print()
                    return 1
        except Exception as exc:
            step_elapsed = time.monotonic() - step_t0
            step_ended_wall = _utc_now_iso()
            msg = f"{key}: {exc}"
            failures.append(msg)
            print(f"    ✗ 失败: {msg}  （本步 {_format_elapsed(step_elapsed)}）")
            results.append(
                {
                    "workflow_key": key,
                    "ok": False,
                    "error": str(exc)[:800],
                    "elapsed_sec": round(step_elapsed, 2),
                    "started_at": step_started_wall,
                    "ended_at": step_ended_wall,
                    "outcome_status": "error",
                    "quality_gate_passed": None,
                    "quality_reason": None,
                }
            )
            if progress_path is not None:
                _append_ndjson(
                    progress_path,
                    {
                        "event": "step_end",
                        "ts": _utc_now_iso(),
                        "case_id": case_slug,
                        "step": i,
                        "total": n,
                        "workflow_key": key,
                        "ok": False,
                        "elapsed_sec": round(step_elapsed, 3),
                        "outcome_status": "error",
                        "error": str(exc)[:500],
                    },
                )
            if args.continue_on_error:
                print("    → 因 --continue-on-error，继续下一步。\n")
            else:
                total_elapsed = time.monotonic() - run_t0
                ok_n = sum(1 for r in results if r.get("ok"))
                print(f"\n已中止：总耗时 {_format_elapsed(total_elapsed)}，已成功 {ok_n} 步后失败。\n")
                _print_run_footer(results, failures=failures)
                if not args.no_save:
                    sp = _save_run_summary(args.case_id, args.profile, results, failures)
                    print(f"执行摘要已写入: {sp.relative_to(WORKSPACE)}")
                    if progress_path is not None:
                        print(f"进度 NDJSON: {progress_path.relative_to(WORKSPACE)}")
                if progress_path is not None:
                    _append_ndjson(
                        progress_path,
                        {
                            "event": "run_end",
                            "ts": _utc_now_iso(),
                            "case_id": case_slug,
                            "ok": False,
                            "failure_count": len(failures),
                            "total_elapsed_sec": round(time.monotonic() - run_t0, 3),
                            "aborted": True,
                        },
                    )
                bundle = _maybe_emit_run_reports(args, case_slug, plan, results, failures)
                prog_rel = (
                    str(progress_path.relative_to(WORKSPACE))
                    if progress_path is not None and progress_path.is_file()
                    else None
                )
                payload = _build_cli_result_payload(
                    command="run",
                    case_id=args.case_id,
                    profile=args.profile,
                    exit_code=1,
                    ok=False,
                    results=results,
                    failures=failures,
                    total_elapsed_sec=time.monotonic() - run_t0,
                    plan=plan,
                    report_bundle=bundle,
                    dry_run=False,
                    progress_relpath=prog_rel,
                    md_refresh=None,
                )
                _print_cli_result_guidance(payload)
                _write_and_maybe_print_cli_result(args, args.case_id, payload)
                print()
                return 1

    total_elapsed = time.monotonic() - run_t0
    print(f"\n全部完成：共 {n} 步，总耗时 {_format_elapsed(total_elapsed)}。\n")
    _print_run_footer(results, failures=failures)

    if not args.no_save:
        sp = _save_run_summary(args.case_id, args.profile, results, failures)
        print(f"执行摘要已写入: {sp.relative_to(WORKSPACE)}")
        if progress_path is not None:
            print(f"进度 NDJSON: {progress_path.relative_to(WORKSPACE)}")
    if progress_path is not None:
        _append_ndjson(
            progress_path,
            {
                "event": "run_end",
                "ts": _utc_now_iso(),
                "case_id": case_slug,
                "ok": not failures,
                "failure_count": len(failures),
                "total_elapsed_sec": round(total_elapsed, 3),
            },
        )
    bundle = _maybe_emit_run_reports(args, case_slug, plan, results, failures)
    prog_rel = (
        str(progress_path.relative_to(WORKSPACE))
        if progress_path is not None and progress_path.is_file()
        else None
    )
    exit_code = 1 if failures else 0
    payload = _build_cli_result_payload(
        command="run",
        case_id=args.case_id,
        profile=args.profile,
        exit_code=exit_code,
        ok=(exit_code == 0),
        results=results,
        failures=failures,
        total_elapsed_sec=total_elapsed,
        plan=plan,
        report_bundle=bundle,
        dry_run=False,
        progress_relpath=prog_rel,
        md_refresh=None,
    )
    _print_cli_result_guidance(payload)
    _write_and_maybe_print_cli_result(args, args.case_id, payload)
    print()
    return exit_code


def cmd_menu(args: argparse.Namespace) -> int:
    catalog = load_catalog(Path(args.catalog) if args.catalog else None)
    print_scope_legend(catalog)
    print(
        "请选择端到端类型（输入数字回车）:\n"
        "  1 — 智能选流（默认：数据就绪 + 提示/启发式，跳过外部与长任务）\n"
        "  2 — 仿真建模 profile\n"
        "  3 — 控制调度 profile\n"
        "  4 — 评价审计 profile\n"
        "  5 — 全量 data_ok 候选（仍受 max-workflows 限制）\n"
        "  6 — 仅打印注册表中文目录（不跑）\n"
    )
    choice = (input("> ").strip() or "1").lower()
    profile_map = {"1": "smart", "2": "modeling", "3": "control", "4": "evaluation", "5": "full"}
    if choice == "6":
        for row in list_workflows_zh(catalog):
            print(f"  [{row['name']}] {row['display_zh']} — {row['description'][:60]}...")
        return 0
    args.profile = profile_map.get(choice, "smart")
    args.dry_run = False
    args.no_save = False
    if not hasattr(args, "dry_run"):
        args.dry_run = False
    if not hasattr(args, "no_save"):
        args.no_save = False
    if choice == "5":
        args.max_workflows = max(args.max_workflows, 80)
    return cmd_run(args)


def cmd_list(args: argparse.Namespace) -> int:
    catalog = load_catalog(Path(args.catalog) if args.catalog else None)
    for row in sorted(list_workflows_zh(catalog), key=lambda r: (r["category_zh"], r["name"])):
        scope_labels = _format_scope_labels(row.get("scopes"))
        print(f"[{row['name']}] {row['display_zh']}  |  {row['category_zh']}  |  适用模式={scope_labels}")
        print(f"    业务场景：{scope_labels}")
        print(f"    {row['description']}")
    return 0


def cmd_legend(args: argparse.Namespace) -> int:
    catalog = load_catalog(Path(args.catalog) if args.catalog else None)
    print_scope_legend(catalog)
    print("业务人员建议按这个顺序使用：\n")
    print("  1. 先执行 legend / list，确认系统支持哪些模式和工作流")
    print("  2. 再执行 plan --case-id <案例>，先看计划，不要一上来就跑")
    print("  3. 确认计划后按适用模式执行 run（默认可先用 --profile smart）")
    print("  4. 如果只是更新文案、看板或 final_report，优先执行 refresh-reports")
    print()
    print("用户可以说：\n")
    for line in catalog.get("user_prompt_examples_zh") or []:
        print(f"  · {line}")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "中文工作流目录 / 自动选流 / 计划与执行。业务人员快速开始：先执行 legend，再 plan，再 run；"
            "改文案后 refresh-reports。研发与现场编排可直接调用本 CLI。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 -m workflows.run_workflow_smart_zh plan --case-id daduhe
  python3 -m workflows.run_workflow_smart_zh plan --case-id daduhe --json-summary
  python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --dry-run
  python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --profile modeling
  python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --continue-on-error -v
  python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --no-progress-file
  python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --simple-report
  python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --no-reports
  python3 -m workflows.run_workflow_smart_zh menu --case-id daduhe
  python3 -m workflows.run_workflow_smart_zh meta
  python3 -m workflows.run_workflow_smart_zh legend
  python3 -m workflows.run_workflow_smart_zh list
  python3 -m workflows.run_workflow_smart_zh plan --case-id daduhe --allow-registry-only
  python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id daduhe --report-level detailed
  python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id daduhe --regenerate-md-reports
  python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id daduhe --smart-reporting-config path/to/custom.yaml
        """.strip(),
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp_meta = sub.add_parser(
        "meta",
        help="输出 Agent/CI 可用的 CLI 契约 JSON（子命令、产物路径、环境变量、退出码）",
    )
    sp_meta.add_argument("--catalog", default="", help="仅用于 meta 内 catalog_path_resolved 示例解析")
    sp_meta.set_defaults(func=cmd_meta)

    def add_agent_json_summary_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--json-summary",
            action="store_true",
            help="写入当前命令/模式 scoped 机器摘要；正式 run --profile smart 额外刷新 workflow_smart_cli_result.latest.json（亦可用环境变量 HYDRO_SMART_JSON_SUMMARY=1）",
        )
        sp.add_argument(
            "--print-json-summary",
            action="store_true",
            help="在 --json-summary 时额外向 stdout 输出一行紧凑 JSON（便于管道采集）",
        )

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--case-id", required=True, help="案例 ID（如 daduhe）")
        sp.add_argument(
            "--profile",
            choices=["smart", "modeling", "control", "evaluation", "full"],
            default="smart",
            help="smart=智能选流；modeling/control/evaluation=按端到端范围过滤；full=data_ok 全候选",
        )
        sp.add_argument(
            "--max-workflows",
            type=int,
            default=32,
            help="计划最多包含多少个工作流（smart 含 D1/D2 报告与水力仿真时需更大上限）",
        )
        sp.add_argument("--include-external", action="store_true", help="包含外部脚本类工作流")
        sp.add_argument("--include-long-running", action="store_true", help="包含 improve/pipeline/DL 等长任务")
        sp.add_argument(
            "--allow-registry-only",
            action="store_true",
            help="将可行性 tier=registry_only 的工作流纳入候选（如 hydro_report 等规则未声明数据信号时）",
        )
        sp.add_argument("--catalog", default="", help="覆盖 workflow_catalog_zh.yaml 路径")
        sp.add_argument("--rules", default="", help="覆盖 workflow_feasibility_rules.yaml 路径")
        sp.add_argument("--config", default="", help="覆盖 hydrodesk loop YAML（建模提示用）")
        sp.add_argument(
            "--restrict-workflow-keys",
            default="",
            help="限制 smart 选流仅可使用这些 workflow key（逗号分隔；也可用 HYDRO_SMART_RESTRICT_WORKFLOW_KEYS）",
        )

    def add_smart_reporting_bundle_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--smart-reporting-config",
            default="",
            metavar="PATH",
            help="覆盖 workflow_smart_reporting.yaml（相对 WORKSPACE 或绝对路径）",
        )
        sp.add_argument(
            "--case-config",
            default="",
            metavar="PATH",
            help="覆盖案例 YAML（用于合并 smart_reporting 块；相对 WORKSPACE 或绝对路径）",
        )

    def add_smart_run_report_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--report-level",
            choices=["detailed", "simple", "none"],
            default="detailed",
            help=(
                "报告详细程度（默认 detailed）：detailed=验证+final+可选 universal+索引；"
                "simple=E2E 看板刷新与本轮索引；none=不生成跑后报告"
            ),
        )
        sp.add_argument("--no-reports", action="store_true", help="等同于 --report-level none")
        sp.add_argument("--simple-report", action="store_true", help="等同于 --report-level simple")
        sp.add_argument(
            "--no-detailed-reports",
            action="store_true",
            help="兼容旧用法：等同于 --report-level none（推荐 --no-reports）",
        )

    sp_plan = sub.add_parser("plan", help="先出执行计划，确认步骤后再正式运行")
    add_common(sp_plan)
    add_smart_reporting_bundle_args(sp_plan)
    add_smart_run_report_args(sp_plan)
    sp_plan.add_argument("--json", action="store_true", help="额外打印完整 JSON")
    sp_plan.add_argument("--no-save", action="store_true", help="不写 contracts JSON")
    sp_plan.add_argument(
        "--no-plan-reports",
        action="store_true",
        help="不写计划说明 workflow_smart_plan_report.latest.md/html（与 --report-level none 二选一即可）",
    )
    add_agent_json_summary_args(sp_plan)
    sp_plan.set_defaults(func=cmd_plan)

    sp_run = sub.add_parser(
        "run",
        help="按计划正式执行；不确定时可先加 --dry-run 预演",
    )
    add_common(sp_run)
    add_smart_reporting_bundle_args(sp_run)
    add_smart_run_report_args(sp_run)
    sp_run.add_argument("--dry-run", action="store_true")
    sp_run.add_argument(
        "--continue-on-error",
        action="store_true",
        help="某步失败后仍继续（默认：遇错立即中止，避免在错误前提下跑后续）",
    )
    sp_run.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="每步打印 UTC 开始时间戳（便于对照日志）",
    )
    sp_run.add_argument(
        "--progress-file",
        default="",
        metavar="PATH",
        help="NDJSON 进度日志路径（默认: cases/<case>/contracts/workflow_smart_progress.latest.ndjson）",
    )
    sp_run.add_argument(
        "--no-progress-file",
        action="store_true",
        help="不写入 NDJSON 进度文件（仅终端输出）",
    )
    sp_run.add_argument(
        "--skip-universal-report",
        action="store_true",
        help="仅当 --report-level detailed 时生效：跳过 generate_universal_report（加快收尾）",
    )
    sp_run.add_argument("--no-save", action="store_true")
    add_agent_json_summary_args(sp_run)
    sp_run.set_defaults(func=cmd_run)

    sp_refresh = sub.add_parser(
        "refresh-reports",
        help=(
            "不重跑，只重出报告与看板；改了文案、模板或 final_report 策略时优先用它。"
        ),
    )
    sp_refresh.add_argument("--case-id", required=True, help="案例 ID")
    add_smart_reporting_bundle_args(sp_refresh)
    add_smart_run_report_args(sp_refresh)
    sp_refresh.add_argument(
        "--skip-universal-report",
        action="store_true",
        help="detailed 时跳过 generate_universal_report（加快刷新）",
    )
    sp_refresh.add_argument(
        "--regenerate-md-reports",
        action="store_true",
        help=(
            "刷新报告链**之前**先重跑 D1/D2/D1–D4 Markdown 生成器（读当前合约与 YAML；"
            "数值结果不变，仅更新文案/分级/知识固化）"
        ),
    )
    add_agent_json_summary_args(sp_refresh)
    sp_refresh.set_defaults(func=cmd_refresh_reports)

    sp_menu = sub.add_parser("menu", help="交互式选端到端类型后执行（同 run）")
    add_common(sp_menu)
    add_smart_reporting_bundle_args(sp_menu)
    add_smart_run_report_args(sp_menu)
    sp_menu.add_argument("--continue-on-error", action="store_true")
    sp_menu.add_argument("-v", "--verbose", action="store_true")
    sp_menu.add_argument("--progress-file", default="", metavar="PATH", help="同 run")
    sp_menu.add_argument("--no-progress-file", action="store_true")
    sp_menu.add_argument(
        "--skip-universal-report",
        action="store_true",
        help="同 run：detailed 时跳过 universal HTML",
    )
    add_agent_json_summary_args(sp_menu)
    sp_menu.set_defaults(func=cmd_menu)

    sp_leg = sub.add_parser("legend", help="先看系统支持什么：业务模式、范围和典型说法")
    sp_leg.add_argument("--catalog", default="", help="覆盖 workflow_catalog_zh.yaml 路径")
    sp_leg.set_defaults(func=cmd_legend)

    sp_list = sub.add_parser("list", help="看当前可用工作流清单，并按业务模式理解用途")
    sp_list.add_argument("--catalog", default="", help="覆盖 workflow_catalog_zh.yaml 路径")
    sp_list.set_defaults(func=cmd_list)

    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "meta":
        return cmd_meta(args)
    if args.command == "legend":
        return cmd_legend(args)
    if args.command == "list":
        return cmd_list(args)
    cid = getattr(args, "case_id", None)
    if cid and str(cid).strip():
        try:
            load_case_config(str(cid).strip())
        except Exception:
            pass
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
