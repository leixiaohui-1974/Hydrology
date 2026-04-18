#!/usr/bin/env python3
"""HydroMind Workflow CLI — 统一产品入口。

用法：
    python3 -m workflows list                         # 列出全部工作流
    python3 -m workflows run pipeline --case-id my_case  # 运行自提升管线
    python3 -m workflows run init --case-id foo --wxq-dir wxq-1d/xxx --display-name 测试
    python3 -m workflows run improve --case-id my_case --threshold 0.85
    python3 -m workflows status my_case                 # 查看案例合约状态
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def cmd_list(args: argparse.Namespace) -> None:
    from workflows import list_workflows
    workflows = list_workflows()
    print(f"{'名称':<12} {'必需参数':<35} 描述")
    print("-" * 80)
    for w in workflows:
        print(f"{w['name']:<12} {', '.join(w['args']):<35} {w['description']}")


def cmd_run(args: argparse.Namespace) -> None:
    from workflows import run_workflow
    kwargs = {}
    if args.case_id:
        kwargs["case_id"] = args.case_id
    if hasattr(args, "wxq_dir") and args.wxq_dir:
        kwargs["wxq_dir"] = args.wxq_dir
    if hasattr(args, "display_name") and args.display_name:
        kwargs["display_name"] = args.display_name
    if hasattr(args, "target_nse") and args.target_nse is not None:
        kwargs["target_nse"] = args.target_nse
    if hasattr(args, "threshold") and args.threshold is not None:
        kwargs["threshold"] = args.threshold
    if hasattr(args, "max_iterations") and args.max_iterations is not None:
        kwargs["max_iterations"] = args.max_iterations
    if hasattr(args, "phases") and args.phases:
        kwargs["phases"] = args.phases.split(",")
    if hasattr(args, "stages") and args.stages:
        kwargs["stages"] = args.stages.split(",")
    if hasattr(args, "config") and args.config:
        kwargs["config_path"] = args.config
    if hasattr(args, "graphify_sidecar_dir") and args.graphify_sidecar_dir:
        kwargs["graphify_sidecar_dir"] = args.graphify_sidecar_dir
    if hasattr(args, "skip_wiki_sync") and args.skip_wiki_sync:
        kwargs["skip_wiki_sync"] = True

    result = run_workflow(args.workflow, **kwargs)
    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_status(args: argparse.Namespace) -> None:
    contracts_dir = WORKSPACE / "cases" / args.case_id / "contracts"
    if not contracts_dir.exists():
        print(f"案例目录不存在: cases/{args.case_id}/contracts/")
        return

    latest = sorted(contracts_dir.glob("*.latest.json"))
    if not latest:
        print(f"案例 {args.case_id} 无合约文件")
        return

    config_path = BASE_DIR / "configs" / f"{args.case_id}.yaml"
    print(f"案例: {args.case_id}")
    print(f"配置: {'存在' if config_path.exists() else '缺失'}")
    print(f"合约: {len(latest)} 个")
    print("-" * 60)
    for p in latest:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            ts = data.get("generated_at") or data.get("completed_at") or data.get("created_at") or "?"
            status = data.get("status") or data.get("phase") or "ok"
            print(f"  {p.stem:<45} {status:<12} {ts}")
        except Exception:
            print(f"  {p.stem:<45} (解析失败)")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python3 -m workflows",
        description="HydroMind Workflow CLI — 统一产品入口",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="列出全部工作流")

    run_p = sub.add_parser("run", help="运行工作流")
    run_p.add_argument("workflow", help="工作流名称")
    run_p.add_argument("--case-id", help="案例 ID")
    run_p.add_argument("--wxq-dir", help="wxq-1d 数据目录（相对 workspace）")
    run_p.add_argument("--display-name", help="显示名称")
    run_p.add_argument("--target-nse", type=float, help="收敛目标 NSE")
    run_p.add_argument("--threshold", type=float, help="精度阈值")
    run_p.add_argument("--max-iterations", type=int, help="最大迭代轮次")
    run_p.add_argument("--phases", help="逗号分隔阶段")
    run_p.add_argument("--stages", help="逗号分隔阶段")
    run_p.add_argument("--config", help="YAML 配置路径")
    run_p.add_argument("--graphify-sidecar-dir", help="可选 Graphify sidecar 目录")
    run_p.add_argument("--skip-wiki-sync", action="store_true", help="仅写 contracts，不更新共享 wiki")

    status_p = sub.add_parser("status", help="查看案例合约状态")
    status_p.add_argument("case_id", help="案例 ID")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
