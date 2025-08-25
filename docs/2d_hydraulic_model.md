# 2D水动力模型 (`model_2d`)

`model_2d`组件提供了一个概念验证的二维水动力模型，用于在非结构化三角网格上模拟深度平均的浅水流动。

## 功能概述

- **数值格式:** 该模型使用一阶准确的**有限体积**方法和**Rusanov通量**格式求解2D浅水方程。
- **非结构化网格:** 它在灵活的三角网格上运行，允许对复杂几何形状进行建模。
- **边界条件:** 该模型现在支持可配置的边界条件，使其超越了简单的概念验证。

## 网格文件格式

该模型需要一个JSON格式的网格定义。该文件必须包含两个键：
- `points`: 每个网格节点的`[x, y]`坐标列表。
- `triangles`: 定义三角面连接性的`[node_id_1, node_id_2, node_id_3]`列表。

提供了一个实用脚本来帮助生成这种格式的简单通道网格：
```bash
python3 utils/create_channel_mesh.py --output_path path/to/your/mesh.json
```
该脚本还会打印上游边界边的ID，您需要这些ID来设置边界条件。

## 配置

要使用2D模型，请在`config.yaml`中定义一个`HydraulicModel2D`组件。

### 配置示例：
```yaml
components:
  - name: "Channel2D"
    type: HydraulicModel2D
    parameters:
      # 网格文件的路径，相对于配置文件
      mesh_file: "channel_mesh.json"

      # 定义网格的边界条件
      boundary_conditions:
        - type: "flow"
          # 应用此条件的边界边ID列表
          edge_ids: [1, 12, 68, 172]

# 定义'flow'边界的流入
global_inputs:
  - target_component: "Channel2D"
    inputs:
      # 组件名称用作其主要流入的键
      Channel2D:
        value: 10.0 # 恒定的10 m^3/s流入
```

### 边界条件

边界条件在`boundary_conditions`参数下定义为列表。列表中的每个项目指定一个`type`和应用的`edge_ids`。

- **`wall` (默认):** 任何未分配类型的边界边将默认为具有零流过的固体反射墙。
- **`flow`:** 此类型用于指定流入或流出。流量值本身通过`global_inputs`部分提供，其中输入键与组件的`name`匹配。正值代表流入，负值代表流出。

## 完整示例

有关完整可运行的演示，请参见`examples/2d_model_example/`目录中的示例。它包括一个网格文件、一个配置文件和一个执行模拟并绘制最终水深2D图的运行脚本。