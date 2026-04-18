# 第3章：项目结构解析

一个组织良好的项目结构是理解和扩展代码的基础。本章将为您详细解析我们这个综合水文模拟框架的目录和文件结构。

## 顶级目录结构

在项目的根目录下，您会看到以下几个核心的目录和文件：

```
.
├── data/
├── docs/
├── examples/
├── gis_data/
├── hydro_model/
├── temp_gis/
└── README.md
```

让我们逐一了解它们的作用：

### `hydro_model/`

这是整个项目的**核心**，一个可被其他脚本导入的Python包。所有水文模拟的核心逻辑和算法都封装在这里。
-   `model.py`: 定义了模块化的水文模型框架 `HydrologicalModel`。
-   `runoff.py`: 包含了所有的**产流**算法模块，如`SimpleRunoffModule`, `SCSCurveNumberModule`。
-   `routing.py`: 包含了所有的**汇流**算法模块，如`SimpleRouting`, `MuskingumRouting`, `UnitHydrographRouting`, `MuskingumCungeRouting`。
-   `catchment.py`: 定义了`Catchment`, `Node`, `Reach`等类，用于构建河网拓扑并管理网络模拟。
-   `enkf.py`: 实现了通用的集合卡尔曼滤波器 `EnsembleKalmanFilter`。

### `examples/`

这个目录包含了所有可独立运行的**示例脚本**。这些脚本旨在演示项目中某一项特定功能的用法。例如：
-   `run_example.py`: 运行基础的准分布式水文模型。
-   `run_scs_example.py`: 演示SCS产流模块。
-   `generate_parameter_zones.py`: 运行完整的GIS流域划分流程。
-   `calibrate_with_enkf.py`: 运行EnKF参数率定与数据同化。
-   ...等等。

当您运行这些示例时，它们生成的图表和CSV结果文件会被保存在 `examples/results/` 子目录中。

### `docs/`

您现在正在阅读的**文档**就存放在这里。
-   `index.md`: 文档的主索引页。
-   `tutorial/`: 存放本教学系列的所有章节。
-   `*.md`: 存放了对每个主要功能示例的简明扼要的说明。

### `data/` 和 `gis_data/`

这两个目录存放了运行示例所需的**输入数据**。
-   `data/`: 存放用于**水文模型**的非空间数据，主要是CSV格式的时间序列文件（如降雨、流量）。
-   `gis_data/`: 存放用于**GIS分析**的地理空间数据，主要是栅格（如`.tif`格式的DEM）和矢量（如`.shp`格式的shapefile）文件。

### `temp_gis/`

当您运行GIS流域划分示例 (`generate_parameter_zones.py`) 时，`whitebox-tools`会产生大量的**中间文件**（如填洼后的DEM、流量方向栅格等）。为了保持项目整洁，所有这些中间文件都会被存放在这个临时目录中。

### `README.md`

这是项目根目录下的主说明文件，提供了对整个项目的最高层级的概览，并引导用户到`docs/`目录来阅读详细文档。

## 总结

现在您已经对项目的整体结构有了清晰的认识。从下一章开始，我们将正式进入水文模型的世界，亲手运行我们的第一个模拟！
