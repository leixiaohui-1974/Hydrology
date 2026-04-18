"""
观测系统设计模块
================

提供水文观测系统的设计功能，包括：
- 观测网络优化
- 观测策略设计
- 观测质量评估
- 观测成本效益分析
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional, Any, Callable, Union
from scipy import stats, optimize, spatial
from scipy.spatial.distance import cdist
import warnings
import logging
from pathlib import Path
import json
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp


class ObservationNetwork:
    """观测网络类"""
    
    def __init__(self, name: str, coordinates: np.ndarray, 
                 observation_types: List[str], costs: Optional[np.ndarray] = None):
        """
        初始化观测网络
        
        Args:
            name: 网络名称
            coordinates: 观测点坐标 (n_points, n_dims)
            observation_types: 观测类型列表
            costs: 观测成本
        """
        self.name = name
        self.coordinates = np.array(coordinates)
        self.observation_types = observation_types
        self.costs = costs if costs is not None else np.ones(len(coordinates))
        
        # 网络属性
        self.n_points = len(coordinates)
        self.n_types = len(observation_types)
        
        # 观测数据
        self.observations = {}
        self.observation_errors = {}
        
    def add_observation_data(self, obs_type: str, data: np.ndarray, errors: Optional[np.ndarray] = None):
        """添加观测数据"""
        if obs_type not in self.observation_types:
            raise ValueError(f"Unknown observation type: {obs_type}")
            
        if len(data) != self.n_points:
            raise ValueError(f"Data length mismatch: {len(data)} != {self.n_points}")
            
        self.observations[obs_type] = np.array(data)
        
        if errors is not None:
            if len(errors) != self.n_points:
                raise ValueError(f"Error length mismatch: {len(errors)} != {self.n_points}")
            self.observation_errors[obs_type] = np.array(errors)
        else:
            self.observation_errors[obs_type] = np.ones(self.n_points) * 0.1
            
    def get_network_coverage(self) -> Dict[str, float]:
        """计算网络覆盖度"""
        if self.coordinates.shape[1] < 2:
            return {'area_coverage': 0.0, 'point_density': 0.0}
            
        # 计算点密度
        point_density = self.n_points / 100.0  # 假设100点/单位面积为满分
        
        return {
            'area_coverage': 0.0,
            'point_density': point_density,
            'average_spacing': self._compute_average_spacing()
        }
        
    def _compute_average_spacing(self) -> float:
        """计算平均点间距"""
        if self.n_points < 2:
            return 0.0
            
        distances = cdist(self.coordinates, self.coordinates)
        distances = distances[distances > 0]
        
        if len(distances) == 0:
            return 0.0
            
        return np.mean(distances)
        
    def get_network_cost(self) -> Dict[str, float]:
        """计算网络成本"""
        total_cost = np.sum(self.costs)
        average_cost = np.mean(self.costs)
        
        return {
            'total_cost': total_cost,
            'average_cost': average_cost,
            'cost_per_point': total_cost / self.n_points
        }


class ObservationNetworkOptimizer:
    """观测网络优化器"""
    
    def __init__(self, objective_function: str = 'coverage_cost_ratio'):
        """初始化观测网络优化器"""
        self.objective_function = objective_function
        self.logger = logging.getLogger(__name__)
        
    def optimize_network(self, domain_bounds: Tuple[float, float, float, float],
                        n_points: int, observation_types: List[str]) -> ObservationNetwork:
        """优化观测网络"""
        self.logger.info(f"Starting network optimization for {n_points} points")
        
        # 简化的优化：随机生成并选择最优
        n_candidates = 10
        best_network = None
        best_score = float('-inf')
        
        for i in range(n_candidates):
            # 随机生成候选网络
            x_min, x_max, y_min, y_max = domain_bounds
            coordinates = np.random.uniform([x_min, y_min], [x_max, y_max], (n_points, 2))
            
            candidate_network = ObservationNetwork(
                name=f"Candidate_{i}",
                coordinates=coordinates,
                observation_types=observation_types
            )
            
            # 评估候选网络
            score = self._evaluate_network_score(candidate_network)
            
            if score > best_score:
                best_score = score
                best_network = candidate_network
                
        if best_network is None:
            # 创建默认网络
            x_min, x_max, y_min, y_max = domain_bounds
            coordinates = np.random.uniform([x_min, y_min], [x_max, y_max], (n_points, 2))
            best_network = ObservationNetwork(
                name="Default_Network",
                coordinates=coordinates,
                observation_types=observation_types
            )
            
        best_network.name = "Optimized_Network"
        return best_network
        
    def _evaluate_network_score(self, network: ObservationNetwork) -> float:
        """评估网络得分"""
        if self.objective_function == 'coverage_cost_ratio':
            coverage = network.get_network_coverage()['point_density']
            cost = network.get_network_cost()['total_cost']
            return coverage / max(cost, 1e-6)
        else:
            return 0.0


class ObservationStrategyDesigner:
    """观测策略设计器"""
    
    def __init__(self):
        """初始化观测策略设计器"""
        self.strategies = {}
        
    def design_adaptive_strategy(self, network: ObservationNetwork,
                                forecast_horizon: int,
                                uncertainty_threshold: float = 0.5) -> Dict[str, Any]:
        """设计自适应观测策略"""
        strategy = {
            'type': 'adaptive',
            'forecast_horizon': forecast_horizon,
            'uncertainty_threshold': uncertainty_threshold,
            'observation_schedule': [],
            'priority_points': []
        }
        
        # 基于不确定性的自适应观测
        if network.observations:
            priorities = self._compute_observation_priorities(network)
            strategy['priority_points'] = priorities
            
            schedule = self._generate_observation_schedule(
                network, forecast_horizon, priorities
            )
            strategy['observation_schedule'] = schedule
            
        return strategy
        
    def _compute_observation_priorities(self, network: ObservationNetwork) -> List[int]:
        """计算观测优先级"""
        priorities = []
        
        for i in range(network.n_points):
            priority_score = 0.0
            
            # 基于观测误差的优先级
            for obs_type in network.observation_types:
                if obs_type in network.observation_errors:
                    error = network.observation_errors[obs_type][i]
                    priority_score += 1.0 / (1.0 + error)
                    
            priorities.append(priority_score)
            
        # 归一化优先级
        priorities = np.array(priorities)
        if np.max(priorities) > np.min(priorities):
            priorities = (priorities - np.min(priorities)) / (np.max(priorities) - np.min(priorities))
        
        return priorities.tolist()
        
    def _generate_observation_schedule(self, network: ObservationNetwork,
                                     forecast_horizon: int,
                                     priorities: List[float]) -> List[Dict[str, Any]]:
        """生成观测时间表"""
        schedule = []
        
        for t in range(forecast_horizon):
            selected_points = self._select_observation_points(
                network, priorities, max_points=min(10, network.n_points)
            )
            
            schedule.append({
                'time_step': t,
                'selected_points': selected_points,
                'observation_types': network.observation_types
            })
            
        return schedule
        
    def _select_observation_points(self, network: ObservationNetwork,
                                 priorities: List[float],
                                 max_points: int) -> List[int]:
        """选择观测点"""
        point_scores = []
        
        for i in range(network.n_points):
            priority = priorities[i]
            cost = network.costs[i]
            score = priority / (1.0 + cost)
            point_scores.append((i, score))
            
        point_scores.sort(key=lambda x: x[1], reverse=True)
        selected = [point_scores[i][0] for i in range(min(max_points, len(point_scores)))]
        
        return selected


class ObservationQualityEvaluator:
    """观测质量评估器"""
    
    def __init__(self):
        """初始化观测质量评估器"""
        self.evaluation_metrics = {}
        
    def evaluate_network_quality(self, network: ObservationNetwork) -> Dict[str, Any]:
        """评估观测网络质量"""
        quality_results = {
            'network_name': network.name,
            'spatial_coverage': self._evaluate_spatial_coverage(network),
            'data_quality': self._evaluate_data_quality(network),
            'cost_efficiency': self._evaluate_cost_efficiency(network),
            'overall_score': 0.0
        }
        
        # 计算综合质量分数
        scores = [
            quality_results['spatial_coverage']['score'],
            quality_results['data_quality']['score'],
            quality_results['cost_efficiency']['score']
        ]
        
        quality_results['overall_score'] = np.mean(scores)
        
        return quality_results
        
    def _evaluate_spatial_coverage(self, network: ObservationNetwork) -> Dict[str, Any]:
        """评估空间覆盖度"""
        coverage_info = network.get_network_coverage()
        point_density = coverage_info['point_density']
        avg_spacing = coverage_info['average_spacing']
        
        density_score = min(1.0, point_density)
        spacing_score = max(0.0, 1.0 - avg_spacing / 100.0)
        
        spatial_score = (density_score + spacing_score) / 2.0
        
        return {
            'score': spatial_score,
            'point_density': point_density,
            'average_spacing': avg_spacing
        }
        
    def _evaluate_data_quality(self, network: ObservationNetwork) -> Dict[str, Any]:
        """评估数据质量"""
        if not network.observations:
            return {'score': 0.0, 'mean_error': 0.0}
            
        all_errors = []
        
        for obs_type in network.observation_types:
            if obs_type in network.observation_errors:
                errors = network.observation_errors[obs_type]
                all_errors.extend(errors)
                
        if not all_errors:
            return {'score': 0.0, 'mean_error': 0.0}
            
        all_errors = np.array(all_errors)
        mean_error = np.mean(all_errors)
        error_score = max(0.0, 1.0 - mean_error)
        
        return {
            'score': error_score,
            'mean_error': mean_error
        }
        
    def _evaluate_cost_efficiency(self, network: ObservationNetwork) -> Dict[str, Any]:
        """评估成本效益"""
        cost_info = network.get_network_cost()
        coverage_info = network.get_network_coverage()
        
        total_cost = cost_info['total_cost']
        coverage_area = coverage_info['point_density']
        
        if total_cost > 0 and coverage_area > 0:
            cost_efficiency = coverage_area / total_cost
        else:
            cost_efficiency = 0.0
            
        efficiency_score = min(1.0, cost_efficiency / 10.0)
        
        return {
            'score': efficiency_score,
            'total_cost': total_cost,
            'cost_efficiency': cost_efficiency
        }


def example_usage():
    """示例用法"""
    
    # 创建示例观测网络
    np.random.seed(42)
    
    n_points = 20
    coordinates = np.random.uniform(0, 100, (n_points, 2))
    observation_types = ['rainfall', 'water_level', 'flow_rate']
    
    network = ObservationNetwork(
        name="Example_Network",
        coordinates=coordinates,
        observation_types=observation_types
    )
    
    # 添加观测数据
    for obs_type in observation_types:
        data = np.random.normal(0, 1, n_points)
        errors = np.random.uniform(0.1, 0.5, n_points)
        network.add_observation_data(obs_type, data, errors)
        
    # 评估网络质量
    evaluator = ObservationQualityEvaluator()
    quality_results = evaluator.evaluate_network_quality(network)
    
    print("Network Quality Assessment:")
    print(f"  Overall Score: {quality_results['overall_score']:.3f}")
    print(f"  Spatial Coverage: {quality_results['spatial_coverage']['score']:.3f}")
    print(f"  Data Quality: {quality_results['data_quality']['score']:.3f}")
    print(f"  Cost Efficiency: {quality_results['cost_efficiency']['score']:.3f}")
    
    # 网络优化
    optimizer = ObservationNetworkOptimizer()
    domain_bounds = (0, 100, 0, 100)
    optimal_network = optimizer.optimize_network(
        domain_bounds, n_points, observation_types
    )
    
    print(f"\nOptimized network created with {optimal_network.n_points} points")
    
    # 观测策略设计
    strategy_designer = ObservationStrategyDesigner()
    strategy = strategy_designer.design_adaptive_strategy(
        network, forecast_horizon=24, uncertainty_threshold=0.5
    )
    
    print(f"\nObservation strategy designed:")
    print(f"  Type: {strategy['type']}")
    print(f"  Forecast horizon: {strategy['forecast_horizon']}")
    print(f"  Priority points: {len(strategy['priority_points'])}")
    print(f"  Schedule length: {len(strategy['observation_schedule'])}")


if __name__ == "__main__":
    example_usage()
