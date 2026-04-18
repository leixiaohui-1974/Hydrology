"""Smart / profile 工作流跑完后：复用 E2E 报告链（看板 + 验证 MD + final_report + 通用仿真 HTML）并写索引页。

行为由 ``Hydrology/configs/workflow_smart_reporting.yaml`` + 案例 ``smart_reporting`` 块驱动；路径相对 WORKSPACE。"""
from __future__ import annotations

import html
import importlib
import inspect
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from workflows._autonomy_policy import _deep_merge

WORKSPACE = Path(__file__).resolve().parents[2]
HYDROLOGY_DIR = WORKSPACE / "Hydrology"
DEFAULT_SMART_REPORTING_YAML = HYDROLOGY_DIR / "configs" / "workflow_smart_reporting.yaml"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _contracts_dir(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id.strip() / "contracts"


def _resolve_reporting_yaml_path(reporting_yaml: str | None) -> Path:
    if reporting_yaml and str(reporting_yaml).strip():
        p = Path(str(reporting_yaml).strip())
        return p if p.is_absolute() else (WORKSPACE / p)
    return DEFAULT_SMART_REPORTING_YAML


def load_workflow_smart_reporting_config(
    case_id: str,
    *,
    config_path: str | None = None,
    reporting_yaml: str | None = None,
) -> dict[str, Any]:
    """加载 smart 报告配置：defaults ← per_case[case_id] ← 案例 YAML ``smart_reporting``。"""
    from workflows._shared import load_case_config

    path = _resolve_reporting_yaml_path(reporting_yaml)
    raw: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            raw = loaded if isinstance(loaded, dict) else {}
        except (OSError, yaml.YAMLError):
            raw = {}

    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    per_all = raw.get("per_case") if isinstance(raw.get("per_case"), dict) else {}
    per = per_all.get(case_id.strip()) if isinstance(per_all.get(case_id.strip()), dict) else {}
    merged = _deep_merge(dict(defaults), dict(per))

    try:
        case_cfg = load_case_config(case_id.strip(), config_path)
        side = case_cfg.get("smart_reporting")
        if isinstance(side, dict) and side:
            merged = _deep_merge(merged, side)
    except Exception:
        pass

    try:
        merged["_config_source"] = str(path.resolve().relative_to(WORKSPACE.resolve()))
    except ValueError:
        merged["_config_source"] = str(path.resolve())
    return merged


def _artifact_path_ctx(case_id: str, cfg: dict[str, Any]) -> dict[str, str]:
    cf = cfg.get("contract_filenames") if isinstance(cfg.get("contract_filenames"), dict) else {}
    uni = cfg.get("universal_report") if isinstance(cfg.get("universal_report"), dict) else {}
    cid = case_id.strip()
    return {
        "case_id": cid,
        "plan_file": str(cf.get("plan") or "workflow_smart_plan.latest.json").strip(),
        "run_summary_file": str(cf.get("run_summary") or "workflow_smart_run_summary.latest.json").strip(),
        "universal_html_file": str(uni.get("output_html_filename") or "universal_report.latest.html").strip(),
    }


def _build_bundle_rel_paths(
    level: str,
    case_id: str,
    cfg: dict[str, Any],
    *,
    skip_universal: bool,
) -> dict[str, str]:
    want = {"detailed"} if level == "detailed" else {"simple"}
    rows = cfg.get("bundle_artifact_links")
    if not isinstance(rows, list):
        return {}
    ctx = _artifact_path_ctx(case_id, cfg)
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        modes = row.get("modes") or ["detailed"]
        if not isinstance(modes, list):
            modes = ["detailed"]
        mode_set = {str(m).strip().lower() for m in modes if str(m).strip()}
        if not (mode_set & want):
            continue
        if skip_universal and row.get("omit_when_skip_universal"):
            continue
        label = str(row.get("label") or "").strip()
        tmpl = str(row.get("path_template") or "").strip()
        if not label or not tmpl:
            continue
        try:
            out[label] = tmpl.format(**ctx)
        except KeyError:
            continue
    return out


def _load_catalog_display_map(cfg: dict[str, Any]) -> dict[str, str]:
    rel = str(cfg.get("workflow_catalog_zh") or "Hydrology/configs/workflow_catalog_zh.yaml").strip()
    path = Path(rel) if rel.startswith("/") else (WORKSPACE / rel)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    workflows = data.get("workflows") if isinstance(data.get("workflows"), dict) else {}
    out: dict[str, str] = {}
    for key, meta in workflows.items():
        if isinstance(meta, dict) and meta.get("display_zh"):
            out[str(key)] = str(meta["display_zh"])
    return out


def _invoke_workflow_registry_entry(
    wf_key: str,
    case_id: str,
    *,
    case_config_path: str | None = None,
) -> Any:
    from workflows import WORKFLOW_REGISTRY

    spec = WORKFLOW_REGISTRY.get(wf_key)
    if not spec:
        raise KeyError(f"未注册的工作流: {wf_key}")
    if spec.get("external_script"):
        raise ValueError(f"{wf_key} 为 external_script 工作流，请在 md_regeneration.workflow_keys 中移除")
    mod = importlib.import_module(str(spec["module"]))
    fn = getattr(mod, str(spec["entry"]))
    sig = inspect.signature(fn)
    kwargs: dict[str, Any] = {}
    if "case_id" in sig.parameters:
        kwargs["case_id"] = case_id.strip()
    if "config_path" in sig.parameters and case_config_path:
        kwargs["config_path"] = case_config_path
    return fn(**kwargs)


def load_smart_run_context_from_contracts(
    case_id: str,
    *,
    case_config_path: str | None = None,
    reporting_yaml: str | None = None,
    reporting_cfg: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[str]]:
    """从 run_summary + plan 合约恢复 :func:`emit_post_run_artifacts` 所需上下文。"""
    cid = case_id.strip()
    cfg = reporting_cfg or load_workflow_smart_reporting_config(
        cid, config_path=case_config_path, reporting_yaml=reporting_yaml
    )
    ctx = _artifact_path_ctx(cid, cfg)
    cdir = _contracts_dir(cid)
    sum_path = cdir / ctx["run_summary_file"]
    plan_path = cdir / ctx["plan_file"]
    if not sum_path.is_file():
        rel = sum_path.relative_to(WORKSPACE)
        raise FileNotFoundError(
            f"缺少 {rel}；请先对本案例执行 `python3 -m workflows.run_workflow_smart_zh run --case-id {cid}`"
        )
    try:
        summary = json.loads(sum_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法解析 {sum_path.name}: {exc}") from exc
    if not isinstance(summary, dict):
        raise ValueError("run_summary 根节点须为对象")
    sid = str(summary.get("case_id") or "").strip()
    if sid and sid != cid:
        raise ValueError(f"summary.case_id={sid!r} 与 --case-id={cid!r} 不一致")
    profile = str(summary.get("profile") or "smart").strip() or "smart"
    raw_steps = summary.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("run_summary.steps 须为非空列表")
    results: list[dict[str, Any]] = [x for x in raw_steps if isinstance(x, dict)]
    if not results:
        raise ValueError("run_summary.steps 为空，无法重建 E2E 看板")
    failures = list(summary.get("failure_messages") or [])
    has_non_blocking_degraded = bool(summary.get("has_non_blocking_degraded"))
    if not summary.get("ok") and not failures and not has_non_blocking_degraded:
        failures = ["run_summary.ok=false（且无 failure_messages）"]

    plan: dict[str, Any] = {}
    if plan_path.is_file():
        try:
            loaded = json.loads(plan_path.read_text(encoding="utf-8"))
            plan = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            plan = {}
    if not plan:
        plan = {"case_id": cid, "workflows": []}

    return profile, plan, results, failures


def regenerate_md_dimension_reports(
    case_id: str,
    *,
    case_config_path: str | None = None,
    reporting_yaml: str | None = None,
    reporting_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按配置 ``md_regeneration.workflow_keys`` 调用注册表入口（Markdown / 知识固化）。"""
    cid = case_id.strip()
    cfg = reporting_cfg or load_workflow_smart_reporting_config(
        cid, config_path=case_config_path, reporting_yaml=reporting_yaml
    )
    md_block = cfg.get("md_regeneration") if isinstance(cfg.get("md_regeneration"), dict) else {}
    keys_raw = md_block.get("workflow_keys") or []
    if isinstance(keys_raw, str):
        keys_raw = [keys_raw]
    if not isinstance(keys_raw, list):
        keys_raw = []

    catalog = _load_catalog_display_map(cfg)
    out: dict[str, Any] = {"case_id": cid, "steps": [], "errors": [], "config_source": cfg.get("_config_source")}

    for wf_key in keys_raw:
        key = str(wf_key).strip()
        if not key:
            continue
        label = catalog.get(key, key)
        try:
            _invoke_workflow_registry_entry(key, cid, case_config_path=case_config_path)
            out["steps"].append({"workflow_key": key, "label": label, "ok": True})
        except Exception as exc:
            out["errors"].append(f"{key}: {exc}")
            out["steps"].append({"workflow_key": key, "label": label, "ok": False, "error": str(exc)})
    return out


def build_smart_e2e_progress_state(
    case_id: str,
    profile: str,
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    reporting_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造与 run_e2e_live_tracker 兼容的 progress 状态，供 _refresh_dashboard_files 使用。"""
    from workflows.run_e2e_live_tracker import OUTCOME_COVERAGE_THRESHOLD

    cid = case_id.strip()
    cfg = reporting_cfg or load_workflow_smart_reporting_config(cid)

    n = len(results)
    passed = sum(1 for r in results if r.get("ok"))
    failed = n - passed
    records: list[dict[str, Any]] = []
    for r in results:
        key = str(r.get("workflow_key") or "")
        ok = bool(r.get("ok"))
        records.append(
            {
                "agent_id": "workflow_smart_zh",
                "agent_name": "智能选流 CLI",
                "workflow_path": f"Hydrology/workflows/run_workflow_smart_zh.py::{key}",
                "workflow_key": key,
                "status": "passed" if ok else "failed",
                "started_at": r.get("started_at") or _utc_iso(),
                "ended_at": r.get("ended_at") or _utc_iso(),
                "duration_s": float(r.get("elapsed_sec") or 0.0),
                "attempts": 1,
                "excerpt": (str(r.get("error") or ""))[:800],
            }
        )
    e2e = cfg.get("e2e_progress") if isinstance(cfg.get("e2e_progress"), dict) else {}
    tmpl = str(
        e2e.get("source_report_path_template") or "cases/{case_id}/contracts/{plan_file}"
    ).strip()
    ctx = _artifact_path_ctx(cid, cfg)
    plan_rel = tmpl.format(**ctx)
    t0 = results[0].get("started_at") if results else _utc_iso()
    return {
        "run_id": f"smart-{uuid.uuid4().hex[:12]}",
        "case_id": cid,
        "started_at": t0,
        "last_updated_at": _utc_iso(),
        "execution_profile": str(profile or "smart"),
        "retry": {"max_retries": 0, "backoff_sec": 0.0},
        "source_report": plan_rel,
        "summary": {
            "total": n,
            "passed": passed,
            "failed": failed,
            "timeout": 0,
            "pending": 0,
            "retries_used": 0,
            "outcomes_generated": 0,
            "outcome_coverage": 0.0,
            "outcome_gate_status": "blocked",
            "outcome_gate_threshold": OUTCOME_COVERAGE_THRESHOLD,
            "outcome_coverage_report": "",
        },
        "current": None,
        "records": records,
        "_auto_generated": True,
        "_generator": "workflows.smart_run_reporting",
    }


def _run_py_script(script_rel: str, argv: list[str], *, timeout_sec: int = 900) -> tuple[int, str]:
    script = WORKSPACE / script_rel
    if not script.is_file():
        return 1, f"script missing: {script_rel}"
    proc = subprocess.run(
        [sys.executable, str(script), *argv],
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2500:]
    return proc.returncode, tail


def refresh_e2e_dashboards(
    case_id: str,
    state: dict[str, Any],
    reporting_cfg: dict[str, Any] | None = None,
) -> dict[str, str]:
    """与 hydrodesk_e2e_actions._refresh_dashboard_files 对齐：写 progress + 看板 MD/HTML。"""
    from workflows.run_e2e_live_tracker import (
        _now_iso,
        _render_dashboard,
        _render_dashboard_html,
        _save_json,
        _write_outcome_coverage_report,
    )

    cid = case_id.strip()
    cfg = reporting_cfg or load_workflow_smart_reporting_config(cid)
    dash = cfg.get("e2e_dashboard") if isinstance(cfg.get("e2e_dashboard"), dict) else {}
    pj = str(dash.get("progress_json") or "e2e_live_progress.latest.json").strip()
    dm = str(dash.get("dashboard_md") or "E2E_LIVE_DASHBOARD.md").strip()
    dh = str(dash.get("dashboard_html") or "E2E_LIVE_DASHBOARD.html").strip()

    contracts = _contracts_dir(cid)
    progress_json = contracts / pj
    dashboard_md = contracts / dm
    dashboard_html = contracts / dh
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


def run_outcome_verification_report(case_id: str, reporting_cfg: dict[str, Any]) -> tuple[int, str]:
    scripts = reporting_cfg.get("subprocess_scripts") if isinstance(reporting_cfg.get("subprocess_scripts"), dict) else {}
    rel = str(
        scripts.get("e2e_outcome_verification")
        or "Hydrology/workflows/generate_e2e_outcome_verification_report.py"
    ).strip()
    timeouts = reporting_cfg.get("subprocess_timeouts_sec") if isinstance(reporting_cfg.get("subprocess_timeouts_sec"), dict) else {}
    to = int(timeouts.get("e2e_outcome_verification") or 300)
    return _run_py_script(rel, ["--case-id", case_id.strip()], timeout_sec=to)


def run_build_final_report(case_id: str, reporting_cfg: dict[str, Any]) -> tuple[int, str]:
    scripts = reporting_cfg.get("subprocess_scripts") if isinstance(reporting_cfg.get("subprocess_scripts"), dict) else {}
    rel = str(scripts.get("build_final_report") or "Hydrology/workflows/build_final_report.py").strip()
    timeouts = reporting_cfg.get("subprocess_timeouts_sec") if isinstance(reporting_cfg.get("subprocess_timeouts_sec"), dict) else {}
    to = int(timeouts.get("build_final_report") or 120)
    return _run_py_script(rel, ["--case-id", case_id.strip()], timeout_sec=to)


def run_generate_object_topology_report(case_id: str, reporting_cfg: dict[str, Any]) -> tuple[int, str]:
    """刷新六类水对象契约样本与 combined_object_topology_report（依赖 pipedream contract_adapters）。"""
    scripts = reporting_cfg.get("subprocess_scripts") if isinstance(reporting_cfg.get("subprocess_scripts"), dict) else {}
    rel = str(
        scripts.get("generate_object_topology_report")
        or "Hydrology/workflows/generate_object_topology_report.py"
    ).strip()
    timeouts = reporting_cfg.get("subprocess_timeouts_sec") if isinstance(reporting_cfg.get("subprocess_timeouts_sec"), dict) else {}
    to = int(timeouts.get("generate_object_topology_report") or 120)
    return _run_py_script(rel, ["--case-id", case_id.strip()], timeout_sec=to)


def run_business_run_digest_subprocess(case_id: str, reporting_cfg: dict[str, Any]) -> tuple[int, str]:
    scripts = reporting_cfg.get("subprocess_scripts") if isinstance(reporting_cfg.get("subprocess_scripts"), dict) else {}
    rel = str(scripts.get("generate_business_run_digest") or "Hydrology/workflows/generate_business_run_digest.py").strip()
    timeouts = reporting_cfg.get("subprocess_timeouts_sec") if isinstance(reporting_cfg.get("subprocess_timeouts_sec"), dict) else {}
    to = int(timeouts.get("generate_business_run_digest") or 180)
    return _run_py_script(rel, ["--case-id", case_id.strip()], timeout_sec=to)


def emit_business_run_digest_step(
    case_id: str,
    reporting_cfg: dict[str, Any],
    *,
    report_level: str,
    out: dict[str, Any],
) -> None:
    """按配置生成业务向长文汇编（复用 hydromind 对象体系 + 拓扑样本 + 运行期索引）。"""
    cid = case_id.strip()
    dig = reporting_cfg.get("business_run_digest")
    if not isinstance(dig, dict) or not dig.get("enabled", True):
        return
    want = {str(x).strip().lower() for x in (dig.get("emit_for_report_levels") or ["detailed"])}
    if (report_level or "").strip().lower() not in want:
        return
    if dig.get("refresh_topology_standard_reports"):
        rc0, tail0 = run_generate_object_topology_report(cid, reporting_cfg)
        out["steps"]["generate_object_topology_report"] = {"returncode": rc0, "tail": tail0}
        if rc0 != 0:
            out["errors"].append(f"generate_object_topology_report rc={rc0}")
    use_subprocess = bool(dig.get("run_digest_via_subprocess", True))
    if use_subprocess:
        rc, tail = run_business_run_digest_subprocess(cid, reporting_cfg)
        out["steps"]["business_run_digest"] = {"returncode": rc, "tail": tail}
        if rc != 0:
            out["errors"].append(f"business_run_digest rc={rc}")
        return
    try:
        from hydro_model.business_run_digest import write_business_run_digest

        md_p, html_p, warns = write_business_run_digest(cid, reporting_cfg)
        out["steps"]["business_run_digest"] = {
            "md": str(md_p.relative_to(WORKSPACE)),
            "html": str(html_p.relative_to(WORKSPACE)),
            "warnings": warns,
        }
    except Exception as exc:
        out["errors"].append(f"business_run_digest: {exc}")


def run_universal_report_html(case_id: str, reporting_cfg: dict[str, Any]) -> tuple[int, str]:
    cid = case_id.strip()
    contracts = _contracts_dir(cid)
    uni = reporting_cfg.get("universal_report") if isinstance(reporting_cfg.get("universal_report"), dict) else {}
    npz_name = str(uni.get("npz_filename") or "sim_data.npz").strip()
    out_name = str(uni.get("output_html_filename") or "universal_report.latest.html").strip()
    npz = contracts / npz_name
    out_html = contracts / out_name
    scripts = reporting_cfg.get("subprocess_scripts") if isinstance(reporting_cfg.get("subprocess_scripts"), dict) else {}
    rel = str(scripts.get("generate_universal_report") or "Hydrology/workflows/generate_universal_report.py").strip()
    timeouts = reporting_cfg.get("subprocess_timeouts_sec") if isinstance(reporting_cfg.get("subprocess_timeouts_sec"), dict) else {}
    to = int(timeouts.get("generate_universal_report") or 600)
    argv = [
        "--case-id",
        cid,
        "--npz-path",
        str(npz),
        "--output-path",
        str(out_html),
    ]
    extra = uni.get("extra_cli_args")
    if isinstance(extra, list):
        argv.extend(str(x) for x in extra if str(x).strip())
    return _run_py_script(rel, argv, timeout_sec=to)


def write_smart_run_index(
    case_id: str,
    profile: str,
    *,
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    failures: list[str],
    report_paths: dict[str, str],
    mode: str = "detailed",
    reporting_cfg: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """本次 smart/profile 运行的总索引（MD + HTML），链到 E2E 看板、验证报告、final_report 等。"""
    cid = case_id.strip()
    cfg = reporting_cfg or load_workflow_smart_reporting_config(cid)
    idx = cfg.get("smart_index_output") if isinstance(cfg.get("smart_index_output"), dict) else {}
    md_name = str(idx.get("run_report_md") or "workflow_smart_report.latest.md").strip()
    html_name = str(idx.get("run_report_html") or "workflow_smart_report.latest.html").strip()

    cdir = _contracts_dir(cid)
    cdir.mkdir(parents=True, exist_ok=True)
    md_path = cdir / md_name
    html_path = cdir / html_name

    mode = (mode or "detailed").strip().lower()
    mode_note_md = ""
    mode_note_html = ""
    if mode == "simple":
        mode_note_md = (
            "\n> **报告模式：简单** — 仅刷新 E2E 看板与 outcome 覆盖；"
            "未生成 E2E 验证 MD/JSON、final_report、通用仿真 HTML。"
            "完整物请使用默认 `--report-level detailed`。\n"
        )
        mode_note_html = (
            "<p><strong>报告模式：简单</strong> — 未生成验证/final/通用仿真 HTML；"
            "完整报告请用 <code>--report-level detailed</code>。</p>"
        )

    has_non_blocking_degraded = any(
        bool(r.get("continued")) and str(r.get("outcome_status") or "") in {"degraded", "insufficient_data", "no_data", "partial", "quality_failed", "skipped"}
        for r in results
    )
    ok_all = not failures and not has_non_blocking_degraded
    overall_status_zh = "完成但有降级步骤" if has_non_blocking_degraded and not failures else ("全部成功" if ok_all else "存在失败步")
    rows_md = []
    rows_html = []
    for i, r in enumerate(results, start=1):
        key = html.escape(str(r.get("workflow_key", "")))
        is_non_blocking_degraded = bool(r.get("continued")) and str(r.get("outcome_status") or "") in {
            "degraded",
            "insufficient_data",
            "no_data",
            "partial",
            "quality_failed",
            "skipped",
        }
        st = "降级继续" if is_non_blocking_degraded else ("OK" if r.get("ok") else "FAIL")
        es = r.get("elapsed_sec", "")
        rows_md.append(f"| {i} | `{key}` | {st} | {es} |")
        cls = "degraded" if is_non_blocking_degraded else ("ok" if r.get("ok") else "fail")
        rows_html.append(
            f"<tr><td>{i}</td><td><code>{key}</code></td><td class={cls}>{st}</td><td>{es}</td></tr>"
        )

    links_md = "\n".join(f"- `{k}`: {v}" for k, v in sorted(report_paths.items()))
    plan_note = f"- profile: `{profile}`\n- 计划工作流数: {len(plan.get('workflows') or [])}\n"
    assets_section = (
        "## 相关产物链接（简单模式）"
        if mode == "simple"
        else "## 自动生成的详细报告（本轮已触发）"
    )

    md = "\n".join(
        [
            f"# 智能选流 / Profile 运行总览 — {cid}",
            "",
            f"- 生成时间（UTC）: {_utc_iso()}",
            f"- 整体状态: **{overall_status_zh}**",
            f"- 报告配置: `{cfg.get('_config_source', '')}`",
            mode_note_md,
            "## 本步执行结果",
            "",
            "| # | workflow | 状态 | 耗时(s) |",
            "|---|----------|------|---------|",
            *rows_md,
            "",
            assets_section,
            "",
            links_md or "- （无）",
            "",
            "## 计划上下文",
            "",
            plan_note,
            "",
            "---",
            "_由 `workflows.smart_run_reporting` 与 `run_workflow_smart_zh` 在跑完后自动生成。_",
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8")

    links_li = "".join(
        f"<li><strong>{html.escape(k)}</strong>: <code>{html.escape(v)}</code></li>" for k, v in sorted(report_paths.items())
    )
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Smart 运行总览 — {html.escape(cid)}</title>
<style>
body {{ font-family: system-ui, "PingFang SC", sans-serif; margin: 24px; background: #0d1117; color: #c9d1d9; }}
h1 {{ color: #58a6ff; }}
table {{ border-collapse: collapse; width: 100%; max-width: 960px; }}
th, td {{ border: 1px solid #30363d; padding: 8px 12px; text-align: left; }}
th {{ background: #161b22; color: #58a6ff; }}
tr:nth-child(even) {{ background: #161b22; }}
.ok {{ color: #3fb950; }}
.fail {{ color: #f85149; }}
.degraded {{ color: #d29922; }}
ul {{ max-width: 960px; }}
code {{ background: #21262d; padding: 2px 6px; border-radius: 4px; }}
</style>
</head>
<body>
<h1>智能选流 / Profile 运行总览 — {html.escape(cid)}</h1>
<p>生成时间（UTC）: {html.escape(_utc_iso())} · profile: <code>{html.escape(profile)}</code></p>
<p>配置: <code>{html.escape(str(cfg.get("_config_source", "")))}</code></p>
<p>整体状态: <strong>{html.escape(overall_status_zh)}</strong></p>
{mode_note_html}
<h2>本步执行结果</h2>
<table>
<thead><tr><th>#</th><th>workflow</th><th>状态</th><th>耗时(s)</th></tr></thead>
<tbody>
{"".join(rows_html)}
</tbody>
</table>
<h2>{"相关产物链接" if mode == "simple" else "详细报告链接"}</h2>
<ul>{links_li or "<li>（无）</li>"}</ul>
</body>
</html>
"""
    html_path.write_text(page, encoding="utf-8")
    return md_path, html_path


def write_plan_index(
    case_id: str,
    profile: str,
    plan: dict[str, Any],
    reporting_cfg: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """仅 plan 子命令：根据计划 JSON 写简要 MD/HTML（无执行记录）。"""
    cid = case_id.strip()
    cfg = reporting_cfg or load_workflow_smart_reporting_config(cid)
    idx = cfg.get("smart_index_output") if isinstance(cfg.get("smart_index_output"), dict) else {}
    md_name = str(idx.get("plan_report_md") or "workflow_smart_plan_report.latest.md").strip()
    html_name = str(idx.get("plan_report_html") or "workflow_smart_plan_report.latest.html").strip()

    cdir = _contracts_dir(cid)
    md_path = cdir / md_name
    html_path = cdir / html_name
    rows = plan.get("workflows") or []
    lines_md = ["| # | workflow | 中文 | tier |", "|---|----------|------|------|"]
    rows_html: list[str] = []
    for i, w in enumerate(rows, start=1):
        key = str(w.get("workflow_key", ""))
        dz = str(w.get("display_zh", ""))
        tier = str(w.get("tier", ""))
        lines_md.append(f"| {i} | `{key}` | {dz} | {tier} |")
        rows_html.append(
            f"<tr><td>{i}</td><td><code>{html.escape(key)}</code></td>"
            f"<td>{html.escape(dz)}</td><td>{html.escape(tier)}</td></tr>"
        )
    md = "\n".join(
        [
            f"# 工作流计划预览 — {cid}",
            "",
            f"- profile: `{profile}`",
            f"- 生成时间（UTC）: {_utc_iso()}",
            f"- 报告配置: `{cfg.get('_config_source', '')}`",
            "",
            *lines_md,
            "",
            "_由 `run_workflow_smart_zh plan` 自动生成。_",
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8")
    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>计划预览 — {html.escape(cid)}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#0d1117;color:#c9d1d9;}}
table{{border-collapse:collapse;width:100%;max-width:900px;}}
th,td{{border:1px solid #30363d;padding:8px;}}
th{{background:#161b22;color:#58a6ff;}}
</style></head><body>
<h1>工作流计划预览 — {html.escape(cid)}</h1>
<p>profile: <code>{html.escape(profile)}</code></p>
<table><thead><tr><th>#</th><th>workflow</th><th>中文</th><th>tier</th></tr></thead>
<tbody>{"".join(rows_html)}</tbody></table>
</body></html>"""
    html_path.write_text(page, encoding="utf-8")
    return md_path, html_path


def emit_post_run_artifacts(
    case_id: str,
    profile: str,
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    failures: list[str],
    *,
    report_level: str = "detailed",
    skip_universal: bool = False,
    case_config_path: str | None = None,
    reporting_yaml: str | None = None,
) -> dict[str, Any]:
    """跑完工作流后：按级别生成报告（detailed / simple / none）。"""
    cid = case_id.strip()
    report_level = (report_level or "detailed").strip().lower()
    if report_level not in ("detailed", "simple", "none"):
        report_level = "detailed"
    if report_level == "none":
        return {
            "case_id": cid,
            "steps": {},
            "errors": [],
            "report_level": "none",
            "report_paths": {},
        }

    rep_cfg = load_workflow_smart_reporting_config(
        cid,
        config_path=case_config_path,
        reporting_yaml=reporting_yaml,
    )

    out: dict[str, Any] = {
        "case_id": cid,
        "steps": {},
        "errors": [],
        "report_level": report_level,
        "reporting_config_source": rep_cfg.get("_config_source"),
    }

    try:
        state = build_smart_e2e_progress_state(cid, profile, plan, results, reporting_cfg=rep_cfg)
        dash = refresh_e2e_dashboards(cid, state, reporting_cfg=rep_cfg)
        out["steps"]["e2e_dashboard"] = dash
    except Exception as exc:
        out["errors"].append(f"e2e_dashboard: {exc}")

    if report_level == "simple":
        rel_paths = _build_bundle_rel_paths("simple", cid, rep_cfg, skip_universal=False)
        md_p, html_p = write_smart_run_index(
            cid,
            profile,
            plan=plan,
            results=results,
            failures=failures,
            report_paths=rel_paths,
            mode="simple",
            reporting_cfg=rep_cfg,
        )
        out["steps"]["smart_index"] = {
            "md": str(md_p.relative_to(WORKSPACE)),
            "html": str(html_p.relative_to(WORKSPACE)),
        }
        out["report_paths"] = rel_paths
        return out

    rc, tail = run_outcome_verification_report(cid, rep_cfg)
    out["steps"]["e2e_outcome_verification"] = {"returncode": rc, "tail": tail}
    if rc != 0:
        out["errors"].append(f"e2e_outcome_verification rc={rc}")

    rc2, tail2 = run_build_final_report(cid, rep_cfg)
    out["steps"]["build_final_report"] = {"returncode": rc2, "tail": tail2}
    if rc2 != 0:
        out["errors"].append(f"build_final_report rc={rc2}")

    emit_business_run_digest_step(cid, rep_cfg, report_level=report_level, out=out)

    if not skip_universal:
        rc3, tail3 = run_universal_report_html(cid, rep_cfg)
        out["steps"]["universal_report"] = {"returncode": rc3, "tail": tail3}
        if rc3 != 0:
            out["errors"].append(f"universal_report rc={rc3}")

    rel_paths = _build_bundle_rel_paths("detailed", cid, rep_cfg, skip_universal=skip_universal)

    md_p, html_p = write_smart_run_index(
        cid,
        profile,
        plan=plan,
        results=results,
        failures=failures,
        report_paths=rel_paths,
        mode="detailed",
        reporting_cfg=rep_cfg,
    )
    out["steps"]["smart_index"] = {
        "md": str(md_p.relative_to(WORKSPACE)),
        "html": str(html_p.relative_to(WORKSPACE)),
    }
    out["report_paths"] = rel_paths
    return out
