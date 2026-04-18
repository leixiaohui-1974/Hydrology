# 高级配置主题

本文档涵盖了更复杂或自定义用例的高级配置选项。

## 灵活的数据到组件映射

默认情况下，框架通过匹配数据注册表中的数据源名称或列名称与组件名称，将数据映射到模型组件。例如，名为`my_component`的数据源或名为`my_component`的列将自动作为输入传递给名为`my_component`的组件。

在某些情况下，您的数据列名称可能与组件名称不匹配(例如，遗留数据、shapefile属性)。为了在不重命名数据的情况下处理此问题，您可以使用`mapping`关键字。

`mapping`关键字是可选字典，可以添加到`config.yaml`的`global_inputs`部分中的任何数据源定义中。它在数据文件中的列名称和模型组件名称之间提供显式链接。

### 使用方法

在`global_inputs`配置中，添加一个`mapping`字典，其中键是数据文件中的列名称，值是目标组件的名称。

```yaml
# 定义一个名称与数据列不同的组件
components:
  - name: "my_model_A"
    type: HydrologicalModel
    # ... 参数 ...

global_inputs:
  some_input_data:
    file: "path/to/your/data.csv"

    # 使用'mapping'关键字将数据连接到组件
    mapping:
      # 这将data.csv中的"DATA_COLUMN_1"列
      # 映射到名为"my_model_A"的组件。
      "DATA_COLUMN_1": "my_model_A"
```

### 详细信息
- 当为数据源提供`mapping`时，它优先于该源的默认名称匹配行为。
- 如果映射中找不到数据列或组件名称，将打印警告，但过程将继续。
- 此功能为集成各种来源的数据提供了极大的灵活性，而无需修改源文件。

### 示例
有关此功能的完整可运行演示，请参见`examples/flexible_mapping_example/`目录中的示例。