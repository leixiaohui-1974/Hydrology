#!/usr/bin/env python3
"""撰报 (ZhuanBao) — 成果报告自动生成

HydroMind 水智工坊 · Agent #9

D2 水力学精度评价报告自动生成器。

从 hydraulic_calibration.latest.json 读取率定验证结果，
自动生成结构化 Markdown 报告 + 知识固化到 precision/history.yaml。

产品化：零硬编码，通用于所有案例。

Usage:
    python3 -m workflows run hyd_report --case-id zhongxian
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
from pathlib import Path as _P
_BASE = _P(__file__).resolve().parents[1]
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

from workflows._shared import (
    BASE_DIR,
    WORKSPACE,
    load_case_config,
    write_json,
    save_knowledge_file,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fmt4(v: float | None, *, na: str = "N/A") -> str:
    return f"{v:.4f}" if v is not None else na


def _grade(nse: float | None) -> str:
    if nse is None:
        return "无数据"
    if nse >= 0.90:
        return "优秀"
    if nse >= 0.80:
        return "良好"
    if nse >= 0.70:
        return "合格"
    if nse >= 0.50:
        return "较差"
    return "不合格"


MODELING_LESSONS = """
### 建模思路笔记（智能建模知识库）

| 路径 | 适用场景 | 失败原因（若有） |
|------|---------|-----------------|
| Manning 方程逐河段 | 明渠/河道段 | 水库系统不适用，NSE 极负 |
| SuperLink 1D | 河道+水工建筑物耦合 | 需精确几何参数，盲配发散 |
| **水库水量平衡** | **梯级水库系统** | ✅ 推荐路径 |

**关键经验：**
1. 先诊断物理过程再选模型（水库调蓄 vs 明渠流动）
2. 观察数据特征推断模型结构（水位范围、Q量级）
3. 三阶段自提升：粗搜 → 精搜 → 高级(非线性+时滞+阻尼)
4. β 回归项是防止误差累积的关键（弱站从 -0.8 提升到 0.85+）
5. 验证期 NSE > 率定期 NSE 时说明模型泛化良好
"""


def generate_report(case_id: str, config_path: str | None = None) -> dict[str, Any]:
    """生成 D2 水力学精度报告（MD + JSON）。"""
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    cal_path = contracts_dir / "hydraulic_calibration.latest.json"
    if not cal_path.exists():
        return {"error": f"未找到率定结果: {cal_path}"}

    cal = json.loads(cal_path.read_text(encoding="utf-8"))
    sr = cal.get("station_results", {})
    steady = cal.get("steady_metrics", {})
    summary = cal.get("summary", {})

    lines = [
        f"# D2 水力学精度评价报告 — {case_id}",
        "",
        f"> 自动生成 | case_id: {case_id} | {_now_iso()}",
        "",
        "## 1. 概述",
        "",
        f"对 {case_id} 梯级电站进行水力学历史率定与验证。"
        f"采用**水库水量平衡模型**逐站率定，分 70% 率定期 / 30% 验证期评价。",
        "",
        "**核心指标：**",
        f"- 站点数: **{summary.get('n_stations_calibrated', 0)}**",
        f"- 平均率定 NSE = **{_fmt4(summary.get('avg_cal_nse'))}**",
        f"- 平均验证 NSE = **{_fmt4(summary.get('avg_val_nse'))}**",
        "",
        "## 2. 逐站精度",
        "",
        "| 站点 | 名称 | 率定 NSE | 验证 NSE | RMSE (m) | 等级 | A_eff (m²) | α | β |",
        "|------|------|---------|---------|----------|------|-----------|-----|-------|",
    ]

    for sid in sorted(sr.keys()):
        r = sr[sid]
        if "calibration" not in r:
            continue
        b = r["calibration"]["best"]
        if not isinstance(b, dict):
            continue
        v = r.get("validation") or {}
        if not isinstance(v, dict):
            v = {}
        v_nse = v.get("nse")
        grade = _grade(v_nse)
        nse_b = b.get("nse")
        rmse_b = b.get("rmse")
        a_eff = b.get("A_eff")
        alpha_b = b.get("alpha")
        beta_b = b.get("beta", 0)
        rmse_s = f"{rmse_b:.3f}" if rmse_b is not None else "N/A"
        a_eff_s = f"{a_eff:,.0f}" if a_eff is not None else "N/A"
        alpha_s = f"{alpha_b:.3f}" if alpha_b is not None else "N/A"
        beta_s = f"{beta_b:.3f}" if beta_b is not None else "N/A"
        lines.append(
            f"| {sid} | {r.get('name', '')} "
            f"| {_fmt4(nse_b)} "
            f"| {_fmt4(v_nse)} "
            f"| {rmse_s} "
            f"| {grade} "
            f"| {a_eff_s} "
            f"| {alpha_s} "
            f"| {beta_s} |"
        )

    lines.extend([
        "",
        "### 等级标准",
        "- 优秀: NSE ≥ 0.90 | 良好: NSE ≥ 0.80 | 合格: NSE ≥ 0.70 | 较差: NSE ≥ 0.50 | 不合格: NSE < 0.50",
        "",
        "## 3. 模型描述",
        "",
        "水库水量平衡核心方程：",
        "",
        "$$H(t+1) = H(t) + \\frac{\\alpha \\cdot (Q_{in}(t-lag) - Q_{out}(t)) \\cdot \\Delta t}"
        "{A_{eff} + k \\cdot (H(t) - H_{ref})} - \\beta \\cdot (H(t) - H_{ref}) \\cdot \\frac{\\Delta t}{86400}$$",
        "",
        "| 参数 | 物理含义 |",
        "|------|---------|",
        "| A_eff | 有效水面面积 (m²) |",
        "| α (alpha) | 入流-出流响应系数 |",
        "| β (beta) | 回归阻尼系数（防误差累积） |",
        "| k_area | 面积-水位变化率 (m²/m) |",
        "| lag | 入流时滞 (小时) |",
    ])

    lines.extend([
        "",
        "## 4. 稳态水位统计",
        "",
        "| 站点 | 名称 | 平均水位 (m) | 水位范围 (m) | 平均流量 (m³/s) |",
        "|------|------|-------------|-------------|----------------|",
    ])
    for sid in sorted(steady.keys()):
        s = steady[sid]
        if not isinstance(s, dict):
            continue
        rng = s.get("obs_range") or [0, 0]
        if not isinstance(rng, (list, tuple)) or len(rng) < 2:
            rng = [0, 0]
        ml = s.get("obs_mean_level")
        mq = s.get("obs_mean_Q")
        ml_s = f"{ml:.1f}" if ml is not None else "N/A"
        r0 = rng[0] if rng[0] is not None else 0.0
        r1 = rng[1] if rng[1] is not None else 0.0
        mq_s = f"{mq:,.0f}" if mq is not None else "N/A"
        lines.append(
            f"| {sid} | {s.get('name', '')} "
            f"| {ml_s} "
            f"| {r0:.1f} ~ {r1:.1f} "
            f"| {mq_s} |"
        )

    lines.extend(["", MODELING_LESSONS, ""])
    lines.extend([
        "---",
        "",
        f"*数据来源: `cases/{case_id}/contracts/hydraulic_calibration.latest.json`*",
        f"*工作流: `Hydrology/workflows/run_hydraulic_calibration.py`*",
        "*_auto_generated: true*",
    ])

    md_content = "\n".join(lines)
    md_path = contracts_dir / "D2_hydraulic_precision_report.md"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"报告: {md_path}")

    # Knowledge fixation
    precision_entry = {
        "dimension": "D2_hydraulics",
        "model": "reservoir_water_balance",
        "generated_at": _now_iso(),
        "stations": {},
    }
    for sid in sorted(sr.keys()):
        r = sr[sid]
        if "calibration" not in r:
            continue
        b = r["calibration"]["best"]
        if not isinstance(b, dict):
            continue
        v = r.get("validation") or {}
        if not isinstance(v, dict):
            v = {}
        precision_entry["stations"][sid] = {
            "name": r.get("name"),
            "cal_nse": b.get("nse"),
            "val_nse": v.get("nse"),
            "rmse": b.get("rmse"),
            "params": {
                "A_eff": b.get("A_eff"),
                "alpha": b.get("alpha"),
                "beta": b.get("beta", 0),
                "k_area": b.get("k_area", 0),
                "lag": b.get("lag", 0),
            },
        }

    save_knowledge_file(case_id, "precision/d2_hydraulics.yaml", precision_entry)
    print(f"知识固化: knowledge/{case_id}/precision/d2_hydraulics.yaml")

    return {
        "report_path": str(md_path),
        "summary": summary,
        "precision_entry": precision_entry,
    }


def main():
    parser = argparse.ArgumentParser(description="D2 水力学精度报告生成")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    generate_report(args.case_id, args.config)


if __name__ == "__main__":
    main()
