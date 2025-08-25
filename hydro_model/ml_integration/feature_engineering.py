"""
特征工程和选择模块
==================

本模块提供水文模型的特征工程和选择功能，包括：
- 自动特征工程（特征生成、变换、组合）
- 特征选择算法（过滤、包装、嵌入、混合方法）
- 特征重要性评估
"""

import numpy as np
import logging
from typing import Optional, Tuple, List, Dict, Any
from sklearn.feature_selection import SelectKBest, f_regression, RFE, SelectFromModel
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler, PolynomialFeatures

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AutoFeatureEngineer:
    """自动特征工程"""
    
    def __init__(self, max_polynomial_degree: int = 2, max_interaction_features: int = 10):
        self.max_polynomial_degree = max_polynomial_degree
        self.max_interaction_features = max_interaction_features
        
        # 特征变换器
        self.poly_transformer = None
        self.scaler = StandardScaler()
        
        logger.info("AutoFeatureEngineer initialized")
    
    def generate_features(self, X: np.ndarray) -> np.ndarray:
        """生成新特征"""
        generated_features = []
        
        # 原始特征
        generated_features.append(X)
        
        # 多项式特征
        if self.max_polynomial_degree > 1:
            poly_transformer = PolynomialFeatures(degree=self.max_polynomial_degree, 
                                                include_bias=False, interaction_only=True)
            poly_features = poly_transformer.fit_transform(X)
            
            # 限制交互特征数量
            if poly_features.shape[1] > X.shape[1] + self.max_interaction_features:
                interaction_features = poly_features[:, X.shape[1]:]
                variances = np.var(interaction_features, axis=0)
                top_indices = np.argsort(variances)[-self.max_interaction_features:]
                poly_features = np.hstack([X, interaction_features[:, top_indices]])
            
            generated_features.append(poly_features)
            self.poly_transformer = poly_transformer
        
        # 统计特征
        stat_features = self._generate_statistical_features(X)
        generated_features.append(stat_features)
        
        # 合并所有特征
        all_features = np.hstack(generated_features)
        
        # 标准化
        all_features = self.scaler.fit_transform(all_features)
        
        logger.info(f"Generated {all_features.shape[1]} features from {X.shape[1]} original features")
        return all_features
    
    def _generate_statistical_features(self, X: np.ndarray) -> np.ndarray:
        """生成统计特征"""
        features = []
        
        # 基本统计量
        features.append(np.mean(X, axis=1, keepdims=True))
        features.append(np.std(X, axis=1, keepdims=True))
        features.append(np.median(X, axis=1, keepdims=True))
        features.append(np.max(X, axis=1, keepdims=True))
        features.append(np.min(X, axis=1, keepdims=True))
        
        # 分位数
        features.append(np.percentile(X, 25, axis=1, keepdims=True))
        features.append(np.percentile(X, 75, axis=1, keepdims=True))
        
        return np.hstack(features)
    
    def transform(self, X: np.ndarray) -> np.ndarray:
        """转换新数据"""
        if self.poly_transformer is None:
            raise ValueError("Model must be fitted before transformation")
        
        # 应用相同的变换
        transformed_features = [X]
        
        # 多项式特征
        poly_features = self.poly_transformer.transform(X)
        transformed_features.append(poly_features)
        
        # 统计特征
        stat_features = self._generate_statistical_features(X)
        transformed_features.append(stat_features)
        
        # 合并并标准化
        all_features = np.hstack(transformed_features)
        return self.scaler.transform(all_features)

class FeatureSelector:
    """特征选择器基类"""
    
    def __init__(self, n_features: Optional[int] = None):
        self.n_features = n_features
        self.selected_features = []
        self.feature_scores = {}
        
        logger.info(f"FeatureSelector initialized: n_features={n_features}")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练特征选择器"""
        raise NotImplementedError("Subclasses must implement fit method")
    
    def transform(self, X: np.ndarray) -> np.ndarray:
        """选择特征"""
        if not self.selected_features:
            raise ValueError("Model must be fitted before transformation")
        
        return X[:, self.selected_features]
    
    def fit_transform(self, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        """训练并选择特征"""
        self.fit(X, y)
        return self.transform(X)

class FilterMethods(FeatureSelector):
    """过滤方法特征选择"""
    
    def __init__(self, n_features: Optional[int] = None, method: str = 'f_regression'):
        super().__init__(n_features)
        self.method = method
        
        logger.info(f"FilterMethods initialized: method={method}")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练特征选择器"""
        if self.n_features is None:
            self.n_features = X.shape[1]
        
        # 使用F检验选择特征
        selector = SelectKBest(score_func=f_regression, k=self.n_features)
        selector.fit(X, y)
        
        self.selected_features = np.where(selector.get_support())[0].tolist()
        
        # 存储特征分数
        scores = selector.scores_
        for i, score in enumerate(scores):
            self.feature_scores[f"feature_{i}"] = score
        
        logger.info(f"Selected {len(self.selected_features)} features using {self.method}")

class WrapperMethods(FeatureSelector):
    """包装方法特征选择"""
    
    def __init__(self, n_features: Optional[int] = None, estimator=None):
        super().__init__(n_features)
        self.estimator = estimator if estimator is not None else RandomForestRegressor()
        
        logger.info("WrapperMethods initialized")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练特征选择器"""
        if self.n_features is None:
            self.n_features = X.shape[1]
        
        # 使用递归特征消除
        rfe = RFE(estimator=self.estimator, n_features_to_select=self.n_features, step=1)
        rfe.fit(X, y)
        
        self.selected_features = np.where(rfe.support_)[0].tolist()
        
        # 计算特征重要性
        if hasattr(self.estimator, 'feature_importances_'):
            importances = self.estimator.feature_importances_
            for i, importance in enumerate(importances):
                self.feature_scores[f"feature_{i}"] = importance
        
        logger.info(f"Selected {len(self.selected_features)} features using RFE")

class EmbeddedMethods(FeatureSelector):
    """嵌入方法特征选择"""
    
    def __init__(self, n_features: Optional[int] = None, estimator=None):
        super().__init__(n_features)
        self.estimator = estimator if estimator is not None else RandomForestRegressor()
        
        logger.info("EmbeddedMethods initialized")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练特征选择器"""
        # 训练模型
        self.estimator.fit(X, y)
        
        # 使用SelectFromModel选择特征
        selector = SelectFromModel(self.estimator, threshold='mean')
        selector.fit(X, y)
        
        self.selected_features = np.where(selector.get_support())[0].tolist()
        
        # 获取特征重要性
        if hasattr(self.estimator, 'feature_importances_'):
            importances = self.estimator.feature_importances_
            for i, importance in enumerate(importances):
                self.feature_scores[f"feature_{i}"] = importance
        
        logger.info(f"Selected {len(self.selected_features)} features using embedded method")

class HybridMethods(FeatureSelector):
    """混合方法特征选择"""
    
    def __init__(self, n_features: Optional[int] = None, filter_ratio: float = 0.5):
        super().__init__(n_features)
        self.filter_ratio = filter_ratio
        
        logger.info(f"HybridMethods initialized: filter_ratio={filter_ratio}")
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """训练特征选择器"""
        if self.n_features is None:
            self.n_features = X.shape[1]
        
        # 第一步：过滤方法预选择
        n_filter_features = max(int(X.shape[1] * self.filter_ratio), self.n_features)
        filter_selector = FilterMethods(n_features=n_filter_features, method='f_regression')
        filter_selector.fit(X, y)
        filter_features = filter_selector.selected_features
        
        # 第二步：包装方法精选择
        X_filtered = X[:, filter_features]
        wrapper_selector = WrapperMethods(n_features=self.n_features)
        wrapper_selector.fit(X_filtered, y)
        
        # 映射回原始特征索引
        self.selected_features = [filter_features[i] for i in wrapper_selector.selected_features]
        
        # 合并特征分数
        self.feature_scores.update(filter_selector.feature_scores)
        self.feature_scores.update(wrapper_selector.feature_scores)
        
        logger.info(f"Selected {len(self.selected_features)} features using hybrid method")

class FeatureImportanceEvaluator:
    """特征重要性评估器"""
    
    def __init__(self, methods: List[str] = None):
        if methods is None:
            methods = ['filter', 'wrapper', 'embedded']
        
        self.methods = methods
        self.evaluators = {}
        self.importance_scores = {}
        
        logger.info(f"FeatureImportanceEvaluator initialized: methods={methods}")
    
    def evaluate_importance(self, X: np.ndarray, y: np.ndarray, 
                           n_features: Optional[int] = None) -> Dict[str, Dict]:
        """评估特征重要性"""
        if n_features is None:
            n_features = min(X.shape[1], 20)
        
        for method in self.methods:
            if method == 'filter':
                evaluator = FilterMethods(n_features=n_features, method='f_regression')
            elif method == 'wrapper':
                evaluator = WrapperMethods(n_features=n_features)
            elif method == 'embedded':
                evaluator = EmbeddedMethods(n_features=n_features)
            else:
                continue
            
            try:
                evaluator.fit(X, y)
                self.evaluators[method] = evaluator
                self.importance_scores[method] = evaluator.feature_scores
            except Exception as e:
                logger.warning(f"Failed to evaluate {method}: {e}")
        
        return self.importance_scores
    
    def get_consensus_features(self, top_k: int = 10) -> List[int]:
        """获取共识特征"""
        if not self.importance_scores:
            return []
        
        # 统计每个特征被选中的次数
        feature_counts = {}
        for method, scores in self.importance_scores.items():
            if method in self.evaluators:
                selected = self.evaluators[method].selected_features
                for feature_idx in selected:
                    feature_counts[feature_idx] = feature_counts.get(feature_idx, 0) + 1
        
        # 按选中次数排序
        sorted_features = sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)
        
        # 返回前top_k个特征
        return [feature_idx for feature_idx, count in sorted_features[:top_k]]
