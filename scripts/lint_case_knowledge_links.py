#!/usr/bin/env python3
"""
案例知识壳层 lint（Karpathy「LLM Knowledge Bases」式：Markdown 为可审计层）。

- 校验 hydrodesk_shell.knowledge_lint.required_paths 存在（{case_id} 占位）
- 报告 raw_dir_rel 是否存在（require_raw_dir=true 时缺失则判失败）
- 扫描配置中的 Markdown 文件，校验 **相对路径** 链接目标是否可达（绝对路径 / URL 仅跳过，避免误报本机路径）

stdout 单行 JSON；与主闭环 YAML 同源，零案例硬编码。

仓库根:
  python3 Hydrology/scripts/lint_case_knowledge_links.py --batch
  python3 Hydrology/scripts/lint_case_knowledge_links.py --case-id daduhe
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]

DEFAULT_LOOP = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"

DEFAULT_KNOWLEDGE_LINT: dict[str, Any] = {
    "raw_dir_rel": "cases/{case_id}/ingest/raw",
    "require_raw_dir": False,
    "required_paths": [
        "cases/{case_id}/manifest.yaml",
        "cases/{case_id}/contracts",
    ],
    "markdown_link_scan_globs": [
        "cases/{case_id}/README.md",
        "cases/{case_id}/contracts/*.md",
        "cases/{case_id}/ingest/raw/**/*.md",
    ],
}

MD_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _subst(case_id: str, template: str) -> str:
    return (template or "").replace("{case_id}", case_id)


def resolve_knowledge_lint(cfg: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_KNOWLEDGE_LINT)
    shell = cfg.get("hydrodesk_shell")
    if isinstance(shell, dict):
        kl = shell.get("knowledge_lint")
        if isinstance(kl, dict):
            for key, val in kl.items():
                if key in ("required_paths", "markdown_link_scan_globs") and isinstance(val, list):
                    merged[key] = [str(x) for x in val if isinstance(x, str) and str(x).strip()]
                elif val is not None:
                    merged[key] = val
    return merged


def _parse_link_target(raw: str) -> str:
    """取 ](...) 内路径，去掉 <> 包裹与可选 title。"""
    t = (raw or "").strip()
    if not t:
        return ""
    if t.startswith("<") and ">" in t:
        t = t[1 : t.index(">")]
    return t.split()[0].strip() if t else ""


def _should_skip_target(t: str) -> bool:
    if not t or t.startswith("#"):
        return True
    low = t.lower()
    if low.startswith("http://") or low.startswith("https://") or low.startswith("mailto:"):
        return True
    if low.startswith("data:") or low.startswith("javascript:"):
        return True
    return False


def _is_absolute_filesystem(t: str) -> bool:
    p = Path(t)
    return p.is_absolute()


def scan_markdown_links(workspace: Path, md_path: Path) -> list[dict[str, Any]]:
    """仅校验相对路径链接。"""
    ws = workspace.resolve()
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError as e:
        return [{"error": "read_failed", "detail": str(e)}]

    out: list[dict[str, Any]] = []
    base = md_path.parent
    for m in MD_LINK_RE.finditer(text):
        raw_inner = m.group(1) or ""
        target = _parse_link_target(raw_inner)
        if _should_skip_target(target):
            continue
        if _is_absolute_filesystem(target):
            out.append(
                {
                    "target": target,
                    "kind": "skipped_absolute",
                    "line_hint": text[: m.start()].count("\n") + 1,
                }
            )
            continue
        # 相对仓库根（以 / 开头但不是绝对盘符）在 Markdown 中少见；按相对当前文件解析
        resolved = (base / target).resolve()
        try:
            resolved.relative_to(ws)
        except ValueError:
            out.append(
                {
                    "target": target,
                    "kind": "broken_relative",
                    "resolved": str(resolved),
                    "reason": "outside_workspace",
                    "line_hint": text[: m.start()].count("\n") + 1,
                }
            )
            continue
        if resolved.is_file() or resolved.is_dir():
            out.append(
                {
                    "target": target,
                    "kind": "ok",
                    "resolved": str(resolved.relative_to(ws)),
                }
            )
        else:
            out.append(
                {
                    "target": target,
                    "kind": "broken_relative",
                    "resolved": str(resolved.relative_to(ws)),
                    "reason": "not_found",
                    "line_hint": text[: m.start()].count("\n") + 1,
                }
            )
    return out


def _expand_scan_files(workspace: Path, case_id: str, globs: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[str] = set()
    for g in globs:
        pattern = _subst(case_id, g).replace("\\", "/")
        for p in sorted(workspace.glob(pattern)):
            if not p.is_file():
                continue
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            files.append(p)
    return files


def _check_required_paths(workspace: Path, case_id: str, templates: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tmpl in templates:
        rel = _subst(case_id, tmpl).replace("\\", "/")
        path = workspace / rel
        ok = path.is_file() or path.is_dir()
        rows.append({"path": rel, "ok": ok})
    return rows


def run_one_case(workspace: Path, case_id: str, config_path: Path) -> dict[str, Any]:
    ws = workspace.resolve()
    cfg = load_loop_yaml(ws, config_path.resolve())
    kl = resolve_knowledge_lint(cfg)
    cid = (case_id or "").strip()
    raw_rel = _subst(cid, str(kl.get("raw_dir_rel") or "")).replace("\\", "/")
    raw_path = ws / raw_rel if raw_rel else None
    raw_exists = raw_path.is_dir() if raw_path else False
    require_raw = bool(kl.get("require_raw_dir"))

    req = _check_required_paths(ws, cid, list(kl.get("required_paths") or []))
    req_ok = all(r["ok"] for r in req)

    md_files = _expand_scan_files(ws, cid, list(kl.get("markdown_link_scan_globs") or []))
    link_results: list[dict[str, Any]] = []
    broken = 0
    for mf in md_files:
        entries = scan_markdown_links(ws, mf)
        rel_self = str(mf.resolve().relative_to(ws))
        for e in entries:
            if e.get("kind") == "broken_relative":
                broken += 1
        link_results.append({"file": rel_self, "entries": entries})

    raw_fail = require_raw and not raw_exists
    case_ok = req_ok and not raw_fail and broken == 0

    return {
        "case_id": cid,
        "ok": case_ok,
        "raw_dir_rel": raw_rel,
        "raw_dir_exists": raw_exists,
        "required_paths": req,
        "markdown_files_scanned": [str(p.resolve().relative_to(ws)) for p in md_files],
        "broken_relative_link_count": broken,
        "markdown_links": link_results,
        "errors": [
            *(["required_path_missing"] if not req_ok else []),
            *(["raw_dir_required_missing"] if raw_fail else []),
            *(["broken_markdown_links"] if broken > 0 else []),
        ],
    }


def run_batch(workspace: Path, config_path: Path) -> dict[str, Any]:
    ws = workspace.resolve()
    cfg = load_loop_yaml(ws, config_path.resolve())
    ids = resolve_case_ids(cfg, ws)
    cases = [run_one_case(ws, cid, config_path) for cid in ids]
    rollup_ok = all(c.get("ok") for c in cases)
    broken_total = sum(int(c.get("broken_relative_link_count") or 0) for c in cases)
    try:
        cfg_rel = str(config_path.resolve().relative_to(ws))
    except ValueError:
        cfg_rel = str(config_path.resolve())
    return {
        "ok": rollup_ok,
        "batch": True,
        "config_path": cfg_rel.replace("\\", "/"),
        "case_ids": ids,
        "cases": cases,
        "rollup": {
            "case_count": len(cases),
            "cases_ok": sum(1 for c in cases if c.get("ok")),
            "broken_relative_links": broken_total,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace", type=Path, default=WORKSPACE)
    parser.add_argument("--config", type=Path, default=DEFAULT_LOOP)
    parser.add_argument("--case-id", default="", help="单案例；与 --batch 二选一")
    parser.add_argument("--batch", action="store_true", help="按 case_selection 扫描全部案例")
    args = parser.parse_args()

    ws = args.workspace.resolve()

    if args.batch:
        payload = run_batch(ws, args.config.resolve())
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return 0 if payload.get("ok") else 1

    if not args.case_id.strip():
        parser.error("请指定 --case-id 或使用 --batch")

    payload = run_one_case(ws, args.case_id.strip(), args.config.resolve())
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
