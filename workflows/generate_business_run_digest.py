"""CLI / WORKFLOW_REGISTRY：按 ``workflow_smart_reporting.yaml`` 的 ``business_run_digest`` 生成业务向长文 MD/HTML。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hydro_model.business_run_digest import write_business_run_digest  # noqa: E402
from workflows.smart_run_reporting import load_workflow_smart_reporting_config  # noqa: E402

WORKSPACE = BASE_DIR.parent


def run_business_run_digest(
    case_id: str,
    *,
    config_path: str | None = None,
    reporting_yaml: str | None = None,
) -> dict[str, Any]:
    """供 ``run_workflow(\"business_run_digest\", case_id=...)`` 调用。"""
    cid = str(case_id or "").strip()
    cfg = load_workflow_smart_reporting_config(
        cid,
        config_path=config_path,
        reporting_yaml=reporting_yaml,
    )
    dig = cfg.get("business_run_digest")
    if not isinstance(dig, dict) or not dig.get("enabled", True):
        return {
            "ok": True,
            "skipped": True,
            "reason": "business_run_digest disabled or missing in merged smart_reporting config",
            "outcome_status": "completed",
        }
    md_p, html_p, warns = write_business_run_digest(cid, cfg)
    return {
        "ok": True,
        "md_path": str(md_p.resolve().relative_to(WORKSPACE)),
        "html_path": str(html_p.resolve().relative_to(WORKSPACE)),
        "warnings": warns,
        "outcome_status": "completed",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="生成业务向运行结果汇总（配置驱动）")
    p.add_argument("--case-id", required=True)
    p.add_argument("--config", default="", help="覆盖案例 YAML 路径（相对 WORKSPACE 或绝对）")
    p.add_argument(
        "--reporting-yaml",
        default="",
        help="覆盖 workflow_smart_reporting.yaml 路径",
    )
    args = p.parse_args()

    try:
        out = run_business_run_digest(
            args.case_id.strip(),
            config_path=args.config.strip() or None,
            reporting_yaml=args.reporting_yaml.strip() or None,
        )
    except ValueError as exc:
        print(f"错误: {exc}")
        return 2
    if out.get("skipped"):
        print(out.get("reason", "skipped"))
        return 0
    md_p = out.get("md_path", "")
    html_p = out.get("html_path", "")
    warns = out.get("warnings") or []
    print(f"MD:   {md_p}")
    print(f"HTML: {html_p}")
    for w in warns:
        print(f"警告: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
