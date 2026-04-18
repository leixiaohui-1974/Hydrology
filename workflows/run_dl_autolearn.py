#!/usr/bin/env python3
"""率定 (LuDing) — 参数校准与自学习

HydroMind 水智工坊 · Agent #5

自学习闭环工作流 — 产品化入口。

自动完成：诊断→弱点识别→超参搜索→择优→固化。

Usage:
    # 自学习（默认 NSE > 0.90，最多 3 轮）
    python3 workflows/run_dl_autolearn.py --case-id zhongxian

    # 高目标
    python3 workflows/run_dl_autolearn.py --case-id zhongxian --target-nse 0.95 --rounds 5

    # 多变量
    python3 workflows/run_dl_autolearn.py --case-id zhongxian --target-vars H_up,Q_in,Q_out
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from workflows._shared import load_case_config, write_json, WORKSPACE, get_station_ids


def _find_db(cfg: dict) -> str | None:
    for p in cfg.get("sqlite_paths", []):
        if "hydromind" in str(p).lower() and Path(p).exists():
            return str(p)
    for scan_dir in cfg.get("scan_dirs", []):
        for f in Path(scan_dir).glob("*hydromind*.sqlite3"):
            return str(f)
    return None


def run_dl_autolearn(
    case_id: str,
    target_nse: float = 0.90,
    max_rounds: int = 3,
    trials_per_weak: int = 8,
    weak_point_batch_size: int = 5,
    target_vars: list[str] | None = None,
    station_ids: list[str] | None = None,
    model_types: list[str] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """自学习闭环主入口。"""
    from hydro_model.dl_forecast.autolearn import AutoLearner

    cfg = load_case_config(case_id, config_path)
    db_path = _find_db(cfg)
    if not db_path:
        return {"error": "No hydromind SQLite found"}

    learner = AutoLearner(
        case_id=case_id,
        db_path=db_path,
        output_dir=WORKSPACE / "cases" / case_id / "contracts",
        target_vars=target_vars or ["H_up", "Q_in", "Q_out"],
        station_ids=station_ids or get_station_ids(cfg),
    )

    result = learner.run(
        target_nse=target_nse,
        max_rounds=max_rounds,
        trials_per_weak=trials_per_weak,
        model_types=model_types,
        weak_point_batch_size=weak_point_batch_size,
    )

    _generate_report(result, case_id)

    out_path = WORKSPACE / "cases" / case_id / "contracts" / "dl_autolearn.latest.json"
    write_json(out_path, result)
    print(f"\n契约: {out_path}")
    return result


def _generate_report(result: dict, case_id: str) -> None:
    """生成自学习报告 Markdown。"""
    lines = [
        "# 深度学习自学习闭环报告",
        "",
        f"**案例**: {case_id}",
        f"**目标 NSE**: {result.get('target_nse', 'N/A')}",
        f"**自学习轮次**: {result.get('rounds_run', 0)}",
        f"**生成时间**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
        "## 改进总结",
        "",
        "| 站点 | 变量 | 原始 NSE | 改进 NSE | 提升 | 状态 |",
        "|------|------|---------|---------|------|------|",
    ]

    for h in result.get("history", []):
        for imp in h.get("improvements", []):
            if isinstance(imp, dict) and imp.get("status") == "completed":
                orig = imp.get("original_nse", 0)
                improved = imp.get("improved_nse", 0)
                delta = imp.get("improvement", 0)
                status = "improved" if delta > 0 else "no_change"
                lines.append(
                    f"| {imp.get('station', '?')} | {imp.get('variable', '?')} "
                    f"| {orig:.4f} | {improved:.4f} | {delta:+.4f} | {status} |"
                )

    lines.extend([
        "",
        "## 自学习机制说明",
        "",
        "1. **诊断**: 遍历所有(站点×变量×模型)组合，生成精度矩阵",
        "2. **识别弱点**: 找出 NSE < 目标的弱项，按差距排序",
        "3. **搜索改进**: 对每个弱项随机搜索超参组合（序列长度、学习率、隐层等）",
        "4. **择优**: 选择精度最高的配置",
        "5. **固化**: 最优配置和评价指标写入知识层",
        "",
        "## 迁移学习策略",
        "",
        "| 层级 | 机制 | 新流域所需 | 预期精度 |",
        "|------|------|-----------|---------|",
        "| L1 零样本 | TimesFM 基础模型 | 零训练 | NSE 0.5~0.8 |",
        "| L2 微调 | 预训练权重 + 冻结底层 | ~100步微调 | NSE 0.85+ |",
        "| L3 自学习 | 自动超参搜索 | 全自动 | NSE 0.90+ |",
        "",
    ])

    report_path = (
        WORKSPACE / "cases" / case_id / "contracts" / "dl_autolearn_report.md"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告: {report_path}")


def main():
    from workflows._autonomy_policy import argv_has, governance_source_relpath, section

    parser = argparse.ArgumentParser(description="自学习闭环工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--target-nse", type=float, default=0.90)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--trials", type=int, default=8)
    parser.add_argument("--target-vars", default=None, help="逗号分隔: H_up,Q_in,Q_out")
    parser.add_argument("--station", default=None)
    parser.add_argument("--models", default=None, help="逗号分隔: lstm,transformer")
    parser.add_argument(
        "--weak-batch",
        dest="weak_batch",
        type=int,
        default=None,
        help="每轮改进的弱项条数上限（默认来自 workflow_autonomy_policy）",
    )
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    pol = section(args.case_id, "dl_autolearn", args.config)
    if not argv_has("--target-nse") and "target_nse" in pol:
        args.target_nse = float(pol["target_nse"])
    if not argv_has("--rounds") and "max_rounds" in pol:
        args.rounds = int(pol["max_rounds"])
    if not argv_has("--trials") and "trials_per_weak" in pol:
        args.trials = int(pol["trials_per_weak"])
    weak_batch = int(args.weak_batch) if args.weak_batch is not None else int(pol.get("weak_point_batch_size", 5))

    applied: dict[str, Any] = {}
    if not argv_has("--target-nse") and "target_nse" in pol:
        applied["target_nse"] = pol["target_nse"]
    if not argv_has("--rounds") and "max_rounds" in pol:
        applied["max_rounds"] = pol["max_rounds"]
    if not argv_has("--trials") and "trials_per_weak" in pol:
        applied["trials_per_weak"] = pol["trials_per_weak"]
    if args.weak_batch is None and "weak_point_batch_size" in pol:
        applied["weak_point_batch_size"] = pol["weak_point_batch_size"]

    target_vars = args.target_vars.split(",") if args.target_vars else None
    station_ids = [args.station] if args.station else None
    model_types = args.models.split(",") if args.models else None

    result = run_dl_autolearn(
        case_id=args.case_id, target_nse=args.target_nse,
        max_rounds=args.rounds, trials_per_weak=args.trials,
        weak_point_batch_size=weak_batch,
        target_vars=target_vars, station_ids=station_ids,
        model_types=model_types, config_path=args.config,
    )
    if "error" not in result:
        result["policy_governance"] = {
            "source": governance_source_relpath(),
            "policy_file": "workflow_autonomy_policy.yaml",
            "section": "dl_autolearn",
            "applied_from_yaml": applied,
        }
        write_json(
            WORKSPACE / "cases" / args.case_id / "contracts" / "dl_autolearn.latest.json",
            result,
        )


if __name__ == "__main__":
    main()
