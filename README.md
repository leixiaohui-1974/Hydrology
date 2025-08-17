### **项目文档: 准分布式水文模型 & GIS流域划分工具**

#### **总览**

本项目包含三个主要部分：

1.  **准分布式水文模型**: 一个用Python实现的、支持多子流域和参数分区的水文模拟程序。
2.  **GIS流域划分工具**: 一个基于DEM、土地利用和土壤等下垫面信息，自动划分亚流域并定义参数分区的程序。
3.  **参数率定与数据同化**: 一个使用集合卡尔曼滤波(EnKF)进行模型参数校准和状态更新的模块。

这些部分可以协同工作，例如，使用GIS工具的输出结果来定义水文模型的输入，然后使用EnKF模块来率定其参数。

---

### **第一部分: 准分布式水文模型**

#### **1.1 简介**

这部分代码是一个用 Python 实现的准分布式水文模型。它能够模拟由多个子流域组成的复杂流域，并支持基于分区的参数化方案和基于 Pfafstetter 编码的流域网络拓扑结构。

#### **1.2 项目结构 (水文模型部分)**

```
.
├── data/
│   ├── catchment_definition.csv
│   ├── observed_flow.csv
│   ├── pet.csv
│   └── rainfall.csv
├── hydro_model/
│   ├── __init__.py
│   ├── catchment.py
│   └── model.py
└── run_example.py
```

#### **1.3 如何运行水文模型**

1.  **安装依赖**: `pip install pandas matplotlib`
2.  **运行**: `python run_example.py`
3.  **输出**: 结果会保存在 `results/` 目录下，包含模拟数据表和对比图。

---

### **第二部分: GIS流域划分与参数分区工具**

#### **2.1 简介**

这是一个基于GIS数据自动进行子流域划分和参数分区的程序。它使用 `whitebox-tools` 作为核心处理引擎，并结合 `geopandas` 进行矢量数据分析。

#### **2.2 项目结构 (GIS工具部分)**

```
.
├── gis_data/
│   ├── dem.tif
│   ├── land_use.shp
│   └── soil.shp
├── temp_gis/
├── create_gis_data.py
├── generate_parameter_zones.py
└── plot_zones.py
```

#### **2.3 如何运行GIS工具**

1.  **安装依赖**: `pip install whitebox geopandas rasterio matplotlib`
2.  **(可选) 生成示例数据**: `python create_gis_data.py`
3.  **运行主程序**: `python generate_parameter_zones.py`
4.  **(可选) 可视化结果**: `python plot_zones.py`
5.  **输出**: `results/subbasins_with_zones.shp` (带有`zone_id`的子流域矢量文件) 和 `results/parameter_zones_map.png` (可视化地图)。

---

### **第三部分: 参数率定与数据同化 (EnKF)**

#### **3.1 简介**

这是一个使用集合卡尔曼滤波 (Ensemble Kalman Filter, EnKF) 对第一部分中的水文模型进行参数率定和数据同化的实现。通过将观测数据（如日流量）同化到模型中，EnKF能够实时地更新模型的内部状态（如土壤水含量）和率定模型的关键参数（如产流系数），从而得到更精确的模拟结果。

本实现采用**增广状态向量**技术，将模型参数与状态变量一同放入状态向量中，使得EnKF可以同时对两者进行优化。

#### **3.2 项目结构 (EnKF部分)**

```
.
├── hydro_model/
│   └── enkf.py                 # 通用EnKF类的实现
├── calibrate_with_enkf.py      # 执行EnKF同化和率定的主脚本
└── plot_enkf_results.py        # 用于可视化EnKF结果的脚本
```

#### **3.3 文件说明**

-   **`hydro_model/enkf.py`**: 实现了一个通用的 `EnsembleKalmanFilter` 类，包含了EnKF算法的“预测”和“分析”两个核心步骤。
-   **`calibrate_with_enkf.py`**: 这是运行数据同化任务的主脚本。它加载水文模型和数据，设置EnKF（如集合数量、观测误差），运行同化循环，并保存结果。为了对比，脚本还会运行一个没有同化过程的“开环”模拟。
-   **`plot_enkf_results.py`**: 读取 `calibrate_with_enkf.py` 生成的结果文件，并创建两张图表用于验证和分析。

#### **3.4 输出结果 (`results`目录)**

-   **`enkf_flow_results.csv`**: 包含三列数据：观测流量、开环模拟流量、EnKF同化后的流量。
-   **`enkf_parameter_evolution.csv`**: 记录了模型关键参数的估计值在整个模拟过程中的演变情况。
-   **`enkf_flow_comparison.png`**: 将三种流量过程线绘制在一起的对比图，直观展示EnKF对模拟结果的改善效果。
-   **`enkf_parameter_convergence.png`**: 将四个关键参数的演变过程绘制在四个子图中的收敛分析图。

#### **3.5 如何运行EnKF模块**

1.  **前提**: 确保水文模型和数据已存在。
2.  **运行主程序**:
    ```bash
    python calibrate_with_enkf.py
    ```
3.  **可视化结果**:
    ```bash
    python plot_enkf_results.py
    ```
