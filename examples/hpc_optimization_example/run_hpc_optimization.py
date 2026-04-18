#!/usr/bin/env python3
"""
HPC优化模块示例程序
==================

本程序演示水文模型的高性能计算优化功能，包括：
- GPU加速计算
- 分布式计算
- 异步计算
- 内存优化
- 算法优化
- 性能监控
"""
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)



import sys
import os
import logging
import time
import numpy as np
import yaml

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hydro_model.hpc_optimization import (
    GPUAccelerator,
    DistributedComputing,
    AsyncComputing,
    TaskScheduler,
    LoadBalancer,
    MemoryManager,
    MemoryPool,
    DataCompressor,
    CacheManager,
    StorageOptimizer,
    LinearSolverOptimizer,
    NonlinearSolverOptimizer,
    NumericalIntegrator,
    DifferentialEquationSolver,
    SparseMatrixOptimizer,
    PerformanceProfiler,
    ResourceMonitor,
    BenchmarkSuite,
    OptimizationAnalyzer
)

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_test_data(size: int = 1000) -> tuple:
    """创建测试数据"""
    logger.info(f"Creating test data with size {size}")
    
    # 创建稀疏矩阵
    A = np.random.rand(size, size)
    A = A + A.T  # 使矩阵对称
    A = A + np.eye(size) * size  # 使矩阵对角占优
    
    # 创建向量
    b = np.random.rand(size)
    
    # 创建时间序列数据
    t = np.linspace(0, 10, size)
    y0 = np.array([1.0, 0.0])  # 初始条件
    
    return A, b, t, y0

def demonstrate_gpu_acceleration():
    """演示GPU加速计算"""
    logger.info("=== GPU加速计算演示 ===")
    
    try:
        # 初始化GPU加速器
        gpu_accelerator = GPUAccelerator()
        
        if gpu_accelerator.is_available:
            logger.info(f"GPU可用: {gpu_accelerator.device_info}")
            
            # 创建测试数据
            data = np.random.rand(1000, 1000)
            
            # 测试张量运算
            start_time = time.time()
            result_gpu = gpu_accelerator.accelerate_tensor_operations(data, "matrix_multiply")
            gpu_time = time.time() - start_time
            
            # CPU运算对比
            start_time = time.time()
            result_cpu = gpu_accelerator._cpu_tensor_operation(data, "matrix_multiply")
            cpu_time = time.time() - start_time
            
            logger.info(f"GPU运算时间: {gpu_time:.4f}s")
            logger.info(f"CPU运算时间: {cpu_time:.4f}s")
            logger.info(f"加速比: {cpu_time/gpu_time:.2f}x")
            
        else:
            logger.info("GPU不可用，跳过GPU加速演示")
            
    except Exception as e:
        logger.error(f"GPU加速演示失败: {e}")

def demonstrate_distributed_computing():
    """演示分布式计算"""
    logger.info("=== 分布式计算演示 ===")
    
    try:
        # 初始化分布式计算
        distributed = DistributedComputing()
        
        # 创建测试任务
        def square_task(x):
            time.sleep(0.1)  # 模拟计算时间
            return x ** 2
        
        # 测试数据
        data = list(range(100))
        
        # 串行计算
        start_time = time.time()
        serial_results = [square_task(x) for x in data]
        serial_time = time.time() - start_time
        
        # 并行计算
        start_time = time.time()
        parallel_results = distributed.parallel_map(square_task, data, max_workers=4)
        parallel_time = time.time() - start_time
        
        logger.info(f"串行计算时间: {serial_time:.4f}s")
        logger.info(f"并行计算时间: {parallel_time:.4f}s")
        logger.info(f"加速比: {serial_time/parallel_time:.2f}x")
        
        # 验证结果
        assert serial_results == parallel_results, "并行计算结果与串行结果不一致"
        logger.info("并行计算结果验证通过")
        
    except Exception as e:
        logger.error(f"分布式计算演示失败: {e}")

def demonstrate_async_computing():
    """演示异步计算"""
    logger.info("=== 异步计算演示 ===")
    
    try:
        # 初始化异步计算
        async_computing = AsyncComputing()
        
        # 创建异步任务
        def async_task(task_id, duration):
            time.sleep(duration)
            return f"Task {task_id} completed"
        
        # 提交多个任务
        task_ids = []
        for i in range(5):
            task_id = async_computing.submit_task(async_task, i, 0.5)
            task_ids.append(task_id)
        
        logger.info(f"提交了 {len(task_ids)} 个异步任务")
        
        # 获取结果
        results = []
        for task_id in task_ids:
            result = async_computing.get_result(task_id, timeout=10)
            results.append(result)
            logger.info(f"获取结果: {result}")
        
        logger.info(f"所有异步任务完成，共 {len(results)} 个结果")
        
    except Exception as e:
        logger.error(f"异步计算演示失败: {e}")

def demonstrate_memory_optimization():
    """演示内存优化"""
    logger.info("=== 内存优化演示 ===")
    
    try:
        # 初始化内存管理器
        memory_manager = MemoryManager()
        memory_pool = MemoryPool(block_size_mb=1.0, max_blocks=100)
        data_compressor = DataCompressor()
        cache_manager = CacheManager(max_cache_size_mb=50)
        
        # 创建大数组
        large_data = np.random.rand(1000, 1000)
        data_size_mb = large_data.nbytes / 1024**2
        
        logger.info(f"创建数据大小: {data_size_mb:.2f}MB")
        
        # 测试内存池
        block_id = memory_pool.allocate_block()
        logger.info(f"分配内存块: {block_id}")
        
        # 测试数据压缩
        compressed_data = data_compressor.compress_data(large_data, algorithm="lz4")
        compression_ratio = len(compressed_data) / large_data.nbytes
        logger.info(f"数据压缩比: {compression_ratio:.2f}")
        
        # 测试缓存
        cache_manager.put("test_data", large_data, data_size_mb)
        cached_data = cache_manager.get("test_data")
        logger.info(f"缓存命中: {cached_data is not None}")
        
        # 清理
        memory_pool.free_block(block_id)
        cache_manager.clear()
        
    except Exception as e:
        logger.error(f"内存优化演示失败: {e}")

def demonstrate_algorithm_optimization():
    """演示算法优化"""
    logger.info("=== 算法优化演示 ===")
    
    try:
        # 创建测试数据
        A, b, t, y0 = create_test_data(500)
        
        # 线性求解器优化
        linear_solver = LinearSolverOptimizer()
        start_time = time.time()
        x_linear = linear_solver.solve_linear_system(A, b)
        linear_time = time.time() - start_time
        
        logger.info(f"线性求解器时间: {linear_time:.4f}s")
        logger.info(f"残差: {np.linalg.norm(A @ x_linear - b):.2e}")
        
        # 非线性求解器优化
        def test_function(x):
            return x**2 - 4
        
        nonlinear_solver = NonlinearSolverOptimizer()
        start_time = time.time()
        root = nonlinear_solver.solve_nonlinear_equation(test_function, x0=1.0)
        nonlinear_time = time.time() - start_time
        
        logger.info(f"非线性求解器时间: {nonlinear_time:.4f}s")
        logger.info(f"根: {root:.6f}")
        
        # 数值积分优化
        def test_ode(t, y):
            return [-y[1], y[0]]
        
        integrator = DifferentialEquationSolver()
        start_time = time.time()
        solution = integrator.solve_ivp(test_ode, t, y0)
        integration_time = time.time() - start_time
        
        logger.info(f"数值积分时间: {integration_time:.4f}s")
        logger.info(f"解的形状: {solution.shape}")
        
    except Exception as e:
        logger.error(f"算法优化演示失败: {e}")

def demonstrate_performance_monitoring():
    """演示性能监控"""
    logger.info("=== 性能监控演示 ===")
    
    try:
        # 初始化性能分析器
        profiler = PerformanceProfiler()
        
        # 使用装饰器进行性能分析
        @profiler.profile_function("test_function")
        def test_function():
            time.sleep(0.5)
            return "test completed"
        
        # 运行函数
        result = test_function()
        logger.info(f"函数结果: {result}")
        
        # 获取性能摘要
        summary = profiler.get_profile_summary("test_function")
        logger.info(f"性能摘要: {summary}")
        
        # 初始化资源监控器
        resource_monitor = ResourceMonitor(monitoring_interval=0.5)
        
        # 开始监控
        resource_monitor.start_monitoring()
        time.sleep(2)  # 监控2秒
        
        # 获取当前指标
        current_metrics = resource_monitor.get_current_metrics()
        logger.info(f"当前资源指标: {current_metrics}")
        
        # 停止监控
        resource_monitor.stop_monitoring()
        
        # 获取监控摘要
        monitoring_summary = resource_monitor.get_monitoring_summary()
        logger.info(f"监控摘要: {monitoring_summary}")
        
    except Exception as e:
        logger.error(f"性能监控演示失败: {e}")

def demonstrate_benchmark_suite():
    """演示基准测试套件"""
    logger.info("=== 基准测试套件演示 ===")
    
    try:
        # 初始化基准测试套件
        benchmark_suite = BenchmarkSuite()
        
        # 定义测试函数
        def benchmark_function_1(size=1000):
            return np.random.rand(size, size).sum()
        
        def benchmark_function_2(size=1000):
            return np.random.rand(size).mean()
        
        # 注册基准测试
        benchmark_suite.register_benchmark("matrix_sum", benchmark_function_1)
        benchmark_suite.register_benchmark("array_mean", benchmark_function_2)
        
        # 运行基准测试
        results = benchmark_suite.run_all_benchmarks(n_runs=3)
        
        # 比较基准测试
        comparison = benchmark_suite.compare_benchmarks(["matrix_sum", "array_mean"])
        logger.info(f"基准测试比较: {comparison}")
        
        # 导出结果
        benchmark_suite.export_benchmark_results("benchmark_results.json")
        logger.info("基准测试结果已导出到 benchmark_results.json")
        
    except Exception as e:
        logger.error(f"基准测试套件演示失败: {e}")

def demonstrate_optimization_analysis():
    """演示优化分析"""
    logger.info("=== 优化分析演示 ===")
    
    try:
        # 初始化优化分析器
        analyzer = OptimizationAnalyzer()
        
        # 模拟基准性能指标
        baseline_metrics = {
            'execution_time': 10.0,
            'memory_usage_mb': 100.0,
            'cpu_usage_percent': 80.0
        }
        
        # 模拟优化后性能指标
        optimized_metrics = {
            'execution_time': 6.0,
            'memory_usage_mb': 70.0,
            'cpu_usage_percent': 60.0
        }
        
        # 分析性能改进
        improvement_analysis = analyzer.analyze_performance_improvement(
            baseline_metrics, optimized_metrics
        )
        
        logger.info(f"性能改进分析: {improvement_analysis}")
        
        # 生成优化报告
        report = analyzer.generate_optimization_report()
        logger.info("优化分析报告:")
        print(report)
        
        # 导出分析结果
        analyzer.export_analysis_results("optimization_analysis.json")
        logger.info("优化分析结果已导出到 optimization_analysis.json")
        
    except Exception as e:
        logger.error(f"优化分析演示失败: {e}")

def main():
    """主函数"""
    logger.info("开始HPC优化模块演示")
    
    try:
        # 演示各种功能
        demonstrate_gpu_acceleration()
        demonstrate_distributed_computing()
        demonstrate_async_computing()
        demonstrate_memory_optimization()
        demonstrate_algorithm_optimization()
        demonstrate_performance_monitoring()
        demonstrate_benchmark_suite()
        demonstrate_optimization_analysis()
        
        logger.info("所有演示完成")
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        raise

if __name__ == "__main__":
    main()

