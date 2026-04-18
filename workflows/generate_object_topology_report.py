#!/usr/bin/env python3
"""Generate standard object report samples from existing pipedream topology/outcomes."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]


def _load_contract_adapters_module():
    pipedream_root = WORKSPACE / "pipedream-hydrology-integration-lab"
    if str(pipedream_root) not in sys.path:
        sys.path.insert(0, str(pipedream_root))
    module_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "contract_adapters.py"
    spec = importlib.util.spec_from_file_location("pipedream_contract_adapters", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_combined_markdown(case_id: str, index_payload: dict[str, Any]) -> str:
    available = [item for item in index_payload.get("reports", []) if item.get("status") == "available"]
    missing = [item for item in index_payload.get("reports", []) if item.get("status") == "missing"]

    lines = [
        f"# {case_id} 标准对象报告样本与拓扑适配汇总",
        "",
        "## 已生成样本",
        "",
    ]
    if available:
        for item in available:
            lines.append(
                f"- {item['object_type']}: {item['display_name']} -> {item['json_path']} / {item['markdown_path']}"
            )
    else:
        lines.append("- 当前未生成对象样本。")

    lines.extend(["", "## 缺省策略", ""])
    if missing:
        for item in missing:
            lines.append(
                f"- {item['object_type']}: {item['default_strategy']} ({item['reason']})"
            )
    else:
        lines.append("- 六类对象均已生成样本。")

    lines.extend(["", "## 说明", ""])
    lines.append("- 数据仅复用现有 topology / outcomes / basin 报告，不修改 HydroClaude。")
    lines.append("- 该汇总用于 Task 3 的最小可落地样本生成与后续 ReviewDelivery 对接。")
    lines.append("")
    return "\n".join(lines)


def generate_object_topology_report(
    case_id: str,
    contracts_dir: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Path]:
    target_contracts_dir = contracts_dir or (WORKSPACE / "cases" / case_id / "contracts")
    target_output_path = output_path or (target_contracts_dir / "combined_object_topology_report.md")

    adapters = _load_contract_adapters_module()
    object_outputs = adapters.export_standard_object_report_samples(case_id, output_dir=target_contracts_dir)
    index_payload = _load_json(object_outputs["object_report_index"])

    target_output_path.parent.mkdir(parents=True, exist_ok=True)
    target_output_path.write_text(
        _render_combined_markdown(case_id=case_id, index_payload=index_payload),
        encoding="utf-8",
    )

    return {
        "combined_report": target_output_path,
        "object_report_index": object_outputs["object_report_index"],
        "object_report_summary": object_outputs["object_report_summary"],
        "object_report_dir": object_outputs["object_report_dir"],
    }


def run_object_topology_report(
    case_id: str,
    *,
    contracts_dir: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """供 ``run_workflow(\"object_topology_report\", case_id=...)`` 调用。"""
    cid = str(case_id or "").strip()
    cdir = Path(contracts_dir) if contracts_dir else None
    outp = Path(output_path) if output_path else None
    result = generate_object_topology_report(case_id=cid, contracts_dir=cdir, output_path=outp)
    root = WORKSPACE

    def _rel(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(root))
        except ValueError:
            return str(p.resolve())

    return {
        "ok": True,
        "combined_report": _rel(result["combined_report"]),
        "object_report_index": _rel(result["object_report_index"]),
        "object_report_summary": _rel(result["object_report_summary"]),
        "object_report_dir": _rel(result["object_report_dir"]),
        "outcome_status": "completed",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate standard object report samples from existing topology/outcomes.")
    parser.add_argument("--case-id", required=True, help="Case ID (e.g., daduhe)")
    parser.add_argument("--contracts-dir", help="Override contracts output directory")
    parser.add_argument("--output", help="Override combined markdown output path")
    args = parser.parse_args()

    result = generate_object_topology_report(
        case_id=args.case_id,
        contracts_dir=Path(args.contracts_dir) if args.contracts_dir else None,
        output_path=Path(args.output) if args.output else None,
    )
    print(f"combined_report: {result['combined_report']}")
    print(f"object_report_index: {result['object_report_index']}")
    print(f"object_report_summary: {result['object_report_summary']}")


if __name__ == "__main__":
    main()
