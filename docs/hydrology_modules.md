# 水文模块

本文档详细介绍了可在`HydrologicalModel`组件中使用的各种基于过程的模块。

## 产流模块

产流模块是水文模型的核心，用于计算从降雨(或融雪模块的液态水)产生的径流量。

### `SimpleRunoffModule`
一个基本的概念模型，具有最大土壤蓄水(`S_max`)和损失系数(`c_loss`)参数。

### `SCSCurveNumberModule`
一种基于广泛使用的SCS曲线数法的经验模型。其主要参数是`CN`。

### `XinanjiangRunoffModule`
一种在湿润地区流行的复杂概念模型，具有许多参数(K, B, IM等)。

### `HymodRunoffModule`
一种流行的5参数概念模型(`cmax`, `bexp`, `alpha`, `ks`, `kq`)。

## 融雪模块

融雪模块可以可选地包含在`HydrologicalModel`中。它们作为产流模块的预处理器，接收总降水和温度输入，并输出可用于产流生成的液态水量(降雨+融雪)。

### `SnowmeltRunoffModule`
一种简单而有效的温度指数(或度日)模型。

#### 功能
- **降水分配:** 根据`base_temperature`确定降水是降雨还是降雪。
- **积雪累积:** 将新降雪添加到雪水当量(SWE)状态变量。
- **融雪计算:** 根据超过基础温度的温度和`degree_day_factor`计算融雪量。

#### 配置示例
`snowmelt_module`在`config.yaml`中的`HydrologicalModel`内定义为子组件：

```yaml
components:
  - name: "SnowyCatchment"
    type: HydrologicalModel
    parameters:
      # 该模型有两个子模块：一个用于融雪，一个用于产流
      snowmelt_module:
        type: SnowmeltRunoffModule
        parameters:
          degree_day_factor: 4.5 # mm/day/°C
          base_temperature: 0.5 # °C

      runoff_module:
        type: SimpleRunoffModule
        parameters:
          S_max: 100.0
          c_loss: 0.1
```

#### 所需输入
当`HydrologicalModel`包含`snowmelt_module`时，除了`rainfall`(代表总降水)外，还需要在`global_inputs`中提供温度时间序列。

#### 示例
有关完整可运行的演示，请参见`examples/snowmelt_example/`目录中的示例。