# 第15章：模型参数自动率定

理论知识已经足够，现在让我们亲眼见证EnKF如何自动“学习”出最优的模型参数。

## 示例脚本

**脚本:** `examples/calibrate_with_enkf.py`

这个脚本是项目中技术含量最高、最核心的示例之一。它完整地展示了如何配置并运行一个EnKF，来对一个水文模型进行参数和状态的同步优化。

## 工作流程解析

让我们分解这个脚本的关键步骤：

### 1. `model_forward_augmented` 函数

这是连接水文模型和EnKF滤波器的桥梁。它被设计为EnKF在**预测**步骤中调用的核心函数。它的任务是：
1.  接收EnKF传来的一组**增广状态向量** `[S, Q_s, S_max, k_q, ...]`。
2.  用向量中的**参数** (`S_max`, `k_q`...) 创建一个临时的水文模型实例。
3.  用向量中的**状态** (`S`, `Q_s`) 初始化这个临时模型。
4.  运行模型一个时间步。
5.  返回**新的**增广状态向量（包含更新后的`S`, `Q_s`和略微扰动过的参数）以及该模型预测出的流量。

### 2. 初始化EnKF和集合

在主程序中，我们首先设置EnKF：
```python
# examples/calibrate_with_enkf.py

N_ENSEMBLE = 50 # 我们将同时运行50个模型实例
R = 10**2       # 观测误差的方差，这是一个关键的调节参数

enkf = EnsembleKalmanFilter(n_ensemble=N_ENSEMBLE)
```
接下来，我们创建初始的“集合”。我们首先对模型的状态和参数给出一个粗略的**初始猜测值**，并为这些猜测值赋予一个**不确定性**（标准差）。
```python
initial_guess = { 'S_max': 180.0, ... }
initial_uncertainty = { 'S_max': 50.0, ... }
```
然后，程序使用这些值，从正态分布中随机抽取50个样本，构成我们最初的、非常不确定的状态集合。

### 3. 同化循环

这是程序的核心循环：
```python
# examples/calibrate_with_enkf.py

for t in range(T): # 对每一个时间步
    # 预测步骤
    forecast_obs = enkf.forecast(...)

    # 分析/更新步骤
    enkf.analysis(observation=observed_flow[t], ...)
```
在循环的每一天：
-   `enkf.forecast()`: 让50个模型成员各自向前运行一步，得到50个不同的流量预测值。
-   `enkf.analysis()`: 将当天的**真实观测流量** `observed_flow[t]` “喂”给EnKF。EnKF会比较真实值和50个预测值，然后根据差异，对50个模型成员的内部状态和参数进行校正。

## 运行与结果

运行此脚本：
```bash
python examples/calibrate_with_enkf.py
```
脚本运行完毕后，会生成 `results/enkf_parameter_evolution.csv` 文件和对应的图表 `results/enkf_parameter_convergence.png`。

请打开这张图表：

*(我们在这里可以插入`enkf_parameter_convergence.png`的图像)*

这张图表生动地展示了“学习”的过程。以`S_max`（第一张子图）为例：
-   它的初始猜测值是180，并且有很大的不确定性。
-   在模拟开始后，EnKF迅速发现这个值太高了，导致模拟流量偏小。
-   于是，EnKF根据观测数据，不断地将`S_max`的值向下调整。
-   大约在模拟的第5-6天之后，`S_max`的值就收敛并稳定在了一个新的、更优的水平（大约20-30）。

其他参数（`k_q`, `k_s`等）也经历了类似的学习和收敛过程。

## 总结

通过这个例子，我们验证了EnKF不仅是一个滤波器，更是一个强大的**在线优化算法**。它能够仅通过观测出水口的流量，就反推出模型内部各个参数的合理数值。

在下一章，我们将分析这个过程带来的最终回报：模拟精度的显著提升。
