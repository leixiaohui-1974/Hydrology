import pandas as pd
from hydro_model.catchment import Catchment

def main():
    # 1. 定义参数
    params_zone_a = {'S_max': 200, 'k_q': 0.8, 'k_s': 0.1, 'c_loss': 0.05}
    params_zone_b = {'S_max': 150, 'k_q': 0.9, 'k_s': 0.05, 'c_loss': 0.02}

    # 2. 加载数据
    # 指定 dtype 确保 pfafstetter 编码被视为字符串
    catchment_def = pd.read_csv('../data/catchment_definition.csv', dtype={'pfaf_code': str, 'downstream_pfaf': str})
    rainfall_df = pd.read_csv('../data/rainfall.csv', index_col='date', parse_dates=True)
    pet_df = pd.read_csv('../data/pet.csv', index_col='date', parse_dates=True)

    # 3. 初始化流域
    catchment = Catchment()
    catchment.add_parameter_zone('zone_A', params_zone_a)
    catchment.add_parameter_zone('zone_B', params_zone_b)

    for _, row in catchment_def.iterrows():
        pfaf_code = row['pfaf_code']
        downstream_pfaf = row['downstream_pfaf']
        # 如果 downstream_pfaf 为空或 NaN，则设为 None
        if pd.isna(downstream_pfaf) or not downstream_pfaf.strip():
            downstream_pfaf = None

        catchment.add_sub_basin(
            pfaf_code=pfaf_code,
            area=row['area_km2'],
            zone_id=row['zone_id'],
            downstream_pfaf=downstream_pfaf
        )

    # 4. 准备输入数据
    rainfall_data = {
        '1': rainfall_df['rainfall_1'].values,
        '2': rainfall_df['rainfall_2'].values,
        '3': rainfall_df['rainfall_3'].values
    }

    # 假设所有子流域的 PET 相同
    pet_values = pet_df['pet'].values
    pet_data = {
        '1': pet_values,
        '2': pet_values,
        '3': pet_values
    }

    # 5. 运行模拟
    simulated_flows = catchment.run_simulation(rainfall_data, pet_data)

    # 将结果保存到 DataFrame 中，以便于后续处理
    results_df = pd.DataFrame(index=rainfall_df.index)
    results_df['simulated_flow_1'] = simulated_flows['1']
    results_df['simulated_flow_2'] = simulated_flows['2']
    results_df['simulated_flow_3'] = simulated_flows['3']

    # 保存结果到 CSV
    results_df.to_csv('results/simulation_results.csv')
    print("模拟完成，结果已保存到 results/simulation_results.csv")

    # 6. 生成最终结果和可视化
    # 加载观测流量
    observed_flow_df = pd.read_csv('../data/observed_flow.csv', index_col='date', parse_dates=True)

    # 准备用于绘图和表格的数据
    comparison_df = pd.DataFrame(index=rainfall_df.index)
    comparison_df['rainfall'] = rainfall_df['rainfall_1'] # 使用出口子流域的降雨
    comparison_df['observed_flow'] = observed_flow_df['flow_m3s']
    comparison_df['simulated_flow'] = results_df['simulated_flow_1']

    # 保存对比数据表
    comparison_df.to_csv('results/final_comparison_table.csv')
    print("对比数据表已保存到 results/final_comparison_table.csv")

    # 生成对比图
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    fig, ax1 = plt.subplots(figsize=(15, 7))

    # 绘制流量
    ax1.plot(comparison_df.index, comparison_df['simulated_flow'], 'b-', label='Simulated Flow')
    ax1.plot(comparison_df.index, comparison_df['observed_flow'], 'k--', label='Observed Flow')
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Flow (m³/s)', color='b')
    ax1.tick_params(axis='y', labelcolor='b')
    ax1.legend(loc='upper left')

    # 创建第二个 y 轴用于绘制降雨
    ax2 = ax1.twinx()
    ax2.bar(comparison_df.index, comparison_df['rainfall'], width=0.6, color='c', alpha=0.6, label='Rainfall')
    ax2.set_ylabel('Rainfall (mm)', color='c')
    ax2.tick_params(axis='y', labelcolor='c')
    ax2.invert_yaxis() # 降雨图倒置

    # 格式化日期
    ax1.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gcf().autofmt_xdate()

    plt.title('Rainfall, Observed Flow, and Simulated Flow at Catchment Outlet')
    plt.tight_layout()
    plt.savefig('results/comparison_plot.png')
    print("对比图已保存到 results/comparison_plot.png")


if __name__ == '__main__':
    main()
