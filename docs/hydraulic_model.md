# 1D水动力模型 (`preissmann_model`)

`preissmann_model`是一个强大的组件，用于模拟明渠中的1D非恒定流。它使用隐式Preissmann格式求解完整的Saint-Venant方程，该格式具有鲁棒性，适用于各种亚临界流场景。

## `HydraulicModel` 组件

用于水动力模拟的主要组件是`HydraulicModel`。它代表一个河段并协调求解器。

**配置示例：**
```yaml
components:
  - name: "MyRiver"
    type: HydraulicModel
    parameters:
      dt: 60 # 时间步长(秒)
      downstream_level: 10.0 # 下游水位边界条件
      reach: { ... } # 河段定义，见下文
      structures: [ ... ] # 液压结构列表，见下文
```

## `RiverReach` 配置

`reach`参数定义了河道的物理属性。

```yaml
      reach:
        type: RiverReach
        parameters:
          num_nodes: 10
          length: 1000 # 米
          slope: 0.001 # m/m
          manning_n: 0.03
          cross_sections:
            - type: ... # 断面定义，见下文
```

## 断面类型

`cross_sections`参数定义了河道的形状。如果只提供一个断面，则假定整个河段是均匀的(棱柱形河道)。

### `RectangularCrossSection`
一个简单的矩形。
```yaml
          cross_sections:
            - type: RectangularCrossSection
              parameters:
                width: 20.0 # 米
```

### `TrapezoidalCrossSection`
梯形形状，适用于工程河道。
```yaml
          cross_sections:
            - type: TrapezoidalCrossSection
              parameters:
                bottom_width: 20.0 # 米
                side_slope: 2.0 # 2:1 (H:V) 边坡
```

### `IrregularCrossSection`
使用一系列站点-高程点定义任意形状。这对于天然河道非常理想。
```yaml
          cross_sections:
            - type: IrregularCrossSection
              parameters:
                # (站点, 高程) 元组列表
                points:
                  - [0, 15]
                  - [10, 10]
                  - [30, 10]
                  - [40, 15]
```

## 液压结构

液压结构如闸门、泵或堰可以放置在河道内的节点上。它们在`HydraulicModel`的`structures`参数下的列表中定义。

### `Gate`
闸门结构。
```yaml
      structures:
        - name: "SluiceGate"
          type: Gate
          parameters:
            node_index: 4 # 放置在第5个节点(0索引)
            opening_height: 1.0 # 米
            width: 20.0 # 米
            C_d: 0.6 # 流量系数
```

### `Pump`
具有特征曲线的泵。
```yaml
      structures:
        - name: "MyPump"
          type: Pump
          parameters:
            node_index: 2
            # (a, b, c) 系数用于 delta_H = a*Q^2 + b*Q + c
            curve_coeffs: [-0.001, 0.1, 5.0]
```

### `Weir`
宽顶堰结构。
```yaml
      structures:
        - name: "UpstreamWeir"
          type: Weir
          parameters:
            node_index: 4
            crest_elevation: 12.0 # 米
            width: 20.0 # 米
            C_d: 1.6 # 流量系数
```

## 完整示例

有关这些功能的完整可运行演示，请参见`examples/hydraulic_features_example/`目录中的示例。