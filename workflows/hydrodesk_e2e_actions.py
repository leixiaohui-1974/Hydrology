#!/usr/bin/env python3
"""HydroDesk actions for pipeline E2E run/review/release."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))
HYDROLOGY_ROOT = WORKSPACE / "Hydrology"
if str(HYDROLOGY_ROOT) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY_ROOT))
_SCRIPTS_DIR = HYDROLOGY_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import yaml

from hydrodesk_loop_yaml_util import load_loop_yaml  # noqa: E402

from Hydrology.mcp_server import hm_run_workflow
from Hydrology.workflows.scada_replay_engine import ReplayConfig, ScadaReplayEngine
from workflows._shared import load_case_config
from workflows.run_e2e_live_tracker import (
    _classify_status,
    _load_json,
    _render_dashboard,
    _render_dashboard_html,
    _save_json,
    _write_outcome_coverage_report,
    _now_iso,
    run_live_tracker,
)


def _contracts_dir(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts"


DEFAULT_AUTONOMOUS_LOOP_CONFIG = HYDROLOGY_ROOT / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"

# contracts/ 下额外快照（与 hydrodesk_shell.delivery_docs_pack.contracts_snapshot_relpaths 可合并）
_DEFAULT_DELIVERY_SNAPSHOT_RELPATHS: tuple[str, ...] = (
    "final_report.latest.json",
    "outcome_coverage_report.latest.json",
    "e2e_outcome_verification_report.json",
    "e2e_outcome_verification_report.md",
    "e2e_live_progress.latest.json",
    "E2E_LIVE_DASHBOARD.md",
    "E2E_LIVE_DASHBOARD.html",
    "data_assimilation.latest.json",
    "state_estimation.latest.json",
    "parameter_governance.latest.json",
)

_OPTIONAL_TRIO_ARTIFACT_FILENAMES: tuple[tuple[str, str], ...] = (
    ("data_assimilation", "data_assimilation.latest.json"),
    ("state_estimation", "state_estimation.latest.json"),
    ("parameter_governance", "parameter_governance.latest.json"),
)


def _optional_trio_release_artifacts(case_id: str, contracts: Path) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for artifact_key, filename in _OPTIONAL_TRIO_ARTIFACT_FILENAMES:
        if (contracts / filename).is_file():
            artifacts[artifact_key] = f"cases/{case_id}/contracts/{filename}"
    return artifacts


def _delivery_snapshot_relpaths() -> list[str]:
    defaults = list(_DEFAULT_DELIVERY_SNAPSHOT_RELPATHS)
    try:
        cfg = load_loop_yaml(WORKSPACE, DEFAULT_AUTONOMOUS_LOOP_CONFIG.resolve())
    except (OSError, ValueError, FileNotFoundError):
        return defaults
    shell = cfg.get("hydrodesk_shell")
    if not isinstance(shell, dict):
        return defaults
    ddp = shell.get("delivery_docs_pack")
    if not isinstance(ddp, dict):
        return defaults
    rels = ddp.get("contracts_snapshot_relpaths")
    if not isinstance(rels, list):
        return defaults
    out = [str(x).strip() for x in rels if isinstance(x, str) and str(x).strip()]
    merged: list[str] = []
    for item in [*defaults, *out]:
        if item not in merged:
            merged.append(item)
    return merged


def _release_gate_detail(case_id: str) -> dict[str, Any]:
    """与 HydroDesk Tauri `get_case_contract_summary` 签发规则对齐（文案一致）。"""
    contracts = _contracts_dir(case_id)
    blockers: list[str] = []
    tri_wr = _triad_resolved_read_path(contracts, "workflow_run")
    tri_rb = _triad_resolved_read_path(contracts, "review_bundle")
    tri_rm = _triad_resolved_read_path(contracts, "release_manifest")
    triad_count = sum(1 for p in (tri_wr, tri_rb, tri_rm) if p.is_file())
    triad_bridge_fallback_count = sum(
        1 for p in (tri_wr, tri_rb, tri_rm) if p.is_file() and p.name.endswith(".contract.json")
    )
    if not tri_wr.is_file():
        blockers.append("缺少 workflow_run（.json / .contract.json）")
    if not tri_rb.is_file():
        blockers.append("缺少 review_bundle（.json / .contract.json）")
    if not tri_rm.is_file():
        blockers.append("缺少 release_manifest（.json / .contract.json）")
    if triad_bridge_fallback_count > 0:
        blockers.append(f"triad 仍使用 bridge fallback（.contract.json {triad_bridge_fallback_count} 项）")

    verification_path = contracts / "e2e_outcome_verification_report.json"
    coverage_path = contracts / "outcome_coverage_report.latest.json"
    verification_exists = verification_path.is_file()
    verification: dict[str, Any] = _load_json(verification_path) if verification_exists else {}
    coverage: dict[str, Any] = _load_json(coverage_path) if coverage_path.is_file() else {}

    closure_check_passed = False
    se0 = verification.get("stage2_execution_integrity")
    if isinstance(se0, dict):
        closure_check_passed = bool(se0.get("closure_check_passed"))
    elif verification_exists:
        closure_check_passed = bool(verification.get("closure_check_passed"))

    pending_workflows: list[str] = []
    se = verification.get("stage2_execution_integrity") if isinstance(verification, dict) else {}
    if isinstance(se, dict):
        pw = se.get("pending_workflows")
        if isinstance(pw, list):
            for item in pw:
                if isinstance(item, dict) and item.get("workflow_key"):
                    pending_workflows.append(str(item["workflow_key"]))
                elif isinstance(item, str):
                    pending_workflows.append(item)

    if verification_exists and not closure_check_passed:
        blockers.append("e2e_outcome_verification_report：closure_check_passed 为 false")
    if pending_workflows:
        blockers.append(f"verification pending_workflows 非空（{len(pending_workflows)} 项）")

    gate_status = str(coverage.get("gate_status") or "unknown")
    if gate_status == "blocked":
        blockers.append("outcome_coverage_report gate_status=blocked")

    eligible = len(blockers) == 0
    return {
        "triad_count": triad_count,
        "triad_bridge_fallback_count": triad_bridge_fallback_count,
        "triad_paths": {
            "workflow_run": str(tri_wr.relative_to(WORKSPACE)).replace("\\", "/") if tri_wr.is_file() else "",
            "review_bundle": str(tri_rb.relative_to(WORKSPACE)).replace("\\", "/") if tri_rb.is_file() else "",
            "release_manifest": str(tri_rm.relative_to(WORKSPACE)).replace("\\", "/") if tri_rm.is_file() else "",
        },
        "gate_status": gate_status,
        "closure_check_passed": closure_check_passed if verification_exists else False,
        "verification_exists": verification_exists,
        "pending_workflows": pending_workflows,
        "release_gate_eligible": eligible,
        "release_gate_blockers": blockers,
    }


def _knowledge_lint_case_json(case_id: str) -> dict[str, Any]:
    script = _SCRIPTS_DIR / "lint_case_knowledge_links.py"
    if not script.is_file():
        return {"ok": False, "error": "lint_script_missing", "case_id": case_id}
    proc = subprocess.run(
        [sys.executable, str(script), "--case-id", case_id],
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        timeout=180,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        return {
            "ok": False,
            "error": "lint_empty_stdout",
            "returncode": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-800:],
        }
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "lint_json_parse_failed", "stdout_tail": raw[-800:]}


def _render_delivery_summary_md(case_id: str, manifest: dict[str, Any]) -> str:
    gate = manifest.get("release_gate") or {}
    lint = manifest.get("knowledge_lint") or {}
    lines = [
        f"# 交付文档包摘要 · `{case_id}`",
        "",
        f"- **pack_id**: `{manifest.get('pack_id', '')}`",
        f"- **generated_at**: {manifest.get('generated_at', '')}",
        f"- **release_gate_eligible**: {gate.get('release_gate_eligible', False)}",
        f"- **knowledge_lint.ok**: {lint.get('ok', False)}",
        f"- **eligible_at_pack_time**（Gate ∧ Lint）: {manifest.get('eligible_at_pack_time', False)}",
        "",
        "## Release gate blockers",
        "",
    ]
    for b in gate.get("release_gate_blockers") or []:
        lines.append(f"- {b}")
    if not gate.get("release_gate_blockers"):
        lines.append("- （无）")
    lines.extend(
        [
            "",
            "## 快照目录",
            "",
            f"`{manifest.get('snapshots_dir', 'snapshots')}`",
            "",
            f"布局：{manifest.get('snapshots_layout', '')}",
            "",
        ]
    )
    return "\n".join(lines)


def action_generate_delivery_docs_pack(
    case_id: str,
    *,
    require_release_gate: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    生成交付文档包：manifest + SUMMARY.md + snapshots/（triad + 配置列出的 contracts 文件）。
    默认即使 Gate/Lint 未过也落盘，但在 manifest 中记录 eligible_at_pack_time；
    --require-release-gate 时若未达标则不写入。
    """
    contracts = _contracts_dir(case_id)
    if not contracts.is_dir():
        raise FileNotFoundError(f"contracts 目录不存在: {contracts}")

    gate = _release_gate_detail(case_id)
    lint_one = _knowledge_lint_case_json(case_id)
    lint_ok = bool(lint_one.get("ok"))
    eligible = bool(gate.get("release_gate_eligible")) and lint_ok
    combined_blockers: list[str] = list(gate.get("release_gate_blockers") or [])
    if not lint_ok:
        combined_blockers.append(
            f"knowledge_lint 未通过: {lint_one.get('errors') or lint_one.get('error', 'unknown')}"
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pack_root = contracts / "delivery_pack" / ts
    snapshots_rel = f"cases/{case_id}/contracts/delivery_pack/{ts}/snapshots"

    base_out: dict[str, Any] = {
        "action": "generate-delivery-docs-pack",
        "case_id": case_id,
        "pack_id": ts,
        "release_gate_eligible": gate.get("release_gate_eligible"),
        "knowledge_lint_ok": lint_ok,
        "eligible_at_pack_time": eligible,
        "require_release_gate": require_release_gate,
        "dry_run": dry_run,
        "combined_blockers": combined_blockers,
    }

    if require_release_gate and not eligible:
        return {
            **base_out,
            "ok": False,
            "error": "blocked_by_release_gate_or_knowledge_lint",
            "pack_dir": "",
        }

    if dry_run:
        return {
            **base_out,
            "ok": True,
            "pack_dir": str(pack_root.relative_to(WORKSPACE)).replace("\\", "/"),
            "would_write_snapshots": _delivery_snapshot_relpaths(),
        }

    pack_root.mkdir(parents=True, exist_ok=True)
    snap_dir = pack_root / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    triad_snap = snap_dir / "triad"
    contracts_snap = snap_dir / "contracts"
    triad_snap.mkdir(parents=True, exist_ok=True)
    contracts_snap.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for stem in ("workflow_run", "review_bundle", "release_manifest"):
        src = _triad_resolved_read_path(contracts, stem)
        if src.is_file():
            dst = triad_snap / src.name
            shutil.copy2(src, dst)
            copied.append(str(dst.relative_to(WORKSPACE)).replace("\\", "/"))

    for rel in _delivery_snapshot_relpaths():
        src = contracts / rel
        if src.is_file():
            dst = contracts_snap / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(str(dst.relative_to(WORKSPACE)).replace("\\", "/"))

    manifest: dict[str, Any] = {
        "_auto_generated": True,
        "_generator": "hydrodesk_e2e_actions.generate-delivery-docs-pack",
        "case_id": case_id,
        "pack_id": ts,
        "generated_at": _now_iso(),
        "release_gate": gate,
        "knowledge_lint": {
            "ok": lint_one.get("ok"),
            "broken_relative_link_count": lint_one.get("broken_relative_link_count"),
            "raw_dir_exists": lint_one.get("raw_dir_exists"),
            "errors": lint_one.get("errors"),
        },
        "snapshots_dir": snapshots_rel,
        "snapshots_layout": "snapshots/triad/<file> + snapshots/contracts/<contracts 内相对路径>",
        "snapshots_copied": copied,
        "eligible_at_pack_time": eligible,
        "contracts_snapshot_relpaths_config": _delivery_snapshot_relpaths(),
    }
    _save_json(pack_root / "manifest.json", manifest)
    summary_path = pack_root / "SUMMARY.md"
    summary_path.write_text(_render_delivery_summary_md(case_id, manifest), encoding="utf-8")

    pointer = {
        "_auto_generated": True,
        "case_id": case_id,
        "latest_pack_rel": str(pack_root.relative_to(WORKSPACE)).replace("\\", "/"),
        "pack_id": ts,
        "updated_at": _now_iso(),
        "eligible_at_pack_time": eligible,
    }
    _save_json(contracts / "delivery_pack.latest.json", pointer)

    pack_rel = str(pack_root.relative_to(WORKSPACE)).replace("\\", "/")
    return {
        **base_out,
        "ok": True,
        "pack_dir": pack_rel,
        "manifest": f"{pack_rel}/manifest.json",
        "summary_md": f"{pack_rel}/SUMMARY.md",
        "pointer": str((contracts / "delivery_pack.latest.json").relative_to(WORKSPACE)).replace("\\", "/"),
    }


def _triad_resolved_read_path(contracts: Path, stem: str) -> Path:
    """Prefer canonical ``{stem}.json``, else ``{stem}.contract.json`` (bootstrap / 双轨)."""
    canonical = contracts / f"{stem}.json"
    alt = contracts / f"{stem}.contract.json"
    if canonical.exists():
        return canonical
    if alt.exists():
        return alt
    return canonical


def _scada_replay_defaults_dict() -> dict[str, Any]:
    defaults_path = HYDROLOGY_ROOT / "configs" / "scada_replay_defaults.yaml"
    if not defaults_path.is_file():
        return {}
    raw = yaml.safe_load(defaults_path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def resolve_scada_replay_config(case_id: str) -> tuple[str | None, str | None, Path, str]:
    """单次加载：时间窗、SQLite 路径、配置态 scenario_id（CLI 在外层覆盖）。"""
    raw_d = _scada_replay_defaults_dict()
    q_start: str | None = None
    q_end: str | None = None
    if raw_d.get("query_start") is not None:
        s = str(raw_d["query_start"]).strip()
        q_start = s or None
    if raw_d.get("query_end") is not None:
        s = str(raw_d["query_end"]).strip()
        q_end = s or None
    sid = "replay_baseline"
    if raw_d.get("scenario_id") is not None:
        s = str(raw_d["scenario_id"]).strip()
        if s:
            sid = s

    cfg = load_case_config(case_id)
    sr = cfg.get("scada_replay")
    sqlite_rel = None
    if isinstance(sr, dict):
        if sr.get("query_start") is not None:
            s = str(sr["query_start"]).strip()
            q_start = s or None
        if sr.get("query_end") is not None:
            s = str(sr["query_end"]).strip()
            q_end = s or None
        if sr.get("scenario_id") is not None:
            s = str(sr["scenario_id"]).strip()
            if s:
                sid = s
        sqlite_rel = sr.get("sqlite_path")

    if sqlite_rel:
        sqlite_path = (WORKSPACE / str(sqlite_rel)).resolve()
    else:
        sqlite_path = (WORKSPACE / "cases" / case_id / f"{case_id}_hydromind.sqlite3").resolve()

    return q_start, q_end, sqlite_path, sid


def resolve_scada_replay_paths(case_id: str) -> tuple[str | None, str | None, Path]:
    """回放时间窗与 SQLite 路径：defaults YAML + 案例 `scada_replay` 段合并（无硬编码日期）。"""
    qs, qe, sp, _ = resolve_scada_replay_config(case_id)
    return qs, qe, sp


def resolve_scada_replay_scenario_id(case_id: str) -> str:
    """消息中的 scenario_id：defaults YAML + 案例 `scada_replay.scenario_id`（CLI 非空时在外层覆盖）。"""
    *_, sid = resolve_scada_replay_config(case_id)
    return sid


def merge_scada_replay_cli_overrides(
    query_start: str | None,
    query_end: str | None,
    sqlite_path: Path,
    *,
    query_start_cli: str = "",
    query_end_cli: str = "",
    sqlite_path_cli: str = "",
) -> tuple[str | None, str | None, Path]:
    """CLI 非空参数覆盖 YAML/defaults（便于试验，不落库）。"""
    qs, qe, sp = query_start, query_end, sqlite_path
    if query_start_cli.strip():
        qs = query_start_cli.strip()
    if query_end_cli.strip():
        qe = query_end_cli.strip()
    if sqlite_path_cli.strip():
        sp = (WORKSPACE / sqlite_path_cli.strip()).resolve()
    return qs, qe, sp


def _source_report_candidates(case_id: str) -> list[Path]:
    return [
        WORKSPACE / "Hydrology" / "cases" / case_id / "contracts" / "mcp_all_agents_e2e_report.v8_fast.fix.json",
        WORKSPACE / "Hydrology" / "cases" / case_id / "contracts" / "mcp_all_agents_e2e_report.v8_fast.json",
        WORKSPACE / "Hydrology" / "cases" / case_id / "contracts" / "mcp_all_agents_e2e_report.v7_fast.json",
        WORKSPACE / "cases" / case_id / "contracts" / "mcp_all_agents_e2e_report.v8_fast.fix.json",
        WORKSPACE / "cases" / case_id / "contracts" / "mcp_all_agents_e2e_report.v8_fast.json",
    ]


def _resolve_source_report(case_id: str, explicit: str = "") -> str:
    if explicit:
        candidate = (WORKSPACE / explicit).resolve() if not Path(explicit).is_absolute() else Path(explicit)
        if candidate.exists():
            return str(candidate.relative_to(WORKSPACE))
    for item in _source_report_candidates(case_id):
        if item.exists():
            return str(item.relative_to(WORKSPACE))
    raise FileNotFoundError(f"no usable source report for case_id={case_id}")


def _progress_paths(case_id: str) -> tuple[Path, Path, Path]:
    contracts = _contracts_dir(case_id)
    return (
        contracts / "e2e_live_progress.latest.json",
        contracts / "E2E_LIVE_DASHBOARD.md",
        contracts / "E2E_LIVE_DASHBOARD.html",
    )


def _latest_records_by_workflow(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record.get("workflow_key", "")).strip()
        if key:
            latest[key] = record
    return latest


def _refresh_dashboard_files(case_id: str, state: dict[str, Any]) -> dict[str, Any]:
    contracts = _contracts_dir(case_id)
    progress_json, dashboard_md, dashboard_html = _progress_paths(case_id)
    state["last_updated_at"] = _now_iso()
    _write_outcome_coverage_report(contracts, state)
    _save_json(progress_json, state)
    _render_dashboard(dashboard_md, state)
    _render_dashboard_html(dashboard_html, state)
    return {
        "progress_json": str(progress_json.relative_to(WORKSPACE)),
        "dashboard_md": str(dashboard_md.relative_to(WORKSPACE)),
        "dashboard_html": str(dashboard_html.relative_to(WORKSPACE)),
    }


def _workflow_status(result: dict[str, Any]) -> str:
    excerpt = json.dumps(result, ensure_ascii=False)[:800]
    return _classify_status(result, excerpt)


def action_run_fast(case_id: str, source_report: str, retry_max: int) -> dict[str, Any]:
    source = _resolve_source_report(case_id, source_report)
    result = run_live_tracker(
        case_id=case_id,
        source_report=source,
        execution_profile="fast_validation",
        retry_max=retry_max,
        retry_backoff_sec=2.0,
    )
    return {"action": "run-fast", "source_report": source, "result": result}


def action_retry_failed(case_id: str, execution_profile: str, retry_max: int) -> dict[str, Any]:
    progress_json, _, _ = _progress_paths(case_id)
    if not progress_json.exists():
        raise FileNotFoundError(f"progress not found: {progress_json}")
    state = _load_json(progress_json)
    latest = _latest_records_by_workflow(state.get("records", []))
    targets = [item for item in latest.values() if item.get("status") in {"failed", "timeout"}]
    current = state.get("current") or {}
    current_key = str(current.get("workflow_key", "")).strip()
    if current_key:
        targets.append(
            {
                "agent_id": current.get("agent_id"),
                "agent_name": current.get("agent_name"),
                "workflow_path": current.get("workflow_path"),
                "workflow_key": current_key,
            }
        )
    retried: list[dict[str, Any]] = []
    for item in targets:
        workflow_key = str(item.get("workflow_key", ""))
        if not workflow_key:
            continue
        state["current"] = {
            "agent_id": item.get("agent_id"),
            "agent_name": item.get("agent_name"),
            "workflow_path": item.get("workflow_path"),
            "workflow_key": workflow_key,
            "started_at": _now_iso(),
        }
        start_ts = time.time()
        status = "failed"
        excerpt = ""
        attempts = 0
        for attempt in range(retry_max + 1):
            attempts = attempt + 1
            try:
                result = hm_run_workflow(
                    workflow=workflow_key,
                    case_id=case_id,
                    execution_profile=execution_profile,
                )
                excerpt = json.dumps(result, ensure_ascii=False)[:800]
                status = _workflow_status(result)
            except TimeoutError as exc:
                excerpt = str(exc)[:800]
                status = "timeout"
            except Exception as exc:
                excerpt = str(exc)[:800]
                status = "failed"
            if status == "passed":
                break
            if attempt < retry_max:
                state["summary"]["retries_used"] = int(state["summary"].get("retries_used", 0)) + 1
                time.sleep(2.0)

        ended_ts = time.time()
        record = {
            "agent_id": item.get("agent_id"),
            "agent_name": item.get("agent_name"),
            "workflow_path": item.get("workflow_path"),
            "workflow_key": workflow_key,
            "status": status,
            "started_at": state["current"]["started_at"],
            "ended_at": _now_iso(),
            "duration_s": round(ended_ts - start_ts, 2),
            "attempts": attempts,
            "excerpt": excerpt,
        }
        state["records"].append(record)
        retried.append({"workflow_key": workflow_key, "status": status, "attempts": attempts})
        state["current"] = None
        summary = state.get("summary", {})
        if status in {"passed", "failed", "timeout"}:
            summary[status] = int(summary.get(status, 0)) + 1
        summary["pending"] = max(0, int(summary.get("pending", 0)) - 1)
        state["summary"] = summary

    refreshed = _refresh_dashboard_files(case_id, state)
    return {
        "action": "retry-failed",
        "execution_profile": execution_profile,
        "retry_targets": len(targets),
        "retried": retried,
        **refreshed,
    }


def action_refresh_dashboard(case_id: str) -> dict[str, Any]:
    progress_json, _, _ = _progress_paths(case_id)
    if not progress_json.exists():
        raise FileNotFoundError(f"progress not found: {progress_json}")
    state = _load_json(progress_json)
    refreshed = _refresh_dashboard_files(case_id, state)
    return {"action": "refresh-dashboard", **refreshed}


def action_run_full_review(case_id: str) -> dict[str, Any]:
    key_workflows = [
        "pipeline",
        "cascade",
        "autonomy_assess",
    ]
    workflow_params: dict[str, dict[str, Any]] = {
        "pipeline": {
            "_external_timeout_sec": 150,
        },
        "cascade": {
            "_external_timeout_sec": 180,
        },
    }
    results: list[dict[str, Any]] = []
    for workflow in key_workflows:
        started = time.time()
        params = workflow_params.get(workflow)
        try:
            res = hm_run_workflow(
                workflow=workflow,
                case_id=case_id,
                execution_profile="default",
                params=params,
            )
        except Exception as exc:
            res = {"ok": False, "error": str(exc)}
        duration_s = round(time.time() - started, 2)
        fallback_ok = False
        fallback_error = None
        fallback_duration_s = 0.0
        default_ok = _workflow_status(res) == "passed"
        if not default_ok:
            fb_started = time.time()
            try:
                fallback_params = {"_external_timeout_sec": 120} if workflow.endswith("_ext") else None
                fb = hm_run_workflow(
                    workflow=workflow,
                    case_id=case_id,
                    execution_profile="fast_validation",
                    params=fallback_params,
                )
                fallback_ok = _workflow_status(fb) == "passed"
                fallback_error = fb.get("error")
            except Exception as exc:
                fallback_error = str(exc)
            fallback_duration_s = round(time.time() - fb_started, 2)
        results.append(
            {
                "workflow": workflow,
                "ok": default_ok,
                "error": res.get("error"),
                "duration_s": duration_s,
                "fallback_ok": fallback_ok,
                "fallback_error": fallback_error,
                "fallback_duration_s": fallback_duration_s,
            }
        )
    default_passed = all(item["ok"] for item in results)
    dual_gate_passed = all(item["ok"] or item.get("fallback_ok") for item in results)
    recovered_count = sum(1 for item in results if (not item["ok"]) and item.get("fallback_ok"))
    default_failed = [item["workflow"] for item in results if not item["ok"]]
    dual_gate_failed = [item["workflow"] for item in results if not (item["ok"] or item.get("fallback_ok"))]
    contracts = _contracts_dir(case_id)
    report = {
        "case_id": case_id,
        "generated_at": _now_iso(),
        "execution_profile": "default",
        "default_gate_passed": default_passed,
        "dual_gate_passed": dual_gate_passed,
        "fallback_recovered_count": recovered_count,
        "default_failed_workflows": default_failed,
        "dual_gate_failed_workflows": dual_gate_failed,
        "workflows": results,
        "_auto_generated": True,
    }
    json_path = contracts / "full_review.latest.json"
    md_path = contracts / "full_review.latest.md"
    _save_json(json_path, report)
    md_lines = [
        f"# full review report ({case_id})",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- default_gate_passed: {default_passed}",
        f"- dual_gate_passed: {dual_gate_passed}",
        f"- fallback_recovered_count: {recovered_count}",
        "",
        "| workflow | ok | error |",
        "|---|---|---|",
    ]
    for item in results:
        fallback_note = "-"
        if item.get("fallback_ok"):
            fallback_note = f"fallback=ok ({item.get('fallback_duration_s')}s)"
        elif item.get("fallback_error"):
            fallback_note = f"fallback={item.get('fallback_error')}"
        md_lines.append(
            f"| {item['workflow']} | {item['ok']} | {item['error'] or '-'} (duration={item['duration_s']}s; {fallback_note}) |"
        )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    action_refresh_dashboard(case_id)
    return {
        "action": "run-full-review",
        "json_report": str(json_path.relative_to(WORKSPACE)),
        "md_report": str(md_path.relative_to(WORKSPACE)),
        "all_passed": dual_gate_passed,
        "default_gate_passed": default_passed,
        "fallback_recovered_count": recovered_count,
    }


def action_run_scada_replay(
    case_id: str,
    scenario_id: str,
    replay_speed: float,
    quality_code: str,
    max_events: int,
    *,
    query_start_cli: str = "",
    query_end_cli: str = "",
    sqlite_path_cli: str = "",
) -> dict[str, Any]:
    scenario_cli = scenario_id.strip()
    contracts = _contracts_dir(case_id)
    summary_path = contracts / "scada_replay.latest.json"
    stream_path = contracts / "scada_replay.stream.ndjson"
    query_start, query_end, sqlite_path, scenario_from_cfg = resolve_scada_replay_config(case_id)
    effective_scenario = scenario_cli or scenario_from_cfg
    query_start, query_end, sqlite_path = merge_scada_replay_cli_overrides(
        query_start,
        query_end,
        sqlite_path,
        query_start_cli=query_start_cli,
        query_end_cli=query_end_cli,
        sqlite_path_cli=sqlite_path_cli,
    )
    cfg = ReplayConfig(
        case_id=case_id,
        sqlite_path=sqlite_path,
        scenario_id=effective_scenario,
        replay_speed=replay_speed,
        quality_code=quality_code,
        max_events=max_events,
        query_start=query_start,
        query_end=query_end,
    )
    summary = ScadaReplayEngine(cfg).run(summary_path=summary_path, stream_path=stream_path)
    return {
        "action": "run-scada-replay",
        "summary_json": str(summary_path.relative_to(WORKSPACE)),
        "stream_ndjson": str(stream_path.relative_to(WORKSPACE)),
        "messages_emitted": summary.get("messages_emitted", 0),
        "run_id": summary.get("run_id"),
        "scenario_id": effective_scenario,
        "query_start": query_start,
        "query_end": query_end,
        "sqlite_path": str(sqlite_path.relative_to(WORKSPACE)),
        "cli_override": bool(
            scenario_cli
            or query_start_cli.strip()
            or query_end_cli.strip()
            or sqlite_path_cli.strip()
        ),
    }


def _run_python_script(script_rel: str, args: list[str]) -> dict[str, Any]:
    script_path = WORKSPACE / script_rel
    cmd = [sys.executable, str(script_path), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        timeout=900,
    )
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[:4000],
        "stderr": (proc.stderr or "")[:4000],
    }


def action_build_release_pack(case_id: str) -> dict[str, Any]:
    contracts = _contracts_dir(case_id)
    progress_json, _, _ = _progress_paths(case_id)
    if not progress_json.exists():
        raise FileNotFoundError(f"progress not found: {progress_json}")
    progress = _load_json(progress_json)
    workflow_run_write = contracts / "workflow_run.json"
    workflow_run_read = _triad_resolved_read_path(contracts, "workflow_run")
    review_bundle = contracts / "review_bundle.json"
    release_manifest = contracts / "release_manifest.json"
    final_report = contracts / "final_report.latest.json"
    workflow_run_payload: dict[str, Any] | None = None
    if workflow_run_read.exists():
        workflow_run_payload = _load_json(workflow_run_read)
    run_id = str(
        ((workflow_run_payload or {}).get("run_id"))
        or progress.get("run_id")
        or f"{case_id}-manual"
    )
    if not workflow_run_read.exists():
        fallback_run = {
            "run_id": run_id,
            "case_id": case_id,
            "workflow_type": "hydrodesk_e2e",
            "status": "completed_with_review",
            "schema_version": "0.1.0",
            "_auto_generated": True,
        }
        _save_json(workflow_run_write, fallback_run)
        workflow_run_read = workflow_run_write

    workflow_run_for_cli = workflow_run_read
    trio_artifacts = _optional_trio_release_artifacts(case_id, contracts)

    verification_call = _run_python_script(
        "Hydrology/workflows/generate_e2e_outcome_verification_report.py",
        ["--case-id", case_id],
    )
    review_call = _run_python_script(
        "Hydrology/workflows/build_review_bundle.py",
        [
            "--case-id",
            case_id,
            "--run-id",
            run_id,
            "--review-output",
            str(review_bundle),
            "--report-output",
            str(contracts / "e2e_review_bundle.html"),
            "--verdict",
            "pass_with_comments",
        ],
    )
    version = datetime.now(timezone.utc).strftime("v%Y.%m.%d-hydrodesk")
    release_manifest_artifacts = [
        f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
        f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
        f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
        f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
        *trio_artifacts.values(),
    ]
    release_manifest_cli: list[str] = [
        "--case-id",
        case_id,
        "--version",
        version,
        "--workflow-run",
        str(workflow_run_for_cli),
        "--review-bundle",
        str(review_bundle),
        "--channel",
        "hydrodesk-shell",
        "--status",
        "review_pending",
        "--output",
        str(release_manifest),
    ]
    for artifact in release_manifest_artifacts:
        release_manifest_cli.extend(["--artifact", artifact])

    release_call = _run_python_script(
        "Hydrology/workflows/build_release_manifest.py",
        release_manifest_cli,
    )
    final_report_call = _run_python_script(
        "Hydrology/workflows/build_final_report.py",
        [
            "--case-id",
            case_id,
            "--workflow-run",
            str(workflow_run_for_cli),
            "--review-bundle",
            str(review_bundle),
            "--release-manifest",
            str(release_manifest),
            "--output",
            str(final_report),
        ],
    )
    release_pack_artifacts = {
        "workflow_run": str(workflow_run_write.relative_to(WORKSPACE)),
        "review_bundle": str(review_bundle.relative_to(WORKSPACE)),
        "release_manifest": str(release_manifest.relative_to(WORKSPACE)),
        "final_report": str(final_report.relative_to(WORKSPACE)),
        "dashboard_md": f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.md",
        "dashboard_html": f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
        "progress_json": f"cases/{case_id}/contracts/e2e_live_progress.latest.json",
        "coverage_report": f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
        "verification_md": f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
        "verification_json": f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
        **trio_artifacts,
        "outcomes_dir": f"cases/{case_id}/contracts/outcomes",
        "full_review_json": f"cases/{case_id}/contracts/full_review.latest.json",
        "full_review_md": f"cases/{case_id}/contracts/full_review.latest.md",
    }

    release_pack = {
        "case_id": case_id,
        "generated_at": _now_iso(),
        "run_id": run_id,
        "version": version,
        "artifacts": release_pack_artifacts,
        "calls": {
            "verification": verification_call,
            "review_bundle": review_call,
            "release_manifest": release_call,
            "final_report": final_report_call,
        },
        "_auto_generated": True,
    }
    pack_path = contracts / "release_pack.latest.json"
    _save_json(pack_path, release_pack)
    action_refresh_dashboard(case_id)
    return {
        "action": "build-release-pack",
        "release_pack": str(pack_path.relative_to(WORKSPACE)),
        "release_manifest": str(release_manifest.relative_to(WORKSPACE)),
        "ok": all(
            call.get("returncode", 1) == 0
            for call in [verification_call, review_call, release_call, final_report_call]
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HydroDesk pipeline E2E action runner")
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "run-fast",
            "retry-failed",
            "refresh-dashboard",
            "run-full-review",
            "build-release-pack",
            "generate-delivery-docs-pack",
            "run-scada-replay",
        ],
    )
    parser.add_argument("--source-report", default="")
    parser.add_argument("--execution-profile", default="fast_validation")
    parser.add_argument("--retry-max", type=int, default=2)
    parser.add_argument(
        "--scenario-id",
        default="",
        help="run-scada-replay：非空则覆盖 defaults/案例 YAML 中的 scenario_id",
    )
    parser.add_argument("--replay-speed", type=float, default=60.0)
    parser.add_argument("--quality-code", default="GOOD")
    parser.add_argument("--max-events", type=int, default=1200)
    parser.add_argument(
        "--query-start",
        default="",
        help="run-scada-replay：非空则覆盖 YAML/默认 query_start",
    )
    parser.add_argument(
        "--query-end",
        default="",
        help="run-scada-replay：非空则覆盖 YAML/默认 query_end",
    )
    parser.add_argument(
        "--sqlite-path",
        default="",
        help="run-scada-replay：非空则覆盖案例 scada_replay.sqlite_path（相对仓库根）",
    )
    parser.add_argument(
        "--require-release-gate",
        action="store_true",
        help="generate-delivery-docs-pack：Gate 与 knowledge_lint 均通过才写入磁盘",
    )
    parser.add_argument(
        "--delivery-pack-dry-run",
        action="store_true",
        help="generate-delivery-docs-pack：仅输出 JSON，不写 delivery_pack 目录",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.action == "run-fast":
        payload = action_run_fast(args.case_id, args.source_report, args.retry_max)
    elif args.action == "retry-failed":
        payload = action_retry_failed(args.case_id, args.execution_profile, args.retry_max)
    elif args.action == "refresh-dashboard":
        payload = action_refresh_dashboard(args.case_id)
    elif args.action == "run-full-review":
        payload = action_run_full_review(args.case_id)
    elif args.action == "run-scada-replay":
        payload = action_run_scada_replay(
            case_id=args.case_id,
            scenario_id=args.scenario_id,
            replay_speed=args.replay_speed,
            quality_code=args.quality_code,
            max_events=args.max_events,
            query_start_cli=args.query_start or "",
            query_end_cli=args.query_end or "",
            sqlite_path_cli=args.sqlite_path or "",
        )
    elif args.action == "build-release-pack":
        payload = action_build_release_pack(args.case_id)
    elif args.action == "generate-delivery-docs-pack":
        payload = action_generate_delivery_docs_pack(
            args.case_id,
            require_release_gate=bool(args.require_release_gate),
            dry_run=bool(args.delivery_pack_dry_run),
        )
    else:
        raise RuntimeError(f"unhandled action: {args.action}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
