"""
Performance Monitoring and Benchmarking Module
==============================================
This module provides tools for monitoring and optimizing simulation performance.
"""
import time
import functools
import psutil
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager
import numpy as np
import matplotlib.pyplot as plt
import json
import os


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""
    execution_time: float = 0.0
    memory_usage: float = 0.0
    cpu_usage: float = 0.0
    throughput: float = 0.0  # operations per second
    efficiency: float = 0.0   # throughput per CPU core
    parallelization_speedup: float = 1.0
    memory_efficiency: float = 0.0  # operations per MB of memory


class PerformanceMonitor:
    """
    A comprehensive performance monitoring system for hydrological simulations.
    """
    
    def __init__(self, enable_monitoring: bool = True):
        self.enable_monitoring = enable_monitoring
        self.metrics_history: List[PerformanceMetrics] = []
        self.current_metrics = PerformanceMetrics()
        self.monitoring_thread = None
        self._stop_monitoring = False
        
        # Performance counters
        self.operation_count = 0
        self.start_time = None
        self.memory_snapshots = []
        self.cpu_snapshots = []
        
    def start_monitoring(self):
        """Start continuous performance monitoring."""
        if not self.enable_monitoring:
            return
            
        self.start_time = time.time()
        self._stop_monitoring = False
        self.monitoring_thread = threading.Thread(target=self._monitor_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        
    def stop_monitoring(self):
        """Stop continuous performance monitoring."""
        if self.monitoring_thread:
            self._stop_monitoring = True
            self.monitoring_thread.join()
            
    def _monitor_loop(self):
        """Background monitoring loop."""
        while not self._stop_monitoring:
            self._take_snapshot()
            time.sleep(0.1)  # Sample every 100ms
            
    def _take_snapshot(self):
        """Take a snapshot of current system resources."""
        process = psutil.Process()
        
        # Memory usage
        memory_info = process.memory_info()
        self.memory_snapshots.append({
            'timestamp': time.time(),
            'rss': memory_info.rss / 1024 / 1024,  # MB
            'vms': memory_info.vms / 1024 / 1024   # MB
        })
        
        # CPU usage
        cpu_percent = process.cpu_percent()
        self.cpu_snapshots.append({
            'timestamp': time.time(),
            'cpu_percent': cpu_percent
        })
        
    @contextmanager
    def measure_operation(self, operation_name: str):
        """Context manager for measuring individual operations."""
        if not self.enable_monitoring:
            yield
            return
            
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss
        
        try:
            yield
        finally:
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss
            
            execution_time = end_time - start_time
            memory_delta = (end_memory - start_memory) / 1024 / 1024  # MB
            
            self._record_operation(operation_name, execution_time, memory_delta)
            
    def time_func(self, func):
        """A decorator to time the execution of a function."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            start_memory = psutil.Process().memory_info().rss
            try:
                return func(*args, **kwargs)
            finally:
                end_time = time.time()
                end_memory = psutil.Process().memory_info().rss
                execution_time = end_time - start_time
                memory_delta = (end_memory - start_memory) / 1024 / 1024
                self._record_operation(func.__name__, execution_time, memory_delta)
        return wrapper

    def _record_operation(self, operation_name: str, execution_time: float, memory_delta: float):
        """Record metrics for a single operation."""
        self.operation_count += 1
        
        # Update current metrics
        self.current_metrics.execution_time += execution_time
        self.current_metrics.memory_usage = max(self.current_metrics.memory_usage, memory_delta)
        
        # Calculate throughput
        if self.current_metrics.execution_time > 0:
            self.current_metrics.throughput = self.operation_count / self.current_metrics.execution_time
            
    def finalize_metrics(self, parallel_controller=None) -> PerformanceMetrics:
        """Finalize and calculate comprehensive performance metrics."""
        if not self.enable_monitoring:
            return PerformanceMetrics()
            
        # Calculate final metrics
        if self.start_time:
            total_time = time.time() - self.start_time
            self.current_metrics.execution_time = total_time
            
        # Memory efficiency
        if self.current_metrics.memory_usage > 0:
            self.current_metrics.memory_efficiency = (
                self.operation_count / self.current_metrics.memory_usage
            )
            
        # CPU efficiency
        cpu_count = psutil.cpu_count()
        if cpu_count > 0:
            self.current_metrics.efficiency = self.current_metrics.throughput / cpu_count
            
        # Parallelization speedup
        if parallel_controller:
            stats = parallel_controller.get_parallelization_stats()
            if stats['parallel_groups'] > 1:
                # Estimate speedup based on parallel groups
                self.current_metrics.parallelization_speedup = min(
                    stats['max_workers'], 
                    len(stats['group_sizes'])
                )
                
        # Store in history
        self.metrics_history.append(self.current_metrics)
        
        return self.current_metrics

    def reset(self):
        """Resets the monitor to clear all collected data."""
        self.metrics_history = []
        self.current_metrics = PerformanceMetrics()
        self.operation_count = 0
        self.start_time = None
        self.memory_snapshots = []
        self.cpu_snapshots = []
        
    def generate_report(self, output_file: str = None) -> str:
        """Generate a comprehensive performance report."""
        if not self.metrics_history:
            return "No performance data available."
            
        latest_metrics = self.metrics_history[-1]
        
        report = f"""
Performance Report
=================

Execution Summary:
- Total execution time: {latest_metrics.execution_time:.2f} seconds
- Operations performed: {self.operation_count}
- Throughput: {latest_metrics.throughput:.2f} ops/sec
- Memory usage: {latest_metrics.memory_usage:.2f} MB
- CPU efficiency: {latest_metrics.efficiency:.2f} ops/sec/core
- Parallelization speedup: {latest_metrics.parallelization_speedup:.2f}x
- Memory efficiency: {latest_metrics.memory_efficiency:.2f} ops/MB

Resource Utilization:
- Peak memory: {max(s['rss'] for s in self.memory_snapshots) if self.memory_snapshots else 0:.2f} MB
- Average CPU: {np.mean([s['cpu_percent'] for s in self.cpu_snapshots]) if self.cpu_snapshots else 0:.2f}%
- Peak CPU: {max(s['cpu_percent'] for s in self.cpu_snapshots) if self.cpu_snapshots else 0:.2f}%

Recommendations:
"""
        
        # Add recommendations based on metrics
        if latest_metrics.memory_usage > 1000:  # > 1GB
            report += "- Consider optimizing memory usage or using streaming data processing\n"
            
        if latest_metrics.efficiency < 10:  # < 10 ops/sec/core
            report += "- Consider parallelization for CPU-intensive operations\n"
            
        if latest_metrics.parallelization_speedup < 2:
            report += "- Parallelization benefits may be limited by dependencies\n"
            
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
                
        return report
        
    def plot_performance_timeline(self, output_file: str = None):
        """Plot performance metrics over time."""
        if not self.memory_snapshots or not self.cpu_snapshots:
            print("No performance data available for plotting.")
            return
            
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        # Memory usage over time
        timestamps = [s['timestamp'] - self.start_time for s in self.memory_snapshots]
        memory_values = [s['rss'] for s in self.memory_snapshots]
        
        ax1.plot(timestamps, memory_values, 'b-', label='Memory Usage (MB)')
        ax1.set_ylabel('Memory (MB)')
        ax1.set_title('Memory Usage Over Time')
        ax1.grid(True)
        ax1.legend()
        
        # CPU usage over time
        cpu_timestamps = [s['timestamp'] - self.start_time for s in self.cpu_snapshots]
        cpu_values = [s['cpu_percent'] for s in self.cpu_snapshots]
        
        ax2.plot(cpu_timestamps, cpu_values, 'r-', label='CPU Usage (%)')
        ax2.set_xlabel('Time (seconds)')
        ax2.set_ylabel('CPU (%)')
        ax2.set_title('CPU Usage Over Time')
        ax2.grid(True)
        ax2.legend()
        
        plt.tight_layout()
        
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
        else:
            plt.show()
            
        plt.close()


class PerformanceBenchmark:
    """
    A benchmarking system for comparing different simulation configurations.
    """
    
    def __init__(self):
        self.benchmark_results = {}
        
    def benchmark_configuration(self, config_name: str, simulation_func, 
                              iterations: int = 3) -> Dict[str, Any]:
        """
        Benchmark a simulation configuration.
        
        Args:
            config_name: Name of the configuration being tested
            simulation_func: Function that runs the simulation
            iterations: Number of times to run the benchmark
            
        Returns:
            Dictionary containing benchmark results
        """
        print(f"Benchmarking configuration: {config_name}")
        
        results = {
            'execution_times': [],
            'memory_usage': [],
            'throughput': []
        }
        
        for i in range(iterations):
            print(f"  Running iteration {i+1}/{iterations}")
            
            # Monitor the simulation
            monitor = PerformanceMonitor()
            monitor.start_monitoring()
            
            start_time = time.time()
            start_memory = psutil.Process().memory_info().rss
            
            # Run simulation
            simulation_func()
            
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss
            
            monitor.stop_monitoring()
            metrics = monitor.finalize_metrics()
            
            # Record results
            execution_time = end_time - start_time
            memory_usage = (end_memory - start_memory) / 1024 / 1024  # MB
            
            results['execution_times'].append(execution_time)
            results['memory_usage'].append(memory_usage)
            results['throughput'].append(metrics.throughput)
            
        # Calculate statistics
        results['avg_execution_time'] = np.mean(results['execution_times'])
        results['std_execution_time'] = np.std(results['execution_times'])
        results['avg_memory_usage'] = np.mean(results['memory_usage'])
        results['avg_throughput'] = np.mean(results['throughput'])
        
        self.benchmark_results[config_name] = results
        
        print(f"  Average execution time: {results['avg_execution_time']:.2f}s")
        print(f"  Average memory usage: {results['avg_memory_usage']:.2f}MB")
        print(f"  Average throughput: {results['avg_throughput']:.2f} ops/sec")
        
        return results
        
    def compare_configurations(self) -> str:
        """Generate a comparison report for all benchmarked configurations."""
        if not self.benchmark_results:
            return "No benchmark results available."
            
        report = "Configuration Comparison Report\n"
        report += "==============================\n\n"
        
        # Find the fastest configuration
        fastest_config = min(
            self.benchmark_results.keys(),
            key=lambda x: self.benchmark_results[x]['avg_execution_time']
        )
        
        fastest_time = self.benchmark_results[fastest_config]['avg_execution_time']
        
        for config_name, results in self.benchmark_results.items():
            speedup = fastest_time / results['avg_execution_time']
            report += f"{config_name}:\n"
            report += f"  Execution time: {results['avg_execution_time']:.2f}s (±{results['std_execution_time']:.2f}s)\n"
            report += f"  Memory usage: {results['avg_memory_usage']:.2f}MB\n"
            report += f"  Throughput: {results['avg_throughput']:.2f} ops/sec\n"
            report += f"  Speedup vs fastest: {speedup:.2f}x\n\n"
            
        return report
        
    def save_benchmark_results(self, output_file: str):
        """Save benchmark results to a JSON file."""
        with open(output_file, 'w') as f:
            json.dump(self.benchmark_results, f, indent=2, default=str)
            
    def load_benchmark_results(self, input_file: str):
        """Load benchmark results from a JSON file."""
        with open(input_file, 'r') as f:
            self.benchmark_results = json.load(f)


# Utility functions for easy performance monitoring
def quick_benchmark(simulation_func, iterations: int = 3) -> Dict[str, Any]:
    """Quick benchmark of a simulation function."""
    benchmark = PerformanceBenchmark()
    return benchmark.benchmark_configuration("Quick Test", simulation_func, iterations)


def monitor_simulation(simulation_func) -> PerformanceMetrics:
    """Monitor a single simulation run."""
    monitor = PerformanceMonitor()
    monitor.start_monitoring()
    
    try:
        simulation_func()
    finally:
        monitor.stop_monitoring()
        
    return monitor.finalize_metrics()

