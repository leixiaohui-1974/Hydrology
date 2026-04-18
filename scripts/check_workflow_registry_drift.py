#!/usr/bin/env python3
"""Fail if MCP fast_validation profile references unknown workflow keys.

用法（在 Hydrology 目录下）:
  python3 scripts/check_workflow_registry_drift.py

可选：第二个参数为 workspace 相对路径的 E2E JSON，检查其中非空 workflow_key ⊆ REGISTRY。
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


def _registry_keys_from_init(init_path: Path) -> set[str]:
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "WORKFLOW_REGISTRY":
            if isinstance(node.value, ast.Dict):
                keys: set[str] = set()
                for k in node.value.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys.add(k.value)
                return keys
    raise RuntimeError("WORKFLOW_REGISTRY dict not found in AST")


def _fast_profile_keys(mcp_path: Path) -> set[str]:
    text = mcp_path.read_text(encoding="utf-8")
    start = text.find("def _fast_profile_params")
    if start < 0:
        raise RuntimeError("_fast_profile_params not found")
    block = text[start : text.find("\n    return mapping.get", start)]
    return set(re.findall(r'^\s{8}"([a-z0-9_]+)":\s+\{', block, re.M))


def _e2e_workflow_keys(report_path: Path) -> set[str]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for ag in data.get("agent_results", []) or []:
        for wf in ag.get("workflow_results", []) or []:
            k = wf.get("workflow_key")
            if k:
                keys.add(str(k))
    return keys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    init_path = root / "workflows" / "__init__.py"
    mcp_path = root / "mcp_server.py"
    reg = _registry_keys_from_init(init_path)
    fast = _fast_profile_keys(mcp_path)
    orphan_fast = sorted(fast - reg)
    if orphan_fast:
        print("ERROR: _fast_profile_params keys not in WORKFLOW_REGISTRY:", orphan_fast)
        return 1

    if len(sys.argv) > 1:
        raw = Path(sys.argv[1])
        if raw.is_absolute():
            candidates = [raw]
        else:
            # 支持相对 workspace 根（research/）或相对 Hydrology/ 的路径
            candidates = [root.parent / raw, root / raw]
        e2e = next((p for p in candidates if p.is_file()), None)
        if e2e is not None:
            e2e_keys = _e2e_workflow_keys(e2e)
            missing = sorted(e2e_keys - reg)
            if missing:
                print("ERROR: E2E workflow_key not in WORKFLOW_REGISTRY:", missing)
                return 1
            print(f"OK: fast_profile ⊆ registry; E2E ({e2e}) keys ⊆ registry ({len(e2e_keys)} keys).")
            return 0
        print("WARN: E2E report not found (tried workspace + Hydrology roots):", raw)

    print(f"OK: fast_profile ⊆ WORKFLOW_REGISTRY ({len(reg)} registered).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
