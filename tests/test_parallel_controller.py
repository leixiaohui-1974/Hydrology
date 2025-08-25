"""
Tests for the parallel controller functionality.
"""
import unittest
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from unittest.mock import Mock, patch
from common.parallel_controller import ParallelSimulationController, HybridParallelController
from common.base_model import BaseModelComponent


class MockComponent(BaseModelComponent):
    """Mock component for testing."""
    
    def __init__(self, name: str, execution_time: float = 0.1):
        super().__init__(name)
        self.execution_time = execution_time
        self.outflow = 0.0
        self.step_count = 0
        
    def step(self, inflows: dict, dt: float):
        """Mock step method that simulates computation time."""
        import time
        time.sleep(self.execution_time)  # Simulate computation
        self.outflow = sum(inflows.values()) + 1.0
        self.step_count += 1
        
    def get_outflow(self):
        return self.outflow


class TestParallelController(unittest.TestCase):
    """Test cases for the parallel controller."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.controller = ParallelSimulationController(max_workers=2)
        
    def test_identify_parallel_groups(self):
        """Test identification of parallel execution groups."""
        # Add components
        for i in range(3):
            component = MockComponent(f"Component{i}")
            self.controller.add_component(component)
            
        # Connect in a chain: Component0 -> Component1 -> Component2
        self.controller.connect("Component0", "Component1")
        self.controller.connect("Component1", "Component2")
        
        # Identify parallel groups
        groups = self.controller._identify_parallel_groups()
        
        # Should have 3 groups since components depend on each other
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0], ["Component0"])
        self.assertEqual(groups[1], ["Component1"])
        self.assertEqual(groups[2], ["Component2"])
        
    def test_identify_parallel_groups_independent(self):
        """Test identification of independent parallel groups."""
        # Add components
        for i in range(3):
            component = MockComponent(f"Component{i}")
            self.controller.add_component(component)
            
        # No connections - all components are independent
        groups = self.controller._identify_parallel_groups()
        
        # Should have 1 group with all components
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 3)
        
    def test_parallel_execution_stats(self):
        """Test parallelization statistics."""
        # Add components
        for i in range(4):
            component = MockComponent(f"Component{i}")
            self.controller.add_component(component)
            
        # Connect in parallel branches
        self.controller.connect("Component0", "Component1")
        self.controller.connect("Component0", "Component2")
        self.controller.connect("Component1", "Component3")
        self.controller.connect("Component2", "Component3")
        
        stats = self.controller.get_parallelization_stats()
        
        self.assertEqual(stats['max_workers'], 2)
        self.assertEqual(stats['use_processes'], True)
        self.assertGreater(stats['parallel_groups'], 1)
        
    @patch('concurrent.futures.ProcessPoolExecutor')
    def test_execute_group_parallel(self, mock_executor):
        """Test parallel execution of a group."""
        # Mock the executor
        mock_executor_instance = Mock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance
        
        # Mock future results
        mock_future1 = Mock()
        mock_future1.result.return_value = 10.0
        mock_future2 = Mock()
        mock_future2.result.return_value = 20.0
        
        mock_executor_instance.submit.side_effect = [mock_future1, mock_future2]
        mock_executor_instance.submit.return_value = mock_future1
        
        # Add components
        component1 = MockComponent("Component1")
        component2 = MockComponent("Component2")
        self.controller.add_component(component1)
        self.controller.add_component(component2)
        
        # Execute group in parallel
        group = ["Component1", "Component2"]
        inflows = {"rainfall": 5.0}
        
        results = self.controller._execute_group_parallel(group, inflows)
        
        # Verify results
        self.assertEqual(len(results), 2)
        self.assertIn("Component1", results)
        self.assertIn("Component2", results)
        
    def test_hybrid_controller_component_classification(self):
        """Test hybrid controller's component classification."""
        hybrid_controller = HybridParallelController()
        
        # Test CPU-intensive component classification
        component = MockComponent("HydrologicalModel")
        component_type = type(component).__name__
        
        # Mock the component type for testing
        with patch.object(type(component), '__name__', 'HydrologicalModel'):
            classification = hybrid_controller._classify_component("Component1")
            self.assertEqual(classification, 'cpu')
            
    def test_hybrid_controller_io_classification(self):
        """Test hybrid controller's I/O component classification."""
        hybrid_controller = HybridParallelController()
        
        # Test I/O-intensive component classification
        component = MockComponent("DataLoader")
        component_type = type(component).__name__
        
        # Mock the component type for testing
        with patch.object(type(component), '__name__', 'DataLoader'):
            classification = hybrid_controller._classify_component("Component1")
            self.assertEqual(classification, 'io')
            
    def test_controller_inheritance(self):
        """Test that parallel controllers inherit from base controller."""
        parallel_controller = ParallelSimulationController()
        hybrid_controller = HybridParallelController()
        
        # Both should have the basic controller methods
        self.assertTrue(hasattr(parallel_controller, 'add_component'))
        self.assertTrue(hasattr(parallel_controller, 'connect'))
        self.assertTrue(hasattr(parallel_controller, 'run'))
        
        self.assertTrue(hasattr(hybrid_controller, 'add_component'))
        self.assertTrue(hasattr(hybrid_controller, 'connect'))
        self.assertTrue(hasattr(hybrid_controller, 'run'))
        
    def test_worker_count_validation(self):
        """Test worker count validation and defaults."""
        # Test with explicit worker count
        controller = ParallelSimulationController(max_workers=4)
        self.assertEqual(controller.max_workers, 4)
        
        # Test with None (should use CPU count)
        controller = ParallelSimulationController(max_workers=None)
        self.assertIsNotNone(controller.max_workers)
        self.assertGreater(controller.max_workers, 0)
        
    def test_process_vs_thread_selection(self):
        """Test process vs thread selection."""
        # Test process-based controller
        process_controller = ParallelSimulationController(use_processes=True)
        self.assertTrue(process_controller.use_processes)
        
        # Test thread-based controller
        thread_controller = ParallelSimulationController(use_processes=False)
        self.assertFalse(thread_controller.use_processes)


class TestPerformanceMonitoring(unittest.TestCase):
    """Test cases for performance monitoring."""
    
    def setUp(self):
        """Set up test fixtures."""
        from utils.performance_monitor import PerformanceMonitor
        self.monitor = PerformanceMonitor(enable_monitoring=True)
        
    def test_metrics_initialization(self):
        """Test performance metrics initialization."""
        from utils.performance_monitor import PerformanceMetrics
        
        metrics = PerformanceMetrics()
        self.assertEqual(metrics.execution_time, 0.0)
        self.assertEqual(metrics.memory_usage, 0.0)
        self.assertEqual(metrics.throughput, 0.0)
        
    def test_operation_measurement(self):
        """Test operation measurement context manager."""
        with self.monitor.measure_operation("test_operation"):
            # Simulate some work
            import time
            time.sleep(0.01)
            
        # Check that operation was recorded
        self.assertEqual(self.monitor.operation_count, 1)
        self.assertGreater(self.monitor.current_metrics.execution_time, 0)
        
    def test_metrics_finalization(self):
        """Test metrics finalization."""
        # Record some operations
        with self.monitor.measure_operation("test1"):
            import time
            time.sleep(0.01)
            
        with self.monitor.measure_operation("test2"):
            time.sleep(0.01)
            
        # Finalize metrics
        metrics = self.monitor.finalize_metrics()
        
        # Check metrics
        self.assertEqual(metrics.throughput, 2.0 / metrics.execution_time)
        self.assertGreater(metrics.memory_efficiency, 0)
        
    def test_benchmark_basic(self):
        """Test basic benchmarking functionality."""
        from utils.performance_monitor import PerformanceBenchmark
        
        benchmark = PerformanceBenchmark()
        
        def test_function():
            import time
            time.sleep(0.01)
            
        # Run benchmark
        results = benchmark.benchmark_configuration("test", test_function, iterations=2)
        
        # Check results structure
        self.assertIn('execution_times', results)
        self.assertIn('avg_execution_time', results)
        self.assertIn('avg_memory_usage', results)
        self.assertEqual(len(results['execution_times']), 2)


if __name__ == '__main__':
    unittest.main()

