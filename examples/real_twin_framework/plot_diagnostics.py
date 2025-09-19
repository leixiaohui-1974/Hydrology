"""生成实景孪生框架的诊断图表。"""
import os
import sys

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main() -> None:
    """读取诊断结果并输出多子图分析图。"""
    script_dir = os.path.dirname(__file__)
    results_file = os.path.join(script_dir, "final_results.csv")
    output_path = os.path.join(script_dir, "diagnostic_plot.png")

    if not os.path.exists(results_file):
        print("错误: 未找到 final_results.csv，请先运行 run_real_twin_simulation.py。")
        return

    df = pd.read_csv(results_file, index_col="time_step")

    print("正在生成诊断图...")
    fig = plt.figure(figsize=(15, 12))
    gs = gridspec.GridSpec(4, 1, height_ratios=[3, 1, 1, 2])

    ax1 = plt.subplot(gs[0])
    flow_column = "Catchment1" if "Catchment1" in df.columns else df.columns[0]
    ax1.plot(df.index, df[flow_column], label="出口模拟流量", color="b", linewidth=2)
    ax1.set_ylabel("流量 (m³/s)")
    ax1.set_title("Real-Twin 框架诊断与修正结果")
    ax1.legend()
    ax1.grid(True, linestyle="--", alpha=0.6)

    ax2 = plt.subplot(gs[1], sharex=ax1)
    if "reliability_index" in df:
        ax2.plot(df.index, df["reliability_index"], label="预测可靠性指数", color="g")
    ax2.set_ylabel("可靠性 (%)")
    ax2.set_ylim(0, 110)
    ax2.legend()
    ax2.grid(True, linestyle="--", alpha=0.6)

    ax3 = plt.subplot(gs[2], sharex=ax1)
    for gauge_col, style in [("health_RG1", "-"), ("health_RG2", "--"), ("health_RG3", ":")]:
        if gauge_col in df:
            ax3.plot(df.index, df[gauge_col], label=gauge_col.replace("_", " "), linestyle=style)
    ax3.set_ylabel("健康度评分")
    ax3.set_ylim(0, 110)
    ax3.legend()
    ax3.grid(True, linestyle="--", alpha=0.6)

    ax4 = plt.subplot(gs[3], sharex=ax1)
    if "raw_RG2" in df:
        ax4.plot(df.index, df["raw_RG2"], "r-o", label="原始 RG2", markersize=4)
    if "corrected_RG2" in df:
        ax4.plot(df.index, df["corrected_RG2"], "g-o", label="校正后 RG2", markersize=4)
    ax4.set_xlabel("时间步")
    ax4.set_ylabel("雨量 (折算流量)")
    ax4.legend()
    ax4.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    plt.savefig(output_path)
    print(f"诊断图已保存至 {output_path}")


if __name__ == "__main__":
    main()
