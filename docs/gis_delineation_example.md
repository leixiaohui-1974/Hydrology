# 示例: GIS流域划分与参数分区

**脚本:**
- `examples/create_gis_data.py`
- `examples/generate_parameter_zones.py`
- `examples/plot_zones.py`

## 目的

此示例用于演示项目的第二部分功能：基于GIS的自动化流域处理。它展示了如何：
1.  使用 `whitebox-tools` 这一强大的地理空间分析引擎，对DEM进行一系列标准的水文分析。
2.  从DEM数据中自动提取河网，并划分出所有子流域。
3.  将栅格格式的子流域结果转换为矢量多边形（Shapefile）。
4.  利用 `geopandas` 进行空间叠加分析，将子流域图层与土地利用、土壤类型图层进行合并。
5.  根据每个子流域内占主导地位的土地利用和土壤类型，为其创建一个唯一的、可用于水文模型的**参数分区ID** (`zone_id`)。

## 如何运行

1.  **(可选) 创建示例数据:** 如果您没有自己的GIS数据，可以运行此脚本来生成一套用于演示的合成数据。
    ```bash
    python examples/create_gis_data.py
    ```
2.  **运行主程序:** 此脚本将执行从DEM到带有`zone_id`的子流域的全过程。
    ```bash
    python examples/generate_parameter_zones.py
    ```
3.  **(可选) 可视化结果:**
    ```bash
    python examples/plot_zones.py
    ```

## 输入

-   `gis_data/dem.tif`: 数字高程模型。
-   `gis_data/land_use.shp`: 土地利用矢量数据。
-   `gis_data/soil.shp`: 土壤类型矢量数据。

## 输出

-   `examples/results/subbasins_with_zones.shp`: **核心输出成果**。这是一个shapefile文件，其中每一个多边形代表一个子流域，其属性表中包含了根据叠加分析生成的`zone_id`。这个文件可以直接作为后续水文模型设置的依据。
-   `examples/results/parameter_zones_map.png`: 一张可视化的验证地图，将子流域根据其`zone_id`进行着色，并叠加在DEM背景上，以便直观地检查分区结果。
-   `temp_gis/`: 此目录中存放了所有GIS处理的中间文件，可用于调试或检查特定步骤的结果。
