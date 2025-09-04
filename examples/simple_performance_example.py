#!/usr/bin/env python3
"""Simple performance monitoring example using only standard library.

This script demonstrates basic performance monitoring functionality
without requiring external dependencies like numpy or scipy.
"""
import sys
import os
import time
import random
import math
from pathlib import Path

# Add the parent directory to the path so we can import from the framework
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from common import (
        setup_performance_monitoring,
        PerformanceMonitor,
        PerformanceTimer,
        get_system_info,
        check_dependencies
    )
    PERFORMANCE_AVAILABLE = True
except ImportError as e:
    print(f"Performance monitoring not available: {e}")
    PERFORMANCE_AVAILABLE = False


def simulate_simple_computation():
    """Simulate a simple computational task."""
    print("Simulating basic mathematical computation...")
    
    # Generate some data
    data = [random.random() for _ in range(10000)]
    
    # Perform calculations
    results = []
    for i, value in enumerate(data):
        # Some mathematical operations
        result = math.sin(value) * math.cos(value * 2)
        result += math.sqrt(abs(value))
        result *= math.log(value + 1)
        results.append(result)
        
        # Simulate progress reporting
        if i % 2000 == 0:
            print(f"Processed {i} items...")
    
    # Calculate statistics
    total = sum(results)
    average = total / len(results)
    maximum = max(results)
    minimum = min(results)
    
    print(f"Computation completed:")
    print(f"  Total: {total:.4f}")
    print(f"  Average: {average:.4f}")
    print(f"  Max: {maximum:.4f}")
    print(f"  Min: {minimum:.4f}")
    
    return results


def simulate_data_processing():
    """Simulate data processing operations."""
    print("Simulating data processing...")
    
    # Create synthetic data
    raw_data = []
    for i in range(1000):
        # Simulate time series data
        timestamp = i * 0.1
        value = math.sin(timestamp) + random.random() * 0.1
        raw_data.append((timestamp, value))
    
    # Process data - smoothing
    smoothed_data = []
    window_size = 5
    
    for i in range(len(raw_data)):
        start_idx = max(0, i - window_size // 2)
        end_idx = min(len(raw_data), i + window_size // 2 + 1)
        
        window_values = [raw_data[j][1] for j in range(start_idx, end_idx)]
        smoothed_value = sum(window_values) / len(window_values)
        
        smoothed_data.append((raw_data[i][0], smoothed_value))
    
    # Calculate trends
    trends = []
    for i in range(1, len(smoothed_data)):
        trend = smoothed_data[i][1] - smoothed_data[i-1][1]
        trends.append(trend)
    
    print(f"Processed {len(raw_data)} data points")
    print(f"Calculated {len(trends)} trend values")
    
    return smoothed_data, trends


def simulate_memory_operations():
    """Simulate memory-intensive operations."""
    print("Simulating memory operations...")
    
    # Create and manipulate data structures
    data_structures = []
    
    for i in range(5):
        # Create lists of different sizes
        size = 1000 * (i + 1)
        data_list = [random.random() for _ in range(size)]
        
        # Create dictionary
        data_dict = {f"key_{j}": value for j, value in enumerate(data_list)}
        
        # Store structures
        data_structures.append({
            'list': data_list,
            'dict': data_dict,
            'size': size
        })
        
        print(f"Created data structure {i+1} with {size} elements")
        
        # Simulate some processing delay
        time.sleep(0.05)
    
    # Process the data structures
    total_elements = 0
    for structure in data_structures:
        # Perform operations on the data
        data_list = structure['list']
        
        # Sort the list
        sorted_data = sorted(data_list)
        
        # Find statistics
        total = sum(sorted_data)
        count = len(sorted_data)
        average = total / count if count > 0 else 0
        
        total_elements += count
        
        print(f"Processed structure with {count} elements, average: {average:.4f}")
    
    print(f"Total elements processed: {total_elements}")
    
    # Clean up
    del data_structures
    
    return total_elements


def run_simple_performance_example():
    """Run the simple performance monitoring example."""
    print("=" * 60)
    print("🌊 Hydrology Framework - Simple Performance Example")
    print("=" * 60)
    
    if not PERFORMANCE_AVAILABLE:
        print("❌ Performance monitoring is not available.")
        print("This example will run basic operations without monitoring.")
        print()
        
        # Run basic operations without monitoring
        print("Running basic operations...")
        
        start_time = time.time()
        simulate_simple_computation()
        comp_time = time.time() - start_time
        print(f"Computation took: {comp_time:.3f} seconds")
        
        start_time = time.time()
        simulate_data_processing()
        proc_time = time.time() - start_time
        print(f"Data processing took: {proc_time:.3f} seconds")
        
        start_time = time.time()
        simulate_memory_operations()
        mem_time = time.time() - start_time
        print(f"Memory operations took: {mem_time:.3f} seconds")
        
        total_time = comp_time + proc_time + mem_time
        print(f"\nTotal execution time: {total_time:.3f} seconds")
        
        return
    
    # Check system information
    print("\n📊 System Information:")
    try:
        system_info = get_system_info()
        for key, value in system_info.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
    except Exception as e:
        print(f"  Could not retrieve system info: {e}")
    
    # Check dependencies
    print("\n📦 Dependency Status:")
    try:
        deps = check_dependencies()
        for category, category_deps in deps.items():
            print(f"  {category.title()}:")
            for dep, available in category_deps.items():
                status = "✅" if available else "❌"
                print(f"    {status} {dep}")
    except Exception as e:
        print(f"  Could not check dependencies: {e}")
    
    # Setup performance monitoring
    print("\n🔧 Setting up performance monitoring...")
    
    try:
        # Try to load configuration
        config_file = Path(__file__).parent.parent / "config" / "performance_config.yaml"
        
        monitor_setup = setup_performance_monitoring(
            config_file=str(config_file) if config_file.exists() else None,
            auto_start=True,
            enable_dashboard=False
        )
        
        if monitor_setup['status'] != 'success':
            print(f"❌ Failed to setup monitoring: {monitor_setup.get('error', 'Unknown error')}")
            return
        
        monitor = monitor_setup['monitor']
        print("✅ Performance monitoring started successfully")
        
    except Exception as e:
        print(f"❌ Error setting up monitoring: {e}")
        return
    
    # Wait a moment for initial metrics
    time.sleep(1)
    
    print("\n🚀 Running performance tests...")
    
    try:
        # Test 1: Simple computation with timing
        print("\n1️⃣ Testing simple computation performance...")
        with monitor.timer("simple_computation"):
            results = simulate_simple_computation()
        
        # Record custom metrics
        monitor.record_custom_metric("computation_results", len(results))
        monitor.record_custom_metric("max_result", max(results) if results else 0)
        
        # Test 2: Data processing
        print("\n2️⃣ Testing data processing performance...")
        with monitor.timer("data_processing"):
            smoothed_data, trends = simulate_data_processing()
        
        monitor.record_custom_metric("processed_points", len(smoothed_data))
        monitor.record_custom_metric("trend_points", len(trends))
        
        # Test 3: Memory operations
        print("\n3️⃣ Testing memory operations...")
        with monitor.timer("memory_operations"):
            total_elements = simulate_memory_operations()
        
        monitor.record_custom_metric("total_elements", total_elements)
        
        # Test 4: Using decorator
        print("\n4️⃣ Testing performance decorator...")
        
        from common.performance_monitor import performance_monitor
        
        @performance_monitor("decorated_function", monitor)
        def example_decorated_function(n):
            """Example function with performance monitoring decorator."""
            # Simulate some work
            result = 0
            for i in range(n):
                result += math.sin(i) * math.cos(i)
            return result
        
        result = example_decorated_function(10000)
        print(f"Decorated function result: {result:.4f}")
        
        # Wait for more metrics to accumulate
        print("\n⏱️ Collecting performance data...")
        time.sleep(2)
        
        # Generate performance report
        print("\n📈 Generating performance report...")
        report = monitor.get_performance_report()
        
        # Display key metrics
        print("\n📊 Performance Summary:")
        
        if 'resource_summary' in report:
            resource_summary = report['resource_summary']
            if 'cpu_percent' in resource_summary:
                cpu_data = resource_summary['cpu_percent']
                print(f"  CPU Usage: {cpu_data.get('mean', 0):.1f}% avg, {cpu_data.get('max', 0):.1f}% max")
            
            if 'memory_mb' in resource_summary:
                memory_data = resource_summary['memory_mb']
                print(f"  Memory Usage: {memory_data.get('mean', 0):.1f} MB avg, {memory_data.get('max', 0):.1f} MB max")
        
        if 'timing_summary' in report:
            timing_summary = report['timing_summary']
            print(f"  Total Operations: {timing_summary.get('total_operations', 0)}")
            print(f"  Total Time: {timing_summary.get('total_time_seconds', 0):.2f} seconds")
            print(f"  Average Duration: {timing_summary.get('average_duration_seconds', 0):.3f} seconds")
            
            # Show operation breakdown
            if 'operations_by_name' in timing_summary:
                print("\n  Operation Breakdown:")
                for name, stats in timing_summary['operations_by_name'].items():
                    print(f"    {name}: {stats['count']} runs, "
                          f"{stats['total_time_seconds']:.2f}s total, "
                          f"{stats['average_duration_seconds']:.3f}s avg")
        
        # Show custom metrics
        if 'custom_metrics' in report and report['custom_metrics']:
            print("\n  Custom Metrics:")
            for name, stats in report['custom_metrics'].items():
                print(f"    {name}: {stats['latest']} (avg: {stats['average']:.2f})")
        
        # Show alerts
        if 'alerts' in report and report['alerts']:
            print(f"\n⚠️ Performance Alerts ({len(report['alerts'])}):")
            for alert in report['alerts'][-5:]:  # Show last 5 alerts
                print(f"  - {alert['message']}")
        else:
            print("\n✅ No performance alerts")
        
        # Show recommendations
        if 'recommendations' in report and report['recommendations']:
            print("\n💡 Performance Recommendations:")
            for rec in report['recommendations']:
                print(f"  - {rec}")
        
        # Save detailed report
        report_file = Path("simple_performance_report.json")
        monitor.save_report(str(report_file))
        print(f"\n💾 Detailed report saved to: {report_file.absolute()}")
        
        # Stop monitoring
        print("\n🛑 Stopping performance monitoring...")
        monitor.stop_monitoring()
        
        print("\n✅ Simple performance monitoring example completed successfully!")
        print("\n📝 Summary:")
        print("  - Monitored system resources (CPU, memory)")
        print("  - Timed multiple operations with basic metrics")
        print("  - Tracked custom computational metrics")
        print("  - Generated performance report")
        print("  - Demonstrated decorator usage")
        
    except Exception as e:
        print(f"\n❌ Error during performance testing: {e}")
        import traceback
        traceback.print_exc()
        
        # Try to stop monitoring
        try:
            monitor.stop_monitoring()
        except:
            pass


if __name__ == '__main__':
    try:
        run_simple_performance_example()
    except KeyboardInterrupt:
        print("\n\n⏹️ Example interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error running example: {e}")
        import traceback
        traceback.print_exc()