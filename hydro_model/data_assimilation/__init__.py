"""
数据同化模块
============

本模块提供水文模型的数据同化功能，包括：
- 高级EnKF算法（局部化、自适应）
- 粒子滤波实现
- 多源数据融合
- 观测系统设计
- 数据质量控制
"""

from .enkf_enhanced import LocalizedEnKF, AdaptiveEnKF
from .particle_filter import ParticleFilter
from .multi_source_fusion import MultiSourceDataFusion
from .observation_system import ObservationSystemDesign
from .data_quality import DataQualityControl
from .spatial_temporal import SpatioTemporalAssimilation

__all__ = [
    'LocalizedEnKF',
    'AdaptiveEnKF', 
    'ParticleFilter',
    'MultiSourceDataFusion',
    'ObservationSystemDesign',
    'DataQualityControl',
    'SpatioTemporalAssimilation'
]

__version__ = '1.0.0'
__author__ = 'Hydro-Suite Team'
