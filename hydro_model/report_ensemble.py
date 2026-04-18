"""集合预报 Markdown 报告生成器。

产品级报告，包含：
  1. 预报体系概览（长中短嵌套）
  2. 各预见期集合成员及权重
  3. 置信区间覆盖率与锐度
  4. PIT 可靠性诊断
  5. 自学习推荐
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


class EnsembleReportGenerator:
    """集合预报 Markdown 报告。"""

    def __init__(self, case_id: str, output_dir: str | Path):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, contract: dict[str, Any]) -> Path:
        lines = [
            f"# {self.case_id.upper()} 嵌套集合预报评价报告",
            "",
            f"> 自动生成: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## 1. 预报体系架构",
            "",
            "| 预见期 | 时长 | 时间步 | 集合成员 | 集合方法 |",
            "|--------|------|--------|----------|----------|",
            "| 短期 | 0-24h | 1h | LSTM + Transformer + 水库水量平衡 | RMSE反比权重 |",
            "| 中期 | 1-7d | 1h | Transformer + TimesFM + 水文模型 | RMSE反比权重 |",
            "| 长期 | 7-30d | 6h | TimesFM + 气候统计 + 水文模型 | BMA |",
            "",
            "### 1.1 方法论",
            "",
            "- **数据驱动**: LSTM、Transformer、TimesFM（Google 基础模型）",
            "- **物理模型**: 水库水量平衡、水文概念模型",
            "- **统计方法**: 气候统计学基线",
            "- **不确定性**: 模型间方差 + MC-Dropout + 分位数回归",
            "- **可靠性**: PIT 直方图、CRPS、覆盖率-锐度图",
            "",
        ]

        station_results = contract.get("station_results", {})

        lines.append("## 2. 逐站集合预报结果")
        lines.append("")

        for sid, horizons in station_results.items():
            lines.append(f"### 站点 {sid}")
            lines.append("")

            for hz_name, hz_data in horizons.items():
                lines.append(f"#### {hz_name}")
                lines.append("")

                members = hz_data.get("members", [])
                if members:
                    lines.append("| 模型 | 类型 | NSE | RMSE | 权重 |")
                    lines.append("|------|------|-----|------|------|")
                    weights = hz_data.get("weights", {})
                    for m in members:
                        w = weights.get(m["name"], "N/A")
                        w_str = f"{w:.3f}" if isinstance(w, float) else str(w)
                        nse = f"{m.get('nse', 0):.4f}" if m.get("nse") is not None else "N/A"
                        rmse = f"{m.get('rmse', 0):.3f}" if m.get("rmse") is not None else "N/A"
                        lines.append(f"| {m['name']} | {m['model_type']} | {nse} | {rmse} | {w_str} |")
                    lines.append("")

                rel = hz_data.get("reliability", {})
                det = rel.get("deterministic", {})
                if det:
                    lines.append(f"**集合确定性精度**: NSE={det.get('nse', 'N/A')}, "
                                 f"RMSE={det.get('rmse', 'N/A')}")
                    lines.append("")

                ci_report = []
                for level in [50, 80, 95]:
                    cov = rel.get(f"coverage_{level}")
                    sharp = rel.get(f"sharpness_{level}")
                    if cov is not None:
                        ci_report.append(
                            f"| {level}% | {cov:.1%} | {level}% | "
                            f"{'✓ 达标' if cov >= level / 100 else '✗ 不足'} | "
                            f"{sharp:.4f}m |"
                        )

                if ci_report:
                    lines.append("| 置信水平 | 覆盖率 | 目标 | 状态 | 锐度 |")
                    lines.append("|----------|--------|------|------|------|")
                    lines.extend(ci_report)
                    lines.append("")

                pit = rel.get("pit", {})
                if pit:
                    status = "✓ 可靠" if pit.get("is_reliable") else "✗ 需改进"
                    lines.append(f"**PIT 可靠性**: χ²={pit.get('chi2', 'N/A'):.2f}, "
                                 f"判定: {status}")
                    lines.append("")

        lines.append("## 3. 自学习建议")
        lines.append("")
        lines.append("| 条件 | 动作 |")
        lines.append("|------|------|")
        lines.append("| 覆盖率 < 目标 | 增大 MC-Dropout 样本数或扩展集合成员 |")
        lines.append("| NSE < 0.8 | 触发自动重训练或增加训练轮次 |")
        lines.append("| PIT 不均匀 | 校准分位数映射或增加集合多样性 |")
        lines.append("| 锐度过宽 | 淘汰最差成员，提高精度权重 |")
        lines.append("")
        lines.append("---")
        lines.append(f"*报告由 HydroMind 集合预报产品自动生成*")

        out_path = self.output_dir / "ensemble_forecast_report.md"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return out_path
