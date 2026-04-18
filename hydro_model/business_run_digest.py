"""业务向运行结果汇总（长文 MD/HTML）：章节与数据源由 ``workflow_smart_reporting.yaml`` 的 ``business_run_digest`` 块配置。

禁止在业务章节中硬编码案例名；路径均相对 ``cases/<case_id>/contracts/`` 或通过模板变量解析。"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

WORKSPACE = Path(__file__).resolve().parents[2]
HYDROLOGY_DIR = WORKSPACE / "Hydrology"

_HMC_SRC = WORKSPACE / "hydromind-contracts"
if _HMC_SRC.is_dir():
    _hp = str(_HMC_SRC.resolve())
    if _hp not in sys.path:
        sys.path.insert(0, _hp)

from hydromind_contracts.water_object_report import (  # noqa: E402
    get_water_object_report_conventions,
)


def _contracts_dir(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id.strip() / "contracts"


def _path_ctx(case_id: str, reporting_cfg: dict[str, Any]) -> dict[str, str]:
    cf = reporting_cfg.get("contract_filenames") if isinstance(reporting_cfg.get("contract_filenames"), dict) else {}
    uni = reporting_cfg.get("universal_report") if isinstance(reporting_cfg.get("universal_report"), dict) else {}
    cid = case_id.strip()
    return {
        "case_id": cid,
        "plan_file": str(cf.get("plan") or "workflow_smart_plan.latest.json").strip(),
        "run_summary_file": str(cf.get("run_summary") or "workflow_smart_run_summary.latest.json").strip(),
        "universal_html_file": str(uni.get("output_html_filename") or "universal_report.latest.html").strip(),
    }


def _fmt_template(tmpl: str, ctx: dict[str, str]) -> str:
    try:
        return str(tmpl).format(**ctx)
    except Exception:
        return str(tmpl)


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _get_by_dotted(data: Any, dotted: str) -> Any:
    cur: Any = data
    for part in str(dotted).split("."):
        if part == "":
            continue
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _format_template(template: str, values: dict[str, Any]) -> str:
    try:
        return str(template).format(**values).strip()
    except Exception:
        return str(template).strip()


def _maybe_rewrite_auto_summary(summary: str, default_summary: str, prefixes: list[str]) -> str:
    cleaned = summary.strip()
    if not cleaned:
        return default_summary
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            return default_summary
    return cleaned


def _render_business_scalar(value: Any, item: dict[str, Any]) -> tuple[str, bool]:
    bool_map = _string_dict(item.get("bool_map"))
    if isinstance(value, bool) and bool_map:
        mapped = bool_map.get(str(value)) or bool_map.get(str(value).lower())
        if mapped:
            return mapped, False

    value_map = _string_dict(item.get("value_map"))
    raw_key = str(value)
    if value_map and raw_key in value_map:
        return value_map[raw_key], False

    fmt = str(item.get("format") or "").strip()
    if fmt:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = None
        if fmt == "percent_0" and numeric_value is not None:
            return f"{numeric_value * 100:.0f}%", False
        if fmt == "percent_1" and numeric_value is not None:
            return f"{numeric_value * 100:.1f}%", False
        if fmt == "plain":
            return str(value), False

    return str(value), True


def _load_workflow_display_zh(reporting_cfg: dict[str, Any]) -> dict[str, str]:
    wc = reporting_cfg.get("workflow_catalog_zh") if isinstance(reporting_cfg.get("workflow_catalog_zh"), str) else ""
    rel = str(wc or "Hydrology/configs/workflow_catalog_zh.yaml").strip()
    path = Path(rel)
    if not path.is_absolute():
        path = WORKSPACE / path
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    wfs = raw.get("workflows") if isinstance(raw.get("workflows"), dict) else {}
    out: dict[str, str] = {}
    for k, v in wfs.items():
        if isinstance(v, dict):
            dz = str(v.get("display_zh") or "").strip()
            out[str(k)] = dz or str(k)
    return out


def _resolve_contract_file(contracts: Path, rel: str, ctx: dict[str, str]) -> Path:
    rel_f = _fmt_template(rel, ctx).strip()
    if not rel_f:
        return contracts / ".__missing__"
    p = Path(rel_f)
    if p.is_absolute():
        return p
    if rel_f.startswith("cases/"):
        return WORKSPACE / rel_f
    return contracts / rel_f


def _render_workflow_steps_table(
    contracts: Path,
    ctx: dict[str, str],
    block: dict[str, Any],
    labels: dict[str, str],
) -> str:
    src = str(block.get("source") or "{run_summary_file}").strip()
    path = _resolve_contract_file(contracts, src, ctx)
    data = _load_json(path)
    if not isinstance(data, dict):
        return f"_（未找到执行摘要：`{path.relative_to(WORKSPACE)}`）_\n"
    steps = data.get("steps")
    if not isinstance(steps, list):
        return "_（执行摘要中无 steps 列表）_\n"
    if not steps:
        return "_（执行摘要中无工作流步骤）_\n"
    lines = [
        "| # | 业务名称 | 工作流 | 状态 | 耗时(s) | 说明 |",
        "|---|----------|--------|------|---------|------|",
    ]
    rendered_rows = 0
    for row in steps:
        if not isinstance(row, dict):
            continue
        key = str(row.get("workflow_key") or "").strip()
        if not key:
            continue
        ok_value = row.get("ok")
        if not isinstance(ok_value, bool):
            continue
        ok = ok_value
        st = "成功" if ok else "失败"
        err = str(row.get("error") or "").strip().replace("\n", " ")[:120]
        if ok:
            err = "—"
        dz = labels.get(key, key)
        es = row.get("elapsed_sec", "")
        row_number = rendered_rows + 1
        lines.append(f"| {row_number} | {dz} | `{key}` | {st} | {es} | {err} |")
        rendered_rows += 1
    if rendered_rows == 0:
        return "_（执行摘要中无工作流步骤）_\n"
    return "\n".join(lines) + "\n"


def _strip_markdown_title(body: str) -> str:
    lines = body.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].lstrip().startswith("# "):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines)


_METADATA_LINE_RE = re.compile(r"^\*+(?:数据来源|工作流|报告生成|_?auto_generated|生成时间|来源路径)[:：].*\*+$")
_PLACEHOLDER_LINE_PREFIXES = (
    "_（未找到执行摘要：",
    "_（执行摘要中无 steps 列表）_",
    "_（执行摘要中无工作流步骤）_",
    "_（文件不存在，已跳过：",
    "_（读取失败，已跳过：",
    "_（对象报告索引不存在或无效：",
    "_（索引中无 reports）_",
    "_（nested_json_bullets 缺少 picks）_",
    "_（JSON 不存在：",
    "_（本块渲染异常：",
)
_BULLET_PLACEHOLDER_LINE_RE = re.compile(r"^- \*\*[^*]+\*\*:\s+_（无此字段）_$")
_DIGEST_BOILERPLATE_PREFIXES = (
    "- **案例**:",
    "- **用途**:",
    "- **说明**:",
    "_附录：",
)
_BLOCKQUOTE_METADATA_PATTERNS = (
    re.compile(r"^(?:\*\*案例\*\*|案例|case_id)\s*[:：]", re.IGNORECASE),
    re.compile(r"^(?:\*\*维度\*\*|维度)\s*[:：]", re.IGNORECASE),
    re.compile(r"^(?:\*\*生成时间\*\*|生成时间|generated_at)\s*[:：]", re.IGNORECASE),
    re.compile(r"^(?:\*\*工作流\*\*|工作流|workflow)\s*[:：]", re.IGNORECASE),
    re.compile(r"^(?:\*\*来源路径\*\*|来源路径)\s*[:：]", re.IGNORECASE),
    re.compile(r"^自动生成(?:\s*\|.*)?$", re.IGNORECASE),
    re.compile(r"^_?系统说明_?$", re.IGNORECASE),
    re.compile(r"^_?auto_generated\s*[:：].*$", re.IGNORECASE),
    re.compile(r"^_?本报告由.+自动生成_?$", re.IGNORECASE),
)


def _workspace_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE))
    except ValueError:
        return str(path.name)



def _strip_trailing_metadata_lines(body: str) -> str:
    lines = body.splitlines()
    while lines:
        tail = lines[-1].strip()
        if not tail:
            lines.pop()
            continue
        if _METADATA_LINE_RE.match(tail):
            lines.pop()
            continue
        break
    return "\n".join(lines)



def _normalize_markdown_heading_text(text: str) -> str:
    text = re.sub(r"\s+#+\s*$", "", text.strip())
    return re.sub(r"\s+", " ", text)



def _exclude_markdown_headings(body: str, excluded_headings: list[str]) -> str:
    excluded = {
        _normalize_markdown_heading_text(str(item))
        for item in excluded_headings
        if str(item).strip()
    }
    if not excluded:
        return body
    lines = body.splitlines()
    kept: list[str] = []
    dropping = False
    current_level = 0
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            heading_level = len(match.group(1))
            heading_text = _normalize_markdown_heading_text(match.group(2))
            if heading_text in excluded:
                dropping = True
                current_level = heading_level
                continue
            if dropping and heading_level <= current_level:
                dropping = False
                current_level = 0
        if not dropping:
            kept.append(line)
    return "\n".join(kept)



def _truncate_markdown_preserving_structure(body: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(body) <= max_chars:
        return body, False
    kept: list[str] = []
    total = 0
    in_fence = False
    for line in body.splitlines():
        addition = len(line) + (1 if kept else 0)
        if kept and total + addition > max_chars:
            break
        kept.append(line)
        total += addition
        if line.strip().startswith("```"):
            in_fence = not in_fence
    truncated = len("\n".join(kept)) < len(body)
    if in_fence:
        kept.append("```")
    return "\n".join(kept).rstrip(), truncated



def _is_metadata_blockquote_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith(">"):
        return False
    content = stripped.lstrip(">").strip()
    if not content:
        return True
    normalized = content.strip()
    return any(pattern.match(normalized) for pattern in _BLOCKQUOTE_METADATA_PATTERNS)



def _strip_leading_blockquote_metadata_lines(body: str) -> str:
    lines = body.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and _is_metadata_blockquote_line(lines[0]):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines)



def _render_markdown_include(
    contracts: Path,
    ctx: dict[str, str],
    block: dict[str, Any],
) -> str:
    rel = str(block.get("path") or "").strip()
    max_chars = int(block.get("max_chars") or 0)
    path = _resolve_contract_file(contracts, rel, ctx)
    display_path = _workspace_relative_path(path)
    if not path.is_file():
        return f"_（文件不存在，已跳过：`{display_path}`）_\n"
    try:
        body = path.read_text(encoding="utf-8")
    except OSError:
        return f"_（读取失败，已跳过：`{display_path}`）_\n"
    if bool(block.get("strip_title")):
        body = _strip_markdown_title(body)
    if bool(block.get("strip_leading_blockquote_metadata")):
        body = _strip_leading_blockquote_metadata_lines(body)
    exclude_headings = block.get("exclude_headings")
    if isinstance(exclude_headings, list) and exclude_headings:
        body = _exclude_markdown_headings(body, [str(item) for item in exclude_headings])
    if bool(block.get("strip_trailing_metadata")):
        body = _strip_trailing_metadata_lines(body)
    body = body.strip()
    note = ""
    body, truncated = _truncate_markdown_preserving_structure(body, max_chars)
    if truncated:
        body = body.rstrip() + "\n\n…（已按配置截断，见完整文件链接下方）\n"
        note = f"\n_完整路径：`{display_path}`_\n"
    return body + "\n" + note if note else body + "\n"


def _norm_report_path(p: str, contracts: Path) -> Path:
    """索引中的路径可能是绝对路径、相对 contracts、或相对 object_reports/。"""
    raw = (p or "").strip()
    if not raw:
        return contracts / ".__missing__"
    path = Path(raw)
    if path.is_file():
        return path
    if not path.is_absolute():
        cand = contracts / path
        if cand.is_file():
            return cand
        cand2 = contracts / "object_reports" / path.name
        if cand2.is_file():
            return cand2
    return path


def _render_object_reports_index(
    contracts: Path,
    ctx: dict[str, str],
    block: dict[str, Any],
    *,
    digest: dict[str, Any],
) -> str:
    rel = str(block.get("index_path") or "object_reports/standard_object_reports.index.json").strip()
    max_reports = int(block.get("max_reports") or 200)
    skip_sample = bool(block.get("skip_sample_files", True))
    path = _resolve_contract_file(contracts, rel, ctx)
    data = _load_json(path)
    if not isinstance(data, dict):
        return f"_（对象报告索引不存在或无效：`{path.relative_to(WORKSPACE)}`）_\n"
    reports = data.get("reports")
    if not isinstance(reports, list):
        return "_（索引中无 reports）_\n"

    object_type_labels = _string_dict(digest.get("object_type_labels_zh"))
    object_cfg = digest.get("object_reports") if isinstance(digest.get("object_reports"), dict) else {}
    type_heading_template = str(object_cfg.get("type_heading_template_zh") or "对象类型：{object_type_label}").strip()
    item_heading_template = str(object_cfg.get("item_heading_template_zh") or "{display_name}").strip()
    item_heading_fallback_template = str(
        object_cfg.get("item_heading_fallback_template_zh") or "{object_type_label} `{object_id}`"
    ).strip()
    default_summary = str(object_cfg.get("default_summary_zh") or "本轮运行结果报告").strip()
    findings_heading = str(object_cfg.get("findings_heading_zh") or "要点").strip()
    json_label = str(object_cfg.get("json_label_zh") or "结果文件").strip()
    markdown_label = str(object_cfg.get("markdown_label_zh") or "阅读版说明").strip()
    trim_auto_summary_prefixes = _string_list(object_cfg.get("trim_auto_summary_prefixes")) or ["自动生成的 "]

    by_type: dict[str, list[dict[str, Any]]] = {}
    count = 0
    for ent in reports:
        if count >= max_reports:
            break
        if not isinstance(ent, dict):
            continue
        jp = str(ent.get("json_path") or "").strip()
        if skip_sample and (".sample." in jp or "sample" in Path(jp).name.lower()):
            continue
        ot = str(ent.get("object_type") or "Unknown")
        by_type.setdefault(ot, []).append(ent)
        count += 1

    lines: list[str] = []
    for ot in sorted(by_type.keys()):
        object_type_label = object_type_labels.get(ot) or ot
        lines.append(f"### {_format_template(type_heading_template, {'object_type': ot, 'object_type_label': object_type_label})}\n")
        for ent in by_type[ot]:
            oid = str(ent.get("object_id") or "").strip()
            jp = _norm_report_path(str(ent.get("json_path") or ""), contracts)
            mp = _norm_report_path(str(ent.get("markdown_path") or ""), contracts)
            payload = _load_json(jp) if jp.is_file() else None
            summary = ""
            findings: list[str] = []
            display_name = str(ent.get("display_name") or "").strip()
            if isinstance(payload, dict):
                display_name = str(payload.get("display_name") or display_name).strip()
                summary = _maybe_rewrite_auto_summary(
                    str(payload.get("summary") or "").strip(),
                    default_summary,
                    trim_auto_summary_prefixes,
                )
                fnd = payload.get("findings")
                if isinstance(fnd, list):
                    findings = [str(x) for x in fnd[:5] if str(x).strip()]
            heading_values = {
                'display_name': display_name,
                'object_id': oid,
                'object_type': ot,
                'object_type_label': object_type_label,
            }
            item_heading = _format_template(item_heading_template, heading_values)
            if not item_heading:
                item_heading = _format_template(item_heading_fallback_template, heading_values)

            rel_j = jp.resolve() if jp.is_file() else jp
            try:
                rel_j_s = str(rel_j.relative_to(WORKSPACE))
            except ValueError:
                rel_j_s = str(rel_j)
            lines.append(f"#### {item_heading}\n")
            if summary:
                lines.append(f"{summary}\n")
            if findings:
                lines.append(f"**{findings_heading}：**\n")
                for finding in findings:
                    lines.append(f"- {finding}\n")
            lines.append(f"- {json_label}: `{rel_j_s}`\n")
            if mp.is_file():
                try:
                    rel_m = str(mp.resolve().relative_to(WORKSPACE))
                except ValueError:
                    rel_m = str(mp.resolve())
                lines.append(f"- {markdown_label}: `{rel_m}`\n")
            lines.append("\n")
    if count >= max_reports:
        lines.append(f"\n_（已达 max_reports={max_reports}，其余对象见索引文件）_\n")
    return "".join(lines)


def _render_nested_json_bullets(
    contracts: Path,
    ctx: dict[str, str],
    block: dict[str, Any],
) -> str:
    rel = str(block.get("path") or "").strip()
    picks = block.get("picks")
    if not isinstance(picks, list):
        return "_（nested_json_bullets 缺少 picks）_\n"
    path = _resolve_contract_file(contracts, rel, ctx)
    data = _load_json(path)
    if data is None:
        return f"_（JSON 不存在：`{path.relative_to(WORKSPACE)}`）_\n"
    lines: list[str] = []
    for item in picks:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("json_path") or "?").strip()
        jpath = str(item.get("json_path") or "").strip()
        val = _get_by_dotted(data, jpath)
        if val is None:
            lines.append(f"- **{label}**: _（无此字段）_\n")
        elif isinstance(val, (dict, list)):
            lines.append(f"- **{label}**:\n\n```json\n{json.dumps(val, ensure_ascii=False, indent=2)[:4000]}\n```\n")
        else:
            rendered_value, render_as_code = _render_business_scalar(val, item)
            if render_as_code:
                lines.append(f"- **{label}**: `{rendered_value}`\n")
            else:
                lines.append(f"- **{label}**: {rendered_value}\n")
    return "\n".join(lines) + "\n"


def _render_static_note(block: dict[str, Any]) -> str:
    body = block.get("body_zh") or block.get("body")
    if isinstance(body, list):
        return "\n".join(str(x) for x in body) + "\n"
    return str(body or "").strip() + ("\n" if str(body or "").strip() else "")



def _is_placeholder_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if any(stripped.startswith(prefix) for prefix in _PLACEHOLDER_LINE_PREFIXES):
        return True
    return bool(_BULLET_PLACEHOLDER_LINE_RE.match(stripped))



def _is_placeholder_only_markdown(markdown: str) -> bool:
    meaningful_lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    if not meaningful_lines:
        return True
    content_lines = [
        line
        for line in meaningful_lines
        if not line.startswith("#")
        and line != "---"
        and not any(line.startswith(prefix) for prefix in _DIGEST_BOILERPLATE_PREFIXES)
    ]
    if not content_lines:
        return True
    return all(_is_placeholder_line(line) for line in content_lines)


def _render_topology_standard_object_matrix(
    contracts: Path,
    ctx: dict[str, str],
    block: dict[str, Any],
    *,
    digest: dict[str, Any],
) -> str:
    """复用 ``contract_adapters.export_standard_object_report_samples`` 写入的契约级索引（contracts 根目录）。"""
    rel = str(block.get("index_path") or "standard_object_reports.index.json").strip()
    path = _resolve_contract_file(contracts, rel, ctx)
    data = _load_json(path)
    type_labels: dict[str, str] = {}
    bl = block.get("type_labels_zh")
    if isinstance(bl, dict):
        type_labels = {str(k): str(v) for k, v in bl.items()}
    gl = digest.get("object_type_labels_zh") if isinstance(digest, dict) else None
    if isinstance(gl, dict):
        merged = {str(k): str(v) for k, v in gl.items()}
        merged.update(type_labels)
        type_labels = merged

    conventions = get_water_object_report_conventions()
    custom_order = block.get("canonical_object_types_order")
    if isinstance(custom_order, list) and custom_order:
        order = [str(x) for x in custom_order if str(x) in conventions]
        for k in conventions:
            if k not in order:
                order.append(k)
    else:
        order = list(conventions.keys())

    reports_by_type: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict):
        for item in data.get("reports") or []:
            if isinstance(item, dict) and item.get("object_type"):
                reports_by_type[str(item["object_type"])] = item

    lines = [
        "| 契约对象类型 | 业务对照 | 覆盖状态 | 对象 ID | JSON | Markdown | 说明 |",
        "|---|---|---|---|---|---|---|",
    ]
    for ot in order:
        conv = conventions.get(ot)
        biz = type_labels.get(ot) or (conv.display_name if conv else ot)
        item = reports_by_type.get(ot, {})
        st = str(item.get("status") or "—")
        oid = str(item.get("object_id") or "—")
        jp = str(item.get("json_path") or "—")
        mp = str(item.get("markdown_path") or "—")
        note = "—"
        if st == "missing":
            note = str(item.get("reason") or item.get("default_strategy") or "—")
        elif st == "available":
            note = str(item.get("display_name") or "契约样本已落盘")
        lines.append(f"| `{ot}` | {biz} | {st} | `{oid}` | `{jp}` | `{mp}` | {note} |")
    lines.append("")
    if isinstance(data, dict) and block.get("list_source_artifacts"):
        src = data.get("source_artifacts")
        if isinstance(src, dict):
            lines.append("**索引所依据的源产物（节选）**\n")
            for k, v in list(src.items())[:15]:
                lines.append(f"- `{k}` → `{v}`\n")
            lines.append("")
    rel_idx = _workspace_relative_path(path)
    lines.append(
        "_对象契约覆盖表展示六类标准对象当前是否已具备样本与说明；"
        f"如需刷新，请重新生成对象拓扑汇编。索引：`{rel_idx}`_\n"
    )
    return "\n".join(lines)


_BLOCK_RENDERERS = {
    "workflow_steps_table": _render_workflow_steps_table,
    "markdown_include": _render_markdown_include,
    "object_reports_index": _render_object_reports_index,
    "nested_json_bullets": _render_nested_json_bullets,
    "topology_standard_object_matrix": _render_topology_standard_object_matrix,
}


def build_business_digest_markdown(
    case_id: str,
    reporting_cfg: dict[str, Any],
) -> tuple[str, list[str]]:
    """根据 reporting_cfg['business_run_digest'] 生成 Markdown 正文与警告列表。"""
    warnings: list[str] = []
    dig = reporting_cfg.get("business_run_digest")
    if not isinstance(dig, dict):
        raise ValueError("business_run_digest 配置缺失")

    sections = dig.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("business_run_digest.sections 为空")

    cid = case_id.strip()
    contracts = _contracts_dir(cid)
    ctx = _path_ctx(cid, reporting_cfg)
    labels = _load_workflow_display_zh(reporting_cfg)

    title = str(dig.get("title_zh") or "案例运行结果汇总（业务版）").strip()
    subtitle = str(dig.get("subtitle_zh") or "").strip()
    purpose = str(dig.get("purpose_zh") or "面向业务会商、结果复核与交付阅读的摘要汇编。")
    lines: list[str] = [
        f"# {title}",
        "",
        f"- **案例**: `{cid}`",
        f"- **用途**: {purpose}",
    ]
    if subtitle:
        lines.append(f"- **说明**: {subtitle}")
    lines.append("")

    has_effective_data_block = False
    has_data_block_configured = False

    for sec in sections:
        if not isinstance(sec, dict):
            continue
        sec_id = str(sec.get("id") or "").strip()
        sec_title = str(sec.get("title_zh") or sec_id or "章节").strip()
        intro = str(sec.get("intro_zh") or "").strip()
        lines.append(f"## {sec_title}\n")
        if intro:
            lines.append(f"{intro}\n\n")
        blocks = sec.get("blocks")
        if not isinstance(blocks, list):
            warnings.append(f"章节 {sec_id or sec_title} 无 blocks")
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type") or "").strip()
            if btype == "static_note":
                lines.append(_render_static_note(block))
                continue
            has_data_block_configured = True
            fn = _BLOCK_RENDERERS.get(btype)
            if fn is None:
                warnings.append(f"未知 block 类型: {btype}")
                continue
            try:
                rendered = ""
                if btype == "workflow_steps_table":
                    rendered = fn(contracts, ctx, block, labels)
                elif btype in ("topology_standard_object_matrix", "object_reports_index"):
                    rendered = fn(contracts, ctx, block, digest=dig)
                elif btype == "nested_json_bullets":
                    rendered = fn(contracts, ctx, block)
                elif btype == "markdown_include":
                    rendered = fn(contracts, ctx, block)
                lines.append(rendered)
                if rendered.strip() and not _is_placeholder_only_markdown(rendered):
                    has_effective_data_block = True
            except Exception as exc:
                warnings.append(f"block {btype} 渲染失败: {exc}")
                lines.append(f"_（本块渲染异常：{exc}）_\n")

    lines.append("---\n")
    lines.append(
        "_附录：各工作流完整产出仍以 `cases/{case_id}/contracts/` 下 JSON/Markdown/HTML 为准；"
        "本页为可配置的汇编视图。_\n".replace("{case_id}", cid)
    )
    markdown = "\n".join(lines).strip()
    if not markdown or markdown == f"# {title}":
        raise ValueError("business_run_digest 生成结果为空")
    if has_data_block_configured and not has_effective_data_block:
        raise ValueError("business_run_digest 生成结果为空")
    return markdown + "\n", warnings


def markdown_to_html_page(title: str, md_body: str) -> str:
    """极简 Markdown → HTML（标题、表格、列表、代码块、段落）。"""
    parts = re.split(r"(?m)^```(?:\w*)?\s*$", md_body)
    html_chunks: list[str] = []
    for i, chunk in enumerate(parts):
        if i % 2 == 1:
            html_chunks.append("<pre><code>" + html.escape(chunk.rstrip("\n")) + "</code></pre>")
        else:
            html_chunks.append(_md_fragment_to_html(chunk))
    nav_ids: list[tuple[str, str]] = []
    # 从 md_body 提取 ## 标题做侧栏（粗略）
    for m in re.finditer(r"(?m)^## (.+)$", md_body):
        t = m.group(1).strip()
        sid = "sec-" + re.sub(r"[^\w\u4e00-\u9fff]+", "-", t.lower()).strip("-")[:40]
        nav_ids.append((sid, t))
    nav_li = "".join(f'<li><a href="#{html.escape(sid)}">{html.escape(tt)}</a></li>' for sid, tt in nav_ids)
    body = "\n".join(html_chunks)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
body {{ font-family: "PingFang SC", system-ui, sans-serif; margin: 0; background: #0d1117; color: #c9d1d9; display: flex; }}
nav.side {{ width: 220px; flex-shrink: 0; border-right: 1px solid #30363d; padding: 16px; position: sticky; top: 0; align-self: flex-start; max-height: 100vh; overflow: auto; background: #161b22; }}
nav.side ul {{ list-style: none; padding: 0; margin: 0; font-size: 13px; }}
nav.side a {{ color: #58a6ff; text-decoration: none; display: block; padding: 4px 0; }}
nav.side a:hover {{ text-decoration: underline; }}
main {{ flex: 1; padding: 28px 40px; max-width: 1100px; }}
h1 {{ color: #58a6ff; font-size: 1.75rem; }}
h2 {{ color: #4CAF50; margin-top: 2rem; padding-bottom: 0.35rem; border-bottom: 1px solid #30363d; }}
h3 {{ color: #c9d1d9; margin-top: 1.25rem; }}
h4 {{ color: #8b949e; margin-top: 1rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 13px; }}
th, td {{ border: 1px solid #30363d; padding: 8px 10px; text-align: left; vertical-align: top; }}
th {{ background: #161b22; color: #58a6ff; }}
pre {{ background: #161b22; border: 1px solid #30363d; padding: 12px; overflow: auto; font-size: 12px; }}
code {{ background: #21262d; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
pre code {{ background: transparent; padding: 0; }}
p {{ margin: 0.5rem 0; line-height: 1.6; }}
ul {{ margin: 0.5rem 0 0.5rem 1.2rem; }}
.digest-p {{ white-space: pre-wrap; }}
</style>
</head>
<body>
<nav class="side"><ul>{nav_li or "<li>（无章节导航）</li>"}</ul></nav>
<main>
<h1>{html.escape(title)}</h1>
{body}
</main>
</body>
</html>
"""


def _md_fragment_to_html(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    table_buf: list[str] = []
    list_buf: list[str] = []

    def flush_table() -> None:
        nonlocal table_buf
        if not table_buf:
            return
        rows_html: list[str] = []
        body_rows = list(table_buf)
        if len(body_rows) >= 2 and re.match(r"^\|[\s\-:|]+\|$", body_rows[1].strip()):
            body_rows = [body_rows[0]] + body_rows[2:]
        for ri, row in enumerate(body_rows):
            cells = [c.strip() for c in row.strip().split("|") if c.strip() != ""]
            if not cells:
                continue
            tag = "th" if ri == 0 else "td"
            rows_html.append(
                "<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>"
            )
        if rows_html:
            out.append("<table>" + "".join(rows_html) + "</table>")
        table_buf = []

    def flush_list() -> None:
        nonlocal list_buf
        if list_buf:
            out.append("<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in list_buf) + "</ul>")
            list_buf = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("|") and "|" in stripped[1:]:
            flush_list()
            table_buf.append(line)
            i += 1
            continue
        else:
            flush_table()

        if stripped.startswith("#### "):
            flush_list()
            out.append(f"<h4>{html.escape(stripped[5:])}</h4>")
        elif stripped.startswith("### "):
            flush_list()
            out.append(f"<h3>{html.escape(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            flush_list()
            title = stripped[3:].strip()
            sid = "sec-" + re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.lower()).strip("-")[:40]
            out.append(f'<h2 id="{html.escape(sid)}">{html.escape(title)}</h2>')
        elif stripped.startswith("# "):
            flush_list()
            out.append(f"<h1>{html.escape(stripped[2:])}</h1>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            list_buf.append(stripped[2:].strip())
        elif stripped == "":
            flush_list()
            i += 1
            continue
        else:
            flush_list()
            # 行内 `code` 与 **bold**
            seg = html.escape(line)
            seg = re.sub(r"`([^`]+)`", lambda m: "<code>" + html.escape(m.group(1)) + "</code>", seg)
            seg = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", seg)
            if seg.strip():
                out.append(f"<p>{seg}</p>")
        i += 1
    flush_table()
    flush_list()
    return "\n".join(out)


def write_business_run_digest(
    case_id: str,
    reporting_cfg: dict[str, Any],
) -> tuple[Path, Path, list[str]]:
    """写入 contracts 下 MD/HTML；返回路径与警告。"""
    dig = reporting_cfg.get("business_run_digest")
    if not isinstance(dig, dict):
        raise ValueError("business_run_digest 未配置")

    cid = case_id.strip()
    contracts = _contracts_dir(cid)
    contracts.mkdir(parents=True, exist_ok=True)

    out_md = str(dig.get("output_md") or "business_run_digest.latest.md").strip()
    out_html = str(dig.get("output_html") or "business_run_digest.latest.html").strip()

    md_body, warnings = build_business_digest_markdown(cid, reporting_cfg)
    md_path = contracts / out_md
    md_path.write_text(md_body, encoding="utf-8")

    title = str(dig.get("title_zh") or "案例运行结果汇总").strip() + f" — {cid}"
    html_page = markdown_to_html_page(title, md_body)
    html_path = contracts / out_html
    html_path.write_text(html_page, encoding="utf-8")
    return md_path, html_path, warnings
