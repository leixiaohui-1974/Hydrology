# 快速水文建模框架 (Hydro-Suite)

本项目是一个综合性的、基于Python的框架，用于构建、耦合和运行各种水系统模型。它从一个简单的水文模型发展成为一个强大的套件，包含了1D/2D水动力求解器、灵活的耦合机制，以及用于快速模型开发的图形用户界面。

## 核心功能

1.  **模块化水文模型 (`hydro_model/`)**: 一个灵活的降雨径流建模框架。它支持各种模块用于不同的水文过程，包括：
    -   `SCSCurveNumberModule`: 一种广泛使用的经验模型，用于估算径流。
    -   `XinanjiangRunoffModule`: 一种在湿润和半湿润地区流行的概念模型。
    -   `HymodRunoffModule`: 一种简单而有效的概念模型。

2.  **1D水动力模型 (`preissmann_model/`)**: 一个强大的1D水动力模型，使用隐式Preissmann格式求解Saint-Venant方程。它支持：
    -   非结构化河段。
    -   液压结构，如**闸门**和**水泵**作为内部边界条件。

3.  **2D水动力模型概念验证 (`model_2d/`)**: 一个概念验证的2D水动力模型，在非结构化三角网格上使用有限体积法求解浅水方程。

4.  **耦合框架 (`common/`)**: 一个强大的基于控制器的框架，允许任何模型组件连接成复杂的网络。
    -   **SimulationController**: 管理网络拓扑并逐步执行模拟。
    -   **Junctions**: 一个用于合并和分流流量的组件，支持树状网络结构。

5.  **快速建模GUI (`gui/`)**: 一个用于可视化构建、运行和分析模型的图形用户界面。
    -   将组件拖放到画布上。
    -   连接组件以定义网络。
    -   在属性窗格中编辑所有组件参数。
    -   运行模拟并通过实时日志和实时更新的图表获得**实时反馈**。
    -   模拟后分析和绘制任何组件的结果。
    -   将可视化设计的模型保存到`yaml`配置文件中。

6.  **基于配置的运行器**: 一个通用脚本(`run_from_config.py`)，可以从YAML配置文件运行任何模拟，允许无代码模型执行。

7.  **面雨量模块**: 使用反距离加权(IDW)或泰森多边形等方法，从点雨量数据自动计算子流域的面平均降雨量。详情请参见[**面雨量文档](./docs/areal_precipitation.md)**。

8.  **数据预处理与验证**: 一个可配置的流水线，在模拟前验证输入数据并生成派生时间序列。功能包括径流系数验证和Lyne-Hollick基流分割。详情请参见[**预处理文档](./docs/preprocessing.md)**。

## 高级功能

### 顺序分区率定

对于复杂的流域，框架支持使用集合卡尔曼滤波器(EnKF)进行顺序、从上游到下游的参数率定。这允许您按逻辑顺序率定流域的不同部分，提高最终参数集的稳定性和准确性。

-   **参数分区**: 将子流域分组到共享参数集的分区中。
-   **顺序率定**: 首先率定上游分区的参数，然后在率定下游分区之前"锁定"结果。
-   **工作示例**: 在`examples/simple_zoned_calibration/`中提供了一个完整、简单的示例来演示此功能。

## 入门指南

### 1. 安装

所需的Python包在`requirements.txt`中列出。此外，GUI和YAML解析器有它们自己的依赖项。安装所有必要的包：

```bash
pip install -r requirements.txt
pip install eel PyYAML
```

### 2. 运行GUI

使用该工具的最简单方法是通过GUI。从项目根目录启动它：

```bash
python3 gui/main.py
```

这将打开主应用程序窗口。有关如何使用界面的详细说明，请参见**[GUI手册](./docs/gui_manual.md)**。

### 3. 从配置文件运行

您也可以直接从命令行使用YAML配置文件运行模拟。提供了一个全面的示例。

```bash
python3 run_from_config.py examples/full_case_study/config.yaml
```

## 文档与示例

-   **2D水动力模型**: [./docs/2d_hydraulic_model.md](./docs/2d_hydraulic_model.md)
-   **分析工具**: [./docs/analysis_tools.md](./docs/analysis_tools.md)
-   **水文模块 (产流与融雪)**: [./docs/hydrology_modules.md](./docs/hydrology_modules.md)
-   **1D水动力模型**: [./docs/hydraulic_model.md](./docs/hydraulic_model.md)
-   **数据库集成**: [./docs/database_integration.md](./docs/database_integration.md)
-   **数据预处理与验证**: [./docs/preprocessing.md](./docs/preprocessing.md)
-   **面雨量**: [./docs/areal_precipitation.md](./docs/areal_precipitation.md)
-   **高级配置**: [./docs/advanced_configuration.md](./docs/advanced_configuration.md)
-   **GUI手册**: [./docs/gui_manual.md](./docs/gui_manual.md)
-   **案例研究教程**: [./docs/case_study_tutorial.md](./docs/case_study_tutorial.md)
-   **独立示例**: `examples/`目录包含运行单个组件和测试特定功能的脚本：
    -   `run_preissmann_simulation.py`: 测试1D水动力模型。
    -   `run_coupled_model.py`: 测试水文和水动力模型的耦合。
    -   `run_junction_model.py`: 测试网络交汇功能。
    -   `run_structure_model.py`: 测试液压闸门实现。
    -   `run_pump_model.py`: 测试液压泵实现。
    -   `run_2d_model.py`: 测试2D模型概念验证。
-   **完整案例研究数据**: 教程的数据和配置可以在`examples/full_case_study/`中找到。