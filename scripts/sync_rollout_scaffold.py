#!/usr/bin/env python3
"""将标准 rollout scaffold 合并到既有案例入口文件。

只同步通用的 workflow/review/release scaffold 字段，保留每个案例已有的
描述、原始数据入口、补充链接和其他特定元数据。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from scaffold_new_case import (  # noqa: E402
    STANDARD_WORKFLOW_TARGETS,
    STANDARD_WORKFLOW_VALIDATION_PRIORITY,
    rollout_links,
    rollout_release_handoff,
    rollout_shell_entrypoints,
    rollout_workflow_baseline,
)

WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CASES = [
    "jiaodongtiaoshui",
    "xuhonghe",
    "yinchuojiliao",
    "zhongxian",
    "yjdt",
]


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return payload


def _merge_manifest(case_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    merged = dict(manifest)
    merged["workflow_targets"] = list(STANDARD_WORKFLOW_TARGETS)
    merged["workflow_validation_priority"] = list(STANDARD_WORKFLOW_VALIDATION_PRIORITY)
    merged["workflow_baseline"] = rollout_workflow_baseline()
    merged["shell_entrypoints"] = rollout_shell_entrypoints(case_id)
    merged["release_handoff"] = rollout_release_handoff(case_id)
    return merged


def _merge_links(case_id: str, manifest: dict[str, Any], links_payload: dict[str, Any]) -> dict[str, Any]:
    existing_links = (links_payload.get("links") or {}) if isinstance(links_payload, dict) else {}
    raw_case_root = existing_links.get("raw_case_root") or {}
    raw_root = str(raw_case_root.get("path") or ((manifest.get("locations") or {}).get("raw_root") or ""))
    raw_root_purpose = str(raw_case_root.get("purpose") or "原始资料入口")
    merged_links = dict(existing_links)
    merged_links.update(rollout_links(case_id, raw_root=raw_root, raw_root_purpose=raw_root_purpose))
    return {"links": merged_links}


def sync_case(case_id: str, *, dry_run: bool) -> dict[str, Any]:
    case_root = WORKSPACE / "cases" / case_id
    manifest_path = case_root / "manifest.yaml"
    links_path = case_root / "links.yaml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    if not links_path.is_file():
        raise FileNotFoundError(f"missing links: {links_path}")

    manifest = _load_yaml(manifest_path)
    merged_manifest = _merge_manifest(case_id, manifest)
    links_payload = _load_yaml(links_path)
    merged_links = _merge_links(case_id, merged_manifest, links_payload)

    if not dry_run:
        manifest_path.write_text(yaml.safe_dump(merged_manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
        links_path.write_text(yaml.safe_dump(merged_links, allow_unicode=True, sort_keys=False), encoding="utf-8")

    return {
        "case_id": case_id,
        "manifest": str(manifest_path.relative_to(WORKSPACE)),
        "links": str(links_path.relative_to(WORKSPACE)),
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync reusable rollout scaffold into existing case manifests/links")
    parser.add_argument("--case-id", action="append", default=[], help="可重复；默认同步五个非 daduhe rollout 案例")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    case_ids = [str(item).strip() for item in (args.case_id or []) if str(item).strip()] or list(DEFAULT_CASES)
    rows = [sync_case(case_id, dry_run=args.dry_run) for case_id in case_ids]
    print(json.dumps({"ok": True, "cases": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
