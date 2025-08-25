"""
机器学习集成系统示例
==================

本示例展示机器学习集成系统的各种功能
"""

import numpy as np
import matplotlib.pyplot as plt
import logging
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hydro_model.ml_integration.deep_learning import (
    TimeSeriesTransformer, QLearningAgent
)
from hydro_model.ml_integration.traditional_ml import (
    RandomForestRegressor, GradientBoostingRegressor, SupportVectorMachine
)
from hydro_model.ml_integration.feature_engineering import (
    AutoFeatureEngineer, FilterMethods
)
from hydro_model.ml_integration.model_training import (
    ModelTrainer, CrossValidator
)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_synthetic_data(n_samples=1000, n_features=10):
    """生成合成数据"""
    logger.info("生成合成数据...")
    
    np.random.seed(42)
    X = np.random.randn(n_samples, n_features)
    y = (X[:, 0] ** 2 + X[:, 1] * X[:, 2] + np.sin(X[:, 3]) + 
         np.random.normal(0, 0.1, n_samples))
    
    split_idx = int(0.8 * n_samples)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    
    return X_train, X_test, y_train, y_test

def demonstrate_traditional_ml(X_train, y_train, X_test, y_test):
    """演示传统机器学习方法"""
    logger.info("=== 传统机器学习方法演示 ===")
    
    results = {}
    
    # 随机森林
    try:
        logger.info("训练随机森林...")
        rf_model = RandomForestRegressor(n_estimators=100, max_depth=10)
        rf_trainer = ModelTrainer(rf_model, "RandomForest")
        rf_trainer.train(X_train, y_train)
        
        metrics = rf_trainer.evaluate(X_test, y_test)
        results['random_forest'] = metrics
        
        logger.info(f"随机森林R²: {metrics['r2']:.4f}")
        
    except Exception as e:
        logger.error(f"随机森林训练失败: {e}")
    
    # 梯度提升
    try:
        logger.info("训练梯度提升...")
        gb_model = GradientBoostingRegressor(n_estimators=100, learning_rate=0.1)
        gb_trainer = ModelTrainer(gb_model, "GradientBoosting")
        gb_trainer.train(X_train, y_train)
        
        metrics = gb_trainer.evaluate(X_test, y_test)
        results['gradient_boosting'] = metrics
        
        logger.info(f"梯度提升R²: {metrics['r2']:.4f}")
        
    except Exception as e:
        logger.error(f"梯度提升训练失败: {e}")
    
    return results

def demonstrate_feature_engineering(X_train, y_train, X_test, y_test):
    """演示特征工程和选择"""
    logger.info("=== 特征工程和选择演示 ===")
    
    results = {}
    
    # 自动特征工程
    try:
        logger.info("执行自动特征工程...")
        feature_engineer = AutoFeatureEngineer(max_polynomial_degree=2, max_interaction_features=20)
        
        X_train_enhanced = feature_engineer.generate_features(X_train)
        X_test_enhanced = feature_engineer.transform(X_test)
        
        results['feature_engineering'] = {
            'original_features': X_train.shape[1],
            'enhanced_features': X_train_enhanced.shape[1]
        }
        
        logger.info(f"特征工程: {X_train.shape[1]} -> {X_train_enhanced.shape[1]} 特征")
        
    except Exception as e:
        logger.error(f"特征工程失败: {e}")
    
    # 特征选择
    try:
        logger.info("执行特征选择...")
        filter_selector = FilterMethods(n_features=min(20, X_train.shape[1]))
        X_train_filtered = filter_selector.fit_transform(X_train, y_train)
        
        results['feature_selection'] = {
            'n_selected': X_train_filtered.shape[1]
        }
        
        logger.info(f"特征选择: 选择了 {X_train_filtered.shape[1]} 个特征")
        
    except Exception as e:
        logger.error(f"特征选择失败: {e}")
    
    return results

def demonstrate_model_training(X_train, y_train, X_test, y_test):
    """演示模型训练和评估"""
    logger.info("=== 模型训练和评估演示 ===")
    
    results = {}
    
    # 交叉验证
    try:
        logger.info("执行交叉验证...")
        rf_model = RandomForestRegressor(n_estimators=100, max_depth=10)
        cv_validator = CrossValidator(rf_model, cv=5, scoring='r2')
        cv_results = cv_validator.cross_validate(X_train, y_train)
        
        results['cross_validation'] = cv_results
        logger.info(f"交叉验证: {cv_results['mean_score']:.4f} ± {cv_results['std_score']:.4f}")
        
    except Exception as e:
        logger.error(f"交叉验证失败: {e}")
    
    return results

def plot_results(results):
    """绘制结果图表"""
    logger.info("绘制结果图表...")
    
    try:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        fig.suptitle('机器学习集成系统演示结果', fontsize=16)
        
        # 传统机器学习模型性能比较
        if 'traditional_ml' in results:
            ax1 = axes[0]
            model_names = []
            r2_scores = []
            
            for name, result in results['traditional_ml'].items():
                if 'r2' in result:
                    model_names.append(name)
                    r2_scores.append(result['r2'])
            
            if model_names:
                bars = ax1.bar(model_names, r2_scores)
                ax1.set_title('传统机器学习模型性能比较')
                ax1.set_ylabel('R² Score')
                ax1.set_ylim(0, 1)
        
        # 特征工程效果
        if 'feature_engineering' in results:
            ax2 = axes[1]
            fe_result = results['feature_engineering']
            
            if 'original_features' in fe_result:
                original = fe_result['original_features']
                enhanced = fe_result['enhanced_features']
                
                ax2.bar(['原始特征', '增强特征'], [original, enhanced], color=['skyblue', 'lightcoral'])
                ax2.set_title('特征工程效果')
                ax2.set_ylabel('特征数量')
        
        plt.tight_layout()
        plt.savefig('ml_integration_results.png', dpi=300, bbox_inches='tight')
        logger.info("结果图表已保存")
        
    except Exception as e:
        logger.error(f"绘制结果图表失败: {e}")

def main():
    """主函数"""
    logger.info("开始机器学习集成系统演示")
    
    # 生成数据
    X_train, X_test, y_train, y_test = generate_synthetic_data()
    
    # 演示各个模块
    results = {}
    results['traditional_ml'] = demonstrate_traditional_ml(X_train, y_train, X_test, y_test)
    results['feature_engineering'] = demonstrate_feature_engineering(X_train, y_train, X_test, y_test)
    results['model_training'] = demonstrate_model_training(X_train, y_train, X_test, y_test)
    
    # 绘制结果
    plot_results(results)
    
    logger.info("机器学习集成系统演示完成！")

if __name__ == "__main__":
    main()
