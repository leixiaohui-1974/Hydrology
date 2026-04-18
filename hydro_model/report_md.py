"""Markdown 精度报告生成器 — 通用产品模块。

将工作流评价结果自动转换为结构化 Markdown 报告。
支持 D1(水文) / D2(水力学) / D3(系统辨识) / D4(状态估计) 四维度。

使用方式::

    from hydro_model.report_md import ReportGenerator
    gen = ReportGenerator(case_id="daduhe", dimension="D2")
    md = gen.build(station_results=..., summary=...)
    gen.write("cases/daduhe/contracts/D2_hydraulic_report.md")
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


class ReportGenerator:
    """通用 Markdown 精度报告生成器。"""

    def __init__(self, case_id: str, dimension: str, title: str | None = None):
        self.case_id = case_id
        self.dimension = dimension
        self.title = title or f"{dimension} 精度评价报告 — {case_id}"
        self._sections: list[str] = []
        self._generated_at = datetime.utcnow().isoformat(timespec="seconds")

    def build(self, **data: Any) -> str:
        """根据传入数据自动构建报告。"""
        self._sections = []
        self._add_header()
        self._add_summary(data.get("summary", {}))
        self._add_station_table(data.get("station_results", {}))
        self._add_reach_table(data.get("reach_results", {}))
        self._add_steady_metrics(data.get("steady_metrics", {}))
        self._add_unsteady_results(data.get("unsteady_result", {}))
        self._add_methodology(data.get("methodology", ""))
        self._add_conclusions(data.get("summary", {}), data.get("station_results", {}))
        self._add_footer()
        return "\n\n".join(self._sections)

    def write(self, output_path: str | Path) -> Path:
        """将报告写入文件。"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n\n".join(self._sections), encoding="utf-8")
        return path

    def _add_header(self):
        self._sections.append(f"# {self.title}")
        self._sections.append(
            f"> **案例**: {self.case_id} | "
            f"**维度**: {self.dimension} | "
            f"**生成时间**: {self._generated_at} UTC\n>\n"
            f"> _本报告由 HydroMind 精度评价系统自动生成_"
        )

    def _add_summary(self, summary: dict):
        if not summary:
            return
        self._sections.append("## 总体摘要")
        rows = []
        label_map = {
            "n_stations_calibrated": "率定站点数",
            "avg_cal_nse": "平均率定 NSE",
            "avg_val_nse": "平均验证 NSE",
            "avg_cal_rmse": "平均率定 RMSE (m)",
            "n_reaches_calibrated": "率定河段数",
        }
        for k, v in summary.items():
            label = label_map.get(k, k)
            if isinstance(v, float):
                rows.append(f"| {label} | {v:.4f} |")
            elif v is not None:
                rows.append(f"| {label} | {v} |")
        if rows:
            self._sections.append("| 指标 | 值 |\n|------|---|\n" + "\n".join(rows))

    def _add_station_table(self, results: dict):
        if not results:
            return
        self._sections.append("## 逐站率定验证结果")
        header = "| 站点 | 名称 | 率定NSE | 率定RMSE(m) | 验证NSE | 验证RMSE(m) | 评级 |"
        sep = "|------|------|---------|-------------|---------|-------------|------|"
        rows = []
        for sid, r in results.items():
            if not isinstance(r, dict) or "calibration" not in r:
                continue
            name = r.get("name", sid)
            cal = r.get("calibration", {}).get("best", r.get("calibration", {}))
            val = r.get("validation", {})
            cal_nse = cal.get("nse", "N/A")
            cal_rmse = cal.get("rmse", "N/A")
            val_nse = val.get("nse", "N/A")
            val_rmse = val.get("rmse", "N/A")
            grade = _grade(val_nse if isinstance(val_nse, (int, float)) else cal_nse)
            cal_nse_s = f"{cal_nse:.4f}" if isinstance(cal_nse, float) else str(cal_nse)
            cal_rmse_s = f"{cal_rmse:.3f}" if isinstance(cal_rmse, float) else str(cal_rmse)
            val_nse_s = f"{val_nse:.4f}" if isinstance(val_nse, float) else str(val_nse)
            val_rmse_s = f"{val_rmse:.3f}" if isinstance(val_rmse, float) else str(val_rmse)
            rows.append(f"| {sid} | {name} | {cal_nse_s} | {cal_rmse_s} | {val_nse_s} | {val_rmse_s} | {grade} |")
        if rows:
            self._sections.append(header + "\n" + sep + "\n" + "\n".join(rows))

    def _add_reach_table(self, results: dict):
        if not results:
            return
        self._sections.append("## 逐河段率定结果")
        header = "| 河段 | 率定NSE | 率定RMSE(m) | 验证NSE | Manning n | 评级 |"
        sep = "|------|---------|-------------|---------|-----------|------|"
        rows = []
        for name, r in results.items():
            if not isinstance(r, dict) or "calibration" not in r:
                continue
            cal = r["calibration"].get("best", {})
            val = r.get("validation", {})
            n_val = cal.get("manning_n", "N/A")
            rows.append(
                f"| {name} | {_f4(cal.get('nse'))} | {_f3(cal.get('rmse'))} | "
                f"{_f4(val.get('nse'))} | {_f4(n_val)} | {_grade(val.get('nse', cal.get('nse')))} |"
            )
        if rows:
            self._sections.append(header + "\n" + sep + "\n" + "\n".join(rows))

    def _add_steady_metrics(self, metrics: dict):
        if not metrics:
            return
        self._sections.append("## 稳态水位统计")
        header = "| 站点 | 名称 | 平均水位(m) | 平均流量(m³/s) | 水位范围(m) |"
        sep = "|------|------|-------------|----------------|-------------|"
        rows = []
        for sid, m in metrics.items():
            name = m.get("name", sid)
            h = m.get("obs_mean_level", 0)
            q = m.get("obs_mean_Q", 0)
            rng = m.get("obs_range", [0, 0])
            rows.append(f"| {sid} | {name} | {h:.1f} | {q:.0f} | {rng[0]:.1f}~{rng[1]:.1f} |")
        if rows:
            self._sections.append(header + "\n" + sep + "\n" + "\n".join(rows))

    def _add_unsteady_results(self, result: dict):
        if not result or result.get("status") != "completed":
            return
        self._sections.append("## 非稳态全模型验证")
        sm = result.get("station_metrics", {})
        if sm:
            header = "| 站点 | 名称 | NSE | RMSE(m) | 模拟均值(m) | 实测均值(m) |"
            sep = "|------|------|-----|---------|-------------|-------------|"
            rows = []
            for sid, m in sm.items():
                rows.append(
                    f"| {sid} | {m.get('name', sid)} | {_f4(m.get('nse'))} | "
                    f"{_f3(m.get('rmse'))} | {_f1(m.get('sim_mean'))} | {_f1(m.get('obs_mean'))} |"
                )
            self._sections.append(header + "\n" + sep + "\n" + "\n".join(rows))

    def _add_methodology(self, methodology: str):
        if not methodology:
            methodology = _default_methodology(self.dimension)
        self._sections.append("## 方法论")
        self._sections.append(methodology)

    def _add_conclusions(self, summary: dict, station_results: dict):
        self._sections.append("## 结论")
        lines = []
        avg_cal = summary.get("avg_cal_nse")
        avg_val = summary.get("avg_val_nse")
        n_sta = summary.get("n_stations_calibrated", 0)

        if avg_cal is not None:
            lines.append(f"- 共率定 **{n_sta}** 个站点，平均率定 NSE = **{avg_cal:.4f}**")
        if avg_val is not None:
            quality = "优秀" if avg_val >= 0.90 else ("良好" if avg_val >= 0.75 else "合格" if avg_val >= 0.50 else "待改善")
            lines.append(f"- 平均验证 NSE = **{avg_val:.4f}**，整体质量：**{quality}**")

        weak = []
        for sid, r in station_results.items():
            if not isinstance(r, dict):
                continue
            val = r.get("validation", {})
            if isinstance(val.get("nse"), (int, float)) and val["nse"] < 0.85:
                weak.append(f"{sid}({r.get('name', sid)}, NSE={val['nse']:.3f})")
        if weak:
            lines.append(f"- 弱站: {', '.join(weak)}，建议进一步精细化搜索或引入更多物理约束")

        strong = []
        for sid, r in station_results.items():
            if not isinstance(r, dict):
                continue
            val = r.get("validation", {})
            if isinstance(val.get("nse"), (int, float)) and val["nse"] >= 0.95:
                strong.append(f"{sid}({r.get('name', sid)}, NSE={val['nse']:.3f})")
        if strong:
            lines.append(f"- 强站: {', '.join(strong)}")

        if not lines:
            lines.append("- 评价完成，详见各表格")

        self._sections.append("\n".join(lines))

    def _add_footer(self):
        self._sections.append("---")
        self._sections.append(
            f"*报告生成: {self._generated_at} UTC | "
            f"系统: HydroMind Precision Evaluation v2.0 | "
            f"案例: {self.case_id}*"
        )


def _grade(nse: Any) -> str:
    if not isinstance(nse, (int, float)):
        return "—"
    if nse >= 0.95:
        return "**A+**"
    if nse >= 0.85:
        return "**A**"
    if nse >= 0.75:
        return "B"
    if nse >= 0.50:
        return "C"
    return "D"


def _f4(v: Any) -> str:
    return f"{v:.4f}" if isinstance(v, (int, float)) else "N/A"

def _f3(v: Any) -> str:
    return f"{v:.3f}" if isinstance(v, (int, float)) else "N/A"

def _f1(v: Any) -> str:
    return f"{v:.1f}" if isinstance(v, (int, float)) else "N/A"


def _default_methodology(dimension: str) -> str:
    if dimension == "D2":
        return (
            "本维度采用**水库水量平衡模型**进行逐站水力学率定验证：\n\n"
            "1. **模型**: H(t+1) = H(t) + α·(Q_in(t-lag) - Q_out(t))·Δt / A(H) - β·(H-H_ref)\n"
            "2. **率定策略**: 三阶段自提升\n"
            "   - Phase 1: 基础网格搜索 (A_eff × α)\n"
            "   - Phase 2: 精细化网格 (最优邻域缩小 5×)\n"
            "   - Phase 3: 高级搜索 (非线性面积 k_area + 时滞 lag + 回归 β)\n"
            "3. **验证**: 前 70% 数据率定，后 30% 独立验证\n"
            "4. **指标**: NSE, RMSE, MAE, R², PBIAS\n"
            "5. **评级标准**: A+ (≥0.95) | A (≥0.85) | B (≥0.75) | C (≥0.50) | D (<0.50)"
        )
    return f"标准 {dimension} 评价方法论。"
