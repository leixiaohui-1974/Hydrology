#!/usr/bin/env python3
"""
从自主运行水网建模 Agent 平台主闭环 YAML 导出 platform + quality_loop（单行 JSON 至 stdout）。

供 HydroDesk「评审 / 规划」面板消费；编辑 YAML 后无需同步手写前端。
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

from hydrodesk_loop_yaml_util import load_loop_yaml  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export quality_loop + platform from autonomous waternet loop YAML")
    parser.add_argument(
        "--config",
        type=Path,
        default=WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml",
        help="Loop YAML (supports redirect_config stub)",
    )
    args = parser.parse_args()
    cfg = load_loop_yaml(WORKSPACE, args.config.resolve())
    resolved = args.config.resolve()
    try:
        cfg_rel = str(resolved.relative_to(WORKSPACE))
    except ValueError:
        cfg_rel = str(resolved)
    out: dict[str, Any] = {
        "config_path": cfg_rel,
        "version": cfg.get("version"),
        "platform": cfg.get("platform") or {},
        "quality_loop": cfg.get("quality_loop") or {},
        "html_contracts": cfg.get("html_contracts") or {},
    }
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
