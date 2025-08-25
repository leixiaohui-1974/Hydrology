"""
粒子滤波实现
============

提供多种粒子滤波算法，包括：
- 标准粒子滤波 (Standard Particle Filter)
- 辅助粒子滤波 (Auxiliary Particle Filter)
- 正则化粒子滤波 (Regularized Particle Filter)
- 自适应重采样策略
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional, Any, Callable
from scipy import stats
from scipy.stats import multivariate_normal
import warnings
import logging
from pathlib import Path
import json
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp


class ParticleFilter:
    """
    标准粒子滤波
    
    实现基本的粒子滤波算法，包括预测、更新和重采样步骤
    """
    
    def __init__(self, n_particles: int = 1000, resampling_method: str = 'systematic',
                 effective_size_threshold: float = 0.5, n_workers: int = None):
        """
        初始化粒子滤波
        
        Args:
            n_particles: 粒子数量
            resampling_method: 重采样方法 ('systematic', 'multinomial', 'stratified')
            effective_size_threshold: 有效粒子大小阈值
            n_workers: 并行工作进程数
        """
        self.n_particles = n_particles
        self.resampling_method = resampling_method
        self.effective_size_threshold = effective_size_threshold
        self.n_workers = n_workers or min(mp.cpu_count(), 8)
        
        # 粒子状态和权重
        self.particles = None
        self.weights = None
        
        # 历史记录
        self.particle_history = []
        self.weight_history = []
        self.effective_size_history = []
        
        # 模型和观测函数
        self.transition_model = None
        self.observation_model = None
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
    def set_transition_model(self, transition_func: Callable):
        """
        设置状态转移模型
        
        Args:
            transition_func: 状态转移函数 f(x_t) -> x_{t+1}
        """
        self.transition_model = transition_func
        self.logger.info("Transition model set")
        
    def set_observation_model(self, observation_func: Callable):
        """
        设置观测模型
        
        Args:
            observation_func: 观测函数 h(x_t) -> y_t
        """
        self.observation_model = observation_func
        self.logger.info("Observation model set")
        
    def initialize_particles(self, initial_distribution: Callable, **kwargs):
        """
        初始化粒子
        
        Args:
            initial_distribution: 初始分布函数
            **kwargs: 传递给初始分布函数的参数
        """
        self.particles = initial_distribution(self.n_particles, **kwargs)
        self.weights = np.ones(self.n_particles) / self.n_particles
        
        self.logger.info(f"Initialized {self.n_particles} particles")
        
    def predict(self, control_input: Optional[np.ndarray] = None):
        """
        预测步骤
        
        Args:
            control_input: 控制输入
        """
        if self.transition_model is None:
            raise ValueError("Transition model not set")
            
        if self.particles is None:
            raise ValueError("Particles not initialized")
            
        # 应用状态转移模型
        if control_input is not None:
            self.particles = self.transition_model(self.particles, control_input)
        else:
            self.particles = self.transition_model(self.particles)
            
        # 添加过程噪声（如果需要）
        # self.particles += np.random.normal(0, process_noise_std, self.particles.shape)
        
        self.logger.debug("Prediction step completed")
        
    def update(self, observation: np.ndarray, observation_noise_std: float = 1.0):
        """
        更新步骤
        
        Args:
            observation: 观测值
            observation_noise_std: 观测噪声标准差
        """
        if self.observation_model is None:
            raise ValueError("Observation model not set")
            
        if self.particles is None:
            raise ValueError("Particles not initialized")
            
        # 计算观测似然
        predicted_obs = self.observation_model(self.particles)
        
        # 计算似然权重
        likelihoods = self._compute_likelihood(observation, predicted_obs, observation_noise_std)
        
        # 更新权重
        self.weights *= likelihoods
        self.weights += 1e-300  # 避免数值下溢
        
        # 归一化权重
        self.weights /= np.sum(self.weights)
        
        self.logger.debug("Update step completed")
        
    def _compute_likelihood(self, observation: np.ndarray, predicted_obs: np.ndarray, 
                           noise_std: float) -> np.ndarray:
        """
        计算似然函数
        
        Args:
            observation: 真实观测
            predicted_obs: 预测观测
            noise_std: 噪声标准差
            
        Returns:
            似然值数组
        """
        # 假设观测噪声服从高斯分布
        residuals = observation - predicted_obs
        likelihoods = np.exp(-0.5 * (residuals / noise_std)**2) / (noise_std * np.sqrt(2 * np.pi))
        
        # 对于多维观测，计算联合似然
        if len(likelihoods.shape) > 1:
            likelihoods = np.prod(likelihoods, axis=1)
            
        return likelihoods
        
    def resample(self):
        """重采样步骤"""
        if self.particles is None:
            raise ValueError("Particles not initialized")
            
        # 检查是否需要重采样
        effective_size = self._compute_effective_size()
        self.effective_size_history.append(effective_size)
        
        if effective_size < self.effective_size_threshold * self.n_particles:
            self.logger.info(f"Resampling triggered. Effective size: {effective_size:.1f}")
            
            # 执行重采样
            if self.resampling_method == 'systematic':
                indices = self._systematic_resampling()
            elif self.resampling_method == 'multinomial':
                indices = self._multinomial_resampling()
            elif self.resampling_method == 'stratified':
                indices = self._stratified_resampling()
            else:
                raise ValueError(f"Unknown resampling method: {self.resampling_method}")
                
            # 更新粒子和权重
            self.particles = self.particles[indices]
            self.weights = np.ones(self.n_particles) / self.n_particles
            
            self.logger.info("Resampling completed")
        else:
            self.logger.debug(f"No resampling needed. Effective size: {effective_size:.1f}")
            
    def _compute_effective_size(self) -> float:
        """计算有效粒子大小"""
        return 1.0 / np.sum(self.weights**2)
        
    def _systematic_resampling(self) -> np.ndarray:
        """系统重采样"""
        cumsum_weights = np.cumsum(self.weights)
        positions = (np.random.random() + np.arange(self.n_particles)) / self.n_particles
        
        indices = np.searchsorted(cumsum_weights, positions)
        indices = np.clip(indices, 0, self.n_particles - 1)
        
        return indices
        
    def _multinomial_resampling(self) -> np.ndarray:
        """多项式重采样"""
        indices = np.random.choice(self.n_particles, size=self.n_particles, p=self.weights)
        return indices
        
    def _stratified_resampling(self) -> np.ndarray:
        """分层重采样"""
        positions = (np.random.random(self.n_particles) + np.arange(self.n_particles)) / self.n_particles
        cumsum_weights = np.cumsum(self.weights)
        
        indices = np.searchsorted(cumsum_weights, positions)
        indices = np.clip(indices, 0, self.n_particles - 1)
        
        return indices
        
    def step(self, observation: np.ndarray, control_input: Optional[np.ndarray] = None,
             observation_noise_std: float = 1.0):
        """
        执行一个完整的滤波步骤
        
        Args:
            observation: 观测值
            control_input: 控制输入
            observation_noise_std: 观测噪声标准差
        """
        # 预测
        self.predict(control_input)
        
        # 更新
        self.update(observation, observation_noise_std)
        
        # 重采样
        self.resample()
        
        # 记录历史
        self.particle_history.append(self.particles.copy())
        self.weight_history.append(self.weights.copy())
        
    def get_state_estimate(self) -> Dict[str, np.ndarray]:
        """
        获取状态估计
        
        Returns:
            包含均值、方差等统计量的字典
        """
        if self.particles is None:
            return {}
            
        # 加权平均
        mean = np.average(self.particles, axis=0, weights=self.weights)
        
        # 加权方差
        variance = np.average((self.particles - mean)**2, axis=0, weights=self.weights)
        
        # 有效粒子大小
        effective_size = self._compute_effective_size()
        
        return {
            'mean': mean,
            'variance': variance,
            'std': np.sqrt(variance),
            'effective_size': effective_size,
            'particles': self.particles.copy(),
            'weights': self.weights.copy()
        }
        
    def get_filter_statistics(self) -> Dict[str, Any]:
        """获取滤波统计信息"""
        stats = {
            'n_particles': self.n_particles,
            'resampling_method': self.resampling_method,
            'effective_size_threshold': self.effective_size_threshold
        }
        
        # 历史统计
        if self.effective_size_history:
            stats['effective_size_history'] = self.effective_size_history
            stats['effective_size_mean'] = np.mean(self.effective_size_history)
            stats['effective_size_min'] = np.min(self.effective_size_history)
            
        return stats


class AuxiliaryParticleFilter(ParticleFilter):
    """
    辅助粒子滤波
    
    通过引入辅助变量提高粒子滤波的性能
    """
    
    def __init__(self, n_particles: int = 1000, resampling_method: str = 'systematic',
                 effective_size_threshold: float = 0.5, n_workers: int = None):
        super().__init__(n_particles, resampling_method, effective_size_threshold, n_workers)
        
        # 辅助粒子
        self.auxiliary_particles = None
        self.auxiliary_weights = None
        
    def update(self, observation: np.ndarray, observation_noise_std: float = 1.0):
        """
        辅助粒子滤波的更新步骤
        
        Args:
            observation: 观测值
            observation_noise_std: 观测噪声标准差
        """
        if self.observation_model is None:
            raise ValueError("Observation model not set")
            
        if self.particles is None:
            raise ValueError("Particles not initialized")
            
        # 计算辅助权重（基于预测观测）
        predicted_obs = self.observation_model(self.particles)
        auxiliary_weights = self._compute_likelihood(observation, predicted_obs, observation_noise_std)
        
        # 归一化辅助权重
        auxiliary_weights *= self.weights
        auxiliary_weights /= np.sum(auxiliary_weights)
        
        # 基于辅助权重重采样
        indices = self._systematic_resampling()
        self.particles = self.particles[indices]
        self.weights = np.ones(self.n_particles) / self.n_particles
        
        # 计算新的似然权重
        new_predicted_obs = self.observation_model(self.particles)
        new_likelihoods = self._compute_likelihood(observation, new_predicted_obs, observation_noise_std)
        
        # 更新权重
        self.weights *= new_likelihoods
        self.weights += 1e-300
        self.weights /= np.sum(self.weights)
        
        self.logger.debug("Auxiliary particle filter update completed")


class RegularizedParticleFilter(ParticleFilter):
    """
    正则化粒子滤波
    
    通过核密度估计和正则化提高粒子滤波的性能
    """
    
    def __init__(self, n_particles: int = 1000, resampling_method: str = 'systematic',
                 effective_size_threshold: float = 0.5, bandwidth_method: str = 'silverman',
                 n_workers: int = None):
        super().__init__(n_particles, resampling_method, effective_size_threshold, n_workers)
        
        self.bandwidth_method = bandwidth_method
        
    def resample(self):
        """正则化重采样"""
        if self.particles is None:
            raise ValueError("Particles not initialized")
            
        # 检查是否需要重采样
        effective_size = self._compute_effective_size()
        self.effective_size_history.append(effective_size)
        
        if effective_size < self.effective_size_threshold * self.n_particles:
            self.logger.info(f"Regularized resampling triggered. Effective size: {effective_size:.1f}")
            
            # 执行重采样
            indices = self._systematic_resampling()
            
            # 正则化：添加小的随机扰动
            self.particles = self.particles[indices]
            
            # 计算带宽
            bandwidth = self._compute_bandwidth()
            
            # 添加正则化噪声
            regularization_noise = np.random.normal(0, bandwidth, self.particles.shape)
            self.particles += regularization_noise
            
            # 更新权重
            self.weights = np.ones(self.n_particles) / self.n_particles
            
            self.logger.info("Regularized resampling completed")
        else:
            self.logger.debug(f"No resampling needed. Effective size: {effective_size:.1f}")
            
    def _compute_bandwidth(self) -> float:
        """计算核密度估计的带宽"""
        if self.particles is None:
            return 1.0
            
        # 使用Silverman规则
        if self.bandwidth_method == 'silverman':
            n, d = self.particles.shape
            sigma = np.std(self.particles, axis=0)
            bandwidth = sigma * (n * (d + 2) / 4.)**(-1. / (d + 4))
            return np.mean(bandwidth)
        else:
            # 简单方法：基于粒子间距离
            return np.std(self.particles) * 0.1


def example_usage():
    """示例用法"""
    
    # 定义简单的状态转移模型
    def transition_model(particles, control=None):
        """线性状态转移模型"""
        if control is None:
            control = 0
        return 0.8 * particles + 0.1 + np.random.normal(0, 0.1, particles.shape)
        
    # 定义观测模型
    def observation_model(particles):
        """线性观测模型"""
        return particles + np.random.normal(0, 0.2, particles.shape)
        
    # 初始分布
    def initial_distribution(n_particles, **kwargs):
        """初始分布"""
        return np.random.normal(0, 1, (n_particles, 1))
        
    # 创建标准粒子滤波
    pf = ParticleFilter(n_particles=500)
    pf.set_transition_model(transition_model)
    pf.set_observation_model(observation_model)
    pf.initialize_particles(initial_distribution)
    
    # 模拟数据
    true_states = []
    observations = []
    
    # 真实状态演化
    x = 0.0
    for t in range(50):
        x = 0.8 * x + 0.1 + np.random.normal(0, 0.1)
        y = x + np.random.normal(0, 0.2)
        
        true_states.append(x)
        observations.append(y)
        
    # 运行粒子滤波
    estimated_states = []
    
    for t in range(50):
        pf.step(observations[t])
        estimate = pf.get_state_estimate()
        estimated_states.append(estimate['mean'][0])
        
    # 绘制结果
    plt.figure(figsize=(12, 8))
    
    plt.subplot(2, 1, 1)
    plt.plot(true_states, 'b-', label='True State', linewidth=2)
    plt.plot(estimated_states, 'r--', label='Particle Filter Estimate', linewidth=2)
    plt.plot(observations, 'g.', label='Observations', alpha=0.6)
    plt.xlabel('Time Step')
    plt.ylabel('State')
    plt.title('Particle Filter Tracking')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.subplot(2, 1, 2)
    plt.plot(pf.effective_size_history, 'b-', linewidth=2)
    plt.axhline(y=pf.effective_size_threshold * pf.n_particles, color='r', linestyle='--', 
                label='Resampling Threshold')
    plt.xlabel('Time Step')
    plt.ylabel('Effective Sample Size')
    plt.title('Effective Sample Size Evolution')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()
    
    # 创建辅助粒子滤波
    apf = AuxiliaryParticleFilter(n_particles=500)
    apf.set_transition_model(transition_model)
    apf.set_observation_model(observation_model)
    apf.initialize_particles(initial_distribution)
    
    # 运行辅助粒子滤波
    apf_estimated_states = []
    
    for t in range(50):
        apf.step(observations[t])
        estimate = apf.get_state_estimate()
        apf_estimated_states.append(estimate['mean'][0])
        
    # 比较性能
    pf_mse = np.mean((np.array(estimated_states) - np.array(true_states))**2)
    apf_mse = np.mean((np.array(apf_estimated_states) - np.array(true_states))**2)
    
    print(f"Standard PF MSE: {pf_mse:.4f}")
    print(f"Auxiliary PF MSE: {apf_mse:.4f}")
    
    # 创建正则化粒子滤波
    rpf = RegularizedParticleFilter(n_particles=500)
    rpf.set_transition_model(transition_model)
    rpf.set_observation_model(observation_model)
    rpf.initialize_particles(initial_distribution)
    
    # 运行正则化粒子滤波
    rpf_estimated_states = []
    
    for t in range(50):
        rpf.step(observations[t])
        estimate = rpf.get_state_estimate()
        rpf_estimated_states.append(estimate['mean'][0])
        
    rpf_mse = np.mean((np.array(rpf_estimated_states) - np.array(true_states))**2)
    print(f"Regularized PF MSE: {rpf_mse:.4f}")


if __name__ == "__main__":
    example_usage()
