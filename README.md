### **项目文档: 准分布式水文模型 & GIS流域划分工具**

#### **总览**

本项目包含两个主要部分：

1.  **准分布式水文模型**: 一个用Python实现的、支持多子流域和参数分区的水文模拟程序。
2.  **GIS流域划分工具**: 一个基于DEM、土地利用和土壤等下垫面信息，自动划分亚流域并定义参数分区的程序。

这两个部分可以协同工作，例如，使用GIS工具的输出结果来定义水文模型的输入。

---

### **第一部分: 准分布式水文模型**

*(这部分与之前的文档相同)*

#### **1.1 简介**

这部分代码是一个用 Python 实现的准分布式水文模型。它能够模拟由多个子流域组成的复杂流域，并支持基于分区的参数化方案和基于 Pfafstetter 编码的流域网络拓扑结构。

#### **1.2 项目结构 (水文模型部分)**

```
.
├── data/                     # 水文模型输入数据
│   ├── catchment_definition.csv
│   ├── observed_flow.csv
│   ├── pet.csv
│   └── rainfall.csv
├── hydro_model/              # 水文模型 Python 包
│   ├── __init__.py
│   ├── catchment.py
│   └── model.py
└── run_example.py            # 水文模型运行脚本
```

#### **1.3 如何运行水文模型**

1.  **安装依赖**: `pip install pandas matplotlib`
2.  **运行**: `python run_example.py`
3.  **输出**: 结果会保存在 `results/` 目录下，包含模拟数据表和对比图。

---

### **第二部分: GIS流域划分与参数分区工具**

#### **2.1 简介**

这是一个基于GIS数据自动进行子流域划分和参数分区的程序。它使用 `whitebox-tools` 作为核心处理引擎，并结合 `geopandas` 进行矢量数据分析。程序能够根据DEM数据划分亚流域，然后根据土地利用和土壤类型数据为每个亚流域确定主导类型，并生成唯一的“参数分区ID”。

#### **2.2 项目结构 (GIS工具部分)**

```
.
├── gis_data/                 # GIS工具输入数据
│   ├── dem.tif
│   ├── land_use.shp
│   └── soil.shp
├── temp_gis/                 # GIS处理的中间文件
├── create_gis_data.py        # 用于生成示例GIS数据的脚本
├── generate_parameter_zones.py # 主程序: 执行划分与分区
└── plot_zones.py             # 用于可视化最终结果的脚本
```

#### **2.3 文件说明**

-   **`create_gis_data.py`**: 一个辅助脚本，用于创建一套小型的、合成的GIS数据（DEM、土地利用、土壤类型），方便用户在没有真实数据的情况下运行和测试本程序。
-   **`generate_parameter_zones.py`**: 这是核心程序。它执行了从DEM预处理、河网提取、亚流域划分，到最后的与土地利用/土壤数据叠加分析，并为每个亚流域创建`zone_id`的全过程。
-   **`plot_zones.py`**: 一个验证脚本，用于读取最终生成的带有分区ID的子流域shapefile，并将其与DEM数据叠加，生成一张可视化的地图，以便直观地检查结果的合理性。

#### **2.4 输入数据 (`gis_data`目录)**

-   **`dem.tif`**: 数字高程模型(Digital Elevation Model)，是划分流域的基础。
-   **`land_use.shp`**: 土地利用类型矢量文件，包含一个`land_use`字段（如'Forest', 'Urban'）。
-   **`soil.shp`**: 土壤类型矢量文件，包含一个`soil_type`字段（如'Clay', 'Sand'）。

#### **2.5 输出结果 (`results`目录)**

-   **`subbasins_with_zones.shp`**: 这是程序的最终成果。一个shapefile文件，其中每个多边形代表一个划分出的亚流域。其属性表包含了每个亚流域的唯一ID (`VALUE`)，以及根据主要土地利用和土壤类型生成的`zone_id`。
-   **`parameter_zones_map.png`**: 一张可视化的验证地图，将子流域根据其`zone_id`进行着色，并叠加在DEM背景上。

#### **2.6 如何运行GIS工具**

1.  **安装依赖**:
    ```bash
    pip install whitebox geopandas rasterio matplotlib
    ```
2.  **(可选) 生成示例数据**: 如果您没有自己的GIS数据，可以先运行此脚本生成一套示例数据。
    ```bash
    python create_gis_data.py
    ```
3.  **运行主程序**:
    ```bash
    python generate_parameter_zones.py
    ```
4.  **(可选) 可视化结果**: 运行主程序后，可以运行此脚本来生成验证地图。
    ```bash
    python plot_zones.py
    ```
