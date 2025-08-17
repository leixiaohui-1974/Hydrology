# 示例: EnKF参数率定与数据同化

**脚本:**
- `examples/calibrate_with_enkf.py`
- `examples/plot_enkf_results.py`

## 目的

此示例用于演示项目的第三部分功能：使用集合卡尔曼滤波（EnKF）进行参数率定和数据同化。它展示了：
1.  如何使用“增广状态向量”技术，将模型参数与状态变量一同放入EnKF框架中进行优化。
2.  如何实时地将观测流量数据同化进模型，动态地校正模型状态和参数。
3.  同化过程如何显著改善流量模拟效果（相比于无同化的“开环”模拟）。
4.  模型参数如何随着时间的推移，从一个不准确的初始猜测值，逐渐收敛到更优、更稳定的值。

## 如何运行

1.  **运行同化程序:**
    ```bash
    python examples/calibrate_with_enkf.py
    ```
2.  **可视化结果:**
    ```bash
    python examples/plot_enkf_results.py
    ```

## 输入

-   `data/rainfall.csv`: 降雨数据。
-   `data/pet.csv`: 潜在蒸散发数据。
-   `data/observed_flow.csv`: 每日观测流量，这是EnKF进行校正的依据。

## 输出

-   `examples/results/enkf_flow_results.csv`: 包含观测流量、开环模拟流量和同化后流量的数据表。
-   `examples/results/enkf_parameter_evolution.csv`: 记录了模型状态和参数的均值在模拟过程中的逐日演变。
-   `examples/results/enkf_flow_comparison.png`: 一张对比图，直观展示同化后的流量过程线相比于开环模拟，如何更逼近于真实的观测值。
-   `examples/results/enkf_parameter_convergence.png`: 一张包含多个子图的图表，展示了每个关键水文参数（如`S_max`, `k_q`等）是如何从初始猜测值开始，通过学习观测数据，逐步收敛的。
