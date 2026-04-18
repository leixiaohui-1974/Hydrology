"""Human-readable workflow reports alongside outcome contracts.

See docs/2026-04-13_水网对象报告模板与工作流矩阵深化设计.md and
docs/architecture/agent-system/2026-04-13_水网报告矩阵_BRIDGE融合实施规划.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workflows.outcome_contract import WORKSPACE, _utc_now


def _contracts_dir(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts"


def _flatten_dimension_lines(dimensions: dict[str, Any], *keys: str) -> list[str]:
    lines: list[str] = []
    for key in keys:
        items = dimensions.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            metric = item.get("metric") or item.get("name") or key
            value = item.get("value")
            ev = item.get("evidence_path") or item.get("evidence")
            extra = f"（证据: `{ev}`）" if ev else ""
            lines.append(f"- **{metric}**: {value}{extra}")
    return lines


def _extract_executed_models(result: Any) -> list[dict[str, Any]]:
    """Best-effort extraction of model/parser/solver identifiers from workflow result."""
    found: list[dict[str, Any]] = []
    if not isinstance(result, dict):
        return found

    def add(registry: str, key: str, params: Any = None) -> None:
        entry: dict[str, Any] = {"registry": registry, "key": str(key)}
        if params is not None:
            entry["params_digest"] = str(params)[:500]
        found.append(entry)

    for k in ("model_type", "parser_type", "solver", "algorithm", "routing_model", "runoff_model"):
        v = result.get(k)
        if v is not None and str(v).strip():
            add("workflow_result", k, v)

    cfg = result.get("config")
    if isinstance(cfg, dict):
        for k in ("model_type", "parser_type", "seq_len", "horizon"):
            v = cfg.get(k)
            if v is not None:
                add("config", k, v)

    nested = result.get("forecast") or result.get("model")
    if isinstance(nested, dict):
        for k in ("model_type", "name"):
            v = nested.get(k)
            if v is not None:
                add("nested", k, v)

    seen: set[tuple[str, str]] = set()
    uniq: list[dict[str, Any]] = []
    for e in found:
        t = (e["registry"], e["key"])
        if t in seen:
            continue
        seen.add(t)
        uniq.append(e)
    return uniq


def _model_entry_key(entry: dict[str, Any]) -> tuple[str, str]:
    return (str(entry.get("registry", "")), str(entry.get("key", "")))


def merge_executed_models_from_result(raw_result: Any) -> tuple[list[dict[str, Any]], list[Any]]:
    """
    Merge workflow-declared executed_models (preferred) with heuristic extraction.
    Returns (merged_models, candidate_models_not_run).
    """
    explicit: list[dict[str, Any]] = []
    candidates_not_run: list[Any] = []
    if isinstance(raw_result, dict):
        em = raw_result.get("executed_models")
        if isinstance(em, list):
            explicit = [x for x in em if isinstance(x, dict)]
        cnr = raw_result.get("candidate_models_not_run")
        if isinstance(cnr, list):
            candidates_not_run = list(cnr)
    heuristic = _extract_executed_models(raw_result) if isinstance(raw_result, dict) else []
    seen = {_model_entry_key(e) for e in explicit}
    merged: list[dict[str, Any]] = list(explicit)
    for h in heuristic:
        k = _model_entry_key(h)
        if k in seen:
            continue
        seen.add(k)
        merged.append(h)
    return merged, candidates_not_run


def _format_input_asset_lines(raw_result: Any) -> list[str]:
    if not isinstance(raw_result, dict):
        return []
    assets = raw_result.get("report_input_assets")
    lines: list[str] = []
    if isinstance(assets, list):
        for item in assets[:60]:
            if isinstance(item, dict):
                p = item.get("path") or item.get("ref") or ""
                role = item.get("role") or ""
                note = item.get("note") or ""
                frag = " ".join(s for s in (str(role), str(note)) if s).strip()
                if frag:
                    lines.append(f"- `{p}` — {frag}" if p else f"- {frag}")
                elif p:
                    lines.append(f"- `{p}`")
            elif isinstance(item, str) and item.strip():
                lines.append(f"- `{item.strip()}`")
        return lines
    refs = raw_result.get("input_asset_refs")
    if isinstance(refs, list):
        for r in refs[:60]:
            if isinstance(r, str) and r.strip():
                lines.append(f"- `{r.strip()}`")
    return lines


def build_workflow_report_markdown(
    *,
    case_id: str,
    workflow_key: str,
    outcome_contract: dict[str, Any],
    executed_models: list[dict[str, Any]],
    candidate_models_not_run: list[Any],
    raw_result: Any,
) -> str:
    status = str(outcome_contract.get("status", ""))
    template_id = str(outcome_contract.get("template_id", ""))
    oc_path = str(outcome_contract.get("contract_path", ""))
    gen_at = str(outcome_contract.get("generated_at", ""))
    dims = outcome_contract.get("dimensions") or {}
    if not isinstance(dims, dict):
        dims = {}

    business_lines = _flatten_dimension_lines(dims, "business")
    process_lines = _flatten_dimension_lines(dims, "process")
    method_lines = _flatten_dimension_lines(dims, "method")
    acc_lines = _flatten_dimension_lines(dims, "accuracy")
    concl_lines = _flatten_dimension_lines(dims, "conclusion")
    rec_lines = _flatten_dimension_lines(dims, "recommendation")

    artifacts = outcome_contract.get("artifacts") or []
    art_lines: list[str] = []
    if isinstance(artifacts, list):
        for a in artifacts[:80]:
            if isinstance(a, dict) and a.get("path"):
                mark = "✓" if a.get("exists") else "✗"
                art_lines.append(f"- `{a['path']}` {mark}")

    model_lines: list[str] = []
    for m in executed_models:
        ver = f" v{m['version']}" if m.get("version") is not None else ""
        tail = f": {m['params_digest']}" if m.get("params_digest") else ""
        model_lines.append(
            f"- `{m.get('registry', '')}` / `{m.get('key', '')}`{ver}{tail}"
        )
    if not model_lines:
        model_lines.append("_（本次运行未从结果中解析到 model_type/parser 等字段；详见 outcome JSON）_")

    c_lines: list[str] = []
    for item in candidate_models_not_run[:25]:
        if isinstance(item, dict):
            c_lines.append(f"- {json.dumps(item, ensure_ascii=False)[:200]}")
        else:
            c_lines.append(f"- `{item}`")
    if len(candidate_models_not_run) > 25:
        c_lines.append(f"_… 另有 {len(candidate_models_not_run) - 25} 条未展示_")

    input_lines = _format_input_asset_lines(raw_result)

    metrics = outcome_contract.get("metrics") or {}
    metrics_lines: list[str] = []
    if isinstance(metrics, dict) and metrics:
        for k, v in list(metrics.items())[:40]:
            metrics_lines.append(f"- `{k}`: {v}")

    def or_placeholder(lines: list[str], placeholder: str) -> list[str]:
        return lines if lines else [placeholder]

    sections = [
        f"# 工作流报告：`{workflow_key}`",
        "",
        f"**案例**: `{case_id}`  ",
        f"**状态**: `{status}`  ",
        f"**模板**: `{template_id}`  ",
        f"**生成时间（UTC）**: `{gen_at}`  ",
        "",
        "## 1. 背景与目标",
        "",
        *or_placeholder(business_lines, "_（见 outcome 契约 business 维度）_"),
        "",
        "## 2. 输出证据（artifacts）",
        "",
        *or_placeholder(art_lines, "_（无 artifacts 条目；见 outcome JSON）_"),
        "",
        "## 3. 输入资产",
        "",
        *(
            input_lines
            if input_lines
            else ["_（工作流未显式提供 `report_input_assets` / `input_asset_refs`；详见 outcome JSON）_"]
        ),
        "",
        "## 4. 选用模型与算法",
        "",
        *model_lines,
        "",
        "## 4.1 配置候选但未运行",
        "",
        *(
            c_lines
            if c_lines
            else ["_（无 `candidate_models_not_run` 或未配置）_"]
        ),
        "",
        "## 5. 执行过程与配置摘要",
        "",
        *or_placeholder(process_lines, "_（见 outcome process 维度）_"),
        *or_placeholder(method_lines, "_（见 outcome method 维度）_"),
        "",
        "## 6. 结果与指标",
        "",
        *or_placeholder(acc_lines, "_（见 outcome accuracy 维度）_"),
        *metrics_lines,
        "",
        "## 7. 结论与建议",
        "",
        *or_placeholder(concl_lines, "_（见 outcome conclusion 维度）_"),
        *or_placeholder(rec_lines, "_（见 outcome recommendation 维度）_"),
        "",
        "## 8. 追溯",
        "",
        f"- Outcome 契约: `{oc_path}`",
        f"- 报告 JSON: `cases/{case_id}/contracts/{workflow_key}_report.latest.json`",
        "",
        "---",
        "",
        "_auto_generated: workflow human report (emit_workflow_report)_",
    ]
    return "\n".join(sections)


def _raw_result_from_outcome(outcome_contract: dict[str, Any]) -> Any:
    dims = outcome_contract.get("dimensions")
    if not isinstance(dims, dict):
        return None
    result_obj = dims.get("result")
    if not isinstance(result_obj, list) or not result_obj:
        return None
    first = result_obj[0]
    if isinstance(first, dict):
        return first.get("value")
    return None


def emit_workflow_report(
    *,
    case_id: str,
    workflow_key: str,
    outcome_contract: dict[str, Any],
) -> dict[str, Any]:
    """
    Write `{workflow_key}_report.latest.md` and `.json` under cases/{case_id}/contracts/.
    Overwrites latest pointers each run.
    """
    case_id = str(case_id).strip()
    workflow_key = str(workflow_key).strip()
    if not case_id or not workflow_key:
        raise ValueError("case_id and workflow_key are required")

    raw_result = _raw_result_from_outcome(outcome_contract)
    executed_models, candidate_models_not_run = merge_executed_models_from_result(raw_result)
    md_body = build_workflow_report_markdown(
        case_id=case_id,
        workflow_key=workflow_key,
        outcome_contract=outcome_contract,
        executed_models=executed_models,
        candidate_models_not_run=candidate_models_not_run,
        raw_result=raw_result,
    )

    cdir = _contracts_dir(case_id)
    cdir.mkdir(parents=True, exist_ok=True)
    md_path = cdir / f"{workflow_key}_report.latest.md"
    json_path = cdir / f"{workflow_key}_report.latest.json"

    oc_rel = str(
        outcome_contract.get("contract_path", "")
        or f"cases/{case_id}/contracts/outcomes/{workflow_key}.latest.json"
    )
    gen = outcome_contract.get("generated_at") or _utc_now()
    run_id = f"{workflow_key}_{gen}"
    val_errs = outcome_contract.get("validation_errors")
    gaps: list[Any] = val_errs if isinstance(val_errs, list) else []
    report_doc: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_type": "workflow_human_report",
        "workflow_key": workflow_key,
        "case_id": case_id,
        "status": outcome_contract.get("status"),
        "run_id": run_id,
        "workflow_run_id": run_id,
        "outcome_contract_path": oc_rel,
        "dependencies": [oc_rel],
        "markdown_path": str(md_path.relative_to(WORKSPACE)),
        "generated_at": _utc_now(),
        "_auto_generated": True,
        "executed_models": executed_models,
        "template_id": outcome_contract.get("template_id"),
        "gaps": gaps,
    }
    if candidate_models_not_run:
        report_doc["candidate_models_not_run"] = candidate_models_not_run
    if gaps:
        report_doc["outcome_validation_errors"] = gaps

    md_path.write_text(md_body, encoding="utf-8")
    json_path.write_text(json.dumps(report_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    report_doc["written_paths"] = {
        "markdown": str(md_path.relative_to(WORKSPACE)),
        "json": str(json_path.relative_to(WORKSPACE)),
    }
    return report_doc


def write_report_emit_error_sidecar(
    *,
    case_id: str,
    workflow_key: str,
    error_message: str,
    exc_type: str | None = None,
) -> Path | None:
    """
    Minimal contract when emit_workflow_report fails (e.g. success path with dict result
    uses report_emit_error on result; failure path before re-raise uses this file).
    """
    case_id = str(case_id).strip()
    workflow_key = str(workflow_key).strip()
    if not case_id or not workflow_key:
        return None
    cdir = _contracts_dir(case_id)
    cdir.mkdir(parents=True, exist_ok=True)
    path = cdir / f"{workflow_key}_report_emit_error.latest.json"
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_type": "workflow_report_emit_error",
        "case_id": case_id,
        "workflow_key": workflow_key,
        "error": str(error_message)[:2000],
        "exc_type": exc_type,
        "generated_at": _utc_now(),
        "_auto_generated": True,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
