# 第13章：利用GIS划分结果

在上一章，我们成功地生成了一个核心成果：`subbasins_with_zones.shp`。这是一个矢量文件，其中包含了划分好的亚流域以及它们各自的参数分区ID（`zone_id`）。

现在的问题是：**如何将这些GIS分析结果，应用到我们的水文模型中？**

本章将为您描绘一座桥梁，连接起GIS分析和水文模拟这两个世界。

## 从`zone_id`到模型参数

`zone_id` （例如 `Forest-Clay`）本身只是一个字符串，水文模型并不能直接理解它。我们需要将这些ID“翻译”成模型能够使用的具体参数。

这个“翻译”的过程，通常是在一个**参数查找表 (Parameter Lookup Table)** 中完成的。这个查找表可以是一个简单的CSV文件，也可以是代码中的一个字典。

例如，我们可以创建一个名为 `parameter_lookup.csv` 的文件：

| zone_id     | S_max | k_q  | k_s  | CN | Manning_n |
|-------------|-------|------|------|----|-----------|
| Forest-Clay | 250   | 0.5  | 0.05 | 60 | 0.05      |
| Forest-Sand | 300   | 0.6  | 0.10 | 50 | 0.04      |
| Urban-Clay  | 80    | 0.9  | 0.02 | 90 | 0.015     |
| ...         | ...   | ...  | ...  | ...| ...       |

这个表格的每一行，都定义了一个参数分区所对应的**一套**水文模型参数。

## 构建水文模型的步骤

有了`subbasins_with_zones.shp`和参数查找表，构建一个完整的、物理基础坚实的准分布式水文模型的流程就变得非常清晰了：

1.  **读取子流域数据**: 使用`geopandas`读取`subbasins_with_zones.shp`文件。

2.  **读取参数查找表**: 使用`pandas`读取`parameter_lookup.csv`文件。

3.  **创建`Catchment`实例**: 创建一个我们水文模型的`Catchment`对象。

4.  **遍历每个子流域**:
    -   对于`subbasins_with_zones.shp`中的每一个子流域多边形：
        a.  获取其几何信息，如**面积**。
        b.  获取其属性信息，最重要的是 `zone_id`。
        c.  使用`zone_id`去参数查找表中，找到对应的**一整套**模型参数（S_max, CN, K, x, ...）。
        d.  根据您想使用的算法，选择相应的参数，创建一个产流模块实例和一个汇流模块实例。例如：
            ```python
            # 伪代码
            params = lookup_table.get_params(zone_id)

            # 选择使用SCS产流和马斯京根汇流
            runoff_module = SCSCurveNumberModule(CN=params['CN'])
            routing_module = MuskingumRouting(K=params['K'], x=params['x'])

            model = HydrologicalModel(runoff_module, routing_module)
            ```
        e.  将这个配置好的`model`和子流域的面积、ID等信息，一起添加到`Catchment`对象中。

5.  **运行模拟**: 当所有子流域都按上述方法添加完毕后，您就拥有了一个完整的、每个子流域的参数都由其下垫面特征决定的、具有坚实物理基础的准分布式水文模型。之后就可以像我们第四章那样，输入气象数据来运行它了。

## 总结

GIS分析的最终目的，是为水文模型提供更合理、更有依据的参数。通过`zone_id`和参数查找表，我们成功地将描述性的地理信息（“这是一片黏土上的森林”）转化为了模型可以使用的定量参数（`S_max=250`, `CN=60`...）。

这个过程实现了真正的“水文-GIS”耦合，是构建精细化、物理性强的环境模型的关键一步。
