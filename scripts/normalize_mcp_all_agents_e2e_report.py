#!/usr/bin/env python3
"""从 agent_results 叶子 workflow_results 重算 totals 与根级 passed/failed/timeout/skipped。

解决历史报告中 totals 块与根级字段互相矛盾的问题（例如 v8_fast.fix 中两套数字不一致）。

说明：`mcp_all_agents_e2e_report*.json` 的生成器可能在本仓库外（例如外部 Agent 批量调 MCP）；
若无法改上游聚合逻辑，可在落盘后运行本脚本写回，或在 CI 中使用 ``--check`` 拦截漂移。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _rollup(report: dict[str, Any]) -> dict[str, int]:
    passed = failed = timeout = skipped = other = 0
    leaves = 0
    for ag in report.get("agent_results", []) or []:
        for wf in ag.get("workflow_results", []) or []:
            leaves += 1
            st = str(wf.get("status") or "").strip().lower()
            if st == "passed":
                passed += 1
            elif st == "failed":
                failed += 1
            elif st == "timeout":
                timeout += 1
            elif "skipped" in st:
                skipped += 1
            else:
                other += 1
    return {
        "workflow_calls": leaves,
        "passed": passed,
        "failed": failed,
        "timeout": timeout,
        "skipped": skipped,
        "other_status": other,
    }


def normalize_report(report: dict[str, Any]) -> dict[str, Any]:
    r = dict(report)
    agg = _rollup(r)
    r["totals"] = {
        "workflow_calls": agg["workflow_calls"],
        "passed": agg["passed"],
        "failed": agg["failed"],
        "timeout": agg["timeout"],
        "skipped": agg["skipped"],
    }
    if agg["other_status"]:
        r["totals"]["_other_status_count"] = agg["other_status"]
    r["passed"] = agg["passed"]
    r["failed"] = agg["failed"]
    r["timeout"] = agg["timeout"]
    r["skipped"] = agg["skipped"]
    return r


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("json_path", type=Path, help="mcp_all_agents_e2e_report*.json")
    p.add_argument("--dry-run", action="store_true", help="只打印重算结果，不写回")
    p.add_argument(
        "--check",
        action="store_true",
        help="若 totals/根级与叶子重算不一致则退出码 1（CI 门禁）",
    )
    args = p.parse_args()
    path: Path = args.json_path
    if not path.is_file():
        print(f"ERROR: not a file: {path}")
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("ERROR: root must be object")
        return 2
    before_totals = data.get("totals")
    out = normalize_report(data)
    root_keys = ("passed", "failed", "timeout", "skipped")
    root_match = all(data.get(k) == out.get(k) for k in root_keys)
    totals_match = data.get("totals") == out.get("totals")
    if args.check:
        if root_match and totals_match:
            print("OK: totals and root fields match leaf rollup")
            return 0
        print("MISMATCH: expected normalization would change file")
        print("before totals:", json.dumps(before_totals, ensure_ascii=False))
        print("expected totals:", json.dumps(out["totals"], ensure_ascii=False))
        print("root before:", {k: data.get(k) for k in root_keys})
        print("root expected:", {k: out.get(k) for k in root_keys})
        return 1
    print("before totals:", json.dumps(before_totals, ensure_ascii=False))
    print("after totals: ", json.dumps(out["totals"], ensure_ascii=False))
    print(
        "after root: ",
        json.dumps(
            {k: out[k] for k in root_keys if k in out},
            ensure_ascii=False,
        ),
    )
    if args.dry_run:
        return 0
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
