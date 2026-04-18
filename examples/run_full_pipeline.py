#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 完整水文建模流程：流域划分检查 -> 面雨量插值 -> 水文模拟 -> 结果对比 -> 报告生成

import math
import argparse
import json
import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
GIS_DIR = BASE_DIR / "gis_data"
RESULTS_DIR = BASE_DIR / "examples" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from common.program_contract_bridge import CONTRACTS_AVAILABLE
from common.program_contract_outputs import (
    build_artifact_payload,
    build_workflow_run_payload,
    build_workflow_step_payload,
    write_workflow_run_metadata,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

PARAMS_MAP: Dict[str, Dict[str, float]] = {
    "zone_A": {"S_max": 200.0, "k_q": 0.8,  "k_s": 0.1,  "c_loss": 0.05},
    "zone_B": {"S_max": 150.0, "k_q": 0.9,  "k_s": 0.05, "c_loss": 0.02},
    "zone1":  {"S_max": 180.0, "k_q": 0.75, "k_s": 0.08, "c_loss": 0.04},
    "zone2":  {"S_max": 160.0, "k_q": 0.85, "k_s": 0.06, "c_loss": 0.03},
    # 水文站自动生成的分区（上游 -> 下游，S_max/k_s 递减）
    "zone_headwater":    {"S_max": 200.0, "k_q": 0.70, "k_s": 0.10, "c_loss": 0.05},
    "zone_confluence_1": {"S_max": 185.0, "k_q": 0.75, "k_s": 0.08, "c_loss": 0.04},
    "zone_confluence_2": {"S_max": 170.0, "k_q": 0.80, "k_s": 0.07, "c_loss": 0.035},
    "zone_confluence_3": {"S_max": 160.0, "k_q": 0.82, "k_s": 0.06, "c_loss": 0.03},
    "zone_outlet":       {"S_max": 150.0, "k_q": 0.85, "k_s": 0.05, "c_loss": 0.025},
}


# =========================================================
# 内联水文模型核心类（从 run_example.py 提取）
# =========================================================

class Subbasin:
    """基于简化线性水库的子流域模型。"""

    def __init__(self, pfaf: str, area_km2: float, params: Dict[str, float]):
        self.pfaf = pfaf
        self.area_km2 = area_km2
        self.params = params
        self.storage = 0.0

    def reset(self) -> None:
        self.storage = 0.0

    def run_timestep(self, rainfall_mm: float, pet_mm: float, dt_seconds: float) -> float:
        """返回当前时段的出流量（m³/s）。"""
        effective_rain = max(rainfall_mm - self.params.get("c_loss", 0.0) * pet_mm, 0.0)
        quick_runoff = self.params.get("k_q", 0.5) * effective_rain
        infiltration = (1.0 - self.params.get("k_q", 0.5)) * effective_rain

        self.storage += infiltration
        s_max = self.params.get("S_max", math.inf)
        if self.storage > s_max:
            quick_runoff += self.storage - s_max
            self.storage = s_max

        baseflow = self.params.get("k_s", 0.05) * self.storage
        self.storage = max(self.storage - baseflow, 0.0)

        total_runoff_mm = quick_runoff + baseflow
        volume_m3 = total_runoff_mm / 1000.0 * self.area_km2 * 1_000_000.0
        return volume_m3 / dt_seconds


def _normalize_downstream(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return str(value)


def build_subbasins(catchment_df: pd.DataFrame, params_map: Dict[str, Dict[str, float]]) -> Dict[str, Subbasin]:
    subbasins = {}
    for _, row in catchment_df.iterrows():
        zone_id = row["zone_id"]
        if zone_id not in params_map:
            # 对未知分区（如水文站自动生成的分区），用默认参数兜底
            logger.warning("参数分区 %s 未在 PARAMS_MAP 中定义，使用默认参数", zone_id)
            params_map[zone_id] = {"S_max": 170.0, "k_q": 0.80, "k_s": 0.07, "c_loss": 0.035}
        subbasins[row["pfaf_code"]] = Subbasin(
            pfaf=row["pfaf_code"],
            area_km2=float(row["area_km2"]),
            params=params_map[zone_id],
        )
    return subbasins


def get_topological_order(catchment_df: pd.DataFrame) -> List[str]:
    downstream_map = {row["pfaf_code"]: _normalize_downstream(row.get("downstream_pfaf")) for _, row in catchment_df.iterrows()}
    upstream_map: Dict[str, List[str]] = {}
    for pfaf, downstream in downstream_map.items():
        if downstream:
            upstream_map.setdefault(downstream, []).append(pfaf)

    sources = [pfaf for pfaf in downstream_map if pfaf not in upstream_map]
    order: List[str] = []
    queue: List[str] = sources[:]

    while queue:
        current = queue.pop(0)
        order.append(current)
        downstream = downstream_map.get(current)
        if downstream and downstream not in order:
            prerequisites = upstream_map.get(downstream, [])
            if all(up in order for up in prerequisites):
                queue.append(downstream)
    return order


def simulate_network(
    catchment_df: pd.DataFrame,
    params_map: Dict[str, Dict[str, float]],
    rainfall_df: pd.DataFrame,
    pet_series: pd.Series,
) -> pd.DataFrame:
    subbasins = build_subbasins(catchment_df, params_map)
    topo_order = get_topological_order(catchment_df)
    downstream_map = {row["pfaf_code"]: _normalize_downstream(row.get("downstream_pfaf")) for _, row in catchment_df.iterrows()}
    index = rainfall_df.index
    dt_seconds = float((index[1] - index[0]).total_seconds()) if len(index) > 1 else 24 * 3600.0

    for basin in subbasins.values():
        basin.reset()

    local_flows: Dict[str, np.ndarray] = {pfaf: np.zeros(len(index)) for pfaf in subbasins}
    total_flows: Dict[str, np.ndarray] = {pfaf: np.zeros(len(index)) for pfaf in subbasins}

    for t, timestamp in enumerate(index):
        pet_mm = float(pet_series.iloc[t])
        for pfaf in topo_order:
            basin = subbasins[pfaf]
            rain_col = f"rainfall_{pfaf}"
            rainfall_mm = float(rainfall_df.at[timestamp, rain_col]) if rain_col in rainfall_df.columns else float(rainfall_df.iloc[t])
            flow_cms = basin.run_timestep(rainfall_mm, pet_mm, dt_seconds)
            local_flows[pfaf][t] = flow_cms
            total_flows[pfaf][t] += flow_cms
            downstream = downstream_map.get(pfaf)
            if downstream:
                total_flows[downstream][t] += total_flows[pfaf][t]

    result = pd.DataFrame({f"simulated_flow_{pfaf}": total_flows[pfaf] for pfaf in sorted(total_flows)}, index=index)
    return result



# =========================================================
# Step 1: 流域划分检查
# =========================================================

def step1_check_subbasins() -> Optional[Path]:
    print("[Step1] 检查子流域划分结果...")
    subbasins_file = RESULTS_DIR / "subbasins_with_zones.shp"
    if subbasins_file.exists():
        print(f"[Step1] 使用已有子流域划分: {subbasins_file}")
        return subbasins_file
    try:
        script = BASE_DIR / "examples" / "generate_parameter_zones.py"
        if script.exists():
            print(f"[Step1] 运行流域划分脚本: {script}")
            subprocess.run([sys.executable, str(script)], check=True, cwd=str(BASE_DIR), timeout=300)
            if subbasins_file.exists():
                return subbasins_file
        else:
            print("[Step1] 未找到流域划分脚本，跳过")
    except subprocess.TimeoutExpired:
        print("[Step1] 警告: 流域划分脚本超时")
    except subprocess.CalledProcessError as e:
        print(f"[Step1] 警告: 流域划分失败 (返回码 {e.returncode})")
    except Exception as e:
        print(f"[Step1] 警告: {e}")
    print("[Step1] 未找到子流域 Shapefile，后续降级为站点平均法")
    return None


# =========================================================
# Step 2: 面雨量插值
# =========================================================

def step2_areal_precipitation(subbasins_file: Optional[Path], rainfall_df: pd.DataFrame) -> pd.DataFrame:
    print("[Step2] 计算面雨量...")
    if subbasins_file is not None:
        try:
            from hydro_model.areal_precipitation import ArealPrecipitation
            rain_gauges_file = GIS_DIR / "rain_gauges.csv"
            if not rain_gauges_file.exists():
                raise FileNotFoundError(f"雨量站文件不存在: {rain_gauges_file}")
            calc = ArealPrecipitation(
                subbasins_shapefile=str(subbasins_file),
                rain_gauges_file=str(rain_gauges_file),
            )
            # ArealPrecipitation._calculate_idw 用 gauges_gdf 整数 index 与 rainfall_df 列名对齐
            # 需要将 rainfall_df 列名重命名为雨量站的整数顺序（0,1,2...）
            gauges_df = pd.read_csv(rain_gauges_file)
            gauge_ids = gauges_df["station_id"].tolist()
            # 构建列名映射：station_id -> 整数 index
            col_rename = {sid: i for i, sid in enumerate(gauge_ids) if sid in rainfall_df.columns}
            rainfall_for_idw = rainfall_df.rename(columns=col_rename)
            areal_rain = calc.calculate_areal_rainfall(rainfall_for_idw, method="idw")
            print(f"[Step2] IDW 面雨量完成，子流域数: {areal_rain.shape[1]}")
            return areal_rain
        except ImportError as e:
            print(f"[Step2] 警告: {e}")
        except FileNotFoundError as e:
            print(f"[Step2] 警告: {e}")
        except Exception as e:
            print(f"[Step2] 警告: 面雨量插值失败: {e}")
    mean_rain = rainfall_df.mean(axis=1)
    print("[Step2] 降级为站点平均面雨量")
    return pd.DataFrame({"SB_avg": mean_rain})


# =========================================================
# Step 3: 水文模拟
# =========================================================

def step3_simulate(
    catchment_df: pd.DataFrame,
    areal_rain_df: pd.DataFrame,
    pet_series: pd.Series,
) -> pd.DataFrame:
    print("[Step3] 运行水文模拟...")
    pfaf_codes = catchment_df["pfaf_code"].astype(str).tolist()
    rain_cols = areal_rain_df.columns.tolist()
    adapted_rain = pd.DataFrame(index=areal_rain_df.index)
    if len(rain_cols) == 1:
        single_col = rain_cols[0]
        print(f"  面雨量单列，复制至 {len(pfaf_codes)} 个子流域")
        for pfaf in pfaf_codes:
            adapted_rain[f"rainfall_{pfaf}"] = areal_rain_df[single_col].values
    else:
        for i, pfaf in enumerate(pfaf_codes):
            expected = f"rainfall_{pfaf}"
            if expected in areal_rain_df.columns:
                adapted_rain[expected] = areal_rain_df[expected].values
            elif pfaf in areal_rain_df.columns:
                adapted_rain[expected] = areal_rain_df[pfaf].values
            else:
                col_idx = i % len(rain_cols)
                adapted_rain[expected] = areal_rain_df.iloc[:, col_idx].values
                print(f"  警告: 子流域 {pfaf} 无对应降雨列，使用第 {col_idx} 列")
    print(f"  子流域数: {len(pfaf_codes)}，时间步数: {len(adapted_rain)}")
    result = simulate_network(catchment_df, PARAMS_MAP, adapted_rain, pet_series)
    print(f"  模拟完成，输出形状: {result.shape}")
    return result


# =========================================================
# Step 4: 性能指标
# =========================================================

def compute_metrics(observed: pd.Series, simulated: pd.Series) -> Dict[str, float]:
    common_index = observed.index.intersection(simulated.index)
    if len(common_index) == 0:
        raise ValueError("实测与模拟序列无公共时间步")
    obs = observed.loc[common_index].values.astype(float)
    sim = simulated.loc[common_index].values.astype(float)
    mask = ~(np.isnan(obs) | np.isnan(sim))
    obs, sim = obs[mask], sim[mask]
    if len(obs) == 0:
        raise ValueError("去除 NaN 后有效数据点为零")
    obs_mean = np.mean(obs)
    ss_res = np.sum((obs - sim) ** 2)
    ss_tot = np.sum((obs - obs_mean) ** 2)
    nse = float(1.0 - ss_res / ss_tot) if ss_tot > 0.0 else float("nan")
    rmse = float(np.sqrt(np.mean((obs - sim) ** 2)))
    r2 = float(np.corrcoef(obs, sim)[0, 1] ** 2) if np.std(obs) > 0 and np.std(sim) > 0 else float("nan")
    bias_pct = float((np.mean(sim) - obs_mean) / obs_mean * 100.0) if obs_mean != 0 else float("nan")
    metrics = {"NSE": nse, "RMSE": rmse, "R2": r2, "Bias_pct": bias_pct, "n_samples": int(len(obs))}
    print(f"[Step4] NSE={nse:.4f}  RMSE={rmse:.2f} m3/s  R2={r2:.4f}  Bias={bias_pct:.2f}%  n={len(obs)}")
    return metrics



# ========= Step 5 =========

def step5_plot_comparison(
    rainfall_df: pd.DataFrame,
    observed_df: pd.DataFrame,
    simulated_df: pd.DataFrame,
    metrics: Dict[str, float],
) -> Optional[Path]:
    print("[Step5] 生成对比图...")
    try:
        sim_cols = simulated_df.columns.tolist()
        try:
            outlet_col = min(sim_cols, key=lambda c: int(c.replace("simulated_flow_", "")))
        except (ValueError, TypeError):
            outlet_col = sim_cols[0]
        outlet_pfaf = outlet_col.replace("simulated_flow_", "")
        sim_outlet = simulated_df[outlet_col]
        obs_outlet = observed_df.iloc[:, 0]
        rain_mean = rainfall_df.mean(axis=1)
        common_idx = sim_outlet.index.intersection(obs_outlet.index)
        if len(common_idx) == 0:
            print("[Step5] 警告: 无公共时间步，跳过绘图")
            return None
        sim_plot = sim_outlet.loc[common_idx]
        obs_plot = obs_outlet.loc[common_idx]
        rain_plot = rain_mean.reindex(common_idx).fillna(0.0)
        fig, ax1 = plt.subplots(figsize=(14, 6))
        ax1.plot(common_idx, obs_plot.values, color="#1f77b4", linewidth=1.8, label="实测流量", zorder=3)
        ax1.plot(common_idx, sim_plot.values, color="#d62728", linewidth=1.8, linestyle="--", label="模拟流量", zorder=3)
        ax1.set_xlabel("日期", fontsize=11)
        ax1.set_ylabel("流量 (m3/s)", fontsize=11, color="#1f77b4")
        ax1.tick_params(axis="y", labelcolor="#1f77b4")
        ax1.set_ylim(bottom=0)
        ax2 = ax1.twinx()
        ax2.bar(common_idx, rain_plot.values, color="#aec7e8", alpha=0.55, label="面雨量")
        rain_max = float(rain_plot.max())
        ax2.set_ylim(rain_max * 3.5 if rain_max > 0 else 10, 0)
        ax2.set_ylabel("面雨量 (mm)", fontsize=11, color="#5b9bd5")
        ax2.tick_params(axis="y", labelcolor="#5b9bd5")
        ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
        n_ticks = max(len(common_idx) // 12, 1)
        ax1.xaxis.set_major_locator(mdates.DayLocator(interval=n_ticks))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        plt.gcf().autofmt_xdate(rotation=30)
        fmt2f = ".2f"
        def _fmt(v: float, fmt: str = ".4f") -> str:
            return f"{v:{fmt}}" if not math.isnan(v) else "N/A"
        nse_v  = metrics.get("NSE",      float("nan"))
        rmse_v = metrics.get("RMSE",     float("nan"))
        r2_v   = metrics.get("R2",       float("nan"))
        bias_v = metrics.get("Bias_pct", float("nan"))
        t1 = f"流量模拟对比（出口子流域: {outlet_pfaf})"
        t2 = f"NSE={_fmt(nse_v)}  RMSE={_fmt(rmse_v, fmt2f)} m3/s  R2={_fmt(r2_v)}  Bias={_fmt(bias_v, fmt2f)}%"
        ax1.set_title(t1 + chr(10) + t2, fontsize=11, pad=10)
        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=9)
        plt.tight_layout()
        save_path = RESULTS_DIR / "flow_comparison.png"
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"[Step5] 对比图已保存: {save_path}")
        return save_path
    except Exception as e:
        print(f"[Step5] 警告: 绘图失败: {e}")
        return None

# ========= Step 6 =========

def step6_generate_report(
    subbasins_file: Optional[Path],
    catchment_df: pd.DataFrame,
    areal_rain_df: pd.DataFrame,
    simulated_df: pd.DataFrame,
    observed_df: pd.DataFrame,
    metrics: Dict[str, float],
    plot_path: Optional[Path],
) -> Path:
    print("[Step6] 生成 Markdown 报告...")
    fmt2f = ".2f"
    def _fmt(v: float, fmt: str = ".4f") -> str:
        return f"{v:{fmt}}" if not math.isnan(v) else "N/A"
    n_sb = len(catchment_df)
    total_area = float(catchment_df["area_km2"].sum())
    zone_counts = catchment_df["zone_id"].value_counts().to_dict()
    zone_summary = "、".join(f"{z}（{c} 个）" for z, c in zone_counts.items())
    sb_status = str(subbasins_file) if subbasins_file else "未使用（已降级）"
    rtm = float(areal_rain_df.sum().mean()) if len(areal_rain_df) > 0 else 0.0
    rmax = float(areal_rain_df.max().max()) if len(areal_rain_df) > 0 else 0.0
    rcols = ", ".join(str(c) for c in areal_rain_df.columns[:5])
    if len(areal_rain_df.columns) > 5:
        rcols += f" ...共{len(areal_rain_df.columns)}列"
    ss = str(simulated_df.index[0].date()) if len(simulated_df) > 0 else "N/A"
    se = str(simulated_df.index[-1].date()) if len(simulated_df) > 0 else "N/A"
    sc = list(areal_rain_df.columns[:3])
    rs = areal_rain_df[sc].describe().round(2)
    tbl = ["| 统计量 | " + " | ".join(str(c) for c in sc) + " |",
           "|---|" + "---|" * len(sc)]
    for sn in ["mean", "std", "min", "max"]:
        if sn in rs.index:
            rv = " | ".join(f"{rs.loc[sn, c]:.2f}" for c in sc)
            tbl.append(f"| {sn} | {rv} |")
    stats_table = chr(10).join(tbl)
    nse_v  = metrics.get("NSE",      float("nan"))
    rmse_v = metrics.get("RMSE",     float("nan"))
    r2_v   = metrics.get("R2",       float("nan"))
    bias_v = metrics.get("Bias_pct", float("nan"))
    n_samp = metrics.get("n_samples", "N/A")
    pref = "![流量对比图](./flow_comparison.png)" if plot_path else "_（绘图失败）_"
    ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    doc = [
        "# 水文建模完整流程报告", "",
        f"> 生成时间：{ts}", "", "---", "",
        "## 1. 流域概况", "",
        "| 项目 | 值 |", "|---|---|",
        f"| 子流域数 | {n_sb} |",
        f"| 总面积 | {total_area:.1f} km2 |",
        f"| 参数分区 | {zone_summary} |",
        f"| Shapefile | {sb_status} |",
        f"| 模拟时段 | {ss} ~ {se} |",
        "| 时间步长 | 日步长（86400 秒）|",
        "", "---", "",
        "## 2. 面雨量统计", "",
        "- 计算方法：IDW（失败时降级为站点平均）",
        f"- 面雨量列：{rcols}",
        f"- 累计降雨均值：**{rtm:.1f} mm**",
        f"- 单时步最大：**{rmax:.1f} mm**",
        "", "### 面雨量统计（前3列）", "",
        stats_table,
        "", "---", "",
        "## 3. 模拟性能指标", "",
        "| 指标 | 值 | 说明 |", "|---|---|---|",
        f"| NSE | **{_fmt(nse_v)}** | Nash-Sutcliffe，1 为完美 |",
        f"| RMSE | **{_fmt(rmse_v, fmt2f)} m3/s** | 均方根误差 |",
        f"| R2 | **{_fmt(r2_v)}** | Pearson r 的平方 |",
        f"| Bias | **{_fmt(bias_v, fmt2f)}%** | 系统偏差 |",
        f"| n | {n_samp} | 公共时步数 |",
        "", "---", "",
        "## 4. 对比图", "",
        pref, "",
        "_蓝色实线=实测，红色虚线=模拟，蓝柱=面雨量（倒置）_",
        "", "---", "",
        "## 5. 结论", "",
        f"- 简化线性水库模型，参数分区：{zone_summary}。",
        f"- IDW 面雨量插值，共 {len(areal_rain_df.columns)} 个面雨量区。",
        "- 参数未率定，建议用 calibrate_with_enkf.py 优化。",
        "", "---", "",
        "_由 run_full_pipeline.py 自动生成。_",
    ]
    report_path = RESULTS_DIR / "hydrology_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(chr(10).join(doc))
    print(f"[Step6] 报告已保存: {report_path}")
    return report_path

# ========= Main =========

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the full Hydrology pipeline with workflow metadata output.")
    parser.add_argument("--case-id", default="adhoc", help="Case identifier for workflow metadata")
    parser.add_argument("--run-id", default=None, help="Override workflow run id")
    parser.add_argument("--workflow-type", default="hydrology_full_pipeline", help="Workflow type for metadata")
    parser.add_argument("--metadata-out", default=None, help="Optional output path for workflow_run JSON")
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    started_at = datetime.utcnow().replace(microsecond=0).isoformat()
    run_id = args.run_id or f"hydrology-pipeline-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    workflow_steps: List[dict] = []
    workflow_outputs: List[dict] = []
    print("=" * 60)
    print("  完整水文建模流程")
    print("=" * 60)
    print("[Init] 加载基础数据...")
    rainfall_df = pd.read_csv(DATA_DIR / "rainfall.csv", index_col="date", parse_dates=True)
    pet_df      = pd.read_csv(DATA_DIR / "pet.csv",      index_col="date", parse_dates=True)
    observed_df = pd.read_csv(DATA_DIR / "observed_flow.csv", index_col="date", parse_dates=True)
    catchment_df = pd.read_csv(
        DATA_DIR / "catchment_definition.csv",
        dtype={"pfaf_code": str, "downstream_pfaf": str},
    )
    print(f"  降雨时序: {len(rainfall_df)} 步，列: {list(rainfall_df.columns)}")
    print(f"  子流域: {len(catchment_df)} 个")
    errors: Dict[str, str] = {}
    subbasins_file: Optional[Path] = None
    areal_rain_df: Optional[pd.DataFrame] = None
    simulated_df:  Optional[pd.DataFrame] = None
    metrics: Dict[str, float] = {}
    plot_path:   Optional[Path] = None
    report_path: Optional[Path] = None
    try:
        step_started = datetime.utcnow().replace(microsecond=0).isoformat()
        subbasins_file = step1_check_subbasins()
        step_outputs = []
        if subbasins_file:
            step_outputs.append(
                build_artifact_payload(
                    artifact_id=f"{run_id}:subbasins",
                    artifact_type="vector",
                    path=subbasins_file,
                    metadata={"role": "subbasins_with_zones"},
                )
            )
            workflow_outputs.extend(step_outputs)
        workflow_steps.append(
            build_workflow_step_payload(
                step_id="check_subbasins",
                status="completed",
                outputs=step_outputs,
                started_at=step_started,
                completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                metadata={"used_existing": subbasins_file is not None},
            )
        )
    except Exception as e:
        errors["Step1"] = str(e)
        workflow_steps.append(
            build_workflow_step_payload(
                step_id="check_subbasins",
                status="failed",
                started_at=step_started,
                completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                metadata={"error": str(e)},
            )
        )
    try:
        step_started = datetime.utcnow().replace(microsecond=0).isoformat()
        areal_rain_df = step2_areal_precipitation(subbasins_file, rainfall_df)
        areal_rain_path = RESULTS_DIR / "areal_rainfall.csv"
        areal_rain_df.to_csv(areal_rain_path)
        step_outputs = [
            build_artifact_payload(
                artifact_id=f"{run_id}:areal-rainfall",
                artifact_type="table",
                path=areal_rain_path,
                metadata={"role": "areal_rainfall", "columns": list(areal_rain_df.columns)},
            )
        ]
        workflow_outputs.extend(step_outputs)
        workflow_steps.append(
            build_workflow_step_payload(
                step_id="areal_precipitation",
                status="completed",
                outputs=step_outputs,
                started_at=step_started,
                completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                metadata={"n_timesteps": len(areal_rain_df)},
            )
        )
    except Exception as e:
        errors["Step2"] = str(e)
        areal_rain_df = pd.DataFrame({"SB_avg": rainfall_df.mean(axis=1)})
        workflow_steps.append(
            build_workflow_step_payload(
                step_id="areal_precipitation",
                status="failed",
                started_at=step_started,
                completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                metadata={"error": str(e), "fallback": "station_mean"},
            )
        )
    try:
        step_started = datetime.utcnow().replace(microsecond=0).isoformat()
        simulated_df = step3_simulate(catchment_df, areal_rain_df, pet_df["pet"])
        out_csv = RESULTS_DIR / "pipeline_simulation_results.csv"
        simulated_df.to_csv(out_csv)
        print(f"  模拟结果已保存: {out_csv}")
        step_outputs = [
            build_artifact_payload(
                artifact_id=f"{run_id}:simulation-results",
                artifact_type="table",
                path=out_csv,
                metadata={"role": "simulation_results", "columns": list(simulated_df.columns)},
            )
        ]
        workflow_outputs.extend(step_outputs)
        workflow_steps.append(
            build_workflow_step_payload(
                step_id="hydrological_simulation",
                status="completed",
                outputs=step_outputs,
                started_at=step_started,
                completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                metadata={"n_timesteps": len(simulated_df), "n_subbasins": len(catchment_df)},
            )
        )
    except Exception as e:
        errors["Step3"] = str(e)
        print(f"[Step3] 错误: {e}")
        workflow_steps.append(
            build_workflow_step_payload(
                step_id="hydrological_simulation",
                status="failed",
                started_at=step_started,
                completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                metadata={"error": str(e)},
            )
        )
    if simulated_df is not None:
        try:
            step_started = datetime.utcnow().replace(microsecond=0).isoformat()
            sim_cols = simulated_df.columns.tolist()
            outlet_col = min(sim_cols, key=lambda c: int(c.replace("simulated_flow_", "")))
            metrics = compute_metrics(observed_df["flow_m3s"], simulated_df[outlet_col])
            metrics_path = RESULTS_DIR / "pipeline_metrics.json"
            metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
            step_outputs = [
                build_artifact_payload(
                    artifact_id=f"{run_id}:metrics",
                    artifact_type="json",
                    path=metrics_path,
                    metadata={"role": "performance_metrics"},
                )
            ]
            workflow_outputs.extend(step_outputs)
            workflow_steps.append(
                build_workflow_step_payload(
                    step_id="performance_metrics",
                    status="completed",
                    outputs=step_outputs,
                    started_at=step_started,
                    completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                    metadata={"outlet_column": outlet_col},
                )
            )
        except Exception as e:
            errors["Step4"] = str(e)
            print(f"[Step4] 错误: {e}")
            workflow_steps.append(
                build_workflow_step_payload(
                    step_id="performance_metrics",
                    status="failed",
                    started_at=step_started,
                    completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                    metadata={"error": str(e)},
                )
            )
    if simulated_df is not None:
        try:
            step_started = datetime.utcnow().replace(microsecond=0).isoformat()
            plot_path = step5_plot_comparison(rainfall_df, observed_df, simulated_df, metrics)
            step_outputs = []
            if plot_path:
                step_outputs.append(
                    build_artifact_payload(
                        artifact_id=f"{run_id}:flow-comparison-plot",
                        artifact_type="image",
                        path=plot_path,
                        metadata={"role": "flow_comparison_plot"},
                    )
                )
                workflow_outputs.extend(step_outputs)
            workflow_steps.append(
                build_workflow_step_payload(
                    step_id="comparison_plot",
                    status="completed" if plot_path else "skipped",
                    outputs=step_outputs,
                    started_at=step_started,
                    completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                    metadata={"plot_generated": plot_path is not None},
                )
            )
        except Exception as e:
            errors["Step5"] = str(e)
            print(f"[Step5] 错误: {e}")
            workflow_steps.append(
                build_workflow_step_payload(
                    step_id="comparison_plot",
                    status="failed",
                    started_at=step_started,
                    completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                    metadata={"error": str(e)},
                )
            )
    try:
        step_started = datetime.utcnow().replace(microsecond=0).isoformat()
        empty_df = pd.DataFrame()
        report_path = step6_generate_report(
            subbasins_file=subbasins_file,
            catchment_df=catchment_df,
            areal_rain_df=areal_rain_df if areal_rain_df is not None else empty_df,
            simulated_df=simulated_df  if simulated_df  is not None else empty_df,
            observed_df=observed_df,
            metrics=metrics,
            plot_path=plot_path,
        )
        step_outputs = [
            build_artifact_payload(
                artifact_id=f"{run_id}:markdown-report",
                artifact_type="markdown_report",
                path=report_path,
                metadata={"role": "pipeline_markdown_report"},
            )
        ]
        workflow_outputs.extend(step_outputs)
        workflow_steps.append(
            build_workflow_step_payload(
                step_id="generate_report",
                status="completed",
                outputs=step_outputs,
                started_at=step_started,
                completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                metadata={"report_path": str(report_path)},
            )
        )
    except Exception as e:
        errors["Step6"] = str(e)
        print(f"[Step6] 错误: {e}")
        workflow_steps.append(
            build_workflow_step_payload(
                step_id="generate_report",
                status="failed",
                started_at=step_started,
                completed_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                metadata={"error": str(e)},
            )
        )
    print("")
    print("=" * 60)
    print("  流程完成摘要")
    print("=" * 60)
    if metrics:
        nse  = metrics.get("NSE",      float("nan"))
        rmse = metrics.get("RMSE",     float("nan"))
        r2   = metrics.get("R2",       float("nan"))
        bias = metrics.get("Bias_pct", float("nan"))
        print(f"  NSE   : {nse:.4f}"  if not math.isnan(nse)  else "  NSE   : N/A")
        print(f"  RMSE  : {rmse:.2f} m3/s" if not math.isnan(rmse) else "  RMSE  : N/A")
        print(f"  R2    : {r2:.4f}"   if not math.isnan(r2)   else "  R2    : N/A")
        print(f"  Bias  : {bias:.2f}%" if not math.isnan(bias) else "  Bias  : N/A")
    else:
        print("  （未获得有效性能指标）")
    if errors:
        print("")
        print("各步骤错误汇总:")
        for step, err in errors.items():
            print(f"  {step}: {err}")
    if report_path:
        print(f"")
        print(f"报告路径: {report_path}")
    if plot_path:
        print(f"对比图路径: {plot_path}")
    print("=" * 60)

    if CONTRACTS_AVAILABLE:
        completed_at = datetime.utcnow().replace(microsecond=0).isoformat()
        metadata_out = Path(args.metadata_out) if args.metadata_out else RESULTS_DIR / "pipeline.workflow_run.json"
        summary_out = RESULTS_DIR / "pipeline.run_summary.json"
        payload = build_workflow_run_payload(
            run_id=run_id,
            case_id=args.case_id,
            workflow_type=args.workflow_type,
            status="failed" if errors else "completed",
            config_path=Path(__file__),
            components=["run_full_pipeline"],
            dt_seconds=86400,
            num_steps=len(rainfall_df),
            started_at=started_at,
            completed_at=completed_at,
            output_artifacts=workflow_outputs,
            metadata={
                "errors": errors,
                "results_dir": str(RESULTS_DIR),
                "step_count": len(workflow_steps),
            },
        )
        payload["steps"] = workflow_steps
        write_workflow_run_metadata(metadata_out, payload)
        run_summary = {
            "run_id": run_id,
            "case_id": args.case_id,
            "workflow_type": args.workflow_type,
            "status": "failed" if errors else "completed",
            "results_dir": str(RESULTS_DIR),
            "n_subbasins": len(catchment_df),
            "n_timesteps": len(rainfall_df),
            "subbasins_file": str(subbasins_file) if subbasins_file else None,
            "areal_precipitation_method": "idw_or_station_mean_fallback",
            "metrics": metrics,
            "report_path": str(report_path) if report_path else None,
            "plot_path": str(plot_path) if plot_path else None,
            "warnings": errors,
            "artifacts": workflow_outputs,
        }
        summary_out.write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"workflow metadata: {metadata_out}")
        print(f"run summary: {summary_out}")


if __name__ == "__main__":
    main()
