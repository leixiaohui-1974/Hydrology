"""
数据同化模块
============

本模块提供水文模型的数据同化功能，包括：
- 高级EnKF算法（局部化、自适应）
- 粒子滤波实现
- 多源数据融合
- 时空同化
"""

from .enkf_enhanced import LocalizedEnKF, AdaptiveEnKF
from .particle_filter import ParticleFilter, AuxiliaryParticleFilter, RegularizedParticleFilter
from .multi_source_fusion import MultiSourceDataFusion
from .spatial_temporal import SpatioTemporalAssimilation
# from .observation_system import ObservationStrategyDesigner # Commented out for now, API seems unstable
# from .data_quality import DataQualityControl # Commented out for now, class does not exist

__all__ = [
    'LocalizedEnKF',
    'AdaptiveEnKF', 
    'ParticleFilter',
    'AuxiliaryParticleFilter',
    'RegularizedParticleFilter',
    'MultiSourceDataFusion',
    'SpatioTemporalAssimilation',
    # 'ObservationStrategyDesigner',
]

__version__ = '1.0.0'
__author__ = 'Hydro-Suite Team'
