#!/usr/bin/env python3
"""
对照主闭环 YAML 中 quality_loop.dimensions[].artifact_hints，
检查 cases/<case_id>/contracts/（含 outcomes/*.json）下是否出现文件名线索。

支持单案例 --case-id 或 --batch 按主配置 case_selection 扫描全部案例。
stdout 单行 JSON，供 HydroDesk「产物覆盖」评审；任意案例零代码扩展。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]


def _collect_contract_rel_paths(case_id: str) -> tuple[Path, list[str]]:
    contracts = WORKSPACE / "cases" / case_id / "contracts"
    if not contracts.is_dir():
        return contracts, []
    rels: list[str] = []
    for p in sorted(contracts.iterdir()):
        if p.is_file():
            rels.append(p.name)
    out_dir = contracts / "outcomes"
    if out_dir.is_dir():
        for p in sorted(out_dir.glob("*.json")):
            if p.is_file():
                rels.append(f"outcomes/{p.name}")
    return contracts, rels


def _hint_matches_any(hint: str, rel_paths: list[str]) -> list[str]:
    h = (hint or "").strip()
    if not h:
        return []
    matched = []
    for rel in rel_paths:
        if h in rel or rel.endswith(h) or h in rel.replace("\\", "/"):
            matched.append(rel)
    return matched


def _resolve_data_pack_payload(contracts_dir: Path) -> dict[str, Any]:
    candidates = (
        "data_pack.latest.json",
        "data_pack.contract.json",
        "data_pack.v2.json",
        "data_pack.json",
    )
    for name in candidates:
        path = contracts_dir / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return {}


def _count_workflow_outputs(workflow_payload: dict[str, Any]) -> int:
    outputs = workflow_payload.get("outputs", [])
    if isinstance(outputs, list):
        return len(outputs)
    if isinstance(outputs, dict):
        return len(outputs)

    count = 0
    steps = workflow_payload.get("steps") or []
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_outputs = step.get("outputs", [])
            if isinstance(step_outputs, list):
                count += len(step_outputs)
            elif isinstance(step_outputs, dict):
                count += len(step_outputs)
    return count


def run_check(case_id: str, config_path: Path) -> dict[str, Any]:
    cfg = load_loop_yaml(WORKSPACE, config_path.resolve())
    qloop = cfg.get("quality_loop") or {}
    dimensions = qloop.get("dimensions") or []
    contracts_dir, rel_paths = _collect_contract_rel_paths(case_id)

    checks: list[dict[str, Any]] = []
    scored_satisfied = 0
    scored_total = 0
    for dim in dimensions:
        if not isinstance(dim, dict):
            continue
        hints_raw = dim.get("artifact_hints") or []
        if not isinstance(hints_raw, list):
            hints_raw = []
        hints = [str(h) for h in hints_raw if isinstance(h, str) and str(h).strip()]
        if not hints:
            checks.append(
                {
                    "key": dim.get("key"),
                    "display_zh": dim.get("display_zh"),
                    "artifact_hints": [],
                    "satisfied": None,
                    "skipped": True,
                    "matched_paths": [],
                }
            )
            continue
        all_matched: list[str] = []
        for h in hints:
            all_matched.extend(_hint_matches_any(h, rel_paths))
        seen = set()
        uniq: list[str] = []
        for m in all_matched:
            if m not in seen:
                seen.add(m)
                uniq.append(m)
        sat = len(uniq) > 0
        scored_total += 1
        if sat:
            scored_satisfied += 1
        checks.append(
            {
                "key": dim.get("key"),
                "display_zh": dim.get("display_zh"),
                "artifact_hints": hints,
                "satisfied": sat,
                "skipped": False,
                "matched_paths": uniq,
            }
        )

    workflow_run_path = contracts_dir / "workflow_run.json"
    workflow_outputs_count = 0
    if workflow_run_path.is_file():
        try:
            wr_payload = json.loads(workflow_run_path.read_text(encoding="utf-8"))
            if isinstance(wr_payload, dict):
                workflow_outputs_count = _count_workflow_outputs(wr_payload)
        except Exception:
            workflow_outputs_count = 0

    dp_payload = _resolve_data_pack_payload(contracts_dir)
    review_gates = dp_payload.get("review_gates") or {}
    data_pack_basin_validation_json = review_gates.get("basin_validation_json")
    data_pack_source_bundle_json = dp_payload.get("source_bundle_json")

    data_pack_basin_validation_exists = False
    if isinstance(data_pack_basin_validation_json, str) and data_pack_basin_validation_json.strip():
        data_pack_basin_validation_exists = (WORKSPACE / data_pack_basin_validation_json).is_file()

    source_bundle_exists = False
    if isinstance(data_pack_source_bundle_json, str) and data_pack_source_bundle_json.strip():
        source_bundle_exists = (WORKSPACE / data_pack_source_bundle_json).is_file()

    try:
        contracts_rel = str(contracts_dir.relative_to(WORKSPACE))
    except ValueError:
        contracts_rel = str(contracts_dir)
    return {
        "case_id": case_id,
        "contracts_dir": contracts_rel,
        "contracts_file_count": len(rel_paths),
        "dimension_checks": checks,
        "summary": {
            "dimensions_satisfied": scored_satisfied,
            "dimensions_total": scored_total,
            "ratio": (scored_satisfied / scored_total) if scored_total else 0.0,
            "workflow_outputs_count": workflow_outputs_count,
            "workflow_outputs_ready": workflow_outputs_count > 0,
            "data_pack_basin_validation_present": data_pack_basin_validation_exists,
            "source_bundle_present": source_bundle_exists,
            "pipeline_contract_ready": (
                workflow_outputs_count > 0
                and data_pack_basin_validation_exists
                and source_bundle_exists
            ),
        },
    }


def run_batch(config_path: Path) -> dict[str, Any]:
    cfg = load_loop_yaml(WORKSPACE, config_path.resolve())
    ids = resolve_case_ids(cfg, WORKSPACE)
    cases: list[dict[str, Any]] = []
    ratios: list[float] = []
    for cid in ids:
        one = run_check(cid, config_path)
        if not (WORKSPACE / "cases" / cid / "contracts").is_dir():
            one["error"] = "contracts_directory_missing"
        cases.append(one)
        s = one.get("summary") or {}
        if s.get("dimensions_total", 0) > 0:
            ratios.append(float(s.get("ratio") or 0.0))
    rollup = {
        "case_count": len(ids),
        "cases_with_contracts_dir": sum(1 for c in cases if not c.get("error")),
        "mean_ratio": (sum(ratios) / len(ratios)) if ratios else 0.0,
        "min_ratio": min(ratios) if ratios else 0.0,
        "per_case": [
            {
                "case_id": c["case_id"],
                "ratio": (c.get("summary") or {}).get("ratio"),
                "dimensions_satisfied": (c.get("summary") or {}).get("dimensions_satisfied"),
                "dimensions_total": (c.get("summary") or {}).get("dimensions_total"),
                "workflow_outputs_count": (c.get("summary") or {}).get("workflow_outputs_count"),
                "workflow_outputs_ready": (c.get("summary") or {}).get("workflow_outputs_ready"),
                "data_pack_basin_validation_present": (c.get("summary") or {}).get(
                    "data_pack_basin_validation_present"
                ),
                "source_bundle_present": (c.get("summary") or {}).get("source_bundle_present"),
                "pipeline_contract_ready": (c.get("summary") or {}).get("pipeline_contract_ready"),
                "contracts_file_count": c.get("contracts_file_count"),
                "error": c.get("error"),
            }
            for c in cases
        ],
    }
    try:
        cfg_rel = str(config_path.resolve().relative_to(WORKSPACE))
    except ValueError:
        cfg_rel = str(config_path.resolve())
    return {
        "batch": True,
        "config_path": cfg_rel,
        "case_ids": ids,
        "cases": cases,
        "rollup": rollup,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check case contracts against quality_loop artifact hints")
    parser.add_argument("--case-id", default="", help="单案例 id；与 --batch 二选一")
    parser.add_argument("--batch", action="store_true", help="按主配置 case_selection 扫描全部案例")
    parser.add_argument(
        "--config",
        type=Path,
        default=WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml",
    )
    args = parser.parse_args()

    if args.batch:
        payload = run_batch(args.config)
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return 0

    if not args.case_id:
        parser.error("请指定 --case-id，或使用 --batch")

    payload = run_check(args.case_id, args.config)
    if not (WORKSPACE / "cases" / args.case_id / "contracts").is_dir():
        payload["error"] = "contracts_directory_missing"
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
