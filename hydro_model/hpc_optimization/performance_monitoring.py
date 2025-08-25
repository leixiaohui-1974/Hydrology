"""
性能监控模块
============

本模块提供水文模型的性能监控功能，包括：
- 性能分析器
- 资源监控器
- 基准测试套件
- 优化分析器
"""

import numpy as np
import logging
import time
import psutil
import threading
import matplotlib.pyplot as plt
from typing import Optional, List, Dict, Any, Callable, Tuple
from collections import defaultdict, deque
import json
import os

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerformanceProfiler:
    """性能分析器"""
    
    def __init__(self, enable_profiling: bool = True):
        self.enable_profiling = enable_profiling
        self.profiling_data = defaultdict(list)
        self.active_profiles = {}
        self.lock = threading.Lock()
        
        logger.info(f"PerformanceProfiler initialized: enable_profiling={enable_profiling}")
    
    def start_profile(self, profile_name: str, metadata: Dict[str, Any] = None):
        """开始性能分析"""
        if not self.enable_profiling:
            return
        
        with self.lock:
            if profile_name in self.active_profiles:
                logger.warning(f"Profile {profile_name} already active")
                return
            
            self.active_profiles[profile_name] = {
                'start_time': time.time(),
                'start_cpu_percent': psutil.cpu_percent(),
                'start_memory': psutil.virtual_memory().used,
                'metadata': metadata or {}
            }
            
            logger.info(f"Started profiling: {profile_name}")
    
    def end_profile(self, profile_name: str, additional_metrics: Dict[str, Any] = None):
        """结束性能分析"""
        if not self.enable_profiling:
            return
        
        with self.lock:
            if profile_name not in self.active_profiles:
                logger.warning(f"Profile {profile_name} not found")
                return
            
            start_data = self.active_profiles[profile_name]
            end_time = time.time()
            end_cpu_percent = psutil.cpu_percent()
            end_memory = psutil.virtual_memory().used
            
            # 计算性能指标
            profile_data = {
                'profile_name': profile_name,
                'start_time': start_data['start_time'],
                'end_time': end_time,
                'duration': end_time - start_data['start_time'],
                'cpu_percent_start': start_data['start_cpu_percent'],
                'cpu_percent_end': end_cpu_percent,
                'memory_start_mb': start_data['start_memory'] / 1024**2,
                'memory_end_mb': end_memory / 1024**2,
                'memory_delta_mb': (end_memory - start_data['start_memory']) / 1024**2,
                'metadata': start_data['metadata']
            }
            
            # 添加额外指标
            if additional_metrics:
                profile_data.update(additional_metrics)
            
            # 存储分析数据
            self.profiling_data[profile_name].append(profile_data)
            
            # 移除活动配置
            del self.active_profiles[profile_name]
            
            logger.info(f"Completed profiling: {profile_name} - Duration: {profile_data['duration']:.3f}s")
    
    def profile_function(self, profile_name: str = None):
        """函数性能分析装饰器"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                nonlocal profile_name
                if profile_name is None:
                    profile_name = func.__name__
                
                self.start_profile(profile_name)
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    self.end_profile(profile_name)
            
            return wrapper
        return decorator
    
    def get_profile_summary(self, profile_name: str = None) -> Dict[str, Any]:
        """获取性能分析摘要"""
        with self.lock:
            if profile_name:
                if profile_name not in self.profiling_data:
                    return {"error": f"Profile {profile_name} not found"}
                
                profiles = self.profiling_data[profile_name]
            else:
                # 所有配置的摘要
                all_profiles = []
                for profiles in self.profiling_data.values():
                    all_profiles.extend(profiles)
                profiles = all_profiles
            
            if not profiles:
                return {"error": "No profiling data available"}
            
            # 计算统计信息
            durations = [p['duration'] for p in profiles]
            memory_deltas = [p['memory_delta_mb'] for p in profiles]
            
            summary = {
                'total_runs': len(profiles),
                'avg_duration': np.mean(durations),
                'std_duration': np.std(durations),
                'min_duration': np.min(durations),
                'max_duration': np.max(durations),
                'avg_memory_delta_mb': np.mean(memory_deltas),
                'total_duration': np.sum(durations)
            }
            
            return summary
    
    def export_profiling_data(self, filepath: str):
        """导出性能分析数据"""
        with self.lock:
            try:
                # 转换数据为可序列化格式
                export_data = {}
                for profile_name, profiles in self.profiling_data.items():
                    export_data[profile_name] = []
                    for profile in profiles:
                        # 确保所有值都是可序列化的
                        export_profile = {}
                        for key, value in profile.items():
                            if isinstance(value, np.ndarray):
                                export_profile[key] = value.tolist()
                            elif isinstance(value, (np.integer, np.floating)):
                                export_profile[key] = float(value)
                            else:
                                export_profile[key] = value
                        export_data[profile_name].append(export_profile)
                
                with open(filepath, 'w') as f:
                    json.dump(export_data, f, indent=2)
                
                logger.info(f"Profiling data exported to {filepath}")
                
            except Exception as e:
                logger.error(f"Failed to export profiling data: {e}")

class ResourceMonitor:
    """资源监控器"""
    
    def __init__(self, monitoring_interval: float = 1.0):
        self.monitoring_interval = monitoring_interval
        self.is_monitoring = False
        self.monitoring_thread = None
        self.monitoring_data = {
            'cpu_percent': deque(maxlen=1000),
            'memory_percent': deque(maxlen=1000),
            'disk_io': deque(maxlen=1000),
            'network_io': deque(maxlen=1000),
            'timestamps': deque(maxlen=1000)
        }
        
        logger.info(f"ResourceMonitor initialized: interval={monitoring_interval}s")
    
    def start_monitoring(self):
        """开始资源监控"""
        if self.is_monitoring:
            logger.warning("Resource monitoring already active")
            return
        
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        logger.info("Resource monitoring started")
    
    def stop_monitoring(self):
        """停止资源监控"""
        self.is_monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join()
        logger.info("Resource monitoring stopped")
    
    def _monitoring_loop(self):
        """监控循环"""
        while self.is_monitoring:
            try:
                timestamp = time.time()
                
                # CPU使用率
                cpu_percent = psutil.cpu_percent(interval=0.1)
                
                # 内存使用率
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                # 磁盘I/O
                disk_io = psutil.disk_io_counters()
                disk_io_data = {
                    'read_bytes': disk_io.read_bytes if disk_io else 0,
                    'write_bytes': disk_io.write_bytes if disk_io else 0
                }
                
                # 网络I/O
                network_io = psutil.net_io_counters()
                network_io_data = {
                    'bytes_sent': network_io.bytes_sent if network_io else 0,
                    'bytes_recv': network_io.bytes_recv if network_io else 0
                }
                
                # 存储监控数据
                self.monitoring_data['timestamps'].append(timestamp)
                self.monitoring_data['cpu_percent'].append(cpu_percent)
                self.monitoring_data['memory_percent'].append(memory_percent)
                self.monitoring_data['disk_io'].append(disk_io_data)
                self.monitoring_data['network_io'].append(network_io_data)
                
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                time.sleep(self.monitoring_interval)
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前资源指标"""
        try:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': memory.available / 1024**3,
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free / 1024**3
            }
        except Exception as e:
            logger.error(f"Failed to get current metrics: {e}")
            return {}
    
    def get_monitoring_summary(self) -> Dict[str, Any]:
        """获取监控摘要"""
        if not self.monitoring_data['timestamps']:
            return {"error": "No monitoring data available"}
        
        timestamps = list(self.monitoring_data['timestamps'])
        cpu_percent = list(self.monitoring_data['cpu_percent'])
        memory_percent = list(self.monitoring_data['memory_percent'])
        
        if not timestamps:
            return {"error": "No monitoring data available"}
        
        duration = timestamps[-1] - timestamps[0]
        
        summary = {
            'monitoring_duration': duration,
            'data_points': len(timestamps),
            'cpu_percent': {
                'avg': np.mean(cpu_percent),
                'max': np.max(cpu_percent),
                'min': np.min(cpu_percent)
            },
            'memory_percent': {
                'avg': np.mean(memory_percent),
                'max': np.max(memory_percent),
                'min': np.min(memory_percent)
            }
        }
        
        return summary
    
    def plot_monitoring_data(self, save_path: str = None):
        """绘制监控数据图表"""
        if not self.monitoring_data['timestamps']:
            logger.warning("No monitoring data available for plotting")
            return
        
        try:
            timestamps = np.array(self.monitoring_data['timestamps'])
            cpu_percent = np.array(self.monitoring_data['cpu_percent'])
            memory_percent = np.array(self.monitoring_data['memory_percent'])
            
            # 转换为相对时间（秒）
            relative_time = timestamps - timestamps[0]
            
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
            
            # CPU使用率
            ax1.plot(relative_time, cpu_percent, 'b-', label='CPU %')
            ax1.set_ylabel('CPU Usage (%)')
            ax1.set_title('Resource Monitoring')
            ax1.grid(True)
            ax1.legend()
            
            # 内存使用率
            ax2.plot(relative_time, memory_percent, 'r-', label='Memory %')
            ax2.set_xlabel('Time (s)')
            ax2.set_ylabel('Memory Usage (%)')
            ax2.grid(True)
            ax2.legend()
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Monitoring plot saved to {save_path}")
            else:
                plt.show()
                
        except Exception as e:
            logger.error(f"Failed to plot monitoring data: {e}")

class BenchmarkSuite:
    """基准测试套件"""
    
    def __init__(self):
        self.benchmark_results = {}
        self.benchmark_configs = {}
        
        logger.info("BenchmarkSuite initialized")
    
    def register_benchmark(self, name: str, func: Callable, config: Dict[str, Any] = None):
        """注册基准测试"""
        self.benchmark_configs[name] = {
            'func': func,
            'config': config or {}
        }
        logger.info(f"Benchmark {name} registered")
    
    def run_benchmark(self, name: str, n_runs: int = 5, **kwargs) -> Dict[str, Any]:
        """运行基准测试"""
        if name not in self.benchmark_configs:
            raise ValueError(f"Benchmark {name} not registered")
        
        benchmark_config = self.benchmark_configs[name]
        func = benchmark_config['func']
        config = benchmark_config['config']
        
        # 合并配置
        run_config = {**config, **kwargs}
        
        logger.info(f"Running benchmark {name} with {n_runs} runs")
        
        results = {
            'name': name,
            'n_runs': n_runs,
            'config': run_config,
            'runs': [],
            'summary': {}
        }
        
        # 运行测试
        for i in range(n_runs):
            start_time = time.time()
            start_memory = psutil.virtual_memory().used
            
            try:
                # 运行函数
                result = func(**run_config)
                
                end_time = time.time()
                end_memory = psutil.virtual_memory().used
                
                run_result = {
                    'run_id': i,
                    'execution_time': end_time - start_time,
                    'memory_delta_mb': (end_memory - start_memory) / 1024**2,
                    'success': True,
                    'result': result
                }
                
            except Exception as e:
                end_time = time.time()
                run_result = {
                    'run_id': i,
                    'execution_time': end_time - start_time,
                    'memory_delta_mb': 0,
                    'success': False,
                    'error': str(e)
                }
            
            results['runs'].append(run_result)
        
        # 计算统计摘要
        successful_runs = [r for r in results['runs'] if r['success']]
        
        if successful_runs:
            execution_times = [r['execution_time'] for r in successful_runs]
            memory_deltas = [r['memory_delta_mb'] for r in successful_runs]
            
            results['summary'] = {
                'success_rate': len(successful_runs) / n_runs,
                'execution_time': {
                    'avg': np.mean(execution_times),
                    'std': np.std(execution_times),
                    'min': np.min(execution_times),
                    'max': np.max(execution_times)
                },
                'memory_delta_mb': {
                    'avg': np.mean(memory_deltas),
                    'std': np.std(memory_deltas),
                    'min': np.min(memory_deltas),
                    'max': np.max(memory_deltas)
                }
            }
        
        # 存储结果
        self.benchmark_results[name] = results
        
        logger.info(f"Benchmark {name} completed: success_rate={results['summary'].get('success_rate', 0):.2f}")
        return results
    
    def run_all_benchmarks(self, n_runs: int = 5) -> Dict[str, Any]:
        """运行所有基准测试"""
        logger.info(f"Running all benchmarks with {n_runs} runs each")
        
        all_results = {}
        for name in self.benchmark_configs:
            try:
                result = self.run_benchmark(name, n_runs)
                all_results[name] = result
            except Exception as e:
                logger.error(f"Benchmark {name} failed: {e}")
                all_results[name] = {'error': str(e)}
        
        return all_results
    
    def compare_benchmarks(self, benchmark_names: List[str]) -> Dict[str, Any]:
        """比较多个基准测试"""
        if not benchmark_names:
            return {"error": "No benchmark names provided"}
        
        comparison = {}
        for name in benchmark_names:
            if name in self.benchmark_results:
                result = self.benchmark_results[name]
                if 'summary' in result:
                    comparison[name] = {
                        'avg_execution_time': result['summary']['execution_time']['avg'],
                        'avg_memory_delta': result['summary']['memory_delta_mb']['avg'],
                        'success_rate': result['summary']['success_rate']
                    }
                else:
                    comparison[name] = {'error': 'No summary available'}
            else:
                comparison[name] = {'error': 'Benchmark not found'}
        
        return comparison
    
    def export_benchmark_results(self, filepath: str):
        """导出基准测试结果"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.benchmark_results, f, indent=2, default=str)
            logger.info(f"Benchmark results exported to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export benchmark results: {e}")

class OptimizationAnalyzer:
    """优化分析器"""
    
    def __init__(self):
        self.optimization_data = {}
        self.analysis_results = {}
        
        logger.info("OptimizationAnalyzer initialized")
    
    def analyze_performance_improvement(self, baseline_metrics: Dict[str, Any], 
                                      optimized_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """分析性能改进"""
        analysis = {}
        
        for metric in baseline_metrics:
            if metric in optimized_metrics:
                baseline_value = baseline_metrics[metric]
                optimized_value = optimized_metrics[metric]
                
                if isinstance(baseline_value, (int, float)) and isinstance(optimized_value, (int, float)):
                    if baseline_value != 0:
                        improvement_percent = ((baseline_value - optimized_value) / baseline_value) * 100
                        analysis[metric] = {
                            'baseline': baseline_value,
                            'optimized': optimized_value,
                            'improvement_percent': improvement_percent,
                            'improvement_factor': baseline_value / optimized_value if optimized_value != 0 else float('inf')
                        }
        
        self.analysis_results['performance_improvement'] = analysis
        return analysis
    
    def analyze_resource_usage(self, resource_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析资源使用情况"""
        if not resource_data:
            return {"error": "No resource data provided"}
        
        analysis = {}
        
        # 分析CPU使用
        if 'cpu_percent' in resource_data[0]:
            cpu_values = [d['cpu_percent'] for d in resource_data]
            analysis['cpu'] = {
                'avg': np.mean(cpu_values),
                'max': np.max(cpu_values),
                'min': np.min(cpu_values),
                'std': np.std(cpu_values)
            }
        
        # 分析内存使用
        if 'memory_percent' in resource_data[0]:
            memory_values = [d['memory_percent'] for d in resource_data]
            analysis['memory'] = {
                'avg': np.mean(memory_values),
                'max': np.max(memory_values),
                'min': np.min(memory_values),
                'std': np.std(memory_values)
            }
        
        self.analysis_results['resource_usage'] = analysis
        return analysis
    
    def generate_optimization_report(self) -> str:
        """生成优化报告"""
        if not self.analysis_results:
            return "No analysis results available"
        
        report = "Optimization Analysis Report\n"
        report += "=" * 40 + "\n\n"
        
        # 性能改进分析
        if 'performance_improvement' in self.analysis_results:
            report += "Performance Improvements:\n"
            report += "-" * 25 + "\n"
            
            for metric, data in self.analysis_results['performance_improvement'].items():
                report += f"{metric}:\n"
                report += f"  Baseline: {data['baseline']:.4f}\n"
                report += f"  Optimized: {data['optimized']:.4f}\n"
                report += f"  Improvement: {data['improvement_percent']:.2f}%\n"
                report += f"  Factor: {data['improvement_factor']:.2f}x\n\n"
        
        # 资源使用分析
        if 'resource_usage' in self.analysis_results:
            report += "Resource Usage Analysis:\n"
            report += "-" * 25 + "\n"
            
            for resource, data in self.analysis_results['resource_usage'].items():
                report += f"{resource}:\n"
                report += f"  Average: {data['avg']:.2f}\n"
                report += f"  Maximum: {data['max']:.2f}\n"
                report += f"  Minimum: {data['min']:.2f}\n"
                report += f"  Std Dev: {data['std']:.2f}\n\n"
        
        return report
    
    def export_analysis_results(self, filepath: str):
        """导出分析结果"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.analysis_results, f, indent=2, default=str)
            logger.info(f"Analysis results exported to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export analysis results: {e}")
