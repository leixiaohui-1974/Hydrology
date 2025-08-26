"""
数据质量控制模块
================

提供水文数据的质量控制功能，包括：
- 数据验证和检查
- 异常检测
- 数据修复和插值
- 质量报告生成
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional, Any, Callable, Union
from scipy import stats, interpolate
import warnings
import logging
from pathlib import Path
import json
import time
from datetime import datetime, timedelta


class DataValidator:
    """数据验证器"""
    
    def __init__(self):
        """初始化数据验证器"""
        self.validation_rules = {}
        self.validation_results = {}
        
    def add_validation_rule(self, rule_name: str, rule_function: Callable, 
                           rule_params: Optional[Dict[str, Any]] = None):
        """添加验证规则"""
        self.validation_rules[rule_name] = {
            'function': rule_function,
            'parameters': rule_params or {}
        }
        
    def validate_data(self, data: np.ndarray, data_name: str = "data") -> Dict[str, Any]:
        """验证数据"""
        validation_results = {
            'data_name': data_name,
            'timestamp': datetime.now().isoformat(),
            'data_shape': data.shape,
            'total_points': data.size,
            'validation_rules': {},
            'overall_score': 0.0,
            'issues': []
        }
        
        # 执行所有验证规则
        for rule_name, rule_info in self.validation_rules.items():
            try:
                rule_result = rule_info['function'](data, **rule_info['parameters'])
                validation_results['validation_rules'][rule_name] = rule_result
                
                if 'issues' in rule_result:
                    validation_results['issues'].extend(rule_result['issues'])
                    
            except Exception as e:
                validation_results['validation_rules'][rule_name] = {
                    'status': 'error',
                    'error': str(e),
                    'score': 0.0
                }
                
        # 计算综合评分
        scores = []
        for rule_result in validation_results['validation_rules'].values():
            if 'score' in rule_result:
                scores.append(rule_result['score'])
                
        if scores:
            validation_results['overall_score'] = np.mean(scores)
            
        self.validation_results[data_name] = validation_results
        return validation_results


class AnomalyDetector:
    """异常检测器"""
    
    def __init__(self):
        """初始化异常检测器"""
        self.detection_results = {}
        
    def detect_anomalies(self, data: np.ndarray, data_name: str = "data",
                        threshold: float = 3.5) -> Dict[str, Any]:
        """
        使用中位数绝对偏差(MAD)检测异常，这是一种对异常值更稳健的方法.
        """
        # 移除NaN值
        valid_data = data[~np.isnan(data)]
        
        if len(valid_data) == 0:
            return {'anomalies': [], 'anomaly_count': 0, 'anomaly_ratio': 0.0}
            
        # 计算MAD统计量
        median_val = np.median(valid_data)
        # 计算每个点到中位数的绝对偏差
        abs_dev = np.abs(valid_data - median_val)
        # 计算这些绝对偏差的中位数
        mad = np.median(abs_dev)

        # 避免除以零
        if mad == 0:
            # 如果MAD为0，则回退到标准差方法
            mad = np.std(valid_data) * 1.4826 # 约等于正态分布下的MAD
            if mad == 0: # 如果仍然为0，则无法检测异常
                return {'anomalies': [], 'anomaly_count': 0, 'anomaly_ratio': 0.0}

        # 计算修正的Z-score
        modified_z_scores = 0.6745 * abs_dev / mad

        # 获取原始数据中有效数据的索引
        valid_indices = np.where(~np.isnan(data))[0]
        
        # 检测异常
        anomalies = []
        for i, z_score in enumerate(modified_z_scores):
            if z_score > threshold:
                anomalies.append(valid_indices[i])
                    
        detection_results = {
            'data_name': data_name,
            'anomalies': anomalies,
            'anomaly_count': len(anomalies),
            'anomaly_ratio': len(anomalies) / data.size,
            'statistics': {'median': median_val, 'mad': mad}
        }
        
        self.detection_results[data_name] = detection_results
        return detection_results


class DataRepairer:
    """数据修复器"""
    
    def __init__(self):
        """初始化数据修复器"""
        self.repair_results = {}
        
    def repair_data(self, data: np.ndarray, anomalies: List[int],
                   method: str = 'interpolation') -> np.ndarray:
        """
        修复数据中的异常值和缺失值.
        """
        repaired_data = data.copy()
        
        # 找出所有需要修复的点（异常值 + 缺失值）
        nan_indices = np.where(np.isnan(data))[0]
        points_to_repair = sorted(list(set(anomalies) | set(nan_indices)))

        if not points_to_repair:
            return repaired_data

        if method == 'interpolation':
            # 插值修复
            all_indices = np.arange(len(data))
            # 找到所有有效点（非异常且非NaN）
            valid_mask = np.ones(len(data), dtype=bool)
            valid_mask[points_to_repair] = False
            
            valid_data = data[valid_mask]
            valid_positions = all_indices[valid_mask]
            
            if len(valid_data) >= 2:
                interpolator = interpolate.interp1d(valid_positions, valid_data, 
                                                 kind='linear', bounds_error=False, 
                                                 fill_value='extrapolate')
                
                repaired_values = interpolator(points_to_repair)
                repaired_data[points_to_repair] = repaired_values
                        
        elif method == 'statistical':
            # 统计修复
            valid_mask = np.ones(len(data), dtype=bool)
            valid_mask[points_to_repair] = False
            valid_data = data[valid_mask]
            
            if len(valid_data) > 0:
                replacement_value = np.mean(valid_data)
                repaired_data[points_to_repair] = replacement_value
                    
        return repaired_data


def example_usage():
    """示例用法"""
    
    # 创建示例数据
    np.random.seed(42)
    n_points = 100
    
    # 生成正常数据
    normal_data = np.random.normal(10, 2, n_points)
    
    # 添加异常
    anomaly_indices = [20, 45, 70, 85]
    normal_data[anomaly_indices] = [50, -10, 100, 0]  # 异常值
    
    # 添加缺失值
    missing_indices = [30, 60]
    normal_data[missing_indices] = np.nan
    
    print("原始数据统计:")
    print(f"  数据点数: {len(normal_data)}")
    print(f"  均值: {np.nanmean(normal_data):.2f}")
    print(f"  标准差: {np.nanstd(normal_data):.2f}")
    print(f"  缺失值: {np.sum(np.isnan(normal_data))}")
    
    # 数据验证
    validator = DataValidator()
    
    # 添加验证规则
    def range_check(data, min_val=-20, max_val=30):
        """范围检查"""
        valid_mask = ~np.isnan(data)
        valid_data = data[valid_mask]
        
        in_range = np.sum((valid_data >= min_val) & (valid_data <= max_val))
        total_valid = len(valid_data)
        
        score = in_range / total_valid if total_valid > 0 else 0.0
        issues = []
        
        if score < 1.0:
            issues.append(f"部分数据超出范围 [{min_val}, {max_val}]")
            
        return {
            'status': 'success',
            'score': score,
            'in_range': in_range,
            'total_valid': total_valid,
            'issues': issues
        }
        
    def missing_value_check(data, max_missing_ratio=0.1):
        """缺失值检查"""
        missing_count = np.sum(np.isnan(data))
        total_count = len(data)
        missing_ratio = missing_count / total_count
        
        score = 1.0 - missing_ratio
        issues = []
        
        if missing_ratio > max_missing_ratio:
            issues.append(f"缺失值比例过高: {missing_ratio:.2f}")
            
        return {
            'status': 'success',
            'score': score,
            'missing_count': missing_count,
            'missing_ratio': missing_ratio,
            'issues': issues
        }
        
    validator.add_validation_rule('range_check', range_check, {'min_val': -20, 'max_val': 30})
    validator.add_validation_rule('missing_value_check', missing_value_check, {'max_missing_ratio': 0.1})
    
    # 执行验证
    validation_results = validator.validate_data(normal_data, "example_data")
    
    print(f"\n验证结果:")
    print(f"  总体评分: {validation_results['overall_score']:.3f}")
    print(f"  问题数量: {len(validation_results['issues'])}")
    
    # 异常检测
    detector = AnomalyDetector()
    detection_results = detector.detect_anomalies(normal_data, "example_data", threshold=3.0)
    
    print(f"\n异常检测结果:")
    print(f"  异常总数: {detection_results['anomaly_count']}")
    print(f"  异常比例: {detection_results['anomaly_ratio']:.3f}")
    
    # 数据修复
    repairer = DataRepairer()
    repaired_data = repairer.repair_data(normal_data, detection_results['anomalies'], 'interpolation')
    
    print(f"\n修复结果:")
    print(f"  修复数量: {detection_results['anomaly_count']}")
    print(f"  修复后均值: {np.nanmean(repaired_data):.2f}")
    print(f"  修复后标准差: {np.nanstd(repaired_data):.2f}")


if __name__ == "__main__":
    example_usage()
