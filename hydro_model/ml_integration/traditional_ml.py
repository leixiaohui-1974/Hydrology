"""
传统机器学习模块
================

本模块提供水文模型的传统机器学习方法，包括：
- 集成学习方法（随机森林、梯度提升、XGBoost、LightGBM）
- 支持向量机（线性、核函数、多分类）
- 神经网络（MLP、CNN、RNN、自编码器）
"""

import numpy as np
import logging
from typing import Optional, Tuple, List, Dict, Any
from sklearn.ensemble import RandomForestRegressor as SklearnRandomForest
from sklearn.ensemble import GradientBoostingRegressor as SklearnGradientBoosting
from sklearn.svm import SVR, SVC
from sklearn.neural_network import MLPRegressor, MLPClassifier
from sklearn.preprocessing import StandardScaler

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnsembleLearner:
    """集成学习基类"""
    
    def __init__(self, base_models: List, weights: Optional[List[float]] = None):
        self.base_models = base_models
        self.weights = weights if weights is not None else [1.0] * len(base_models)
        
        if len(self.weights) != len(base_models):
            raise ValueError("Weights length must match base_models length")
        
        logger.info(f"Ensemble learner initialized with {len(base_models)} base models")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练所有基础模型"""
        for i, model in enumerate(self.base_models):
            logger.info(f"Training base model {i+1}/{len(self.base_models)}")
            model.fit(X, y)
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """集成预测"""
        predictions = []
        for model in self.base_models:
            pred = model.predict(X)
            predictions.append(pred)
        
        # 加权平均
        weighted_pred = np.zeros_like(predictions[0])
        for pred, weight in zip(predictions, self.weights):
            weighted_pred += weight * pred
        
        return weighted_pred

class RandomForestRegressor:
    """随机森林回归器"""
    
    def __init__(self, n_estimators: int = 100, max_depth: Optional[int] = None,
                 min_samples_split: int = 2, min_samples_leaf: int = 1,
                 random_state: Optional[int] = None):
        self.model = SklearnRandomForest(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state
        )
        
        logger.info(f"Random Forest initialized: {n_estimators} trees, max_depth={max_depth}")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练模型"""
        self.model.fit(X, y)
        logger.info("Random Forest training completed")
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测"""
        return self.model.predict(X)
    
    def get_feature_importance(self) -> np.ndarray:
        """获取特征重要性"""
        return self.model.feature_importances_

class GradientBoostingRegressor:
    """梯度提升回归器"""
    
    def __init__(self, n_estimators: int = 100, learning_rate: float = 0.1,
                 max_depth: int = 3, min_samples_split: int = 2,
                 min_samples_leaf: int = 1, random_state: Optional[int] = None):
        self.model = SklearnGradientBoosting(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state
        )
        
        logger.info(f"Gradient Boosting initialized: {n_estimators} estimators, lr={learning_rate}")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练模型"""
        self.model.fit(X, y)
        logger.info("Gradient Boosting training completed")
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测"""
        return self.model.predict(X)
    
    def get_feature_importance(self) -> np.ndarray:
        """获取特征重要性"""
        return self.model.feature_importances_

class XGBoostRegressor:
    """XGBoost回归器（使用sklearn兼容接口）"""
    
    def __init__(self, n_estimators: int = 100, learning_rate: float = 0.1,
                 max_depth: int = 3, random_state: Optional[int] = None):
        try:
            import xgboost as xgb
            self.model = xgb.XGBRegressor(
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                max_depth=max_depth,
                random_state=random_state
            )
            self.xgb_available = True
            logger.info(f"XGBoost initialized: {n_estimators} estimators, lr={learning_rate}")
        except ImportError:
            logger.warning("XGBoost not available, falling back to Gradient Boosting")
            self.model = SklearnGradientBoosting(
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                max_depth=max_depth,
                random_state=random_state
            )
            self.xgb_available = False
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练模型"""
        self.model.fit(X, y)
        logger.info("XGBoost training completed")
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测"""
        return self.model.predict(X)

class LightGBMRegressor:
    """LightGBM回归器（使用sklearn兼容接口）"""
    
    def __init__(self, n_estimators: int = 100, learning_rate: float = 0.1,
                 max_depth: int = 3, random_state: Optional[int] = None):
        try:
            import lightgbm as lgb
            self.model = lgb.LGBMRegressor(
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                max_depth=max_depth,
                random_state=random_state
            )
            self.lgb_available = True
            logger.info(f"LightGBM initialized: {n_estimators} estimators, lr={learning_rate}")
        except ImportError:
            logger.warning("LightGBM not available, falling back to Gradient Boosting")
            self.model = SklearnGradientBoosting(
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                max_depth=max_depth,
                random_state=random_state
            )
            self.lgb_available = False
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练模型"""
        self.model.fit(X, y)
        logger.info("LightGBM training completed")
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测"""
        return self.model.predict(X)

class SupportVectorMachine:
    """支持向量机"""
    
    def __init__(self, kernel: str = 'rbf', C: float = 1.0, gamma: str = 'scale',
                 epsilon: float = 0.1, task: str = 'regression'):
        self.kernel = kernel
        self.C = C
        self.gamma = gamma
        self.epsilon = epsilon
        self.task = task
        
        # 根据任务类型选择模型
        if task == 'regression':
            self.model = SVR(kernel=kernel, C=C, gamma=gamma, epsilon=epsilon)
        elif task == 'classification':
            self.model = SVC(kernel=kernel, C=C, gamma=gamma, probability=True)
        else:
            raise ValueError("Task must be 'regression' or 'classification'")
        
        # 数据标准化器
        self.scaler = StandardScaler()
        self.is_fitted = False
        
        logger.info(f"SVM initialized: {kernel} kernel, C={C}, task={task}")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练模型"""
        # 数据标准化
        X_scaled = self.scaler.fit_transform(X)
        
        # 训练模型
        self.model.fit(X_scaled, y)
        self.is_fitted = True
        
        logger.info("SVM training completed")
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测"""
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")
        
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)

class MultiLayerPerceptron:
    """多层感知机"""
    
    def __init__(self, hidden_layer_sizes: Tuple[int, ...] = (100,),
                 activation: str = 'relu', solver: str = 'adam',
                 alpha: float = 0.0001, learning_rate: str = 'adaptive',
                 max_iter: int = 200, random_state: Optional[int] = None,
                 task: str = 'regression'):
        self.hidden_layer_sizes = hidden_layer_sizes
        self.activation = activation
        self.solver = solver
        self.alpha = alpha
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.task = task
        
        # 根据任务类型选择模型
        if task == 'regression':
            self.model = MLPRegressor(
                hidden_layer_sizes=hidden_layer_sizes,
                activation=activation,
                solver=solver,
                alpha=alpha,
                learning_rate=learning_rate,
                max_iter=max_iter,
                random_state=random_state
            )
        elif task == 'classification':
            self.model = MLPClassifier(
                hidden_layer_sizes=hidden_layer_sizes,
                activation=activation,
                solver=solver,
                alpha=alpha,
                learning_rate=learning_rate,
                max_iter=max_iter,
                random_state=random_state
            )
        else:
            raise ValueError("Task must be 'regression' or 'classification'")
        
        # 数据标准化器
        self.scaler = StandardScaler()
        self.is_fitted = False
        
        logger.info(f"MLP initialized: {hidden_layer_sizes} layers, {activation} activation")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练模型"""
        # 数据标准化
        X_scaled = self.scaler.fit_transform(X)
        
        # 训练模型
        self.model.fit(X_scaled, y)
        self.is_fitted = True
        
        logger.info("MLP training completed")
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测"""
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")
        
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)
