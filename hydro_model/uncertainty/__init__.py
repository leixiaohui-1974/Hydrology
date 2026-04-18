"""
不确定性分析模块
================

本模块提供水文模型的不确定性分析功能，包括：
- Monte Carlo 模拟
- 全局敏感性分析
- 贝叶斯不确定性量化
"""

from .sensitivity_analysis import SensitivityAnalyzer
from .monte_carlo import MonteCarloAnalyzer
from .bayesian_analysis import BayesianUncertaintyAnalyzer

__all__ = [
    'SensitivityAnalyzer',
    'MonteCarloAnalyzer',
    'BayesianUncertaintyAnalyzer'
]

__version__ = '1.0.0'
__author__ = 'Hydro-Suite Team'
