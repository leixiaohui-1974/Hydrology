"""简单降雨-径流示例脚本，演示如何在没有完整河网模型的情况下
使用经验参数对多个子流域进行产流并沿着河网汇流。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


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
            raise ValueError(f"未找到参数分区 {zone_id}")
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


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir.parent / "data"

    catchment_df = pd.read_csv(data_dir / "catchment_definition.csv", dtype={"pfaf_code": str, "downstream_pfaf": str})
    rainfall_df = pd.read_csv(data_dir / "rainfall.csv", index_col="date", parse_dates=True)
    pet_df = pd.read_csv(data_dir / "pet.csv", index_col="date", parse_dates=True)
    observed_flow_df = pd.read_csv(data_dir / "observed_flow.csv", index_col="date", parse_dates=True)

    params_map = {
        "zone_A": {"S_max": 200, "k_q": 0.8, "k_s": 0.1, "c_loss": 0.05},
        "zone_B": {"S_max": 150, "k_q": 0.9, "k_s": 0.05, "c_loss": 0.02},
    }

    simulated_df = simulate_network(catchment_df, params_map, rainfall_df, pet_df["pet"])

    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    simulated_df.to_csv(results_dir / "simulation_results.csv")
    print("模拟完成，结果已保存到 results/simulation_results.csv")

    comparison_df = pd.DataFrame(index=rainfall_df.index)
    comparison_df["rainfall"] = rainfall_df.filter(like="rainfall_1").iloc[:, 0]
    comparison_df["observed_flow"] = observed_flow_df["flow_m3s"]
    comparison_df["simulated_flow"] = simulated_df.filter(like="simulated_flow_1").iloc[:, 0]
    comparison_df.to_csv(results_dir / "final_comparison_table.csv")
    print("对比数据表已保存到 results/final_comparison_table.csv")

    fig, ax1 = plt.subplots(figsize=(15, 7))
    ax1.plot(comparison_df.index, comparison_df["simulated_flow"], "b-", label="Simulated Flow")
    ax1.plot(comparison_df.index, comparison_df["observed_flow"], "k--", label="Observed Flow")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Flow (m³/s)", color="b")
    ax1.tick_params(axis="y", labelcolor="b")
    ax1.legend(loc="upper left")

    ax2 = ax1.twinx()
    ax2.bar(comparison_df.index, comparison_df["rainfall"], width=0.6, color="c", alpha=0.6, label="Rainfall")
    ax2.set_ylabel("Rainfall (mm)", color="c")
    ax2.tick_params(axis="y", labelcolor="c")
    ax2.invert_yaxis()

    ax1.xaxis.set_major_locator(mdates.DayLocator(interval=max(len(comparison_df) // 10, 1)))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.gcf().autofmt_xdate()
    plt.title("Rainfall, Observed Flow, and Simulated Flow at Catchment Outlet")
    plt.tight_layout()
    plt.savefig(results_dir / "comparison_plot.png")
    print("对比图已保存到 results/comparison_plot.png")


if __name__ == "__main__":
    main()
