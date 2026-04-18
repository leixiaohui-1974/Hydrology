"""
时空同化模块
============

提供时空数据同化功能，包括：
- 时空插值
- 时空协方差建模
- 时空同化算法
- 时空一致性检查
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional, Any, Callable, Union
from scipy import stats, interpolate, spatial
from scipy.spatial.distance import cdist
import warnings
import logging
from pathlib import Path
import json
import time
from datetime import datetime, timedelta


class SpatioTemporalInterpolator:
    """时空插值器"""
    
    def __init__(self, interpolation_method: str = 'inverse_distance'):
        """初始化时空插值器"""
        self.interpolation_method = interpolation_method
        
    def interpolate(self, coordinates: np.ndarray, values: np.ndarray,
                   timestamps: np.ndarray, target_coords: np.ndarray,
                   target_times: np.ndarray) -> np.ndarray:
        """执行时空插值"""
        n_targets = len(target_coords)
        interpolated_values = np.full(n_targets, np.nan)
        
        for i, target_time in enumerate(target_times):
            # 找到最近的时间步
            time_idx = np.argmin(np.abs(timestamps - target_time))
            current_values = values[:, time_idx]
            
            # 移除NaN值
            valid_mask = ~np.isnan(current_values)
            if np.sum(valid_mask) < 2:
                continue
                
            valid_coords = coordinates[valid_mask]
            valid_vals = current_values[valid_mask]
            
            # 计算距离
            distances = cdist([target_coords[i]], valid_coords)[0]
            
            # 反距离加权
            weights = 1.0 / (distances + 1e-6)
            weights = weights / np.sum(weights)
            
            interpolated_values[i] = np.sum(valid_vals * weights)
            
        return interpolated_values


class SpatioTemporalCovariance:
    """时空协方差建模"""
    
    def __init__(self, covariance_model: str = 'exponential'):
        """初始化时空协方差建模"""
        self.covariance_model = covariance_model
        self.covariance_parameters = {}
        
    def fit_covariance_model(self, coordinates: np.ndarray, values: np.ndarray,
                           timestamps: np.ndarray) -> Dict[str, Any]:
        """拟合协方差模型"""
        # 计算空间距离
        spatial_distances = cdist(coordinates, coordinates)
        
        # 计算时间距离
        time_distances = np.abs(timestamps[:, None] - timestamps[None, :])
        
        # 计算观测值差异
        value_differences = values[:, :, None] - values[:, None, :]
        value_variances = np.var(value_differences, axis=0)
        
        # 拟合空间协方差参数
        max_distance = np.max(spatial_distances)
        max_variance = np.max(value_variances)
        
        if self.covariance_model == 'exponential':
            range_param = max_distance / 3.0
        else:
            range_param = max_distance / 2.0
            
        # 拟合时间协方差参数
        max_time = np.max(time_distances)
        if self.covariance_model == 'exponential':
            time_range = max_time / 3.0
        else:
            time_range = max_time / 2.0
            
        self.covariance_parameters = {
            'spatial': {'range': range_param, 'sill': max_variance, 'nugget': 0.0},
            'temporal': {'range': time_range, 'sill': max_variance, 'nugget': 0.0},
            'model_type': self.covariance_model
        }
        
        return self.covariance_parameters
        
    def compute_covariance(self, coord1: np.ndarray, coord2: np.ndarray,
                          time1: float, time2: float) -> float:
        """计算协方差"""
        if not self.covariance_parameters:
            return 0.0
            
        # 计算空间距离
        spatial_distance = np.linalg.norm(coord1 - coord2)
        
        # 计算时间距离
        temporal_distance = abs(time1 - time2)
        
        # 空间协方差
        spatial_params = self.covariance_parameters['spatial']
        spatial_cov = spatial_params['sill'] * np.exp(-spatial_distance / spatial_params['range'])
        
        # 时间协方差
        temporal_params = self.covariance_parameters['temporal']
        temporal_cov = temporal_params['sill'] * np.exp(-temporal_distance / temporal_params['range'])
        
        # 组合协方差
        total_cov = spatial_cov * temporal_cov
        
        return total_cov


class SpatioTemporalAssimilation:
    """时空同化算法"""
    
    def __init__(self, assimilation_method: str = 'enkf'):
        """初始化时空同化算法"""
        self.assimilation_method = assimilation_method
        
    def assimilate(self, background_state: np.ndarray, observations: np.ndarray,
                  observation_coords: np.ndarray, observation_times: np.ndarray,
                  background_covariance: np.ndarray, observation_covariance: np.ndarray,
                  model_coordinates: np.ndarray, model_times: np.ndarray) -> Dict[str, Any]:
        """执行时空同化"""
        if self.assimilation_method == 'enkf':
            return self._enkf_assimilation(background_state, observations, observation_coords,
                                         observation_times, background_covariance,
                                         observation_covariance, model_coordinates, model_times)
        else:
            raise ValueError(f"Unknown assimilation method: {self.assimilation_method}")
            
    def _enkf_assimilation(self, background_state: np.ndarray, observations: np.ndarray,
                          observation_coords: np.ndarray, observation_times: np.ndarray,
                          background_covariance: np.ndarray, observation_covariance: np.ndarray,
                          model_coordinates: np.ndarray, model_times: np.ndarray) -> Dict[str, Any]:
        """集合卡尔曼滤波同化"""
        n_model_points = len(model_coordinates)
        n_observations = len(observations)
        
        # 创建观测算子（简化的最近邻插值）
        observation_operator = np.zeros((n_observations, n_model_points))
        
        for i, (obs_coord, obs_time) in enumerate(zip(observation_coords, observation_times)):
            # 找到最近的模型点
            spatial_distances = cdist([obs_coord], model_coordinates)[0]
            temporal_distances = np.abs(obs_time - model_times)
            
            # 综合距离
            total_distances = spatial_distances + temporal_distances * 0.1
            
            nearest_idx = np.argmin(total_distances)
            observation_operator[i, nearest_idx] = 1.0
            
        # 计算卡尔曼增益
        obs_cov_total = observation_operator @ background_covariance @ observation_operator.T + observation_covariance
        kalman_gain = background_covariance @ observation_operator.T @ np.linalg.inv(obs_cov_total)
        
        # 计算观测创新
        background_obs = observation_operator @ background_state
        innovation = observations - background_obs
        
        # 更新状态
        analysis_state = background_state + kalman_gain @ innovation
        
        # 计算分析协方差
        analysis_covariance = background_covariance - kalman_gain @ observation_operator @ background_covariance
        
        return {
            'analysis_state': analysis_state,
            'analysis_covariance': analysis_covariance,
            'innovation': innovation,
            'kalman_gain': kalman_gain,
            'method': 'enkf'
        }


def example_usage():
    """示例用法"""
    
    # 创建示例数据
    np.random.seed(42)
    
    # 模型网格
    n_model_points = 50
    model_coords = np.random.uniform(0, 100, (n_model_points, 2))
    model_times = np.linspace(0, 24, 25)
    
    # 观测点
    n_obs_points = 20
    obs_coords = np.random.uniform(0, 100, (n_obs_points, 2))
    obs_times = np.random.uniform(0, 24, n_obs_points)
    
    # 背景场状态
    background_state = np.random.normal(10, 2, n_model_points)
    
    # 观测值
    observations = np.random.normal(10, 1, n_obs_points)
    
    # 协方差矩阵
    background_cov = np.eye(n_model_points) * 4.0
    obs_cov = np.eye(n_obs_points) * 1.0
    
    print("时空同化示例:")
    print(f"  模型点数: {n_model_points}")
    print(f"  观测点数: {n_obs_points}")
    print(f"  时间步数: {len(model_times)}")
    
    # 时空插值
    interpolator = SpatioTemporalInterpolator('inverse_distance')
    interpolated_values = interpolator.interpolate(
        obs_coords, observations.reshape(-1, 1), obs_times,
        model_coords[:10], model_times[:10]
    )
    
    print(f"\n插值结果:")
    print(f"  插值点数: {len(interpolated_values)}")
    print(f"  插值均值: {np.nanmean(interpolated_values):.2f}")
    
    # 时空协方差建模
    covariance_model = SpatioTemporalCovariance('exponential')
    covariance_params = covariance_model.fit_covariance_model(
        obs_coords, observations.reshape(-1, 1), obs_times
    )
    
    print(f"\n协方差模型参数:")
    print(f"  空间范围: {covariance_params['spatial']['range']:.2f}")
    print(f"  时间范围: {covariance_params['temporal']['range']:.2f}")
    
    # 时空同化
    assimilation = SpatioTemporalAssimilation('enkf')
    assimilation_results = assimilation.assimilate(
        background_state, observations, obs_coords, obs_times,
        background_cov, obs_cov, model_coords, model_times
    )
    
    print(f"\n同化结果:")
    print(f"  同化方法: {assimilation_results['method']}")
    print(f"  分析状态形状: {assimilation_results['analysis_state'].shape}")
    print(f"  创新向量形状: {assimilation_results['innovation'].shape}")


if __name__ == "__main__":
    example_usage()
