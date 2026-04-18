"""探源 (TanYuan) — CLI entry point.

HydroMind 水智工坊 · Agent #1 · 数据勘探与知识发现

Usage:
    python -m hydro_model.knowledge_engine pipeline  --case-id daduhe
    python -m hydro_model.knowledge_engine discover  --case-id daduhe
    python -m hydro_model.knowledge_engine evaluate  --case-id daduhe
    python -m hydro_model.knowledge_engine consolidate --case-id daduhe
    python -m hydro_model.knowledge_engine coverage
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_pipeline(args: argparse.Namespace) -> None:
    from hydro_model.knowledge_engine import run_full_pipeline
    result = run_full_pipeline(args.case_id, config_path=args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_discover(args: argparse.Namespace) -> None:
    from workflows._shared import load_case_config
    from hydro_model.knowledge_engine import discover_all

    workspace = BASE_DIR.parent
    cfg = load_case_config(args.case_id, args.config)
    report = discover_all(cfg, workspace)
    summary = {
        "files_scanned": report.files_scanned,
        "files_matched": report.files_matched,
        "coverage": report.coverage,
        "errors": report.errors[:10],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def cmd_evaluate(args: argparse.Namespace) -> None:
    from workflows._shared import load_case_config
    from hydro_model.knowledge_engine import discover_all, evaluate_all
    from hydro_model.knowledge_engine.evaluator import summary_report

    workspace = BASE_DIR.parent
    cfg = load_case_config(args.case_id, args.config)
    report = discover_all(cfg, workspace)
    evaluated = evaluate_all(report)
    print(json.dumps(summary_report(evaluated), ensure_ascii=False, indent=2, default=str))


def cmd_consolidate(args: argparse.Namespace) -> None:
    from workflows._shared import load_case_config
    from hydro_model.knowledge_engine import (
        consolidate_all, discover_all, evaluate_all,
    )

    workspace = BASE_DIR.parent
    cfg = load_case_config(args.case_id, args.config)
    knowledge_dir = BASE_DIR / "knowledge" / args.case_id
    report = discover_all(cfg, workspace)
    evaluated = evaluate_all(report)
    result = consolidate_all(evaluated, knowledge_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_coverage(args: argparse.Namespace) -> None:
    from hydro_model.knowledge_engine import get_registry
    report = get_registry().coverage_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tanyuan",
        description="探源 — 数据勘探与知识发现 (HydroMind 水智工坊)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func in [
        ("pipeline", cmd_pipeline),
        ("discover", cmd_discover),
        ("evaluate", cmd_evaluate),
        ("consolidate", cmd_consolidate),
    ]:
        p = sub.add_parser(name)
        p.add_argument("--case-id", required=True)
        p.add_argument("--config", default=None)
        p.set_defaults(func=func)

    p_cov = sub.add_parser("coverage")
    p_cov.set_defaults(func=cmd_coverage)

    args = parser.parse_args()
    _setup_logging(args.verbose)
    args.func(args)


if __name__ == "__main__":
    main()
