"""探源 (TanYuan) — 数据勘探与知识发现引擎

HydroMind 水智工坊 · Agent #1

自动发现、评估、固化各类水利数据（6 域 28 类），
贯穿建模全生命周期，持续挖掘新数据源。

Public API
----------
    discover_all(cfg, workspace) -> DiscoveryReport
    evaluate_all(report)          -> dict[str, list[EvalResult]]
    consolidate_all(evaluated, knowledge_dir) -> dict
    run_full_pipeline(case_id)    -> dict   (all-in-one convenience)

CLI
---
    python -m hydro_model.knowledge_engine discover  --case-id daduhe
    python -m hydro_model.knowledge_engine evaluate  --case-id daduhe
    python -m hydro_model.knowledge_engine consolidate --case-id daduhe
    python -m hydro_model.knowledge_engine pipeline  --case-id daduhe

Architecture
------------
- taxonomy.py    — 6 domains, 28 data types
- registry.py    — Miner protocol + pluggable registration
- discovery.py   — recursive file scanner → miner dispatch
- evaluator.py   — 4-dimension quality scoring
- consolidator.py — incremental YAML writer
- miners/        — one module per domain (auto-registered on import)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .consolidator import consolidate, update_manifest
from .discovery import DiscoveryReport, run_discovery
from .evaluator import EvalResult, evaluate_results, summary_report
from .registry import GLOBAL_REGISTRY, MineResult, get_registry
from .taxonomy import TYPE_CATALOG, DataType, Domain

log = logging.getLogger(__name__)

# Force miner auto-registration on package import
from . import miners as _miners  # noqa: F401

__all__ = [
    "discover_all",
    "evaluate_all",
    "consolidate_all",
    "run_full_pipeline",
    "DataType",
    "Domain",
    "MineResult",
    "EvalResult",
    "DiscoveryReport",
]


# ── High-level API ──────────────────────────────────────────────────────────

def discover_all(
    cfg: dict[str, Any],
    workspace: Path,
    *,
    types_filter: list[DataType] | None = None,
) -> DiscoveryReport:
    """Scan all configured directories, extract matching data."""
    return run_discovery(cfg, workspace, types_filter=types_filter)


def evaluate_all(
    report: DiscoveryReport,
) -> dict[str, list[EvalResult]]:
    """Score every extracted result on completeness / precision / freshness / consistency."""
    return evaluate_results(report.results_by_type)


def consolidate_all(
    evaluated: dict[str, list[EvalResult]],
    knowledge_dir: Path,
) -> dict[str, Any]:
    """Write accepted results into knowledge YAML directory."""
    result = consolidate(evaluated, knowledge_dir)
    written = result.get("files_written", {})
    if written:
        update_manifest(knowledge_dir, written)
    return result


def run_full_pipeline(
    case_id: str,
    *,
    config_path: str | None = None,
    types_filter: list[DataType] | None = None,
) -> dict[str, Any]:
    """All-in-one: discover → evaluate → consolidate.

    Returns a summary dict suitable for logging or contract output.
    """
    import sys
    base_dir = Path(__file__).resolve().parents[2]
    workspace = base_dir.parent

    sys.path.insert(0, str(base_dir))
    from workflows._shared import load_case_config

    cfg = load_case_config(case_id, config_path)
    knowledge_dir = base_dir / "knowledge" / case_id

    log.info("=== Knowledge Engine: discover ===")
    report = discover_all(cfg, workspace, types_filter=types_filter)
    log.info(
        "scanned %d files, matched %d, errors %d",
        report.files_scanned, report.files_matched, len(report.errors),
    )

    log.info("=== Knowledge Engine: evaluate ===")
    evaluated = evaluate_all(report)
    quality_summary = summary_report(evaluated)
    log.info("evaluated %d types", quality_summary["total_types_evaluated"])

    log.info("=== Knowledge Engine: consolidate ===")
    consol = consolidate_all(evaluated, knowledge_dir)
    log.info("wrote %d files, accepted %d", len(consol.get("files_written", {})), consol["stats"]["accepted"])

    output_dir = Path(cfg.get("output_dir", f"cases/{case_id}/contracts"))
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_report = {
        "case_id": case_id,
        "timestamp": report.timestamp,
        "discovery": {
            "scan_dirs": report.scan_dirs,
            "files_scanned": report.files_scanned,
            "files_matched": report.files_matched,
            "coverage": report.coverage,
            "error_count": len(report.errors),
        },
        "evaluation": quality_summary,
        "consolidation": consol,
        "registry_coverage": get_registry().coverage_report(),
    }

    report_path = output_dir / "knowledge_engine_report.json"
    report_path.write_text(
        json.dumps(pipeline_report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("report → %s", report_path)

    return pipeline_report
