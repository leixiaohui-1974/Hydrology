#!/usr/bin/env python3
"""探源 (TanYuan) — Source 源注册与共享 Wiki 投影

HydroMind 水智工坊 · Agent #1

将原始资料目录收敛为 case 级确定性 contract，
并把摘要增量投影到共享 `wiki/` 页面。
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from workflows._shared import (
    default_graphify_case_sidecar_dir,
    load_case_config,
    load_case_manifest,
)
from workflows.run_knowledge_miner import _load_graphify_sidecar
from workflows.run_knowledge_registry import (
    DATA_EXTENSIONS,
    _file_hash,
    _infer_contributor,
    _infer_data_category,
)


BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent
WIKI_DIR = WORKSPACE / "wiki"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE))
    except ValueError:
        return str(path)


def _safe_load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_workspace_path(raw: str | Path) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (WORKSPACE / candidate).resolve()


def _safe_stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def _mtime_iso(stat_result: os.stat_result | None) -> str | None:
    if stat_result is None:
        return None
    return datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")


def _ensure_wiki_file(path: Path, *, name: str, description: str, type_: str, tags: list[str], title: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = [
        "---",
        f"name: {name}",
        f"description: {description}",
        f"type: {type_}",
        f"tags: [{', '.join(tags)}]",
        f"created: {_utc_date()}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    path.write_text("\n".join(frontmatter), encoding="utf-8")


def _upsert_marked_block(path: Path, block_id: str, title: str, body: str) -> None:
    start_marker = f"<!-- {block_id}:START -->"
    end_marker = f"<!-- {block_id}:END -->"
    block = f"{start_marker}\n{title}\n\n{body.rstrip()}\n{end_marker}"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}", re.DOTALL)
    if pattern.search(content):
        new_content = pattern.sub(block, content)
    else:
        joiner = "\n\n" if content.strip() else ""
        new_content = f"{content.rstrip()}{joiner}{block}\n"
    path.write_text(new_content, encoding="utf-8")


def _append_log(case_id: str, pages: list[str], summary_path: str) -> None:
    path = WIKI_DIR / "log.md"
    _ensure_wiki_file(
        path,
        name="wiki-log",
        description="共享 wiki 运维日志——记录 ingest、索引、会话同步等自动维护动作",
        type_="log",
        tags=["wiki", "log", "operations", "omc"],
        title="Wiki Operation Log",
    )
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = (
        f"\n## [{stamp}] source-sync\n"
        f"- **Case:** {case_id}\n"
        f"- **Pages:** {', '.join(pages)}\n"
        f"- **Summary:** Synced `{summary_path}` into shared wiki projections\n"
    )
    path.write_text(path.read_text(encoding="utf-8") + entry, encoding="utf-8")


def _manifest_raw_root(payload: dict[str, Any]) -> str:
    locations = payload.get("locations") or {}
    raw_root = str(locations.get("raw_root") or payload.get("raw_root") or "").strip()
    return raw_root


def _select_wxq_roots(cfg: dict[str, Any], manifest_payload: dict[str, Any]) -> tuple[str, list[Path]]:
    raw_root = _manifest_raw_root(manifest_payload)
    roots: list[Path] = []
    seen: set[str] = set()

    candidates: list[str] = []
    if raw_root:
        candidates.append(raw_root)
    candidates.extend(str(item) for item in cfg.get("scan_dirs", []) if str(item).strip())

    for raw in candidates:
        resolved = _resolve_workspace_path(raw)
        try:
            rel = resolved.relative_to(WORKSPACE)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] == "wxq-1d" and resolved.exists():
            key = str(resolved)
            if key not in seen:
                seen.add(key)
                roots.append(resolved)

    return raw_root, roots


def _build_file_entry(path: Path, *, source_root: Path) -> dict[str, Any]:
    stat_result = _safe_stat(path)
    rel = _rel(path)
    entry: dict[str, Any] = {
        "path": rel,
        "name": path.name,
        "source_root": _rel(source_root),
        "type": DATA_EXTENSIONS.get(path.suffix.lower(), "unknown"),
        "category": _infer_data_category(path),
        "contributor": _infer_contributor(rel),
        "size_kb": round((stat_result.st_size if stat_result else 0) / 1024, 1),
        "mtime": _mtime_iso(stat_result),
        "fingerprint": (
            f"{stat_result.st_size}:{stat_result.st_mtime_ns}" if stat_result is not None else "missing"
        ),
        "registered_at": _now_iso(),
    }
    return entry


def _scan_wxq_files(roots: list[Path]) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith((".", "__pycache__", "node_modules", ".git"))]
            current_root = Path(dirpath)
            for filename in filenames:
                file_path = current_root / filename
                if file_path.name.startswith("."):
                    continue
                rel = _rel(file_path)
                files.setdefault(rel, _build_file_entry(file_path, source_root=root))
    return dict(sorted(files.items(), key=lambda item: item[0]))


def _build_explicit_ref(path_str: str) -> dict[str, Any]:
    resolved = _resolve_workspace_path(path_str)
    stat_result = _safe_stat(resolved)
    payload = {
        "path": _rel(resolved),
        "exists": resolved.exists(),
        "size_kb": round((stat_result.st_size if stat_result else 0) / 1024, 1),
        "mtime": _mtime_iso(stat_result),
        "fingerprint": f"{stat_result.st_size}:{stat_result.st_mtime_ns}" if stat_result else "missing",
    }
    if resolved.exists():
        payload["content_hash"] = _file_hash(resolved)
    return payload


def _existing_contract_paths(case_id: str) -> dict[str, str]:
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    candidates = {
        "deep_asset_recording": contracts_dir / "deep_asset_recording.latest.json",
        "knowledge_mining": contracts_dir / "knowledge_mining.latest.json",
        "knowledge_registry": WORKSPACE / "cases" / case_id / "knowledge_registry.json",
    }
    present: dict[str, str] = {}
    for key, path in candidates.items():
        if path.exists():
            present[key] = _rel(path)
    return present


def build_source_registry(
    case_id: str,
    *,
    config_path: str | None = None,
    graphify_sidecar_dir: str | None = None,
) -> dict[str, Any]:
    cfg = load_case_config(case_id, config_path)
    _, manifest_payload = load_case_manifest(case_id)
    raw_root, wxq_roots = _select_wxq_roots(cfg, manifest_payload)
    if not raw_root and not wxq_roots:
        raise ValueError(f"{case_id} missing wxq raw_root/scan_dirs configuration")

    files = _scan_wxq_files(wxq_roots)
    type_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    contributors: set[str] = set()
    for item in files.values():
        item_type = str(item.get("type") or "unknown")
        item_category = str(item.get("category") or "unknown")
        type_counts[item_type] = type_counts.get(item_type, 0) + 1
        category_counts[item_category] = category_counts.get(item_category, 0) + 1
        contributor = str(item.get("contributor") or "").strip()
        if contributor:
            contributors.add(contributor)

    topology_paths = [_build_explicit_ref(str(p)) for p in cfg.get("topology_json_paths", []) if str(p).strip()]
    sqlite_paths = [_build_explicit_ref(str(p)) for p in cfg.get("sqlite_paths", []) if str(p).strip()]

    key_assets: dict[str, dict[str, Any]] = {}
    for key, path_str in (
        ("dem", str(cfg.get("dem_path") or "").strip()),
        ("river_network", str(cfg.get("river_network_path") or "").strip()),
        ("source_bundle", str(cfg.get("source_bundle_path") or "").strip()),
    ):
        if path_str:
            key_assets[key] = _build_explicit_ref(path_str)

    if topology_paths:
        key_assets["primary_topology"] = topology_paths[0]
    if sqlite_paths:
        key_assets["primary_sqlite"] = sqlite_paths[0]

    resolved_graphify_dir = graphify_sidecar_dir or str(default_graphify_case_sidecar_dir(case_id))
    graphify_sidecar = _load_graphify_sidecar(resolved_graphify_dir)

    registry = {
        "_meta": {
            "case_id": case_id,
            "built_at": _now_iso(),
            "schema_version": "1.0",
            "workflow": "source_sync",
        },
        "sources": {
            "manifest_raw_root": raw_root,
            "scan_roots": [_rel(path) for path in wxq_roots],
            "config_scan_dirs": [str(item) for item in cfg.get("scan_dirs", []) if str(item).strip()],
            "graphify_sidecar_dir": (
                graphify_sidecar.get("sidecar_dir") if graphify_sidecar else _rel(default_graphify_case_sidecar_dir(case_id))
            ),
        },
        "summary": {
            "total_files": len(files),
            "type_counts": dict(sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))),
            "category_counts": dict(sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))),
            "contributors": sorted(contributors),
            "topology_model_count": len(topology_paths),
            "sqlite_count": len(sqlite_paths),
            "graphify_status": graphify_sidecar.get("status", "missing") if graphify_sidecar else "missing",
        },
        "files": files,
        "topology_models": topology_paths,
        "sqlite_databases": sqlite_paths,
        "key_assets": key_assets,
        "related_contracts": _existing_contract_paths(case_id),
        "graphify_sidecar": graphify_sidecar,
    }
    return registry


def build_source_summary(registry: dict[str, Any]) -> dict[str, Any]:
    case_id = str(registry.get("_meta", {}).get("case_id", "unknown"))
    graphify_sidecar = registry.get("graphify_sidecar") or {}
    return {
        "case_id": case_id,
        "generated_at": _now_iso(),
        "raw_root": registry.get("sources", {}).get("manifest_raw_root"),
        "scan_roots": registry.get("sources", {}).get("scan_roots", []),
        "total_files": registry.get("summary", {}).get("total_files", 0),
        "type_counts": registry.get("summary", {}).get("type_counts", {}),
        "category_counts": registry.get("summary", {}).get("category_counts", {}),
        "contributors": registry.get("summary", {}).get("contributors", []),
        "topology_models": [
            {
                "path": item.get("path"),
                "content_hash": item.get("content_hash"),
                "size_kb": item.get("size_kb"),
            }
            for item in registry.get("topology_models", [])
        ],
        "sqlite_databases": [
            {
                "path": item.get("path"),
                "content_hash": item.get("content_hash"),
                "size_kb": item.get("size_kb"),
            }
            for item in registry.get("sqlite_databases", [])
        ],
        "key_assets": registry.get("key_assets", {}),
        "related_contracts": registry.get("related_contracts", {}),
        "graphify_sidecar": {
            "status": graphify_sidecar.get("status", "missing"),
            "summary": graphify_sidecar.get("graph_report_summary", {}),
            "graph_run_summary": graphify_sidecar.get("graph_run_summary", {}),
        },
    }


def _top_counts(counts: dict[str, int], limit: int = 5) -> str:
    if not counts:
        return "none"
    items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return " · ".join(f"{key} {value}" for key, value in items)


def _render_data_resources_block(summary: dict[str, Any]) -> str:
    case_id = summary["case_id"]
    display_name = case_id
    total_files = summary.get("total_files", 0)
    graphify_status = summary.get("graphify_sidecar", {}).get("status", "missing")
    lines = [
        f"- `{case_id}` | raw_root: `{summary.get('raw_root') or 'missing'}` | files: {total_files} | graphify: `{graphify_status}`",
        f"- 类型分布: {_top_counts(summary.get('type_counts', {}))}",
        f"- 类别分布: {_top_counts(summary.get('category_counts', {}))}",
    ]
    if summary.get("topology_models"):
        topology = " · ".join(f"`{item['path']}`" for item in summary["topology_models"][:3])
        lines.append(f"- 拓扑模型: {topology}")
    if summary.get("sqlite_databases"):
        sqlite = " · ".join(f"`{item['path']}`" for item in summary["sqlite_databases"][:3])
        lines.append(f"- SQLite: {sqlite}")
    lines.append(f"- 摘要合约: `cases/{case_id}/contracts/source_summary.latest.json`")
    lines.append(f"- 兼容摘要合约: `cases/{case_id}/contracts/wxq_source_summary.latest.json`")
    return "\n".join(lines)


def _render_cases_deep_dive_block(summary: dict[str, Any]) -> str:
    case_id = summary["case_id"]
    lines = [
        f"- `raw_root`: `{summary.get('raw_root') or 'missing'}`",
        f"- `source_registry.latest.json`: 已生成",
        f"- `source_summary.latest.json`: 已生成",
        f"- `wxq_source_registry.latest.json`: 兼容输出",
        f"- `wxq_source_summary.latest.json`: 兼容输出",
        f"- 主要类型: {_top_counts(summary.get('type_counts', {}), limit=4)}",
        f"- 主要类别: {_top_counts(summary.get('category_counts', {}), limit=4)}",
        f"- graphify sidecar: `{summary.get('graphify_sidecar', {}).get('status', 'missing')}`",
    ]
    related = summary.get("related_contracts", {})
    if related:
        refs = " · ".join(f"`{path}`" for path in related.values())
        lines.append(f"- 关联 contracts: {refs}")
    return "\n".join(lines)


def sync_wiki_projection(case_id: str, summary: dict[str, Any]) -> list[str]:
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    data_resources = WIKI_DIR / "data-resources.md"
    cases_deep_dive = WIKI_DIR / "cases-deep-dive.md"

    _ensure_wiki_file(
        data_resources,
        name="data-resources",
        description="数据资源与基础设施——wxq-1d原始资料/configs配置/pipedream求解器/算法引擎数据层",
        type_="architecture",
        tags=["data", "wxq-1d", "configs", "pipedream", "Hydrology", "数据资源"],
        title="数据资源与基础设施",
    )
    _ensure_wiki_file(
        cases_deep_dive,
        name="cases-deep-dive",
        description="六案例 contracts、graphify、data source 深入索引",
        type_="architecture",
        tags=["cases", "contracts", "wxq", "graphify"],
        title="案例深入索引",
    )

    _upsert_marked_block(
        data_resources,
        f"SOURCE_SYNC:{case_id}",
        f"### {case_id} · Auto Source Summary",
        _render_data_resources_block(summary),
    )
    _upsert_marked_block(
        cases_deep_dive,
        f"SOURCE_SYNC:{case_id}",
        f"### {case_id} · Source Sync",
        _render_cases_deep_dive_block(summary),
    )

    pages = ["wiki/data-resources.md", "wiki/cases-deep-dive.md"]
    _append_log(case_id, pages, f"cases/{case_id}/contracts/source_summary.latest.json")
    return pages


def run_source_sync(
    case_id: str,
    *,
    config_path: str | None = None,
    graphify_sidecar_dir: str | None = None,
    skip_wiki_sync: bool = False,
) -> dict[str, Any]:
    print(f"\n[Source Sync] 构建: {case_id}")
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    registry = build_source_registry(
        case_id,
        config_path=config_path,
        graphify_sidecar_dir=graphify_sidecar_dir,
    )
    summary = build_source_summary(registry)

    registry_path = contracts_dir / "source_registry.latest.json"
    summary_path = contracts_dir / "source_summary.latest.json"
    legacy_registry_path = contracts_dir / "wxq_source_registry.latest.json"
    legacy_summary_path = contracts_dir / "wxq_source_summary.latest.json"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    legacy_registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    legacy_summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    pages: list[str] = []
    if not skip_wiki_sync:
        pages = sync_wiki_projection(case_id, summary)

    result = {
        "case_id": case_id,
        "generated_at": _now_iso(),
        "registry_path": _rel(registry_path),
        "summary_path": _rel(summary_path),
        "legacy_registry_path": _rel(legacy_registry_path),
        "legacy_summary_path": _rel(legacy_summary_path),
        "raw_root": summary.get("raw_root"),
        "total_files": summary.get("total_files", 0),
        "graphify_sidecar": summary.get("graphify_sidecar", {}),
        "wiki_sync": {
            "enabled": not skip_wiki_sync,
            "pages": pages,
        },
        "outcome_status": "completed",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return result


def build_wxq_source_registry(
    case_id: str,
    *,
    config_path: str | None = None,
    graphify_sidecar_dir: str | None = None,
) -> dict[str, Any]:
    """兼容别名，保留给旧调用方。"""
    return build_source_registry(
        case_id,
        config_path=config_path,
        graphify_sidecar_dir=graphify_sidecar_dir,
    )


def build_wxq_source_summary(registry: dict[str, Any]) -> dict[str, Any]:
    """兼容别名，保留给旧调用方。"""
    return build_source_summary(registry)


def run_wxq_sync(
    case_id: str,
    *,
    config_path: str | None = None,
    graphify_sidecar_dir: str | None = None,
    skip_wiki_sync: bool = False,
) -> dict[str, Any]:
    """兼容别名，保留给旧调用方。"""
    return run_source_sync(
        case_id,
        config_path=config_path,
        graphify_sidecar_dir=graphify_sidecar_dir,
        skip_wiki_sync=skip_wiki_sync,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Source 源注册与共享 Wiki 投影")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", help="YAML 配置路径")
    parser.add_argument("--graphify-sidecar-dir", help="可选 Graphify sidecar 目录（默认自动探测）")
    parser.add_argument("--skip-wiki-sync", action="store_true", help="仅写 contracts，不更新 wiki")
    args = parser.parse_args()
    run_source_sync(
        args.case_id,
        config_path=args.config,
        graphify_sidecar_dir=args.graphify_sidecar_dir,
        skip_wiki_sync=args.skip_wiki_sync,
    )


if __name__ == "__main__":
    main()
