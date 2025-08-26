"""
机器学习集成 - 时间序列预测示例
========================================

本示例展示了如何使用 `TimeSeriesFeatureEngineer` 和 `RandomForestRegressor`
来训练一个模型，该模型根据降雨时间序列数据预测径流。

工作流程:
1. 加载包含时间戳、降雨和径流的样本数据。
2. 使用 `TimeSeriesFeatureEngineer` 从降雨数据中创建滞后和滚动窗口特征。
3. 将数据分为训练集和测试集。
4. 实例化一个 `RandomForestRegressor` 模型。
5. 训练模型以根据工程化的降雨特征预测径流。
6. 将训练好的模型保存到文件。
7. 从文件加载模型并用它来进行新的预测。
"""
import pandas as pd
import numpy as np
import sys
import os
import logging

# 将项目根目录添加到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from hydro_model.ml_integration.feature_engineering import TimeSeriesFeatureEngineer
from hydro_model.ml_integration.traditional_ml import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """主函数"""
    logger.info("--- 开始机器学习集成示例 ---")

    # --- 1. 加载数据 ---
    data_path = os.path.join(os.path.dirname(__file__), 'sample_hydro_data.csv')
    try:
        df = pd.read_csv(data_path, parse_dates=['timestamp'], index_col='timestamp')
        logger.info(f"成功从 {data_path} 加载数据。")
        logger.info(f"数据形状: {df.shape}")
    except FileNotFoundError:
        logger.error(f"数据文件未找到: {data_path}")
        return

    # --- 2. 特征工程 ---
    logger.info("--- 步骤 2: 创建时间序列特征 ---")
    
    # 我们只使用降雨作为输入特征
    rainfall_df = df[['rainfall_mm']]
    
    # 定义特征工程参数
    feature_engineer = TimeSeriesFeatureEngineer(
        lag_features=[1, 2, 3, 6],          # 1, 2, 3, 6小时前的降雨
        rolling_window_sizes=[3, 6, 12]  # 3, 6, 12小时的滚动统计
    )
    
    # 创建特征
    features_df = feature_engineer.fit_transform(rainfall_df)

    # 将目标变量（径流）与特征对齐
    # 由于特征工程会产生NaN值并被移除，我们需要确保目标变量与特征有相同的索引
    target = df['runoff_cfs'].loc[features_df.index]
    
    logger.info(f"特征工程完成。最终特征数量: {len(feature_engineer.feature_names_)}")
    logger.info(f"特征 DataFrame 形状: {features_df.shape}")
    logger.info(f"目标 Series 形状: {target.shape}")

    # --- 3. 准备训练和测试数据 ---
    logger.info("--- 步骤 3: 分割训练和测试数据 ---")
    
    X = features_df.values
    y = target.values
    
    # 按时间顺序分割数据，前80%用于训练，后20%用于测试
    split_index = int(len(X) * 0.8)
    X_train, X_test = X[:split_index], X[split_index:]
    y_train, y_test = y[:split_index], y[split_index:]

    logger.info(f"训练集大小: {X_train.shape[0]}")
    logger.info(f"测试集大小: {X_test.shape[0]}")

    # --- 4. 训练模型 ---
    logger.info("--- 步骤 4: 训练随机森林模型 ---")

    # 实例化一个模型包装器
    rf_model = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        random_state=42
    )

    # 训练模型
    rf_model.fit(X_train, y_train)
    logger.info("模型训练完成。")

    # --- 5. 评估模型 ---
    logger.info("--- 步骤 5: 评估模型性能 ---")

    y_pred = rf_model.predict(X_test)

    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    logger.info(f"测试集上的模型性能:")
    logger.info(f"  均方误差 (MSE): {mse:.4f}")
    logger.info(f"  R² 分数: {r2:.4f}")

    # --- 6. 保存模型 ---
    logger.info("--- 步骤 6: 保存训练好的模型 ---")

    model_path = os.path.join(os.path.dirname(__file__), 'trained_runoff_model.joblib')
    rf_model.save(model_path)
    logger.info(f"模型已保存到: {model_path}")

    # --- 7. 加载模型并进行预测 ---
    logger.info("--- 步骤 7: 加载模型并进行新预测 ---")
    
    # 创建一个新的模型实例来加载保存的模型
    loaded_rf_model = RandomForestRegressor()
    loaded_rf_model.load(model_path)
    logger.info("模型加载成功。")
    
    # 使用加载的模型进行预测 (使用与之前相同的测试数据)
    new_y_pred = loaded_rf_model.predict(X_test)
    
    # 验证新预测是否与原始预测相同
    np.testing.assert_array_almost_equal(y_pred, new_y_pred)
    logger.info("加载的模型预测结果与原始预测结果一致。")
    
    logger.info("--- 机器学习集成示例成功完成！ ---")


if __name__ == "__main__":
    main()
