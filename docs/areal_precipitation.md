# 面雨量计算

该框架现在包含一个强大的模块，用于从点雨量数据计算面雨量。这允许对水文模型进行更空间准确的降雨输入，超越简单的单站每流域方法。

该模块支持三种插值方法：
- **反距离加权(IDW)**
- **泰森多边形**
- **普通克里金**

## 工作原理

面雨量计算在模拟设置期间作为预处理步骤处理。当在`config.yaml`文件中检测到特殊的`areal_precipitation`部分时，`ConfigParser`会自动调用`ArealPrecipitation`模块。

工作流程如下：
1.  模块读取雨量计的位置。
2.  它读取子流域的多边形几何形状。
3.  它加载多站原始降雨时间序列数据。
4.  它执行数据清理步骤以处理缺失值(通过线性插值)并移除负值。
5.  使用指定的方法(IDW或泰森多边形)，它为每个子流域计算唯一的、空间平均的降雨时间序列。
6.  然后将这些新的时间序列传递给相应的水文模型组件进行模拟运行。

## 配置

要启用此功能，请在`config.yaml`文件中添加`areal_precipitation`部分。

```yaml
# 新增：配置面雨量
areal_precipitation:
  subbasins_shapefile: "path/to/your/subbasins.shp"
  rain_gauges_file: "path/to/your/rain_gauges.csv"
  method: "idw" # 或 "thiessen"
  parameters:
    power: 2 # 可选：特定于'idw'方法
```

### 参数：
- `subbasins_shapefile` (必需): 包含子流域多边形的shapefile路径。路径相对于`config.yaml`文件的位置。
- `rain_gauges_file` (必需): 包含雨量计位置的CSV文件路径。
- `method` (必需): 要使用的插值方法。可以是`"idw"`、`"thiessen"`或`"kriging"`。
- `parameters` (可选): 所选方法的附加参数字典。
    - 对于`idw`，您可以指定`power`(默认: 2)。
    - 对于`thiessen`，您可以指定可选的`cache_file`来存储计算的权重并提高后续运行的性能。
    - 对于`kriging`，您可以指定：
        - `variogram_model`(默认: `'linear'`): 要使用的变异函数模型，例如`'linear'`、`'power'`、`'gaussian'`。
        - `grid_resolution`(默认: 10): 插值网格中x和y维度的点数。值越高越准确，但速度显著降低。

> **依赖项说明:** `kriging`方法需要安装`pykrige`库(`pip install pykrige`)。
>
> **方差输出:** 使用`kriging`方法时，会自动创建包含每个子流域平均估计方差的第二个数据源。其名称将是您指定的`output_name`加上`_variance`(例如`precip_areal_variance`)。这些数据可用于不确定性分析。有关示例，请参见分析工具文档。

## 所需数据格式

### 1. 雨量计文件
这必须是一个CSV文件，包含以下列：`station_id`、`x`和`y`。

- `station_id`: 雨量计的标识符。**这必须与降雨数据文件中的相应列名完全匹配。**
- `x`, `y`: 雨量计的空间坐标。

示例(`rain_gauges.csv`)：
```csv
station_id,x,y
rainfall_1,500000,5060000
rainfall_2,510000,5065000
rainfall_3,505000,5055000
```

### 2. 子流域Shapefile
这必须是一个标准的多边形shapefile。模块使用shapefile的索引或指定的ID列来识别每个子流域。为了使框架能够正确地将计算的降雨量映射到模型组件，**配置文件中每个水文模型组件的名称必须与shapefile属性表中相应子流域的ID匹配。**

### 3. 降雨数据文件
这是一个CSV文件，第一列是日期/时间，后续列包含每个雨量计的降雨测量值。

- 索引列必须是可解析的日期/时间。
- 每个降雨列的标题必须与`rain_gauges.csv`文件中的`station_id`匹配。

示例(`rainfall.csv`)：
```csv
date,rainfall_1,rainfall_2,rainfall_3
2023-01-01,0,0,0
2023-01-02,5,4,3
2023-01-03,15,12,10
...
```

## 完整示例
有关此功能的完整可运行演示，请参见`examples/areal_precipitation_example/`目录中的示例。它包含一个工作配置文件、所有必要的数据和运行模拟及绘制结果的脚本。