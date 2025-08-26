"""
机器学习集成系统
================

本模块提供水文模型的机器学习集成功能，包括：
- 深度学习模型增强（Transformer、GNN、强化学习）
- 传统机器学习方法（集成学习、SVM、神经网络）
- 特征工程和选择
- 模型训练和评估
"""

# Commenting out problematic imports until the classes are implemented
# from .deep_learning import (
#     TimeSeriesTransformer,
#     SpatioTemporalTransformer,
#     DynamicGraphNeuralNetwork,
#     SpatioTemporalGCN,
#     GraphAttentionNetwork,
#     QLearningAgent,
#     PolicyGradientAgent,
#     ActorCriticAgent,
#     MultiAgentRL
# )

from .traditional_ml import (
    RandomForestRegressor,
    GradientBoostingRegressor,
    XGBoostRegressor,
    LightGBMRegressor,
    SupportVectorMachine,
    MultiLayerPerceptron,
)

from .feature_engineering import (
    AutoFeatureEngineer,
    FeatureSelector,
    FilterMethods,
    WrapperMethods,
    EmbeddedMethods,
    HybridMethods,
    TimeSeriesFeatureEngineer
)

# Commenting out problematic imports
# from .model_training import (
#     ModelTrainer,
#     HyperparameterOptimizer,
#     CrossValidator,
#     ModelEvaluator,
#     ModelEnsemble
# )

from .base_ml_model import MLModelWrapper

__all__ = [
    # 深度学习 (Commented out)
    # 'TimeSeriesTransformer',
    
    # 传统机器学习
    'RandomForestRegressor',
    'GradientBoostingRegressor',
    'XGBoostRegressor',
    'LightGBMRegressor',
    'SupportVectorMachine',
    'MultiLayerPerceptron',
    
    # 特征工程
    'AutoFeatureEngineer',
    'FeatureSelector',
    'FilterMethods',
    'WrapperMethods',
    'EmbeddedMethods',
    'HybridMethods',
    'TimeSeriesFeatureEngineer',
    
    # 模型训练 (Commented out)
    # 'ModelTrainer',
    # 'HyperparameterOptimizer',
    # 'CrossValidator',

    # 基础类
    'MLModelWrapper'
]

__version__ = '1.0.0'
__author__ = 'Hydro-Suite Team'
