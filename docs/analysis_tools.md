# 分析工具

本节描述位于`analysis/`目录中的独立脚本，可用于后处理和可视化模型结果与数据。

## 插值不确定性绘图器

**脚本:** `analysis/plot_interpolation_uncertainty.py`

### 目的

当使用`kriging`方法进行面雨量计算时，模型计算平均插值降雨量和估计方差。该方差是插值不确定性的度量，通常在远离雨量计的区域更高。该工具允许您可视化这种不确定性。

### 使用方法

该脚本从命令行运行，接受单个参数：已设置为使用`kriging`插值方法的配置文件路径。

1.  **确保您的`config.yaml`配置为克里金插值：**
    ```yaml
    areal_precipitation:
      input_name: "rainfall"
      output_name: "precip_areal"
      # ... 其他必需参数 ...
      method: "kriging"
    ```

2.  **从项目根目录运行脚本：**
    ```bash
    python3 analysis/plot_interpolation_uncertainty.py path/to/your/config.yaml
    ```

### 输出

脚本将：
1.  运行配置文件中定义的数据加载和面雨量步骤。这将生成平均降雨数据源(例如`precip_areal`)和方差数据源(例如`precip_areal_variance`)。
2.  读取方差数据。
3.  在配置文件所在目录中生成并保存名为`interpolation_variance_plot.png`的图表。该图表显示了每个子流域随时间的平均估计方差。