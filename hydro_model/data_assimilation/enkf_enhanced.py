"""
增强的EnKF算法
==============

提供高级的集合卡尔曼滤波算法，包括：
- 局部化EnKF（空间、时间、协方差局部化）
- 自适应EnKF（自适应协方差膨胀、观测误差估计）
- 收敛性监控和诊断
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional, Any, Callable
from scipy import linalg, stats
from scipy.spatial.distance import cdist
import warnings
import logging
from pathlib import Path
import json
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp


class LocalizedEnKF:
    """
    局部化EnKF算法
    
    实现空间、时间和协方差局部化，提高EnKF在大规模问题上的性能
    """
    
    def __init__(self, ensemble_size: int = 100, localization_radius: float = 100.0,
                 localization_type: str = 'gaspari_cohn', n_workers: int = None):
        """
        初始化局部化EnKF
        
        Args:
            ensemble_size: 集合大小
            localization_radius: 局部化半径
            localization_type: 局部化类型 ('gaspari_cohn', 'boxcar', 'exponential')
            n_workers: 并行工作进程数
        """
        self.ensemble_size = ensemble_size
        self.localization_radius = localization_radius
        self.localization_type = localization_type
        self.n_workers = n_workers or min(mp.cpu_count(), 8)
        
        # 状态和观测信息
        self.state_dim = None
        self.obs_dim = None
        self.state_locations = None
        self.obs_locations = None
        
        # 集合状态和观测
        self.ensemble_states = None
        self.ensemble_obs = None
        
        # 局部化矩阵
        self.localization_matrix = None
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
    def set_state_info(self, state_dim: int, state_locations: Optional[np.ndarray] = None):
        """
        设置状态信息
        
        Args:
            state_dim: 状态维度
            state_locations: 状态位置坐标 (n_states, n_coords)
        """
        self.state_dim = state_dim
        if state_locations is not None:
            self.state_locations = np.array(state_locations)
        else:
            # 默认使用一维网格
            self.state_locations = np.arange(state_dim).reshape(-1, 1)
            
        self.logger.info(f"State dimension: {state_dim}")
        
    def set_observation_info(self, obs_dim: int, obs_locations: Optional[np.ndarray] = None):
        """
        设置观测信息
        
        Args:
            obs_dim: 观测维度
            obs_locations: 观测位置坐标 (n_obs, n_coords)
        """
        self.obs_dim = obs_dim
        if obs_locations is not None:
            self.obs_locations = np.array(obs_locations)
        else:
            # 默认使用一维网格
            self.obs_locations = np.arange(obs_dim).reshape(-1, 1)
            
        self.logger.info(f"Observation dimension: {obs_dim}")
        
    def compute_localization_matrix(self):
        """计算局部化矩阵"""
        if self.state_locations is None or self.obs_locations is None:
            raise ValueError("State and observation locations must be set")
            
        self.logger.info("Computing localization matrix...")
        start_time = time.time()
        
        # 计算距离矩阵
        distances = cdist(self.state_locations, self.obs_locations)
        
        # 应用局部化函数
        if self.localization_type == 'gaspari_cohn':
            self.localization_matrix = self._gaspari_cohn_localization(distances)
        elif self.localization_type == 'boxcar':
            self.localization_matrix = self._boxcar_localization(distances)
        elif self.localization_type == 'exponential':
            self.localization_matrix = self._exponential_localization(distances)
        else:
            raise ValueError(f"Unknown localization type: {self.localization_type}")
            
        elapsed_time = time.time() - start_time
        self.logger.info(f"Localization matrix computed in {elapsed_time:.2f}s")
        
    def _gaspari_cohn_localization(self, distances: np.ndarray) -> np.ndarray:
        """Gaspari-Cohn局部化函数"""
        r = distances / self.localization_radius
        
        # 分段函数
        r1 = np.where(r <= 1, r, 0)
        r2 = np.where((r > 1) & (r <= 2), r, 0)
        
        # 计算局部化系数
        rho = np.zeros_like(r)
        
        # r <= 1
        mask1 = r1 > 0
        rho[mask1] = (-r1[mask1]**5/4 + r1[mask1]**4/2 + 5*r1[mask1]**3/8 - 
                      5*r1[mask1]**2/4 + r1[mask1]/4 + 1/2)
        
        # 1 < r <= 2
        mask2 = r2 > 0
        rho[mask2] = (r2[mask2]**5/12 - r2[mask2]**4/2 + 5*r2[mask2]**3/8 + 
                      5*r2[mask2]**2/4 - 5*r2[mask2]/2 + 4/3 - 2/(3*r2[mask2]))
        
        return rho
        
    def _boxcar_localization(self, distances: np.ndarray) -> np.ndarray:
        """Boxcar局部化函数"""
        rho = np.where(distances <= self.localization_radius, 1.0, 0.0)
        return rho
        
    def _exponential_localization(self, distances: np.ndarray) -> np.ndarray:
        """指数局部化函数"""
        rho = np.exp(-distances / self.localization_radius)
        return rho
        
    def set_ensemble(self, ensemble_states: np.ndarray, ensemble_obs: np.ndarray):
        """
        设置集合状态和观测
        
        Args:
            ensemble_states: 集合状态 (n_states, ensemble_size)
            ensemble_obs: 集合观测 (n_obs, ensemble_size)
        """
        if ensemble_states.shape[1] != self.ensemble_size:
            raise ValueError(f"Expected ensemble size {self.ensemble_size}, got {ensemble_states.shape[1]}")
            
        if ensemble_obs.shape[1] != self.ensemble_size:
            raise ValueError(f"Expected ensemble size {self.ensemble_size}, got {ensemble_obs.shape[1]}")
            
        self.ensemble_states = ensemble_states
        self.ensemble_obs = ensemble_obs
        
        self.logger.info(f"Ensemble set: states {ensemble_states.shape}, obs {ensemble_obs.shape}")
        
    def assimilate(self, observations: np.ndarray, obs_errors: Optional[np.ndarray] = None) -> np.ndarray:
        """
        执行局部化EnKF同化
        
        Args:
            observations: 观测值 (n_obs,)
            obs_errors: 观测误差 (n_obs,)
            
        Returns:
            更新后的集合状态
        """
        if self.ensemble_states is None or self.ensemble_obs is None:
            raise ValueError("Ensemble must be set before assimilation")
            
        if self.localization_matrix is None:
            self.compute_localization_matrix()
            
        self.logger.info("Starting localized EnKF assimilation...")
        start_time = time.time()
        
        # 计算集合统计量
        state_mean = np.mean(self.ensemble_states, axis=1, keepdims=True)
        obs_mean = np.mean(self.ensemble_obs, axis=1, keepdims=True)
        
        # 计算集合扰动
        state_perturbations = self.ensemble_states - state_mean
        obs_perturbations = self.ensemble_obs - obs_mean
        
        # 计算协方差矩阵
        state_cov = np.cov(state_perturbations)
        obs_cov = np.cov(obs_perturbations)
        cross_cov = np.cov(state_perturbations, obs_perturbations)[:self.state_dim, self.state_dim:]
        
        # 应用局部化
        localized_cross_cov = cross_cov * self.localization_matrix
        localized_obs_cov = obs_cov * (self.localization_matrix @ self.localization_matrix.T)
        
        # 观测误差协方差
        if obs_errors is None:
            obs_errors = np.ones(self.obs_dim)
        obs_cov_matrix = np.diag(obs_errors**2)
        
        # 计算卡尔曼增益
        try:
            kalman_gain = localized_cross_cov @ np.linalg.inv(localized_obs_cov + obs_cov_matrix)
        except np.linalg.LinAlgError:
            # 使用伪逆
            kalman_gain = localized_cross_cov @ np.linalg.pinv(localized_obs_cov + obs_cov_matrix)
            
        # 更新集合
        obs_innovations = observations.reshape(-1, 1) - obs_mean
        state_updates = kalman_gain @ obs_innovations
        
        updated_states = self.ensemble_states + state_updates
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"Localized EnKF assimilation completed in {elapsed_time:.2f}s")
        
        return updated_states
        
    def get_analysis_statistics(self) -> Dict[str, Any]:
        """获取分析统计信息"""
        if self.ensemble_states is None:
            return {}
            
        stats = {
            'ensemble_size': self.ensemble_size,
            'state_dim': self.state_dim,
            'obs_dim': self.obs_dim,
            'localization_radius': self.localization_radius,
            'localization_type': self.localization_type
        }
        
        # 状态统计
        if self.ensemble_states is not None:
            stats['state_mean'] = np.mean(self.ensemble_states, axis=1)
            stats['state_std'] = np.std(self.ensemble_states, axis=1)
            stats['state_spread'] = np.trace(np.cov(self.ensemble_states))
            
        # 观测统计
        if self.ensemble_obs is not None:
            stats['obs_mean'] = np.mean(self.ensemble_obs, axis=1)
            stats['obs_std'] = np.std(self.ensemble_obs, axis=1)
            stats['obs_spread'] = np.trace(np.cov(self.ensemble_obs))
            
        return stats


class AdaptiveEnKF:
    """
    自适应EnKF算法
    
    实现自适应协方差膨胀、观测误差估计和收敛性监控
    """
    
    def __init__(self, ensemble_size: int = 100, inflation_factor: float = 1.0,
                 adaptive_inflation: bool = True, adaptive_obs_error: bool = True):
        """
        初始化自适应EnKF
        
        Args:
            ensemble_size: 集合大小
            inflation_factor: 初始膨胀因子
            adaptive_inflation: 是否启用自适应膨胀
            adaptive_obs_error: 是否启用自适应观测误差估计
        """
        self.ensemble_size = ensemble_size
        self.inflation_factor = inflation_factor
        self.adaptive_inflation = adaptive_inflation
        self.adaptive_obs_error = adaptive_obs_error
        
        # 状态和观测信息
        self.state_dim = None
        self.obs_dim = None
        
        # 集合状态和观测
        self.ensemble_states = None
        self.ensemble_obs = None
        
        # 自适应参数
        self.inflation_history = [inflation_factor]
        self.obs_error_history = []
        self.innovation_history = []
        
        # 收敛性监控
        self.convergence_metrics = []
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
    def set_state_info(self, state_dim: int):
        """设置状态信息"""
        self.state_dim = state_dim
        self.logger.info(f"State dimension: {state_dim}")
        
    def set_observation_info(self, obs_dim: int):
        """设置观测信息"""
        self.obs_dim = obs_dim
        self.logger.info(f"Observation dimension: {obs_dim}")
        
    def set_ensemble(self, ensemble_states: np.ndarray, ensemble_obs: np.ndarray):
        """设置集合状态和观测"""
        if ensemble_states.shape[1] != self.ensemble_size:
            raise ValueError(f"Expected ensemble size {self.ensemble_size}, got {ensemble_states.shape[1]}")
            
        if ensemble_obs.shape[1] != self.ensemble_size:
            raise ValueError(f"Expected ensemble size {self.ensemble_size}, got {ensemble_obs.shape[1]}")
            
        self.ensemble_states = ensemble_states
        self.ensemble_obs = ensemble_obs
        
        self.logger.info(f"Ensemble set: states {ensemble_states.shape}, obs {ensemble_obs.shape}")
        
    def _compute_adaptive_inflation(self, innovations: np.ndarray, obs_cov: np.ndarray) -> float:
        """
        计算自适应膨胀因子
        
        Args:
            innovations: 观测创新
            obs_cov: 观测协方差
            
        Returns:
            新的膨胀因子
        """
        if not self.adaptive_inflation:
            return self.inflation_factor
            
        # 基于创新统计的自适应膨胀
        innovation_variance = np.var(innovations)
        expected_variance = np.trace(obs_cov)
        
        if expected_variance > 0:
            # 计算方差比
            variance_ratio = innovation_variance / expected_variance
            
            # 自适应调整膨胀因子
            if variance_ratio > 1.5:  # 过度自信
                new_inflation = self.inflation_factor * 1.1
            elif variance_ratio < 0.5:  # 过度保守
                new_inflation = self.inflation_factor * 0.9
            else:
                new_inflation = self.inflation_factor
                
            # 限制膨胀因子范围
            new_inflation = np.clip(new_inflation, 0.5, 3.0)
        else:
            new_inflation = self.inflation_factor
            
        return new_inflation
        
    def _compute_adaptive_obs_error(self, innovations: np.ndarray, 
                                   obs_errors: np.ndarray) -> np.ndarray:
        """
        计算自适应观测误差
        
        Args:
            innovations: 观测创新
            obs_errors: 当前观测误差
            
        Returns:
            新的观测误差
        """
        if not self.adaptive_obs_error:
            return obs_errors
            
        # 基于创新统计的自适应观测误差
        innovation_std = np.std(innovations, axis=1)
        
        # 自适应调整观测误差
        adaptive_errors = obs_errors.copy()
        
        for i in range(len(obs_errors)):
            if innovation_std[i] > obs_errors[i] * 1.5:
                # 创新过大，增加观测误差
                adaptive_errors[i] *= 1.1
            elif innovation_std[i] < obs_errors[i] * 0.5:
                # 创新过小，减少观测误差
                adaptive_errors[i] *= 0.9
                
        # 限制观测误差范围
        adaptive_errors = np.clip(adaptive_errors, obs_errors * 0.5, obs_errors * 2.0)
        
        return adaptive_errors
        
    def _compute_convergence_metrics(self, innovations: np.ndarray, 
                                    state_updates: np.ndarray) -> Dict[str, float]:
        """
        计算收敛性指标
        
        Args:
            innovations: 观测创新
            state_updates: 状态更新
            
        Returns:
            收敛性指标字典
        """
        metrics = {}
        
        # 创新统计
        metrics['innovation_mean'] = np.mean(innovations)
        metrics['innovation_std'] = np.std(innovations)
        metrics['innovation_skewness'] = stats.skew(innovations.flatten())
        
        # 状态更新统计
        metrics['update_mean'] = np.mean(state_updates)
        metrics['update_std'] = np.std(state_updates)
        metrics['update_magnitude'] = np.linalg.norm(state_updates)
        
        # 收敛性指标
        if len(self.convergence_metrics) > 0:
            prev_metrics = self.convergence_metrics[-1]
            metrics['innovation_change'] = abs(metrics['innovation_std'] - prev_metrics['innovation_std'])
            metrics['update_change'] = abs(metrics['update_magnitude'] - prev_metrics['update_magnitude'])
        else:
            metrics['innovation_change'] = float('inf')
            metrics['update_change'] = float('inf')
            
        return metrics
        
    def assimilate(self, observations: np.ndarray, obs_errors: np.ndarray) -> np.ndarray:
        """
        执行自适应EnKF同化
        
        Args:
            observations: 观测值 (n_obs,)
            obs_errors: 观测误差 (n_obs,)
            
        Returns:
            更新后的集合状态
        """
        if self.ensemble_states is None or self.ensemble_obs is None:
            raise ValueError("Ensemble must be set before assimilation")
            
        self.logger.info("Starting adaptive EnKF assimilation...")
        start_time = time.time()
        
        # 应用膨胀
        if self.inflation_factor != 1.0:
            state_mean = np.mean(self.ensemble_states, axis=1, keepdims=True)
            state_perturbations = self.ensemble_states - state_mean
            inflated_states = state_mean + self.inflation_factor * state_perturbations
        else:
            inflated_states = self.ensemble_states.copy()
            
        # 计算集合统计量
        state_mean = np.mean(inflated_states, axis=1, keepdims=True)
        obs_mean = np.mean(self.ensemble_obs, axis=1, keepdims=True)
        
        # 计算集合扰动
        state_perturbations = inflated_states - state_mean
        obs_perturbations = self.ensemble_obs - obs_mean
        
        # 计算协方差矩阵
        state_cov = np.cov(state_perturbations)
        obs_cov = np.cov(obs_perturbations)
        cross_cov = np.cov(state_perturbations, obs_perturbations)[:self.state_dim, self.state_dim:]
        
        # 观测误差协方差
        obs_cov_matrix = np.diag(obs_errors**2)
        
        # 计算卡尔曼增益
        try:
            kalman_gain = cross_cov @ np.linalg.inv(obs_cov + obs_cov_matrix)
        except np.linalg.LinAlgError:
            # 使用伪逆
            kalman_gain = cross_cov @ np.linalg.pinv(obs_cov + obs_cov_matrix)
            
        # 更新集合
        obs_innovations = observations.reshape(-1, 1) - obs_mean
        state_updates = kalman_gain @ obs_innovations
        
        updated_states = inflated_states + state_updates
        
        # 自适应调整
        if self.adaptive_inflation:
            new_inflation = self._compute_adaptive_inflation(obs_innovations, obs_cov)
            self.inflation_factor = new_inflation
            self.inflation_history.append(new_inflation)
            
        if self.adaptive_obs_error:
            new_obs_errors = self._compute_adaptive_obs_error(obs_innovations, obs_errors)
            self.obs_error_history.append(new_obs_errors)
            
        # 计算收敛性指标
        convergence_metrics = self._compute_convergence_metrics(obs_innovations, state_updates)
        self.convergence_metrics.append(convergence_metrics)
        
        # 记录历史
        self.innovation_history.append(obs_innovations.flatten())
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"Adaptive EnKF assimilation completed in {elapsed_time:.2f}s")
        
        return updated_states
        
    def get_adaptive_statistics(self) -> Dict[str, Any]:
        """获取自适应统计信息"""
        stats = {
            'ensemble_size': self.ensemble_size,
            'state_dim': self.state_dim,
            'obs_dim': self.obs_dim,
            'current_inflation': self.inflation_factor,
            'adaptive_inflation': self.adaptive_inflation,
            'adaptive_obs_error': self.adaptive_obs_error
        }
        
        # 膨胀历史
        if self.inflation_history:
            stats['inflation_history'] = self.inflation_history
            stats['inflation_mean'] = np.mean(self.inflation_history)
            stats['inflation_std'] = np.std(self.inflation_history)
            
        # 观测误差历史
        if self.obs_error_history:
            obs_error_array = np.array(self.obs_error_history)
            stats['obs_error_history'] = self.obs_error_history
            stats['obs_error_mean'] = np.mean(obs_error_array, axis=0)
            stats['obs_error_std'] = np.std(obs_error_array, axis=0)
            
        # 创新历史
        if self.innovation_history:
            innovation_array = np.array(self.innovation_history)
            stats['innovation_history'] = self.innovation_history
            stats['innovation_mean'] = np.mean(innovation_array, axis=0)
            stats['innovation_std'] = np.std(innovation_array, axis=0)
            
        # 收敛性指标
        if self.convergence_metrics:
            stats['convergence_metrics'] = self.convergence_metrics
            stats['latest_metrics'] = self.convergence_metrics[-1]
            
        return stats
        
    def plot_adaptive_evolution(self, figsize: Tuple[int, int] = (15, 10)):
        """绘制自适应演化图"""
        if not self.inflation_history and not self.obs_error_history:
            self.logger.warning("No adaptive history available for plotting")
            return
            
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        
        # 膨胀因子演化
        if self.inflation_history:
            ax1 = axes[0, 0]
            ax1.plot(self.inflation_history, 'b-', linewidth=2)
            ax1.set_title('Inflation Factor Evolution')
            ax1.set_xlabel('Assimilation Step')
            ax1.set_ylabel('Inflation Factor')
            ax1.grid(True, alpha=0.3)
            
        # 观测误差演化
        if self.obs_error_history:
            ax2 = axes[0, 1]
            obs_error_array = np.array(self.obs_error_history)
            for i in range(obs_error_array.shape[1]):
                ax2.plot(obs_error_array[:, i], label=f'Obs {i+1}')
            ax2.set_title('Observation Error Evolution')
            ax2.set_xlabel('Assimilation Step')
            ax2.set_ylabel('Observation Error')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
        # 创新统计演化
        if self.innovation_history:
            ax3 = axes[1, 0]
            innovation_array = np.array(self.innovation_history)
            innovation_std = np.std(innovation_array, axis=1)
            ax3.plot(innovation_std, 'g-', linewidth=2)
            ax3.set_title('Innovation Standard Deviation Evolution')
            ax3.set_xlabel('Assimilation Step')
            ax3.set_ylabel('Innovation Std')
            ax3.grid(True, alpha=0.3)
            
        # 收敛性指标演化
        if self.convergence_metrics:
            ax4 = axes[1, 1]
            update_magnitudes = [m['update_magnitude'] for m in self.convergence_metrics]
            ax4.plot(update_magnitudes, 'r-', linewidth=2)
            ax4.set_title('State Update Magnitude Evolution')
            ax4.set_xlabel('Assimilation Step')
            ax4.set_ylabel('Update Magnitude')
            ax4.grid(True, alpha=0.3)
            
        plt.tight_layout()
        return fig


def example_usage():
    """示例用法"""
    
    # 创建局部化EnKF
    localized_enkf = LocalizedEnKF(ensemble_size=50, localization_radius=50.0)
    
    # 设置状态和观测信息
    state_dim = 100
    obs_dim = 20
    
    localized_enkf.set_state_info(state_dim)
    localized_enkf.set_observation_info(obs_dim)
    
    # 创建示例集合
    ensemble_states = np.random.normal(0, 1, (state_dim, 50))
    ensemble_obs = np.random.normal(0, 1, (obs_dim, 50))
    
    localized_enkf.set_ensemble(ensemble_states, ensemble_obs)
    
    # 执行同化
    observations = np.random.normal(0, 0.5, obs_dim)
    updated_states = localized_enkf.assimilate(observations)
    
    # 获取统计信息
    stats = localized_enkf.get_analysis_statistics()
    print("Localized EnKF Statistics:", stats)
    
    # 创建自适应EnKF
    adaptive_enkf = AdaptiveEnKF(ensemble_size=50, adaptive_inflation=True)
    
    adaptive_enkf.set_state_info(state_dim)
    adaptive_enkf.set_observation_info(obs_dim)
    adaptive_enkf.set_ensemble(ensemble_states, ensemble_obs)
    
    # 执行多次同化
    obs_errors = np.ones(obs_dim) * 0.5
    
    for i in range(10):
        observations = np.random.normal(0, 0.5, obs_dim)
        updated_states = adaptive_enkf.assimilate(observations, obs_errors)
        
    # 获取自适应统计信息
    adaptive_stats = adaptive_enkf.get_adaptive_statistics()
    print("Adaptive EnKF Statistics:", adaptive_stats)
    
    # 绘制演化图
    fig = adaptive_enkf.plot_adaptive_evolution()
    plt.show()


if __name__ == "__main__":
    example_usage()

