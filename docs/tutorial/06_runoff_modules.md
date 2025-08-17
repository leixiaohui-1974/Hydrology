# 第6章：产流模块详解

在本章中，我们将深入了解项目中已经实现的两种不同的产流模块。产流是水文循环的核心环节，它决定了在一次降雨事件中，有多少水量能够形成径流，又有多少被土壤吸收或蒸发。

## 1. `SimpleRunoffModule`

**位置:** `hydro_model/runoff.py`

这是我们在项目初期构建的、基于“饱和超渗”概念的简单模型。

### 核心思想

-   **土壤水库**: 模型将土壤视为一个有最大容量 `S_max` 的水库。
-   **产流机制**:
    -   当降雨时，一部分雨水会填补水库的亏缺。
    -   水库中的水会以一定速率 `c_loss` 蒸发或渗漏掉。
    -   产流量与当前水库的饱和度成正比。一个接近饱和的土壤（`S` 接近 `S_max`）在下雨时会产生更多的径流。当土壤完全饱和时，所有后续降雨都将转化为径流。

### 主要参数

-   `S_max`: 土壤最大含水量 (mm)。这是一个关键的率定参数，代表了流域的平均蓄水能力。
-   `c_loss`: 损失系数。一个无量纲参数，代表了每日水库因蒸发或深层渗漏而损失的水量占当前蓄水量的比例。

### 使用示例

```python
from hydro_model.runoff import SimpleRunoffModule

# 创建一个实例
# 参数代表：土壤最大能存储200mm的水，每日损失当前蓄水量的5%
runoff_module = SimpleRunoffModule(S_max=200, c_loss=0.05)

# 模拟一次降雨为30mm，蒸发为2mm的事件
generated_runoff = runoff_module.run(rainfall=30, pet=2)

print(f"产生的径流深为: {generated_runoff:.2f} mm")
```

---

## 2. `SCSCurveNumberModule`

**位置:** `hydro_model/runoff.py`

这是一个经典的、被广泛应用的经验性产流模型，由美国农业部水土保持局（SCS）开发。

### 核心思想

-   **CN值**: 模型的核心是一个单一的、无量纲的参数——**CN (Curve Number)**。CN值的范围是0-100，它综合反映了流域的土壤类型、土地利用状况和前期土壤湿润程度。
    -   一个高的CN值（如90）代表几乎不透水的地表（如城市），产流能力强。
    -   一个低的CN值（如40）代表渗透性很好的地表（如森林），产流能力弱。
-   **产流方程**: 模型使用一个经验方程来计算径流 `Q` 和降雨 `P` 之间的关系，其中考虑了由CN值决定的**初损 `Ia`** 和**潜在最大持留量 `S`**。

### 主要参数

-   `CN`: 曲线数。这是该模块唯一的率定参数。

### 使用示例

**脚本:** `examples/run_scs_example.py`

```python
from hydro_model.runoff import SCSCurveNumberModule

# 创建一个实例，假设研究区的CN值为85（例如，有一定开发度的农田）
scs_module = SCSCurveNumberModule(CN=85)

# 模拟一次50mm的降雨事件 (SCS模型通常不直接考虑PET)
generated_runoff = scs_module.run(rainfall=50, pet=0)

print(f"产生的径流深为: {generated_runoff:.2f} mm")
```
运行这个脚本，您可以直观地看到在给定的CN值下，不同降雨量所产生的径流量。

## 总结

通过这两个例子，您可以看到我们的模块化框架是如何工作的。两个模块都遵循了`BaseRunoffModule`的接口（都有一个`run`方法），但内部的计算逻辑却完全不同。

在下一章，我们将以同样的方式来探索项目中集成的几种汇流模块。
