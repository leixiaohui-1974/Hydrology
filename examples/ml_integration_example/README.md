# 机器学习集成系统示例

## 概述

本示例展示了Hydro-Suite机器学习集成系统的各种功能，包括深度学习模型、传统机器学习方法、特征工程和选择、以及模型训练和评估。

## 功能特性

### 🧠 深度学习模型
- **Transformer架构**: 时间序列和时空数据处理
- **图神经网络**: 动态图和时空图建模
- **强化学习**: Q-learning、策略梯度、多智能体系统

### 🔧 传统机器学习
- **集成学习**: 随机森林、梯度提升、XGBoost、LightGBM
- **支持向量机**: 线性、核函数、多分类支持
- **神经网络**: 多层感知机、卷积网络、循环网络

### ⚙️ 特征工程和选择
- **自动特征工程**: 多项式特征、统计特征、时间特征
- **特征选择**: 过滤方法、包装方法、嵌入方法、混合方法
- **特征重要性评估**: 多方法共识特征识别

### 🚀 模型训练和评估
- **模型训练器**: 统一的训练接口和进度监控
- **超参数优化**: 网格搜索、随机搜索、贝叶斯优化
- **交叉验证**: K折交叉验证、分层交叉验证
- **模型集成**: 投票集成、堆叠集成、加权集成

## 快速开始

### 1. 环境准备

确保已安装所需的依赖包：

```bash
pip install -r requirements.txt
```

### 2. 运行示例

```bash
python run_ml_integration.py
```

### 3. 查看结果

运行完成后，将生成以下输出：
- 控制台日志：显示训练进度和性能指标
- 结果图表：`ml_integration_results.png`
- 模型文件：保存在`models/`目录
- 日志文件：`ml_integration.log`

## 配置说明

### 主要配置项

#### 深度学习设置
```yaml
deep_learning:
  transformer:
    input_dim: 10          # 输入特征维度
    d_model: 128           # 模型维度
    nhead: 8               # 注意力头数
    num_layers: 3          # 层数
    dropout: 0.1           # Dropout率
```

#### 传统机器学习设置
```yaml
traditional_ml:
  random_forest:
    n_estimators: 100      # 树的数量
    max_depth: 10          # 最大深度
    min_samples_split: 2   # 最小分割样本数
```

#### 特征工程设置
```yaml
feature_engineering:
  auto_feature_engineer:
    max_polynomial_degree: 2        # 最大多项式次数
    max_interaction_features: 20    # 最大交互特征数
    include_statistical_features: true  # 包含统计特征
```

## 使用示例

### 1. 传统机器学习

```python
from hydro_model.ml_integration.traditional_ml import RandomForestRegressor
from hydro_model.ml_integration.model_training import ModelTrainer

# 创建模型
rf_model = RandomForestRegressor(n_estimators=100, max_depth=10)

# 训练模型
trainer = ModelTrainer(rf_model, "RandomForest")
trainer.train(X_train, y_train)

# 评估模型
metrics = trainer.evaluate(X_test, y_test)
print(f"R² Score: {metrics['r2']:.4f}")
```

### 2. 特征工程

```python
from hydro_model.ml_integration.feature_engineering import AutoFeatureEngineer

# 自动特征工程
feature_engineer = AutoFeatureEngineer(
    max_polynomial_degree=2,
    max_interaction_features=20
)

# 生成新特征
X_enhanced = feature_engineer.generate_features(X_train)

# 转换新数据
X_test_enhanced = feature_engineer.transform(X_test)
```

### 3. 特征选择

```python
from hydro_model.ml_integration.feature_engineering import FilterMethods

# 过滤方法特征选择
filter_selector = FilterMethods(n_features=20, method='f_regression')
X_selected = filter_selector.fit_transform(X_train, y_train)

# 查看选择的特征
print(f"选择了 {len(filter_selector.selected_features)} 个特征")
```

### 4. 交叉验证

```python
from hydro_model.ml_integration.model_training import CrossValidator

# 执行交叉验证
cv_validator = CrossValidator(rf_model, cv=5, scoring='r2')
cv_results = cv_validator.cross_validate(X_train, y_train)

print(f"平均分数: {cv_results['mean_score']:.4f}")
print(f"标准差: {cv_results['std_score']:.4f}")
```

## 性能优化

### 并行处理
- 启用多进程训练：`n_jobs: -1`
- 批量处理：`batch_size: 32`
- 内存优化：`memory_efficient: true`

### GPU加速
```yaml
performance:
  gpu_acceleration:
    use_gpu: true
    device: "cuda:0"
```

## 输出和报告

### 结果保存
- 模型文件：Joblib格式
- 预测结果：CSV/JSON格式
- 特征重要性：JSON格式

### 可视化报告
- 性能对比图
- 特征重要性图
- 训练过程图
- 交叉验证结果图

## 故障排除

### 常见问题

1. **内存不足**
   - 减少`batch_size`
   - 启用`memory_efficient`
   - 减少特征数量

2. **训练时间过长**
   - 减少`n_estimators`
   - 启用并行处理
   - 使用GPU加速

3. **过拟合问题**
   - 增加正则化参数
   - 减少模型复杂度
   - 使用交叉验证

### 调试模式

启用详细日志：
```yaml
logging:
  level: "DEBUG"
  console: true
  file: "debug.log"
```

## 扩展开发

### 添加新模型

1. 继承基础模型类
2. 实现`fit`和`predict`方法
3. 添加到相应的模块中

### 自定义特征工程

1. 继承`AutoFeatureEngineer`
2. 重写特征生成方法
3. 注册到特征工程系统

### 集成外部库

支持集成其他机器学习库：
- TensorFlow/Keras
- PyTorch
- Scikit-learn
- XGBoost/LightGBM

## 参考资源

### 文档
- [Hydro-Suite 用户手册](../docs/)
- [API 参考文档](../docs/api/)
- [开发指南](../docs/developer_guide.md)

### 论文和教程
- Transformer: "Attention Is All You Need"
- 图神经网络: "Semi-Supervised Classification with Graph Convolutional Networks"
- 强化学习: "Reinforcement Learning: An Introduction"

### 相关项目
- [Scikit-learn](https://scikit-learn.org/)
- [PyTorch](https://pytorch.org/)
- [XGBoost](https://xgboost.readthedocs.io/)

## 贡献指南

欢迎贡献代码、报告问题或提出改进建议！

### 贡献方式
1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 创建 Pull Request

### 代码规范
- 遵循 PEP 8 规范
- 添加类型注解
- 编写文档字符串
- 包含单元测试

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](../../LICENSE) 文件。

## 联系方式

- 项目主页: [GitHub Repository](https://github.com/hydro-suite)
- 问题反馈: [Issues](https://github.com/hydro-suite/issues)
- 讨论交流: [Discussions](https://github.com/hydro-suite/discussions)

---

**注意**: 本示例仅用于演示目的，在实际应用中请根据具体需求调整配置参数和模型选择。
