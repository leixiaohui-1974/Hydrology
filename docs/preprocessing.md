# 数据预处理与验证

为确保模型输入的质量并生成有价值的派生数据，该框架包含一个强大的数据预处理流水线，在主模拟运行之前执行。该流水线通过`config.yaml`文件中的`preprocessing`部分进行配置。

## 径流系数计算

该工具提供了一种快速有效的方法来验证降雨和径流数据的一致性。它计算整个重叠数据期间的径流系数。输出的系数为负数或大于1.0是数据存在问题的强烈指示，如单位不匹配、集水区面积不正确或重大数据质量问题。

### 配置
要启用此检查，请在`config.yaml`的`preprocessing`块中添加`runoff_coefficient`部分：

```yaml
preprocessing:
  runoff_coefficient:
    rainfall_input: "precip_areal"  # 降雨数据源的名称
    flow_input: "observed_flow"     # 径流数据源的名称
    catchment_area_km2: 500.0       # 集水区面积(平方公里)
```

### 参数：
- `rainfall_input` (必需): 包含降雨时间序列的数据源名称。这可以是初始输入或先前处理步骤的输出(如`areal_precipitation`)。
- `flow_input` (必需): 观测径流数据源的名称。
- `catchment_area_km2` (必需): 以平方公里为单位的集水区面积，用于将降雨深度转换为体积。

### 输出：
该工具将计算的总体积和结果径流系数打印到控制台，如果值超出[0, 1]的合理范围，则会发出警告。

## 基流分割

该工具将总径流过程线分割为两个组成部分：快速流(直接径流)和基流。这对于更详细的模型分析和率定很有用。该实现使用鲁棒的三遍Lyne-Hollick数字滤波器。

### 配置
要使用此功能，请在`preprocessing`块中添加`baseflow_separation`部分：

```yaml
preprocessing:
  baseflow_separation:
    flow_input: "observed_flow"
    output_baseflow: "flow_base"     # 新基流数据源的名称
    output_quickflow: "flow_quick"   # 新快速流数据源的名称
    parameters:
      alpha: 0.925
      passes: 3
      n_reflect: 10
```

### 参数：
- `flow_input` (必需): 要分割的径流数据源的名称。
- `output_baseflow` (必需): 要给予新基流时间序列的名称。这个新的数据源可以被其他组件使用。
- `output_quickflow` (必需): 要给予新快速流时间序列的名称。
- `parameters` (可选): Lyne-Hollick滤波器的参数字典。
    - `alpha` (可选，默认: 0.925): 滤波器参数。
    - `passes` (可选，默认: 3): 滤波器遍数。必须是奇数整数。
    - `n_reflect` (可选，默认: 30): 在序列末端反射的数据点数以减少伪影。

## 链式操作

预处理流水线设计为灵活的。一个步骤的`output_name`(例如`areal_precipitation`)可以用作后续步骤的`input_name`或`rainfall_input`。这允许您为数据准备创建自定义的链式工作流。

## 完整示例
有关这些功能的完整可运行演示，请参见`examples/preprocessing_example/`目录中的示例。