#!/usr/bin/env python3
"""Tests for the performance monitoring system.

This module contains tests to verify the functionality of the performance
monitoring components including timing, resource monitoring, and reporting.
"""
import pytest
import time
import tempfile
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

try:
    from common.performance_monitor import (
        PerformanceMonitor,
        PerformanceTimer,
        MemoryProfiler,
        ResourceMonitor,
        PerformanceMetrics
    )
    PERFORMANCE_AVAILABLE = True
except ImportError:
    PERFORMANCE_AVAILABLE = False


@pytest.mark.skipif(not PERFORMANCE_AVAILABLE, reason="Performance monitoring not available")
class TestPerformanceTimer:
    """Test the PerformanceTimer class."""
    
    def test_timer_context_manager(self):
        """Test timer as context manager."""
        timer = PerformanceTimer("test_operation")
        
        with timer:
            time.sleep(0.1)  # Sleep for 100ms
        
        result = timer.get_result()
        assert result['operation_name'] == "test_operation"
        assert result['duration_seconds'] >= 0.1
        assert result['duration_seconds'] < 0.2  # Should be close to 0.1
        assert 'cpu_time_seconds' in result
        assert 'memory_usage_mb' in result
    
    def test_timer_manual_start_stop(self):
        """Test manual timer start/stop."""
        timer = PerformanceTimer("manual_test")
        
        timer.start()
        time.sleep(0.05)
        timer.stop()
        
        result = timer.get_result()
        assert result['operation_name'] == "manual_test"
        assert result['duration_seconds'] >= 0.05
        assert result['duration_seconds'] < 0.1
    
    def test_timer_with_custom_metrics(self):
        """Test timer with custom metrics."""
        timer = PerformanceTimer("custom_metrics_test")
        
        with timer:
            timer.add_custom_metric("items_processed", 100)
            timer.add_custom_metric("error_count", 0)
            time.sleep(0.01)
        
        result = timer.get_result()
        assert result['custom_metrics']['items_processed'] == 100
        assert result['custom_metrics']['error_count'] == 0


@pytest.mark.skipif(not PERFORMANCE_AVAILABLE, reason="Performance monitoring not available")
class TestPerformanceMetrics:
    """Test the PerformanceMetrics class."""
    
    def test_metrics_collection(self):
        """Test basic metrics collection."""
        metrics = PerformanceMetrics()
        
        # Collect metrics
        current_metrics = metrics.get_current_metrics()
        
        # Check that basic metrics are present
        assert 'cpu_percent' in current_metrics
        assert 'memory_mb' in current_metrics
        assert 'timestamp' in current_metrics
        
        # CPU should be a reasonable value
        assert 0 <= current_metrics['cpu_percent'] <= 100
        
        # Memory should be positive
        assert current_metrics['memory_mb'] > 0
    
    def test_metrics_history(self):
        """Test metrics history tracking."""
        metrics = PerformanceMetrics(history_size=5)
        
        # Collect several metrics
        for i in range(3):
            metrics.collect_metrics()
            time.sleep(0.01)
        
        history = metrics.get_metrics_history()
        assert len(history) == 3
        
        # Check that timestamps are increasing
        timestamps = [m['timestamp'] for m in history]
        assert timestamps == sorted(timestamps)


@pytest.mark.skipif(not PERFORMANCE_AVAILABLE, reason="Performance monitoring not available")
class TestResourceMonitor:
    """Test the ResourceMonitor class."""
    
    def test_monitor_start_stop(self):
        """Test starting and stopping the resource monitor."""
        monitor = ResourceMonitor(interval=0.1)
        
        # Start monitoring
        monitor.start()
        assert monitor.is_running()
        
        # Let it collect some data
        time.sleep(0.3)
        
        # Stop monitoring
        monitor.stop()
        assert not monitor.is_running()
        
        # Check that data was collected
        history = monitor.get_metrics_history()
        assert len(history) >= 2  # Should have collected at least 2 samples
    
    def test_monitor_metrics_format(self):
        """Test the format of collected metrics."""
        monitor = ResourceMonitor(interval=0.1)
        
        monitor.start()
        time.sleep(0.2)
        monitor.stop()
        
        history = monitor.get_metrics_history()
        assert len(history) > 0
        
        # Check first metric
        metric = history[0]
        required_keys = ['timestamp', 'cpu_percent', 'memory_mb']
        for key in required_keys:
            assert key in metric


@pytest.mark.skipif(not PERFORMANCE_AVAILABLE, reason="Performance monitoring not available")
class TestMemoryProfiler:
    """Test the MemoryProfiler class."""
    
    def test_memory_snapshot(self):
        """Test taking memory snapshots."""
        profiler = MemoryProfiler()
        
        # Take initial snapshot
        snapshot1 = profiler.take_snapshot()
        assert snapshot1 is not None
        
        # Allocate some memory
        large_list = [i for i in range(10000)]
        
        # Take another snapshot
        snapshot2 = profiler.take_snapshot()
        assert snapshot2 is not None
        
        # Compare snapshots
        diff = profiler.compare_snapshots(snapshot1, snapshot2)
        assert diff is not None
        
        # Clean up
        del large_list
    
    def test_memory_tracking(self):
        """Test memory usage tracking."""
        profiler = MemoryProfiler()
        
        # Start tracking
        profiler.start_tracking()
        
        # Do some memory operations
        data = []
        for i in range(1000):
            data.append(f"item_{i}")
        
        # Stop tracking
        stats = profiler.stop_tracking()
        
        assert 'peak_memory_mb' in stats
        assert 'memory_increase_mb' in stats
        assert stats['peak_memory_mb'] > 0
        
        # Clean up
        del data


@pytest.mark.skipif(not PERFORMANCE_AVAILABLE, reason="Performance monitoring not available")
class TestPerformanceMonitor:
    """Test the main PerformanceMonitor class."""
    
    def test_monitor_initialization(self):
        """Test monitor initialization."""
        monitor = PerformanceMonitor()
        assert monitor is not None
        assert not monitor.is_monitoring()
    
    def test_monitor_start_stop(self):
        """Test starting and stopping monitoring."""
        monitor = PerformanceMonitor()
        
        # Start monitoring
        monitor.start_monitoring()
        assert monitor.is_monitoring()
        
        # Stop monitoring
        monitor.stop_monitoring()
        assert not monitor.is_monitoring()
    
    def test_timer_context(self):
        """Test using timer context."""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        with monitor.timer("test_operation"):
            time.sleep(0.05)
        
        # Check that timing was recorded
        results = monitor.get_timing_results()
        assert len(results) == 1
        assert results[0]['operation_name'] == "test_operation"
        assert results[0]['duration_seconds'] >= 0.05
        
        monitor.stop_monitoring()
    
    def test_custom_metrics(self):
        """Test recording custom metrics."""
        monitor = PerformanceMonitor()
        
        # Record some custom metrics
        monitor.record_custom_metric("test_metric", 42)
        monitor.record_custom_metric("test_metric", 84)
        monitor.record_custom_metric("another_metric", 100)
        
        # Get custom metrics
        metrics = monitor.get_custom_metrics()
        
        assert "test_metric" in metrics
        assert "another_metric" in metrics
        assert len(metrics["test_metric"]) == 2
        assert metrics["test_metric"][-1] == 84  # Latest value
        assert metrics["another_metric"][-1] == 100
    
    def test_performance_report(self):
        """Test generating performance report."""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        # Do some operations
        with monitor.timer("operation1"):
            time.sleep(0.01)
        
        with monitor.timer("operation2"):
            time.sleep(0.02)
        
        monitor.record_custom_metric("items_processed", 100)
        
        # Wait for some resource data
        time.sleep(0.1)
        
        # Generate report
        report = monitor.get_performance_report()
        
        # Check report structure
        assert 'timing_summary' in report
        assert 'resource_summary' in report
        assert 'custom_metrics' in report
        assert 'recommendations' in report
        
        # Check timing summary
        timing = report['timing_summary']
        assert timing['total_operations'] == 2
        assert 'operations_by_name' in timing
        assert 'operation1' in timing['operations_by_name']
        assert 'operation2' in timing['operations_by_name']
        
        monitor.stop_monitoring()
    
    def test_save_load_report(self):
        """Test saving and loading reports."""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        # Do some operations
        with monitor.timer("test_save_load"):
            time.sleep(0.01)
        
        monitor.record_custom_metric("test_value", 123)
        
        # Generate and save report
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            report_file = f.name
        
        try:
            monitor.save_report(report_file)
            
            # Check that file was created
            assert os.path.exists(report_file)
            
            # Load and verify report
            with open(report_file, 'r') as f:
                loaded_report = json.load(f)
            
            assert 'timing_summary' in loaded_report
            assert 'custom_metrics' in loaded_report
            assert loaded_report['custom_metrics']['test_value']['latest'] == 123
            
        finally:
            # Clean up
            if os.path.exists(report_file):
                os.unlink(report_file)
            monitor.stop_monitoring()
    
    def test_performance_decorator(self):
        """Test the performance monitoring decorator."""
        from common.performance_monitor import performance_monitor
        
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        @performance_monitor("decorated_function", monitor)
        def test_function(x, y):
            time.sleep(0.01)
            return x + y
        
        # Call the decorated function
        result = test_function(2, 3)
        assert result == 5
        
        # Check that timing was recorded
        results = monitor.get_timing_results()
        assert len(results) == 1
        assert results[0]['operation_name'] == "decorated_function"
        
        monitor.stop_monitoring()


@pytest.mark.skipif(not PERFORMANCE_AVAILABLE, reason="Performance monitoring not available")
class TestPerformanceIntegration:
    """Integration tests for the performance monitoring system."""
    
    def test_full_monitoring_workflow(self):
        """Test a complete monitoring workflow."""
        monitor = PerformanceMonitor()
        
        # Start monitoring
        monitor.start_monitoring()
        
        # Simulate a complex workflow
        with monitor.timer("data_loading"):
            # Simulate data loading
            data = list(range(1000))
            time.sleep(0.01)
        
        monitor.record_custom_metric("data_points", len(data))
        
        with monitor.timer("data_processing"):
            # Simulate data processing
            processed = [x * 2 for x in data]
            time.sleep(0.02)
        
        monitor.record_custom_metric("processed_points", len(processed))
        
        with monitor.timer("data_output"):
            # Simulate data output
            result = sum(processed)
            time.sleep(0.005)
        
        monitor.record_custom_metric("final_result", result)
        
        # Wait for resource monitoring
        time.sleep(0.1)
        
        # Generate comprehensive report
        report = monitor.get_performance_report()
        
        # Verify report completeness
        assert report['timing_summary']['total_operations'] == 3
        assert 'data_loading' in report['timing_summary']['operations_by_name']
        assert 'data_processing' in report['timing_summary']['operations_by_name']
        assert 'data_output' in report['timing_summary']['operations_by_name']
        
        assert 'data_points' in report['custom_metrics']
        assert 'processed_points' in report['custom_metrics']
        assert 'final_result' in report['custom_metrics']
        
        assert report['custom_metrics']['data_points']['latest'] == 1000
        assert report['custom_metrics']['processed_points']['latest'] == 1000
        assert report['custom_metrics']['final_result']['latest'] == result
        
        # Check resource monitoring
        assert 'resource_summary' in report
        resource_summary = report['resource_summary']
        if 'cpu_percent' in resource_summary:
            assert 'mean' in resource_summary['cpu_percent']
            assert 'max' in resource_summary['cpu_percent']
        
        # Stop monitoring
        monitor.stop_monitoring()
        
        # Clean up
        del data, processed
    
    def test_error_handling(self):
        """Test error handling in performance monitoring."""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        # Test timer with exception
        try:
            with monitor.timer("error_operation"):
                time.sleep(0.01)
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected
        
        # Check that timing was still recorded
        results = monitor.get_timing_results()
        assert len(results) == 1
        assert results[0]['operation_name'] == "error_operation"
        assert results[0]['duration_seconds'] >= 0.01
        
        monitor.stop_monitoring()


if __name__ == '__main__':
    # Run tests if executed directly
    pytest.main([__file__, '-v'])