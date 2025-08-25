# 实时预报系统示例

## 概述

实时预报系统是Hydro-Suite水文建模平台的核心组件，提供实时数据接入、预报模型、预警系统和可视化监控功能。本示例展示了系统的各项功能和使用方法。

## 主要功能

### 1. 实时数据接入
- **传感器数据接入**: 支持多种传感器类型（流量、水位、降雨等）
- **数据质量控制**: 自动检测异常数据，确保数据质量
- **实时数据验证**: 验证数据完整性和一致性
- **数据插补**: 自动填充缺失数据，保持数据连续性

### 2. 预报模型
- **短期预报**: 1-6小时预报，支持实时校正
- **中期预报**: 1-7天预报，基于集合预报方法
- **集合预报**: 多模型集成，提高预报精度
- **预报校正**: 支持卡尔曼滤波、偏差校正等多种方法

### 3. 预警系统
- **预警阈值管理**: 支持静态和动态阈值设置
- **预警信息生成**: 多语言支持，自动生成预警信息
- **预警信息发布**: 多渠道发布（邮件、短信、Webhook等）
- **预警升级管理**: 自动升级机制，支持时间阈值

### 4. 实时仪表板
- **实时监控**: 实时显示关键指标和状态
- **预报可视化**: 多种图表展示预报结果
- **预警监控**: 实时监控预警状态和趋势
- **性能跟踪**: 跟踪系统性能指标

## 文件结构

```
examples/realtime_forecasting_example/
├── run_realtime_forecasting.py      # 主程序
├── config_realtime_forecasting.yaml # 配置文件
├── README.md                        # 说明文档
└── output/                          # 输出目录
    └── forecasts/                   # 预报图表
```

## 快速开始

### 1. 环境准备

确保已安装所需的Python包：

```bash
pip install numpy pandas matplotlib seaborn pyyaml
```

### 2. 运行示例

```bash
cd examples/realtime_forecasting_example
python run_realtime_forecasting.py
```

### 3. 查看结果

程序运行完成后，会在`output/`目录下生成以下文件：
- `forecast_comparison.png`: 预报对比图
- `ensemble_forecast.png`: 集合预报图
- `forecast_skill.png`: 预报技能评分图

## 配置说明

### 数据接入配置

```yaml
data_acquisition:
  sensors:
    flow_sensor:
      type: flow
      unit: m³/s
      location: main_river
      update_frequency: 5s
  acquisition_interval: 60
```

### 预警阈值配置

```yaml
warning_thresholds:
  static_thresholds:
    flow:
      attention: 600
      warning: 800
      severe: 1000
      critical: 1200
```

### 预报模型配置

```yaml
short_term_forecasting:
  forecaster:
    forecast_horizon: 6
    time_step: 15
    correction_method: kalman_filter
```

## 功能演示

### 数据接入演示

```python
# 配置数据接入
config = {
    'sensors': {
        'flow_sensor': {'type': 'flow', 'unit': 'm³/s'},
        'water_level_sensor': {'type': 'water_level', 'unit': 'm'}
    },
    'acquisition_interval': 60
}

# 初始化数据接入器
data_acquisition = SensorDataAcquisition(config)
stats = data_acquisition.get_data_statistics()
```

### 预报模型演示

```python
# 短期预报
short_term_forecaster = ShortTermForecaster(config)
short_term_forecaster.train(training_data)

input_data = {'current_value': 120, 'trend': 3, 'variable': 'flow', 'unit': 'm³/s'}
lead_time = timedelta(hours=2)
forecast_result = short_term_forecaster.forecast(input_data, lead_time)
```

### 预警系统演示

```python
# 预警阈值管理
threshold_manager = WarningThresholdManager(config)
threshold = WarningThreshold(
    variable='flow',
    warning_level=WarningLevel.WARNING,
    threshold_value=800.0,
    threshold_type='above'
)
threshold_manager.add_threshold('flow', threshold)

# 检查预警
warning_event = threshold_manager.check_warning('flow', 850.0, 'main_river')
```

### 可视化演示

```python
# 预报可视化
visualizer = ForecastVisualizer(config)
fig = visualizer.plot_forecast_comparison(
    observed_data, forecast_data, time_index,
    title="流量预报对比图"
)
```

## 性能特点

- **实时性**: 支持秒级数据更新和预报
- **可扩展性**: 模块化设计，易于扩展新功能
- **高精度**: 多种预报方法集成，提高预报精度
- **可靠性**: 完善的异常处理和容错机制

## 技术架构

### 核心模块

1. **数据接入层**: 负责传感器数据采集和预处理
2. **预报引擎**: 执行各种预报算法和模型
3. **预警引擎**: 管理预警阈值和触发逻辑
4. **可视化层**: 提供图表和仪表板展示
5. **监控层**: 跟踪系统性能和状态

### 数据流

```
传感器 → 数据接入 → 质量控制 → 预报模型 → 预警系统 → 可视化展示
```

### 技术栈

- **Python**: 主要开发语言
- **NumPy/Pandas**: 数据处理和分析
- **Matplotlib/Seaborn**: 数据可视化
- **PyYAML**: 配置文件处理
- **Threading**: 多线程并发处理

## 扩展指南

### 添加新的传感器类型

1. 在配置文件中定义新的传感器
2. 实现相应的数据验证规则
3. 添加预警阈值配置

### 集成新的预报模型

1. 继承`BaseForecaster`基类
2. 实现`train`和`forecast`方法
3. 在配置文件中添加模型参数

### 自定义预警规则

1. 定义预警等级和阈值
2. 实现预警触发逻辑
3. 配置预警升级规则

## 故障排除

### 常见问题

1. **数据接入失败**: 检查传感器配置和网络连接
2. **预报精度低**: 调整模型参数或增加训练数据
3. **预警误报**: 优化阈值设置和异常检测参数
4. **性能问题**: 调整更新频率和缓存设置

### 日志分析

系统会生成详细的日志文件，包含：
- 数据接入状态
- 预报模型运行情况
- 预警触发记录
- 系统性能指标

## 联系支持

如有问题或建议，请联系：
- 项目维护者: Hydro-Suite Team
- 邮箱: support@hydro-suite.com
- 文档: https://docs.hydro-suite.com

## 许可证

本项目采用MIT许可证，详见LICENSE文件。
