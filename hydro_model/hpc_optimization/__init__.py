"""
高性能计算优化模块
==================

本模块提供水文模型的高性能计算优化功能，包括：
- GPU加速计算（CUDA、OpenCL）
- 分布式计算（MPI、任务分解）
- 异步计算（任务调度、事件驱动）
- 内存和存储优化
- 算法优化
"""

from .parallel_computing import (
    GPUAccelerator,
    DistributedComputing,
    AsyncComputing,
    TaskScheduler,
    LoadBalancer
)

from .memory_optimization import (
    MemoryManager,
    MemoryPool,
    DataCompressor,
    CacheManager,
    StorageOptimizer
)

from .algorithm_optimization import (
    LinearSolverOptimizer,
    NonlinearSolverOptimizer,
    NumericalIntegrator,
    DifferentialEquationSolver,
    SparseMatrixOptimizer
)

from .performance_monitoring import (
    PerformanceProfiler,
    ResourceMonitor,
    BenchmarkSuite,
    OptimizationAnalyzer
)

__all__ = [
    # 并行计算
    'GPUAccelerator',
    'DistributedComputing',
    'AsyncComputing',
    'TaskScheduler',
    'LoadBalancer',
    
    # 内存优化
    'MemoryManager',
    'MemoryPool',
    'DataCompressor',
    'CacheManager',
    'StorageOptimizer',
    
    # 算法优化
    'LinearSolverOptimizer',
    'NonlinearSolverOptimizer',
    'NumericalIntegrator',
    'DifferentialEquationSolver',
    'SparseMatrixOptimizer',
    
    # 性能监控
    'PerformanceProfiler',
    'ResourceMonitor',
    'BenchmarkSuite',
    'OptimizationAnalyzer'
]

__version__ = '1.0.0'
__author__ = 'Hydro-Suite Team'
