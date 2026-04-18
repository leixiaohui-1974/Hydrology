# 示例: 基础水文模型运行

**脚本:** `examples/run_example.py`

## 目的

此示例用于演示项目第一部分实现的基础准分布式水文模型的核心功能。它展示了如何：
1.  从CSV文件中加载流域定义、参数和气象数据。
2.  设置一个包含多个子流域、多个参数分区的完整流域。
3.  按正确的汇流顺序（从上游到下游）运行模拟。
4.  生成包含模拟流量、观测流量和降雨数据的对比图和数据表。

## 如何运行

```bash
python examples/run_example.py
```

## 输入

-   `data/catchment_definition.csv`: 定义了三个子流域的连接关系、面积和所属参数分区。
-   `data/rainfall.csv`: 为每个子流域提供了独立的降雨时间序列。
-   `data/pet.csv`: 提供了全流域统一的潜在蒸散发数据。
-   `data/observed_flow.csv`: 提供了在总出水口处的“真实”流量，用于与模拟结果进行对比。

## 输出

-   `examples/results/simulation_results.csv`: 包含每个子流域模拟出的流量过程线。
-   `examples/results/final_comparison_table.csv`: 一个合并后的数据表，包含总出水口的降雨、观测流量和模拟流量。
-   `examples/results/comparison_plot.png`: 一张可视化的对比图，用于直观评估模型的模拟效果。
