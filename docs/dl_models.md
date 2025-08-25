# 用于流量预测的深度学习模型

该框架现在支持使用深度学习模型进行水文预报。提供了两种类型的模型：长短期记忆(LSTM)模型和图神经网络(GNN)模型。这些模型可用于基于降雨和其他上游输入预测特定站点的流量。

## 概述

### LSTM模型

`LSTMModel`是一种时间序列预测模型，它使用过去的数据序列(例如，过去10天的降雨量)来预测下一个时间步的流量。它非常适合需要重要时间依赖性的单点预测。

### GNN模型

`GNNModel`将流域视为相互连接的汇水区图。它使用图卷积网络(GCN)来学习汇水区之间的空间关系。当您想模拟流域不同部分之间的相互作用时，该模型更强大。

## 组件

### `LSTMModel`

该组件封装了一个预训练的PyTorch LSTM模型。

-   **`type`**: `LSTMModel`
-   **`parameters`**:
    -   `model_path` (str): 训练好的LSTM模型文件(`.pth`)的路径。
    -   `seq_len` (int): 输入序列的长度(例如，使用多少个过去的时间步进行预测)。
    -   `input_features` (list): 将用作特征的全局输入名称列表。
    -   `inflow_names` (list, 可选): 上游组件名称列表，其出流将用作特征。

### `GNNModel`

该组件封装了一个预训练的PyTorch GNN模型。

-   **`type`**: `GNNModel`
-   **`parameters`**:
    -   `model_path` (str): 训练好的GNN模型文件(`.pth`)的路径。
    -   `catchment_def_path` (str): 定义汇水区及其连接关系的CSV文件路径。
    -   `target_node_id` (str): 目标节点的ID(来自汇水区定义文件)。
    -   `feature_names` (list): 节点特征基本名称列表。组件期望具有类似`{feature_name}_{node_id}`键的全局输入。

## 训练模型

在模拟中使用模型之前，您需要训练它们。在`dl_model`目录中提供了训练脚本。

### 训练LSTM模型

要训练LSTM模型，请从项目根目录运行以下命令：

```bash
python3 -m dl_model.train_lstm
```

这将使用`data`目录中的数据训练一个新模型，并将其保存到`dl_model/lstm_model.pth`。

### 训练GNN模型

要训练GNN模型，请从项目根目录运行以下命令：

```bash
python3 -m dl_model.train_gnn
```

这将训练一个新的GNN模型，并将其保存到`dl_model/gnn_model.pth`。

## 配置示例

以下是在`config.yaml`文件中使用`LSTMModel`的示例：

```yaml
simulation_parameters:
  dt_seconds: 86400
  num_steps: 30

data_sources:
  rainfall_data:
    file: ../../data/rainfall.csv

components:
  - name: LSTM_Flow_Predictor
    type: LSTMModel
    parameters:
      model_path: dl_model/lstm_model.pth
      seq_len: 10
      input_features:
        - rainfall_1
        - rainfall_2
        - rainfall_3

global_inputs:
  - target_component: LSTM_Flow_Predictor
    inputs:
      rainfall_1:
        from_source: rainfall_data
        from_column: rainfall_1
      rainfall_2:
        from_source: rainfall_data
        from_column: rainfall_2
      rainfall_3:
        from_source: rainfall_data
        from_column: rainfall_3

network: []
```

要运行此示例，您可以使用`run_from_config.py`脚本或`examples/dl_model_example/run_lstm.py`中提供的示例脚本。