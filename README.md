### **准分布式水文模型文档**

#### **1. 简介**

本项目是一个用 Python 实现的准分布式水文模型。它能够模拟由多个子流域组成的复杂流域。模型的特点是支持基于分区的参数化方案和基于 Pfafstetter 编码的流域网络拓扑结构。

此实现包含一个完整的示例，用于演示模型如何处理一个包含多个雨量站、多个参数分区和多个子流域的假设性流域。

#### **2. 项目结构**

项目的目录和文件结构如下：

```
.
├── data/
│   ├── catchment_definition.csv  # 流域结构定义
│   ├── observed_flow.csv         # 观测流量数据
│   ├── pet.csv                   # 潜在蒸散发数据
│   ├── rainfall.csv              # 降雨数据
├── hydro_model/
│   ├── __init__.py               # 包初始化文件
│   ├── catchment.py              # 流域结构和模拟管理
│   └── model.py                  # 核心水文模型逻辑
├── results/
│   ├── comparison_plot.png       # 结果对比图
│   ├── final_comparison_table.csv# 最终结果数据表
│   └── simulation_results.csv    # 所有子流域的模拟流量
└── run_example.py                # 模型运行的主脚本
```

-   `data/`: 存放模型运行所需的所有输入数据。
-   `hydro_model/`: 包含模型核心逻辑的 Python 包。
-   `results/`: 存放模型运行生成的输出文件，如图表和数据表格。
-   `run_example.py`: 用于运行示例并生成结果的入口脚本。

#### **3. 模型代码 (`hydro_model`包)**

##### **`hydro_model/model.py`**

-   **`SimpleConceptualModel` 类**: 这是模型的核心，负责进行降雨-径流转换。它是一个简化的概念性模型，包含一个土壤水库，并将产生的径流分为快、慢两种成分。
    -   **初始化参数 (`params`)**:
        -   `S_max`: 土壤最大含水量 (mm)。
        -   `k_q`: 快速流出流系数，控制地表径流的流速。
        -   `k_s`: 慢速流出流系数，控制壤中流或基流的流速。
        -   `c_loss`: 损失系数，用于模拟从土壤水中的蒸发或深层渗漏损失。
    -   **`run(rainfall, pet)` 方法**: 为单个时间步运行模型，输入降雨和潜在蒸散发，输出该时间步产生的总径流量 (mm)。

##### **`hydro_model/catchment.py`**

该文件定义了流域的空间结构和模拟流程。

-   **`ParameterZone` 类**: 用于定义一个参数分区。该分区内的所有子流域共享同一套模型参数。
-   **`SubBasin` 类**: 代表一个子流域，是模型计算的基本单元。
    -   `pfaf_code`: 子流域的唯一标识符（基于 Pfafstetter 编码）。
    -   `area`: 子流域的面积 (km²)。
    -   `zone_id`: 该子流域所属的参数分区的ID。
    -   `downstream_pfaf`: 下游子流域的 `pfaf_code`，用于定义水流路径。
    -   `model`: 每个子流域实例都包含一个独立的 `SimpleConceptualModel` 实例。
-   **`Catchment` 类**: 管理整个流域。
    -   它存储所有的 `SubBasin` 和 `ParameterZone` 对象。
    -   它根据 `pfaf_code` 自动确定计算顺序（从最上游到最下游）。
    -   `run_simulation()` 方法负责驱动整个流域的模拟，处理各子流域的径流计算和简单的流量演算（通过时间延迟）。

#### **4. 输入数据 (`data` 目录)**

所有输入数据均为 CSV 格式。

-   **`catchment_definition.csv`**: 定义了流域的拓扑结构。
    -   `pfaf_code`: 子流域的唯一编码。
    -   `area_km2`: 子流域面积。
    -   `zone_id`: 对应的参数分区ID。
    -   `downstream_pfaf`: 下游子流域的编码，最下游的子流域此项为空。
-   **`rainfall.csv`**: 定义了每个子流域的降雨时间序列。列名应与子流域的 `pfaf_code` 对应（例如 `rainfall_1`, `rainfall_2`）。
-   **`pet.csv`**: 定义了潜在蒸散发的时间序列。在当前示例中，所有子流域共享同一个PET序列。
-   **`observed_flow.csv`**: 定义了在流域总出口处的实测（或合成的“真实”）流量，用于与模拟结果进行对比。

#### **5. 如何运行**

1.  **安装依赖**:
    ```bash
    pip install pandas matplotlib
    ```
2.  **运行示例**:
    在项目根目录下运行以下命令：
    ```bash
    python run_example.py
    ```
    脚本将自动加载数据、运行模拟，并将所有输出保存到 `results/` 目录中。

#### **6. 输出结果 (`results` 目录)**

-   **`simulation_results.csv`**: 包含了每个子流域在每个时间步的模拟流量（单位：m³/s）。
-   **`final_comparison_table.csv`**: 这是为最终展示而生成的数据表，包含了在流域出口处的降雨量、实测流量和模拟流量。
-   **`comparison_plot.png`**: 一张对比图，直观地展示了降雨过程（倒置的条形图）以及实测流量与模拟流量的对比曲线。这有助于评估模型的模拟效果。
