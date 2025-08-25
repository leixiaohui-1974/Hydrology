"""
模型验证和评估系统模块
======================

本模块提供水文模型的验证和评估功能，包括：
- 统计验证指标
- 可视化验证
- 不确定性可视化
- 模型性能评估
"""

from .statistical_validation import (
    FlowValidationMetrics,
    WaterLevelValidationMetrics,
    StatisticalValidator,
    ValidationReport
)

from .visualization_validation import (
    TimeSeriesValidator,
    SpatialValidator,
    ValidationPlotter,
    ComparisonAnalyzer
)

from .uncertainty_visualization import (
    ConfidenceIntervalVisualizer,
    UncertaintyBandVisualizer,
    ProbabilityDistributionPlotter,
    SensitivityVisualizer
)

from .model_performance import (
    ModelPerformanceEvaluator,
    PerformanceMetrics,
    ModelComparison,
    PerformanceReport
)

__all__ = [
    # 统计验证
    'FlowValidationMetrics',
    'WaterLevelValidationMetrics',
    'StatisticalValidator',
    'ValidationReport',
    
    # 可视化验证
    'TimeSeriesValidator',
    'SpatialValidator',
    'ValidationPlotter',
    'ComparisonAnalyzer',
    
    # 不确定性可视化
    'ConfidenceIntervalVisualizer',
    'UncertaintyBandVisualizer',
    'ProbabilityDistributionPlotter',
    'SensitivityVisualizer',
    
    # 模型性能
    'ModelPerformanceEvaluator',
    'PerformanceMetrics',
    'ModelComparison',
    'PerformanceReport'
]

__version__ = '1.0.0'
__author__ = 'Hydro-Suite Team'
