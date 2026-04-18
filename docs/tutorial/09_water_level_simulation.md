# 第9章：模拟河道水位

传统的概念性水文模型通常只关注**流量**的模拟，而无法提供关于**水位**的信息。然而，在防洪、航运、生态等领域，水位是一个至关重要的变量。

我们实现的 `MuskingumCungeRouting` 模块的一个核心优势，就在于它能够在演算流量的同时，估算出河道的平均水深。

## 水位是如何计算的？

回顾上一章，我们知道马斯京根-康基法的核心是在每个时间步动态计算水力学参数。其中一个关键的中间步骤就是求解**曼宁公式**。

曼宁公式描述了明渠恒定均匀流中，流量、流速、水深和河道物理特性之间的关系：
`Q = A * V = A * (1/n) * R_h^(2/3) * S^(1/2)`

其中：
- `Q`: 流量
- `A`: 过水断面面积
- `V`: 流速
- `n`: 曼宁糙率
- `R_h`: 水力半径 (A/P, P为湿周)
- `S`: 河床比降

在我们的模型中，我们已知 `Q` (平均流量), `n`, `S` 以及断面形状（我们假设为宽浅矩形，`A=width*y`, `R_h≈y`）。因此，我们可以反解出公式中唯一未知的变量——**水深 `y`**。

在`MuskingumCungeRouting`的`run`方法中，这部分代码如下：
```python
# hydro_model/routing.py

# ... 估算出平均流量 Q_avg ...

# y ~ (Q*n / (B*S^0.5))^(3/5)  (曼宁公式针对宽浅矩形的反解形式)
y = (Q_avg * self.n / (self.width * self.slope**0.5))**0.6

# 将计算出的水深存储在模块的属性中，供外部访问
self.y_prev = y
```
在每次调用`run`方法后，该模块都会计算出对应于当前流量的平均水深，并将其保存在`self.y_prev`属性中。

## 示例与结果

**脚本:** `examples/run_muskingum_cunge_example.py`

这个脚本在运行模拟时，不仅保存了每个时间步的出流量，也保存了对应的水深。

```python
# examples/run_muskingum_cunge_example.py

# ...
outflow_hydrograph = []
water_depth_series = []
for inflow_val in inflow_hydrograph:
    # 运行演算
    outflow_val = mc_router.run(inflow_val)
    outflow_hydrograph.append(outflow_val)

    # 从模块实例中获取计算出的水深
    water_depth_series.append(mc_router.y_prev)
# ...
```

最终，脚本会生成一张包含两个子图的图片 `results/muskingum_cunge_example_plot.png`。其中第二个子图就展示了模拟出的河道平均水深随时间的变化过程。

*(我们在这里可以插入`muskingum_cunge_example_plot.png`的第二个子图)*

您可以看到，水位的涨落与流量的涨落过程完全对应，这符合物理规律。

## 总结

通过利用水力学公式，马斯京根-康基法为我们提供了一个在概念性模型框架内，模拟物理水位过程的有效途径。这极大地扩展了模型的应用范围，使其能够更好地服务于需要水位信息的实际应用场景。

在下一章，我们将挑战最复杂的河网拓扑——环状河网。
