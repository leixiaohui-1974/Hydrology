"""
多源数据融合系统
================

提供多源水文数据的融合功能，包括：
- 多源数据融合算法
- 数据质量评估
- 融合策略选择
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
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from datetime import datetime, timedelta


class DataSource:
    """数据源类"""
    
    def __init__(self, name: str, data: np.ndarray, coordinates: np.ndarray,
                 timestamps: Optional[np.ndarray] = None, quality_scores: Optional[np.ndarray] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        """
        初始化数据源
        
        Args:
            name: 数据源名称
            data: 数据值
            coordinates: 空间坐标 (n_points, n_dims)
            timestamps: 时间戳
            quality_scores: 质量分数
            metadata: 元数据
        """
        self.name = name
        self.data = np.array(data)
        self.coordinates = np.array(coordinates)
        self.timestamps = timestamps
        self.quality_scores = quality_scores
        self.metadata = metadata or {}
        
        # 数据维度
        self.n_points = self.data.shape[0]
        self.n_timesteps = self.data.shape[1] if len(self.data.shape) > 1 else 1
        
        # 验证数据一致性
        self._validate_data()
        
    def _validate_data(self):
        """验证数据一致性"""
        if self.coordinates.shape[0] != self.n_points:
            raise ValueError(f"Coordinate dimension mismatch: {self.coordinates.shape[0]} != {self.n_points}")
            
        if self.quality_scores is not None and self.quality_scores.shape[0] != self.n_points:
            raise ValueError(f"Quality score dimension mismatch: {self.quality_scores.shape[0]} != {self.n_points}")
            
    def get_data_at_time(self, time_index: int) -> np.ndarray:
        """获取指定时间的数据"""
        if self.n_timesteps == 1:
            return self.data
        else:
            return self.data[:, time_index]
            
    def get_quality_at_time(self, time_index: int) -> Optional[np.ndarray]:
        """获取指定时间的质量分数"""
        if self.quality_scores is None:
            return None
        if self.n_timesteps == 1:
            return self.quality_scores
        else:
            return self.quality_scores[:, time_index]


class DataQualityAssessor:
    """数据质量评估器"""
    
    def __init__(self):
        """初始化数据质量评估器"""
        self.quality_metrics = {}
        
    def assess_data_quality(self, data_source: DataSource) -> Dict[str, Any]:
        """
        评估数据质量
        
        Args:
            data_source: 数据源
            
        Returns:
            质量评估结果
        """
        quality_results = {
            'source_name': data_source.name,
            'completeness': self._assess_completeness(data_source),
            'consistency': self._assess_consistency(data_source),
            'accuracy': self._assess_accuracy(data_source),
            'spatial_coverage': self._assess_spatial_coverage(data_source),
            'temporal_coverage': self._assess_temporal_coverage(data_source),
            'overall_score': 0.0
        }
        
        # 计算综合质量分数
        scores = [
            quality_results['completeness']['score'],
            quality_results['consistency']['score'],
            quality_results['accuracy']['score'],
            quality_results['spatial_coverage']['score'],
            quality_results['temporal_coverage']['score']
        ]
        
        quality_results['overall_score'] = np.mean(scores)
        
        return quality_results
        
    def _assess_completeness(self, data_source: DataSource) -> Dict[str, Any]:
        """评估数据完整性"""
        if data_source.n_timesteps == 1:
            missing_ratio = np.sum(np.isnan(data_source.data)) / data_source.data.size
            completeness_score = 1.0 - missing_ratio
        else:
            missing_ratio = np.sum(np.isnan(data_source.data)) / data_source.data.size
            completeness_score = 1.0 - missing_ratio
            
        return {
            'score': completeness_score,
            'missing_ratio': missing_ratio,
            'available_points': np.sum(~np.isnan(data_source.data))
        }
        
    def _assess_consistency(self, data_source: DataSource) -> Dict[str, Any]:
        """评估数据一致性"""
        if data_source.n_timesteps == 1:
            data = data_source.get_data_at_time(0)
            valid_data = data[~np.isnan(data)]
            
            if len(valid_data) < 2:
                return {'score': 0.0, 'std': 0.0, 'cv': 0.0}
                
            std = np.std(valid_data)
            mean = np.mean(valid_data)
            cv = std / mean if mean != 0 else 0
            
            consistency_score = max(0, 1.0 - cv)
        else:
            consistency_scores = []
            for t in range(data_source.n_timesteps):
                data = data_source.get_data_at_time(t)
                valid_data = data[~np.isnan(data)]
                
                if len(valid_data) >= 2:
                    std = np.std(valid_data)
                    mean = np.mean(valid_data)
                    cv = std / mean if mean != 0 else 0
                    consistency_scores.append(max(0, 1.0 - cv))
                    
            consistency_score = np.mean(consistency_scores) if consistency_scores else 0.0
            
        return {
            'score': consistency_score,
            'std': std if 'std' in locals() else 0.0,
            'cv': cv if 'cv' in locals() else 0.0
        }
        
    def _assess_accuracy(self, data_source: DataSource) -> Dict[str, Any]:
        """评估数据准确性（基于质量分数）"""
        if data_source.quality_scores is None:
            return {'score': 0.5, 'mean_quality': 0.5, 'quality_std': 0.0}
            
        quality_scores = data_source.quality_scores.flatten()
        valid_quality = quality_scores[~np.isnan(quality_scores)]
        
        if len(valid_quality) == 0:
            return {'score': 0.0, 'mean_quality': 0.0, 'quality_std': 0.0}
            
        mean_quality = np.mean(valid_quality)
        quality_std = np.std(valid_quality)
        
        return {
            'score': mean_quality,
            'mean_quality': mean_quality,
            'quality_std': quality_std
        }
        
    def _assess_spatial_coverage(self, data_source: DataSource) -> Dict[str, Any]:
        """评估空间覆盖度"""
        if data_source.coordinates.shape[1] < 2:
            return {'score': 1.0, 'coverage_area': 0.0, 'point_density': 0.0}
            
        # 计算点密度
        point_density = data_source.n_points / 100.0  # 假设100点/单位面积为满分
        
        coverage_score = min(1.0, point_density)
        
        return {
            'score': coverage_score,
            'coverage_area': 0.0,
            'point_density': point_density
        }
        
    def _assess_temporal_coverage(self, data_source: DataSource) -> Dict[str, Any]:
        """评估时间覆盖度"""
        if data_source.n_timesteps == 1:
            return {'score': 1.0, 'temporal_span': 0.0, 'sampling_rate': 0.0}
            
        if data_source.timestamps is None:
            return {'score': 0.5, 'temporal_span': 0.0, 'sampling_rate': 0.0}
            
        # 计算采样率
        sampling_rate = data_source.n_timesteps / 100.0  # 假设100时间步为满分
        
        temporal_score = min(1.0, sampling_rate)
        
        return {
            'score': temporal_score,
            'temporal_span': 0.0,
            'sampling_rate': sampling_rate
        }


class MultiSourceDataFusion:
    """多源数据融合系统"""
    
    def __init__(self, fusion_method: str = 'weighted_average', 
                 quality_weighted: bool = True, spatial_interpolation: bool = True):
        """
        初始化多源数据融合系统
        
        Args:
            fusion_method: 融合方法 ('weighted_average', 'kriging', 'inverse_distance')
            quality_weighted: 是否基于质量分数加权
            spatial_interpolation: 是否进行空间插值
        """
        self.fusion_method = fusion_method
        self.quality_weighted = quality_weighted
        self.spatial_interpolation = spatial_interpolation
        
        # 数据源和质量评估器
        self.data_sources = []
        self.quality_assessor = DataQualityAssessor()
        
        # 融合结果
        self.fused_data = None
        self.fusion_weights = None
        self.fusion_uncertainty = None
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
    def add_data_source(self, data_source: DataSource):
        """添加数据源"""
        self.data_sources.append(data_source)
        self.logger.info(f"Added data source: {data_source.name}")
        
    def remove_data_source(self, source_name: str):
        """移除数据源"""
        self.data_sources = [ds for ds in self.data_sources if ds.name != source_name]
        self.logger.info(f"Removed data source: {source_name}")
        
    def assess_all_sources(self) -> Dict[str, Dict[str, Any]]:
        """评估所有数据源的质量"""
        quality_results = {}
        
        for data_source in self.data_sources:
            quality_results[data_source.name] = self.quality_assessor.assess_data_quality(data_source)
            
        return quality_results
        
    def fuse_data(self, target_coordinates: np.ndarray, time_index: int = 0,
                  fusion_parameters: Optional[Dict[str, Any]] = None) -> Dict[str, np.ndarray]:
        """
        融合多源数据
        
        Args:
            target_coordinates: 目标坐标点
            time_index: 时间索引
            fusion_parameters: 融合参数
            
        Returns:
            融合结果字典
        """
        if not self.data_sources:
            raise ValueError("No data sources available for fusion")
            
        self.logger.info(f"Starting data fusion with {len(self.data_sources)} sources")
        start_time = time.time()
        
        # 评估数据质量
        quality_results = self.assess_all_sources()
        
        # 执行融合
        if self.fusion_method == 'weighted_average':
            fused_result = self._weighted_average_fusion(target_coordinates, time_index, quality_results)
        elif self.fusion_method == 'inverse_distance':
            fused_result = self._inverse_distance_fusion(target_coordinates, time_index, quality_results)
        else:
            raise ValueError(f"Unknown fusion method: {self.fusion_method}")
            
        # 计算融合不确定性
        fused_result['uncertainty'] = self._compute_fusion_uncertainty(
            target_coordinates, time_index, quality_results
        )
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"Data fusion completed in {elapsed_time:.2f}s")
        
        # 保存结果
        self.fused_data = fused_result['data']
        self.fusion_weights = fused_result['weights']
        self.fusion_uncertainty = fused_result['uncertainty']
        
        return fused_result
        
    def _weighted_average_fusion(self, target_coordinates: np.ndarray, time_index: int,
                                quality_results: Dict[str, Dict[str, Any]]) -> Dict[str, np.ndarray]:
        """加权平均融合"""
        n_targets = target_coordinates.shape[0]
        fused_data = np.full(n_targets, np.nan)
        fusion_weights = np.zeros((n_targets, len(self.data_sources)))
        
        for i, target_coord in enumerate(target_coordinates):
            valid_sources = []
            source_weights = []
            
            for j, data_source in enumerate(self.data_sources):
                # 找到最近的数据点
                distances = cdist([target_coord], data_source.coordinates)[0]
                nearest_idx = np.argmin(distances)
                nearest_distance = distances[nearest_idx]
                
                # 检查距离阈值
                if nearest_distance > 100.0:  # 假设100单位距离阈值
                    continue
                    
                # 获取数据值
                data_value = data_source.get_data_at_time(time_index)[nearest_idx]
                
                if np.isnan(data_value):
                    continue
                    
                # 计算权重
                if self.quality_weighted:
                    quality_score = quality_results[data_source.name]['overall_score']
                    distance_weight = 1.0 / (1.0 + nearest_distance)
                    weight = quality_score * distance_weight
                else:
                    weight = 1.0 / (1.0 + nearest_distance)
                    
                valid_sources.append(data_value)
                source_weights.append(weight)
                
            if valid_sources:
                # 归一化权重
                source_weights = np.array(source_weights)
                source_weights /= np.sum(source_weights)
                
                # 加权平均
                fused_data[i] = np.average(valid_sources, weights=source_weights)
                
                # 记录权重
                for j, data_source in enumerate(self.data_sources):
                    if j < len(source_weights):
                        fusion_weights[i, j] = source_weights[j]
                        
        return {
            'data': fused_data,
            'weights': fusion_weights,
            'method': 'weighted_average'
        }
        
    def _inverse_distance_fusion(self, target_coordinates: np.ndarray, time_index: int,
                                quality_results: Dict[str, Dict[str, Any]]) -> Dict[str, np.ndarray]:
        """反距离加权融合"""
        n_targets = target_coordinates.shape[0]
        fused_data = np.full(n_targets, np.nan)
        fusion_weights = np.zeros((n_targets, len(self.data_sources)))
        
        for i, target_coord in enumerate(target_coordinates):
            valid_sources = []
            source_weights = []
            
            for j, data_source in enumerate(self.data_sources):
                data_values = data_source.get_data_at_time(time_index)
                valid_mask = ~np.isnan(data_values)
                
                if np.any(valid_mask):
                    coords = data_source.coordinates[valid_mask]
                    values = data_values[valid_mask]
                    
                    # 计算距离
                    distances = cdist([target_coord], coords)[0]
                    
                    # 反距离加权
                    for k, (coord, value, distance) in enumerate(zip(coords, values, distances)):
                        if distance < 1e-6:  # 避免除零
                            distance = 1e-6
                            
                        # 计算权重
                        if self.quality_weighted:
                            quality_score = quality_results[data_source.name]['overall_score']
                            weight = quality_score / (distance ** 2)
                        else:
                            weight = 1.0 / (distance ** 2)
                            
                        valid_sources.append(value)
                        source_weights.append(weight)
                        
            if valid_sources:
                # 归一化权重
                source_weights = np.array(source_weights)
                source_weights /= np.sum(source_weights)
                
                # 加权平均
                fused_data[i] = np.average(valid_sources, weights=source_weights)
                
        return {
            'data': fused_data,
            'weights': fusion_weights,
            'method': 'inverse_distance'
        }
        
    def _compute_fusion_uncertainty(self, target_coordinates: np.ndarray, time_index: int,
                                   quality_results: Dict[str, Dict[str, Any]]) -> np.ndarray:
        """计算融合不确定性"""
        n_targets = target_coordinates.shape[0]
        uncertainty = np.full(n_targets, np.nan)
        
        for i, target_coord in enumerate(target_coordinates):
            uncertainties = []
            weights = []
            
            for data_source in self.data_sources:
                data_values = data_source.get_data_at_time(time_index)
                valid_mask = ~np.isnan(data_values)
                
                if np.any(valid_mask):
                    coords = data_source.coordinates[valid_mask]
                    values = data_values[valid_mask]
                    
                    # 找到最近的点
                    distances = cdist([target_coord], coords)[0]
                    nearest_idx = np.argmin(distances)
                    nearest_distance = distances[nearest_idx]
                    
                    if nearest_distance <= 100.0:  # 距离阈值
                        # 基于质量分数和距离的不确定性
                        quality_score = quality_results[data_source.name]['overall_score']
                        distance_factor = 1.0 / (1.0 + nearest_distance / 100.0)
                        
                        # 假设不确定性与质量分数和距离相关
                        uncertainty_val = (1.0 - quality_score) * distance_factor
                        weight = quality_score * distance_factor
                        
                        uncertainties.append(uncertainty_val)
                        weights.append(weight)
                        
            if uncertainties:
                # 加权平均不确定性
                weights = np.array(weights)
                weights /= np.sum(weights)
                uncertainty[i] = np.average(uncertainties, weights=weights)
                
        return uncertainty
        
    def get_fusion_statistics(self) -> Dict[str, Any]:
        """获取融合统计信息"""
        stats = {
            'n_sources': len(self.data_sources),
            'fusion_method': self.fusion_method,
            'quality_weighted': self.quality_weighted,
            'spatial_interpolation': self.spatial_interpolation
        }
        
        if self.fused_data is not None:
            stats['fused_data_shape'] = self.fused_data.shape
            stats['fused_data_mean'] = np.nanmean(self.fused_data)
            stats['fused_data_std'] = np.nanstd(self.fused_data)
            stats['fused_data_nan_ratio'] = np.sum(np.isnan(self.fused_data)) / self.fused_data.size
            
        if self.fusion_uncertainty is not None:
            stats['uncertainty_mean'] = np.nanmean(self.fusion_uncertainty)
            stats['uncertainty_std'] = np.nanstd(self.fusion_uncertainty)
            
        return stats


def example_usage():
    """示例用法"""
    
    # 创建示例数据源
    np.random.seed(42)
    
    # 数据源1：高精度但稀疏
    coords1 = np.random.uniform(0, 100, (50, 2))
    data1 = 10 + 0.1 * coords1[:, 0] + 0.05 * coords1[:, 1] + np.random.normal(0, 0.5, 50)
    quality1 = np.random.uniform(0.8, 1.0, 50)
    
    source1 = DataSource(
        name="High_Quality_Sparse",
        data=data1.reshape(-1, 1),
        coordinates=coords1,
        quality_scores=quality1.reshape(-1, 1)
    )
    
    # 数据源2：中等精度，中等密度
    coords2 = np.random.uniform(0, 100, (100, 2))
    data2 = 10 + 0.1 * coords2[:, 0] + 0.05 * coords2[:, 1] + np.random.normal(0, 1.0, 100)
    quality2 = np.random.uniform(0.6, 0.8, 100)
    
    source2 = DataSource(
        name="Medium_Quality_Dense",
        data=data2.reshape(-1, 1),
        coordinates=coords2,
        quality_scores=quality2.reshape(-1, 1)
    )
    
    # 创建融合系统
    fusion_system = MultiSourceDataFusion(
        fusion_method='weighted_average',
        quality_weighted=True,
        spatial_interpolation=True
    )
    
    # 添加数据源
    fusion_system.add_data_source(source1)
    fusion_system.add_data_source(source2)
    
    # 评估数据质量
    quality_results = fusion_system.assess_all_sources()
    print("Data Quality Assessment:")
    for source_name, results in quality_results.items():
        print(f"  {source_name}: {results['overall_score']:.3f}")
        
    # 创建目标网格
    x_grid = np.linspace(0, 100, 20)
    y_grid = np.linspace(0, 100, 20)
    X, Y = np.meshgrid(x_grid, y_grid)
    target_coords = np.column_stack([X.flatten(), Y.flatten()])
    
    # 执行数据融合
    fusion_result = fusion_system.fuse_data(target_coords, time_index=0)
    
    # 获取统计信息
    stats = fusion_system.get_fusion_statistics()
    print(f"\nFusion Statistics: {stats}")


if __name__ == "__main__":
    example_usage()
