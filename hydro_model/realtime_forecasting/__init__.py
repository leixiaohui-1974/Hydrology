"""
实时预报系统模块
==================

本模块提供水文模型的实时预报功能，包括：
- 实时数据接入
- 预报模型
- 预警系统
"""

from .data_acquisition import (
    SensorDataAcquisition,
    DataQualityControl,
    RealTimeDataValidator,
    DataInterpolation
)

from .forecasting_models import (
    ShortTermForecaster,
    MediumTermForecaster,
    EnsembleForecaster,
    ForecastCorrector
)

from .warning_system import (
    WarningThresholdManager,
    WarningInformationGenerator,
    WarningDistributionSystem,
    WarningEscalationManager
)

from .real_time_dashboard import (
    RealTimeDashboard,
    ForecastVisualizer,
    WarningMonitor,
    PerformanceTracker
)

__all__ = [
    # 实时数据接入
    'SensorDataAcquisition',
    'DataQualityControl',
    'RealTimeDataValidator',
    'DataInterpolation',

    # 预报模型
    'ShortTermForecaster',
    'MediumTermForecaster',
    'EnsembleForecaster',
    'ForecastCorrector',

    # 预警系统
    'WarningThresholdManager',
    'WarningInformationGenerator',
    'WarningDistributionSystem',
    'WarningEscalationManager',

    # 实时仪表板
    'RealTimeDashboard',
    'ForecastVisualizer',
    'WarningMonitor',
    'PerformanceTracker'
]

__version__ = '1.0.0'
__author__ = 'Hydro-Suite Team'
