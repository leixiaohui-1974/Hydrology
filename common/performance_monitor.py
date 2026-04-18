"""Performance monitoring module for the Hydrology framework.

This module provides comprehensive performance monitoring capabilities
including memory usage, computation time, and resource consumption tracking.
"""
import time
import psutil
import threading
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import os
from collections import defaultdict, deque
import functools
import tracemalloc
import gc


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""
    timestamp: datetime
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0
    gpu_memory_mb: float = 0.0
    gpu_utilization: float = 0.0
    custom_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class TimingResult:
    """Container for timing results."""
    name: str
    duration_seconds: float
    start_time: datetime
    end_time: datetime
    memory_before_mb: float
    memory_after_mb: float
    memory_peak_mb: float
    cpu_time_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class PerformanceTimer:
    """Context manager for timing operations with detailed metrics."""
    
    def __init__(self, name: str, monitor: Optional['PerformanceMonitor'] = None) -> None:
        self.name: str = name
        self.monitor: Optional['PerformanceMonitor'] = monitor
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.start_cpu_time: Optional[float] = None
        self.end_cpu_time: Optional[float] = None
        self.memory_before: Optional[float] = None
        self.memory_after: Optional[float] = None
        self.memory_peak: Optional[float] = None
        self.process: Any = psutil.Process()
        
    def __enter__(self) -> 'PerformanceTimer':
        # Start memory tracking
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        
        self.start_time = datetime.now()
        self.start_cpu_time = self.process.cpu_times().user + self.process.cpu_times().system
        self.memory_before = self.process.memory_info().rss / 1024 / 1024  # MB
        
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Optional[TimingResult]:
        self.end_time = datetime.now()
        self.end_cpu_time = self.process.cpu_times().user + self.process.cpu_times().system
        self.memory_after = self.process.memory_info().rss / 1024 / 1024  # MB
        
        # Get peak memory usage
        if tracemalloc.is_tracing():
            current, peak = tracemalloc.get_traced_memory()
            self.memory_peak = peak / 1024 / 1024  # MB
        else:
            self.memory_peak = self.memory_after
        
        # Create timing result
        result = TimingResult(
            name=self.name,
            duration_seconds=(self.end_time - self.start_time).total_seconds(),
            start_time=self.start_time,
            end_time=self.end_time,
            memory_before_mb=self.memory_before,
            memory_after_mb=self.memory_after,
            memory_peak_mb=self.memory_peak,
            cpu_time_seconds=self.end_cpu_time - self.start_cpu_time
        )
        
        # Report to monitor if available
        if self.monitor:
            self.monitor.record_timing(result)
        
        return result
    
    @property
    def duration(self) -> float:
        """Get duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class MemoryProfiler:
    """Advanced memory profiling utilities."""
    
    def __init__(self) -> None:
        self.process: Any = psutil.Process()
        self.snapshots: List[Dict[str, Any]] = []
        self.tracking_enabled: bool = False
    
    def start_tracking(self) -> None:
        """Start memory tracking."""
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        self.tracking_enabled = True
        self.take_snapshot("start")
    
    def stop_tracking(self) -> None:
        """Stop memory tracking."""
        if self.tracking_enabled:
            self.take_snapshot("end")
            self.tracking_enabled = False
    
    def take_snapshot(self, label: Optional[str] = None) -> Optional[Any]:
        """Take a memory snapshot."""
        if not tracemalloc.is_tracing():
            return None
        
        snapshot = tracemalloc.take_snapshot()
        self.snapshots.append({
            'label': label or f"snapshot_{len(self.snapshots)}",
            'timestamp': datetime.now(),
            'snapshot': snapshot,
            'rss_mb': self.process.memory_info().rss / 1024 / 1024
        })
        
        return snapshot
    
    def get_top_memory_consumers(self, limit: int = 10) -> List[Dict]:
        """Get top memory consuming code locations."""
        if not self.snapshots:
            return []
        
        latest_snapshot = self.snapshots[-1]['snapshot']
        top_stats = latest_snapshot.statistics('lineno')
        
        results = []
        for stat in top_stats[:limit]:
            results.append({
                'filename': stat.traceback.format()[0],
                'size_mb': stat.size / 1024 / 1024,
                'count': stat.count
            })
        
        return results
    
    def compare_snapshots(self, start_label: str, end_label: str) -> Dict:
        """Compare two memory snapshots."""
        start_snapshot = None
        end_snapshot = None
        
        for snap in self.snapshots:
            if snap['label'] == start_label:
                start_snapshot = snap
            elif snap['label'] == end_label:
                end_snapshot = snap
        
        if not start_snapshot or not end_snapshot:
            return {}
        
        # Compare snapshots
        top_stats = end_snapshot['snapshot'].compare_to(
            start_snapshot['snapshot'], 'lineno'
        )
        
        results = {
            'total_increase_mb': (end_snapshot['rss_mb'] - start_snapshot['rss_mb']),
            'top_increases': []
        }
        
        for stat in top_stats[:10]:
            if stat.size_diff > 0:
                results['top_increases'].append({
                    'filename': stat.traceback.format()[0],
                    'size_diff_mb': stat.size_diff / 1024 / 1024,
                    'count_diff': stat.count_diff
                })
        
        return results


class ResourceMonitor:
    """Monitor system resources continuously."""
    
    def __init__(self, interval_seconds: float = 1.0) -> None:
        self.interval: float = interval_seconds
        self.monitoring: bool = False
        self.metrics_history: deque = deque(maxlen=1000)  # Keep last 1000 measurements
        self.thread: Optional[threading.Thread] = None
        self.process: Any = psutil.Process()
        
        # Initialize baseline measurements
        self.initial_disk_io: Optional[Any] = psutil.disk_io_counters()
        self.initial_network_io: Optional[Any] = psutil.net_io_counters()
    
    def start_monitoring(self) -> None:
        """Start continuous resource monitoring."""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
    
    def stop_monitoring(self) -> None:
        """Stop resource monitoring."""
        self.monitoring = False
        if self.thread:
            self.thread.join(timeout=2.0)
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self.monitoring:
            try:
                metrics = self._collect_metrics()
                self.metrics_history.append(metrics)
                time.sleep(self.interval)
            except Exception as e:
                logging.warning(f"Error in resource monitoring: {e}")
                time.sleep(self.interval)
    
    def _collect_metrics(self) -> PerformanceMetrics:
        """Collect current system metrics."""
        # CPU and memory
        cpu_percent = self.process.cpu_percent()
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        memory_percent = self.process.memory_percent()
        
        # Disk I/O
        disk_io = psutil.disk_io_counters()
        disk_read_mb = 0.0
        disk_write_mb = 0.0
        if disk_io and self.initial_disk_io:
            disk_read_mb = (disk_io.read_bytes - self.initial_disk_io.read_bytes) / 1024 / 1024
            disk_write_mb = (disk_io.write_bytes - self.initial_disk_io.write_bytes) / 1024 / 1024
        
        # Network I/O
        network_io = psutil.net_io_counters()
        network_sent_mb = 0.0
        network_recv_mb = 0.0
        if network_io and self.initial_network_io:
            network_sent_mb = (network_io.bytes_sent - self.initial_network_io.bytes_sent) / 1024 / 1024
            network_recv_mb = (network_io.bytes_recv - self.initial_network_io.bytes_recv) / 1024 / 1024
        
        # GPU metrics (if available)
        gpu_memory_mb = 0.0
        gpu_utilization = 0.0
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]  # Use first GPU
                gpu_memory_mb = gpu.memoryUsed
                gpu_utilization = gpu.load * 100
        except ImportError:
            pass  # GPU monitoring not available
        
        return PerformanceMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            memory_percent=memory_percent,
            disk_io_read_mb=disk_read_mb,
            disk_io_write_mb=disk_write_mb,
            network_sent_mb=network_sent_mb,
            network_recv_mb=network_recv_mb,
            gpu_memory_mb=gpu_memory_mb,
            gpu_utilization=gpu_utilization
        )
    
    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """Get the most recent metrics."""
        if self.metrics_history:
            return self.metrics_history[-1]
        return None
    
    def get_metrics_summary(self, duration_minutes: int = 5) -> Dict[str, Any]:
        """Get summary statistics for recent metrics."""
        if not self.metrics_history:
            return {}
        
        # Filter metrics within time window
        cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
        recent_metrics = [
            m for m in self.metrics_history 
            if m.timestamp >= cutoff_time
        ]
        
        if not recent_metrics:
            return {}
        
        # Calculate statistics
        cpu_values = [m.cpu_percent for m in recent_metrics]
        memory_values = [m.memory_mb for m in recent_metrics]
        
        return {
            'duration_minutes': duration_minutes,
            'sample_count': len(recent_metrics),
            'cpu_percent': {
                'mean': sum(cpu_values) / len(cpu_values),
                'max': max(cpu_values),
                'min': min(cpu_values)
            },
            'memory_mb': {
                'mean': sum(memory_values) / len(memory_values),
                'max': max(memory_values),
                'min': min(memory_values)
            },
            'latest_metrics': recent_metrics[-1]
        }


class PerformanceMonitor:
    """Main performance monitoring coordinator."""
    
    def __init__(self, 
                 auto_start_resource_monitoring: bool = True,
                 resource_monitoring_interval: float = 1.0,
                 log_file: Optional[str] = None) -> None:
        self.resource_monitor: ResourceMonitor = ResourceMonitor(resource_monitoring_interval)
        self.memory_profiler: MemoryProfiler = MemoryProfiler()
        self.timing_results: List[TimingResult] = []
        self.custom_metrics: defaultdict = defaultdict(list)
        self.alerts: List[Dict[str, Any]] = []
        self.log_file: Optional[str] = log_file
        
        # Performance thresholds
        self.thresholds: Dict[str, float] = {
            'memory_mb': 1000,  # Alert if memory usage > 1GB
            'cpu_percent': 80,  # Alert if CPU usage > 80%
            'duration_seconds': 60,  # Alert if operation takes > 60s
        }
        
        # Setup logging
        self.logger: logging.Logger = logging.getLogger('performance_monitor')
        if log_file:
            handler = logging.FileHandler(log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        if auto_start_resource_monitoring:
            self.start_monitoring()
    
    def start_monitoring(self) -> None:
        """Start all monitoring components."""
        self.resource_monitor.start_monitoring()
        self.memory_profiler.start_tracking()
        self.logger.info("Performance monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop all monitoring components."""
        self.resource_monitor.stop_monitoring()
        self.memory_profiler.stop_tracking()
        self.logger.info("Performance monitoring stopped")
    
    def timer(self, name: str) -> PerformanceTimer:
        """Create a performance timer."""
        return PerformanceTimer(name, self)
    
    def record_timing(self, result: TimingResult) -> None:
        """Record a timing result."""
        self.timing_results.append(result)
        
        # Check for performance alerts
        self._check_timing_alerts(result)
        
        # Log the result
        self.logger.info(
            f"Timing: {result.name} took {result.duration_seconds:.3f}s, "
            f"memory: {result.memory_before_mb:.1f} -> {result.memory_after_mb:.1f} MB"
        )
    
    def record_custom_metric(self, name: str, value: float, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record a custom metric."""
        metric_data = {
            'timestamp': datetime.now(),
            'value': value,
            'metadata': metadata or {}
        }
        self.custom_metrics[name].append(metric_data)
        
        self.logger.info(f"Custom metric: {name} = {value}")
    
    def _check_timing_alerts(self, result: TimingResult):
        """Check timing result against thresholds."""
        alerts = []
        
        if result.duration_seconds > self.thresholds['duration_seconds']:
            alerts.append(f"Long operation: {result.name} took {result.duration_seconds:.1f}s")
        
        if result.memory_after_mb > self.thresholds['memory_mb']:
            alerts.append(f"High memory usage: {result.name} used {result.memory_after_mb:.1f} MB")
        
        memory_increase = result.memory_after_mb - result.memory_before_mb
        if memory_increase > 100:  # Alert if memory increased by > 100MB
            alerts.append(f"Large memory increase: {result.name} increased memory by {memory_increase:.1f} MB")
        
        for alert in alerts:
            self.alerts.append({
                'timestamp': datetime.now(),
                'message': alert,
                'result': result
            })
            self.logger.warning(alert)
    
    def get_performance_report(self) -> Dict:
        """Generate comprehensive performance report."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'monitoring_duration': None,
            'resource_summary': {},
            'timing_summary': {},
            'memory_analysis': {},
            'custom_metrics': {},
            'alerts': self.alerts[-10:],  # Last 10 alerts
            'recommendations': []
        }
        
        # Resource summary
        resource_summary = self.resource_monitor.get_metrics_summary()
        if resource_summary:
            report['resource_summary'] = resource_summary
        
        # Timing summary
        if self.timing_results:
            durations = [r.duration_seconds for r in self.timing_results]
            memory_increases = [
                r.memory_after_mb - r.memory_before_mb 
                for r in self.timing_results
            ]
            
            report['timing_summary'] = {
                'total_operations': len(self.timing_results),
                'total_time_seconds': sum(durations),
                'average_duration_seconds': sum(durations) / len(durations),
                'longest_operation': max(self.timing_results, key=lambda x: x.duration_seconds).name,
                'average_memory_increase_mb': sum(memory_increases) / len(memory_increases),
                'operations_by_name': self._group_timing_results_by_name()
            }
        
        # Memory analysis
        memory_analysis = self.memory_profiler.get_top_memory_consumers()
        if memory_analysis:
            report['memory_analysis'] = {
                'top_consumers': memory_analysis,
                'total_snapshots': len(self.memory_profiler.snapshots)
            }
        
        # Custom metrics summary
        for name, values in self.custom_metrics.items():
            if values:
                numeric_values = [v['value'] for v in values]
                report['custom_metrics'][name] = {
                    'count': len(values),
                    'latest': values[-1]['value'],
                    'average': sum(numeric_values) / len(numeric_values),
                    'max': max(numeric_values),
                    'min': min(numeric_values)
                }
        
        # Generate recommendations
        report['recommendations'] = self._generate_recommendations(report)
        
        return report
    
    def _group_timing_results_by_name(self) -> Dict:
        """Group timing results by operation name."""
        grouped = defaultdict(list)
        for result in self.timing_results:
            grouped[result.name].append(result)
        
        summary = {}
        for name, results in grouped.items():
            durations = [r.duration_seconds for r in results]
            summary[name] = {
                'count': len(results),
                'total_time_seconds': sum(durations),
                'average_duration_seconds': sum(durations) / len(durations),
                'max_duration_seconds': max(durations),
                'min_duration_seconds': min(durations)
            }
        
        return summary
    
    def _generate_recommendations(self, report: Dict) -> List[str]:
        """Generate performance recommendations based on the report."""
        recommendations = []
        
        # Check resource usage
        if 'resource_summary' in report and report['resource_summary']:
            cpu_max = report['resource_summary'].get('cpu_percent', {}).get('max', 0)
            memory_max = report['resource_summary'].get('memory_mb', {}).get('max', 0)
            
            if cpu_max > 90:
                recommendations.append(
                    "High CPU usage detected. Consider optimizing computational algorithms "
                    "or implementing parallel processing."
                )
            
            if memory_max > 2000:  # > 2GB
                recommendations.append(
                    "High memory usage detected. Consider implementing data streaming, "
                    "chunking, or memory-efficient algorithms."
                )
        
        # Check timing patterns
        if 'timing_summary' in report and report['timing_summary']:
            avg_duration = report['timing_summary'].get('average_duration_seconds', 0)
            if avg_duration > 10:
                recommendations.append(
                    "Long average operation duration. Consider caching, "
                    "pre-computation, or algorithm optimization."
                )
        
        # Check for memory leaks
        if len(self.alerts) > 5:
            memory_alerts = [a for a in self.alerts if 'memory' in a['message'].lower()]
            if len(memory_alerts) > 2:
                recommendations.append(
                    "Multiple memory-related alerts detected. "
                    "Check for potential memory leaks or inefficient memory usage."
                )
        
        return recommendations
    
    def save_report(self, filename: str):
        """Save performance report to file."""
        report = self.get_performance_report()
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        self.logger.info(f"Performance report saved to {filename}")
    
    def set_thresholds(self, **thresholds):
        """Update performance thresholds."""
        self.thresholds.update(thresholds)
        self.logger.info(f"Performance thresholds updated: {thresholds}")


def performance_monitor(name: str = None, monitor: PerformanceMonitor = None):
    """Decorator for monitoring function performance."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            operation_name = name or f"{func.__module__}.{func.__name__}"
            
            if monitor:
                with monitor.timer(operation_name):
                    return func(*args, **kwargs)
            else:
                with PerformanceTimer(operation_name):
                    return func(*args, **kwargs)
        
        return wrapper
    return decorator


# Global performance monitor instance
_global_monitor = None

def get_global_monitor() -> PerformanceMonitor:
    """Get or create global performance monitor."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor

def set_global_monitor(monitor: PerformanceMonitor):
    """Set global performance monitor."""
    global _global_monitor
    _global_monitor = monitor


if __name__ == '__main__':
    # Example usage
    print("Performance Monitor Example")
    print("=" * 40)
    
    # Create monitor
    monitor = PerformanceMonitor(log_file='performance.log')
    
    # Example timed operation
    with monitor.timer("example_operation"):
        # Simulate some work
        import numpy as np
        data = np.random.random((1000, 1000))
        result = np.dot(data, data.T)
        time.sleep(0.1)
    
    # Record custom metric
    monitor.record_custom_metric("data_size", 1000000)
    
    # Wait a bit for resource monitoring
    time.sleep(2)
    
    # Generate and display report
    report = monitor.get_performance_report()
    print("\nPerformance Report:")
    print(f"Total operations: {report.get('timing_summary', {}).get('total_operations', 0)}")
    
    if 'resource_summary' in report:
        cpu_info = report['resource_summary'].get('cpu_percent', {})
        memory_info = report['resource_summary'].get('memory_mb', {})
        print(f"CPU usage: {cpu_info.get('mean', 0):.1f}% (max: {cpu_info.get('max', 0):.1f}%)")
        print(f"Memory usage: {memory_info.get('mean', 0):.1f} MB (max: {memory_info.get('max', 0):.1f} MB)")
    
    # Save report
    monitor.save_report('performance_report.json')
    
    # Stop monitoring
    monitor.stop_monitoring()
    
    print("\nPerformance monitoring example completed!")