"""
机器学习集成系统
================

本模块提供水文模型的机器学习集成功能，包括：
- 深度学习模型增强（Transformer、GNN、强化学习）
- 传统机器学习方法（集成学习、SVM、神经网络）
- 特征工程和选择
- 模型训练和评估
"""

from .deep_learning import (
    TimeSeriesTransformer,
    SpatioTemporalTransformer,
    DynamicGraphNeuralNetwork,
    SpatioTemporalGCN,
    GraphAttentionNetwork,
    QLearningAgent,
    PolicyGradientAgent,
    ActorCriticAgent,
    MultiAgentRL
)

from .traditional_ml import (
    EnsembleLearner,
    RandomForestRegressor,
    GradientBoostingRegressor,
    XGBoostRegressor,
    LightGBMRegressor,
    SupportVectorMachine,
    MultiLayerPerceptron,
    ConvolutionalNN,
    RecurrentNN,
    AutoEncoder
)

from .feature_engineering import (
    AutoFeatureEngineer,
    FeatureSelector,
    FilterMethods,
    WrapperMethods,
    EmbeddedMethods,
    HybridMethods
)

from .model_training import (
    ModelTrainer,
    HyperparameterOptimizer,
    CrossValidator,
    ModelEvaluator,
    ModelEnsemble
)

__all__ = [
    # 深度学习
    'TimeSeriesTransformer',
    'SpatioTemporalTransformer',
    'DynamicGraphNeuralNetwork',
    'SpatioTemporalGCN',
    'GraphAttentionNetwork',
    'QLearningAgent',
    'PolicyGradientAgent',
    'ActorCriticAgent',
    'MultiAgentRL',
    
    # 传统机器学习
    'EnsembleLearner',
    'RandomForestRegressor',
    'GradientBoostingRegressor',
    'XGBoostRegressor',
    'LightGBMRegressor',
    'SupportVectorMachine',
    'MultiLayerPerceptron',
    'ConvolutionalNN',
    'RecurrentNN',
    'AutoEncoder',
    
    # 特征工程
    'AutoFeatureEngineer',
    'FeatureSelector',
    'FilterMethods',
    'WrapperMethods',
    'EmbeddedMethods',
    'HybridMethods',
    
    # 模型训练
    'ModelTrainer',
    'HyperparameterOptimizer',
    'CrossValidator',
    'ModelEvaluator',
    'ModelEnsemble'
]

__version__ = '1.0.0'
__author__ = 'Hydro-Suite Team'
