"""
模型训练模块
============

本模块提供水文模型的机器学习训练功能，包括：
- 模型训练器
- 超参数优化器
- 交叉验证器
- 模型评估器
- 模型集成
"""

import numpy as np
import logging
from typing import Optional, Tuple, List, Dict, Any, Union
from sklearn.model_selection import cross_val_score, GridSearchCV, RandomizedSearchCV
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from sklearn.ensemble import VotingRegressor, VotingClassifier
import joblib
import os

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelTrainer:
    """模型训练器"""
    
    def __init__(self, model, model_name: str = "model"):
        self.model = model
        self.model_name = model_name
        self.is_trained = False
        self.training_history = {}
        
        logger.info(f"ModelTrainer initialized for {model_name}")
    
    def train(self, X_train: np.ndarray, y_train: np.ndarray, 
              X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
              **kwargs) -> Dict[str, Any]:
        """训练模型"""
        start_time = time.time()
        
        logger.info(f"Starting training for {self.model_name}")
        
        # 训练模型
        if hasattr(self.model, 'fit'):
            self.model.fit(X_train, y_train, **kwargs)
            self.is_trained = True
        else:
            raise ValueError("Model must have a 'fit' method")
        
        # 计算训练时间
        training_time = time.time() - start_time
        
        # 评估训练集性能
        train_score = self.evaluate(X_train, y_train)
        
        # 评估验证集性能（如果有）
        val_score = None
        if X_val is not None and y_val is not None:
            val_score = self.evaluate(X_val, y_val)
        
        # 记录训练历史
        self.training_history = {
            'training_time': training_time,
            'train_score': train_score,
            'val_score': val_score,
            'n_samples': X_train.shape[0],
            'n_features': X_train.shape[1]
        }
        
        logger.info(f"Training completed in {training_time:.2f}s")
        logger.info(f"Train score: {train_score}")
        if val_score:
            logger.info(f"Validation score: {val_score}")
        
        return self.training_history
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测"""
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")
        
        if hasattr(self.model, 'predict'):
            return self.model.predict(X)
        else:
            raise ValueError("Model must have a 'predict' method")
    
    def evaluate(self, X: np.ndarray, y: np.ndarray) -> Dict[str, float]:
        """评估模型性能"""
        if not self.is_trained:
            raise ValueError("Model must be trained before evaluation")
        
        y_pred = self.predict(X)
        
        # 计算各种评估指标
        metrics = {}
        
        # 回归指标
        if len(y.shape) == 1 or y.shape[1] == 1:
            metrics['mse'] = mean_squared_error(y, y_pred)
            metrics['rmse'] = np.sqrt(metrics['mse'])
            metrics['mae'] = mean_absolute_error(y, y_pred)
            metrics['r2'] = r2_score(y, y_pred)
            
            # 相对误差
            if np.any(y != 0):
                metrics['mape'] = np.mean(np.abs((y - y_pred) / y)) * 100
        
        # 分类指标
        else:
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
            metrics['accuracy'] = accuracy_score(y, y_pred)
            metrics['precision'] = precision_score(y, y_pred, average='weighted')
            metrics['recall'] = recall_score(y, y_pred, average='weighted')
            metrics['f1'] = f1_score(y, y_pred, average='weighted')
        
        return metrics
    
    def save_model(self, filepath: str):
        """保存模型"""
        if not self.is_trained:
            raise ValueError("Model must be trained before saving")
        
        # 创建目录
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # 保存模型
        joblib.dump(self.model, filepath)
        logger.info(f"Model saved to {filepath}")
    
    def load_model(self, filepath: str):
        """加载模型"""
        if os.path.exists(filepath):
            self.model = joblib.load(filepath)
            self.is_trained = True
            logger.info(f"Model loaded from {filepath}")
        else:
            raise FileNotFoundError(f"Model file not found: {filepath}")
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        info = {
            'model_name': self.model_name,
            'is_trained': self.is_trained,
            'training_history': self.training_history
        }
        
        # 添加模型特定信息
        if hasattr(self.model, 'n_estimators'):
            info['n_estimators'] = self.model.n_estimators
        if hasattr(self.model, 'max_depth'):
            info['max_depth'] = self.model.max_depth
        if hasattr(self.model, 'learning_rate'):
            info['learning_rate'] = self.model.learning_rate
        
        return info

class HyperparameterOptimizer:
    """超参数优化器"""
    
    def __init__(self, model, param_grid: Dict[str, List], cv: int = 5,
                 method: str = 'grid', n_iter: int = 100, scoring: str = 'r2'):
        self.model = model
        self.param_grid = param_grid
        self.cv = cv
        self.method = method
        self.n_iter = n_iter
        self.scoring = scoring
        
        self.best_params = None
        self.best_score = None
        self.optimization_results = None
        
        logger.info(f"HyperparameterOptimizer initialized: method={method}, cv={cv}")
    
    def optimize(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """执行超参数优化"""
        logger.info("Starting hyperparameter optimization")
        
        if self.method == 'grid':
            # 网格搜索
            search = GridSearchCV(
                estimator=self.model,
                param_grid=self.param_grid,
                cv=self.cv,
                scoring=self.scoring,
                n_jobs=-1
            )
        elif self.method == 'random':
            # 随机搜索
            search = RandomizedSearchCV(
                estimator=self.model,
                param_distributions=self.param_grid,
                n_iter=self.n_iter,
                cv=self.cv,
                scoring=self.scoring,
                n_jobs=-1,
                random_state=42
            )
        else:
            raise ValueError("Method must be 'grid' or 'random'")
        
        # 执行搜索
        search.fit(X, y)
        
        # 保存结果
        self.best_params = search.best_params_
        self.best_score = search.best_score_
        self.optimization_results = {
            'best_params': self.best_params,
            'best_score': self.best_score,
            'cv_results': search.cv_results_
        }
        
        logger.info(f"Optimization completed. Best score: {self.best_score:.4f}")
        logger.info(f"Best parameters: {self.best_params}")
        
        return self.optimization_results
    
    def get_best_model(self):
        """获取最佳参数的模型"""
        if self.best_params is None:
            raise ValueError("Must run optimize() first")
        
        # 创建新的模型实例并设置最佳参数
        best_model = type(self.model)(**self.best_params)
        return best_model
    
    def plot_optimization_results(self, save_path: Optional[str] = None):
        """绘制优化结果"""
        if self.optimization_results is None:
            logger.warning("No optimization results available for plotting")
            return
        
        try:
            import matplotlib.pyplot as plt
            
            cv_results = self.optimization_results['cv_results']
            
            # 选择前几个最重要的参数进行可视化
            param_names = list(self.param_grid.keys())[:3]
            
            fig, axes = plt.subplots(1, len(param_names), figsize=(5*len(param_names), 5))
            if len(param_names) == 1:
                axes = [axes]
            
            for i, param_name in enumerate(param_names):
                param_values = cv_results[f'param_{param_name}']
                scores = cv_results['mean_test_score']
                
                # 去重并排序
                unique_values = sorted(set(param_values))
                mean_scores = []
                for value in unique_values:
                    mask = param_values == value
                    mean_scores.append(np.mean(scores[mask]))
                
                axes[i].plot(unique_values, mean_scores, 'o-')
                axes[i].set_xlabel(param_name)
                axes[i].set_ylabel(f'Mean {self.scoring}')
                axes[i].set_title(f'{param_name} vs Score')
                axes[i].grid(True)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Optimization results plot saved to {save_path}")
            else:
                plt.show()
                
        except ImportError:
            logger.warning("matplotlib not available for plotting")
        except Exception as e:
            logger.error(f"Failed to plot optimization results: {e}")

class CrossValidator:
    """交叉验证器"""
    
    def __init__(self, model, cv: int = 5, scoring: str = 'r2'):
        self.model = model
        self.cv = cv
        self.scoring = scoring
        
        self.cv_scores = None
        self.cv_results = None
        
        logger.info(f"CrossValidator initialized: cv={cv}, scoring={scoring}")
    
    def cross_validate(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """执行交叉验证"""
        logger.info(f"Starting {self.cv}-fold cross-validation")
        
        # 执行交叉验证
        scores = cross_val_score(
            estimator=self.model,
            X=X,
            y=y,
            cv=self.cv,
            scoring=self.scoring,
            n_jobs=-1
        )
        
        # 保存结果
        self.cv_scores = scores
        self.cv_results = {
            'scores': scores,
            'mean_score': np.mean(scores),
            'std_score': np.std(scores),
            'min_score': np.min(scores),
            'max_score': np.max(scores)
        }
        
        logger.info(f"Cross-validation completed")
        logger.info(f"Mean score: {self.cv_results['mean_score']:.4f} ± {self.cv_results['std_score']:.4f}")
        
        return self.cv_results
    
    def get_performance_summary(self) -> str:
        """获取性能摘要"""
        if self.cv_results is None:
            return "No cross-validation results available"
        
        summary = f"""
Cross-Validation Performance Summary:
====================================
Scoring metric: {self.scoring}
Number of folds: {self.cv}
Mean score: {self.cv_results['mean_score']:.4f}
Standard deviation: {self.cv_results['std_score']:.4f}
Min score: {self.cv_results['min_score']:.4f}
Max score: {self.cv_results['max_score']:.4f}
        """
        return summary.strip()

class ModelEvaluator:
    """模型评估器"""
    
    def __init__(self, models: Dict[str, Any], metrics: List[str] = None):
        self.models = models
        if metrics is None:
            metrics = ['mse', 'rmse', 'mae', 'r2']
        self.metrics = metrics
        
        self.evaluation_results = {}
        
        logger.info(f"ModelEvaluator initialized with {len(models)} models")
    
    def evaluate_models(self, X_test: np.ndarray, y_test: np.ndarray) -> Dict[str, Dict]:
        """评估多个模型"""
        logger.info("Starting model evaluation")
        
        for model_name, model in self.models.items():
            logger.info(f"Evaluating {model_name}")
            
            try:
                # 预测
                y_pred = model.predict(X_test)
                
                # 计算评估指标
                metrics = {}
                if 'mse' in self.metrics:
                    metrics['mse'] = mean_squared_error(y_test, y_pred)
                if 'rmse' in self.metrics:
                    metrics['rmse'] = np.sqrt(metrics['mse'])
                if 'mae' in self.metrics:
                    metrics['mae'] = mean_absolute_error(y_test, y_pred)
                if 'r2' in self.metrics:
                    metrics['r2'] = r2_score(y_test, y_pred)
                
                self.evaluation_results[model_name] = metrics
                
            except Exception as e:
                logger.error(f"Failed to evaluate {model_name}: {e}")
                self.evaluation_results[model_name] = {'error': str(e)}
        
        logger.info("Model evaluation completed")
        return self.evaluation_results
    
    def get_best_model(self, metric: str = 'r2', higher_is_better: bool = True) -> str:
        """获取最佳模型"""
        if not self.evaluation_results:
            raise ValueError("Must run evaluate_models() first")
        
        valid_models = {name: results for name, results in self.evaluation_results.items() 
                       if metric in results and 'error' not in results}
        
        if not valid_models:
            raise ValueError(f"No valid results for metric: {metric}")
        
        if higher_is_better:
            best_model = max(valid_models.items(), key=lambda x: x[1][metric])
        else:
            best_model = min(valid_models.items(), key=lambda x: x[1][metric])
        
        return best_model[0]
    
    def plot_comparison(self, save_path: Optional[str] = None):
        """绘制模型比较图"""
        if not self.evaluation_results:
            logger.warning("No evaluation results available for plotting")
            return
        
        try:
            import matplotlib.pyplot as plt
            
            # 准备数据
            model_names = list(self.evaluation_results.keys())
            metrics = [m for m in self.metrics if m in ['mse', 'rmse', 'mae', 'r2']]
            
            # 过滤掉有错误的模型
            valid_models = {name: results for name, results in self.evaluation_results.items() 
                           if 'error' not in results}
            
            if not valid_models:
                logger.warning("No valid models for plotting")
                return
            
            # 创建子图
            n_metrics = len(metrics)
            fig, axes = plt.subplots(1, n_metrics, figsize=(5*n_metrics, 5))
            if n_metrics == 1:
                axes = [axes]
            
            for i, metric in enumerate(metrics):
                values = [valid_models[name][metric] for name in valid_models.keys()]
                
                axes[i].bar(range(len(values)), values)
                axes[i].set_title(f'{metric.upper()} Comparison')
                axes[i].set_xlabel('Models')
                axes[i].set_ylabel(metric.upper())
                axes[i].set_xticks(range(len(values)))
                axes[i].set_xticklabels(list(valid_models.keys()), rotation=45)
                axes[i].grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Model comparison plot saved to {save_path}")
            else:
                plt.show()
                
        except ImportError:
            logger.warning("matplotlib not available for plotting")
        except Exception as e:
            logger.error(f"Failed to plot model comparison: {e}")

class ModelEnsemble:
    """模型集成"""
    
    def __init__(self, models: Dict[str, Any], ensemble_method: str = 'voting',
                 weights: Optional[List[float]] = None):
        self.models = models
        self.ensemble_method = ensemble_method
        self.weights = weights
        
        self.ensemble_model = None
        self.is_trained = False
        
        logger.info(f"ModelEnsemble initialized: method={ensemble_method}")
    
    def create_ensemble(self, task: str = 'regression'):
        """创建集成模型"""
        if self.ensemble_method == 'voting':
            if task == 'regression':
                self.ensemble_model = VotingRegressor(
                    estimators=list(self.models.items()),
                    weights=self.weights
                )
            else:
                self.ensemble_model = VotingClassifier(
                    estimators=list(self.models.items()),
                    weights=self.weights,
                    voting='soft'
                )
        else:
            raise ValueError(f"Unknown ensemble method: {self.ensemble_method}")
        
        logger.info(f"Ensemble model created using {self.ensemble_method}")
        return self.ensemble_model
    
    def train_ensemble(self, X: np.ndarray, y: np.ndarray):
        """训练集成模型"""
        if self.ensemble_model is None:
            self.create_ensemble()
        
        logger.info("Training ensemble model")
        self.ensemble_model.fit(X, y)
        self.is_trained = True
        
        logger.info("Ensemble model training completed")
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """集成预测"""
        if not self.is_trained:
            raise ValueError("Ensemble model must be trained before prediction")
        
        return self.ensemble_model.predict(X)
    
    def get_ensemble_info(self) -> Dict[str, Any]:
        """获取集成模型信息"""
        info = {
            'ensemble_method': self.ensemble_method,
            'n_models': len(self.models),
            'model_names': list(self.models.keys()),
            'weights': self.weights,
            'is_trained': self.is_trained
        }
        
        if self.ensemble_model is not None:
            info['ensemble_type'] = type(self.ensemble_model).__name__
        
        return info

# 导入时间模块
import time
