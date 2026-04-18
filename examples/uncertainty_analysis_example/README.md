# 不确定性分析示例

本示例演示如何使用Hydro-Suite的不确定性分析功能，包括Monte Carlo分析、敏感性分析和贝叶斯不确定性量化。

## 🎯 功能特性

### 1. Monte Carlo不确定性分析
- **参数空间采样**: 支持正态、对数正态、均匀、三角分布
- **并行化计算**: 多进程并行执行，提高计算效率
- **统计分析**: 自动计算均值、标准差、分位数等统计量
- **置信区间**: 计算不同置信水平的置信区间
- **可视化**: 参数分布图、输出分布图、散点图矩阵

### 2. 敏感性分析
- **Sobol指数**: 计算一阶、二阶和总阶敏感性指数
- **Morris方法**: 基于轨迹的敏感性分析方法
- **FAST方法**: 傅里叶振幅敏感性测试
- **参数排序**: 自动生成敏感性参数排序
- **结果对比**: 多种方法的敏感性结果对比

### 3. 贝叶斯不确定性量化
- **MCMC采样**: 使用emcee库进行MCMC采样
- **先验分布**: 支持多种先验分布类型
- **后验推断**: 计算后验统计量和可信区间
- **模型拟合**: 观测数据与模型预测的对比
- **诊断图**: 参数轨迹图、自相关图、后验分布图

## 🚀 快速开始

### 安装依赖
```bash
pip install -r ../../requirements.txt
```

### 运行示例
```bash
python run_uncertainty_analysis.py
```

### 配置文件
修改 `config_uncertainty.yaml` 文件来自定义分析参数。

## 📊 示例结果

### Monte Carlo分析结果
- **参数样本**: `monte_carlo_results/parameter_samples.csv`
- **模型输出**: `monte_carlo_results/model_outputs.csv`
- **统计信息**: `monte_carlo_results/statistics.json`
- **置信区间**: `monte_carlo_results/confidence_intervals.json`
- **分布图**: `monte_carlo_results/parameter_distributions.png`

### 敏感性分析结果
- **Sobol指数**: `sensitivity_analysis_results/sobol_indices.json`
- **Morris指数**: `sensitivity_analysis_results/morris_indices.json`
- **FAST指数**: `sensitivity_analysis_results/fast_indices.json`
- **参数排序**: `sensitivity_analysis_results/*_ranking.csv`
- **敏感性图**: `sensitivity_analysis_results/sensitivity_analysis.png`

### 贝叶斯分析结果
- **MCMC样本**: `bayesian_analysis_results/mcmc_samples.csv`
- **后验统计**: `bayesian_analysis_results/posterior_statistics.json`
- **可信区间**: `bayesian_analysis_results/credible_intervals.json`
- **有效样本**: `bayesian_analysis_results/effective_sample_sizes.json`
- **诊断图**: `bayesian_analysis_results/*.png`

### 综合对比图
- **对比分析**: `uncertainty_analysis_comparison.png`

## 🔧 配置说明

### 分析类型配置
```yaml
analysis_types:
  monte_carlo: true          # 启用Monte Carlo分析
  sensitivity_analysis: true # 启用敏感性分析
  bayesian_analysis: true    # 启用贝叶斯分析
```

### 参数配置
```yaml
parameters:
  curve_number:
    distribution: "normal"    # 分布类型
    mean: 75.0               # 分布参数
    std: 8.0
```

### 性能配置
```yaml
performance:
  parallel:
    enabled: true            # 启用并行计算
    max_workers: 4          # 最大工作进程数
    backend: "multiprocessing"
```

## 📈 模型说明

本示例使用简化的集总式水文模型，包括：

### 1. SCS曲线数方法
```python
s = 254 * (100 / cn - 1)  # 潜在最大滞留量
q = (rainfall - 0.2 * s) ** 2 / (rainfall + 0.8 * s)
```

### 2. 不透水面积处理
```python
total_runoff = q * (1 - imp) + rainfall * imp
```

### 3. 蓄水容量限制
```python
actual_runoff = min(total_runoff, sc)
```

### 4. 路由延迟
```python
delay_factor = np.exp(-time / (rc * 10))
```

## 🎨 可视化特性

### 1. 参数分布图
- 直方图显示采样分布
- 理论分布曲线对比
- 多参数并排显示

### 2. 敏感性分析图
- Sobol指数条形图
- Morris散点图（μ* vs σ）
- FAST敏感性指数图

### 3. 贝叶斯诊断图
- 后验分布corner图
- 参数轨迹图
- 自相关图
- 模型拟合图

### 4. 综合对比图
- 2x2子图布局
- 不同分析方法结果对比
- 统一的图例和标签

## 📝 输出报告

### 1. 控制台输出
- 分析进度显示
- 关键结果摘要
- 错误和警告信息

### 2. 文本报告
- 详细统计信息
- 参数估计结果
- 不确定性量化指标

### 3. 图形报告
- 高质量PNG图像
- 可调整的图形尺寸
- 专业的科学图表样式

## 🔍 高级功能

### 1. 自定义模型
```python
def custom_model(params, times):
    # 实现自定义水文模型
    return outputs

analyzer.set_model_function(custom_model)
```

### 2. 自定义先验
```python
analyzer.add_parameter('param_name', 'custom_prior', **prior_params)
```

### 3. 自定义输出
```python
analyzer.save_results('custom_output_dir')
```

### 4. 进度监控
```python
def progress_callback(progress):
    print(f"Progress: {progress:.1f}%")

analyzer.run_monte_carlo(model_function, progress_callback)
```

## ⚠️ 注意事项

### 1. 计算资源
- Monte Carlo分析计算量大，建议使用多核CPU
- 贝叶斯分析需要足够的内存存储MCMC样本
- 敏感性分析可以并行化以提高效率

### 2. 参数设置
- 采样数量影响分析精度和计算时间
- 先验分布选择影响贝叶斯分析结果
- 参数边界设置要合理

### 3. 模型要求
- 模型函数需要能够处理向量化输入
- 输出格式要一致
- 异常处理要完善

## 🚀 扩展应用

### 1. 集成到现有模型
```python
from hydro_model.uncertainty import MonteCarloAnalyzer

# 使用现有的水文模型
analyzer = MonteCarloAnalyzer()
analyzer.set_model_function(existing_hydrology_model)
```

### 2. 批量分析
```python
# 分析多个参数组合
for param_set in parameter_sets:
    analyzer.add_parameter_distribution(**param_set)
    results = analyzer.run_monte_carlo(model_function)
```

### 3. 结果后处理
```python
# 自定义结果分析
samples = analyzer.samples
custom_analysis = perform_custom_analysis(samples)
```

## 📚 参考文献

1. Saltelli, A., et al. (2008). Global Sensitivity Analysis: The Primer
2. Morris, M. D. (1991). Factorial sampling plans for preliminary computational experiments
3. Cukier, R. I., et al. (1978). Study of the sensitivity of coupled reaction systems to uncertainties in rate coefficients
4. Foreman-Mackey, D., et al. (2013). emcee: The MCMC Hammer

## 🤝 贡献指南

欢迎提交问题报告和功能建议！

### 报告问题
- 使用GitHub Issues
- 提供详细的错误信息
- 包含系统环境信息

### 贡献代码
- Fork项目仓库
- 创建功能分支
- 提交Pull Request

## 📄 许可证

本项目采用MIT许可证，详见LICENSE文件。

---

*本示例展示了Hydro-Suite不确定性分析功能的强大能力，为水文建模提供了科学的参数估计和不确定性量化工具。*

