#!/usr/bin/env python3
"""Performance monitoring example for the Hydrology framework.

This script demonstrates how to use the performance monitoring system
to track resource usage, timing, and generate reports.
"""
import sys
import os
import time
import numpy as np
from pathlib import Path

# Add the parent directory to the path so we can import from the framework
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from common import (
        setup_performance_monitoring,
        PerformanceMonitor,
        PerformanceTimer,
        performance_monitor,
        get_system_info,
        check_dependencies
    )
    PERFORMANCE_AVAILABLE = True
except ImportError as e:
    print(f"Performance monitoring not available: {e}")
    PERFORMANCE_AVAILABLE = False


def simulate_hydrological_computation():
    """Simulate a computationally intensive hydrological calculation."""
    print("Simulating 2D shallow water equations...")
    
    # Create a large mesh
    nx, ny = 500, 500
    dx, dy = 1.0, 1.0
    
    # Initialize water depth and velocity fields
    h = np.ones((nx, ny)) * 2.0  # Initial water depth
    u = np.zeros((nx, ny))       # x-velocity
    v = np.zeros((nx, ny))       # y-velocity
    
    # Add some initial disturbance (dam break scenario)
    h[nx//4:3*nx//4, ny//4:3*ny//4] = 5.0
    
    # Simulation parameters
    dt = 0.01
    g = 9.81  # gravity
    
    # Run simulation for several time steps
    for step in range(100):
        # Compute gradients (simplified)
        dh_dx = np.gradient(h, dx, axis=0)
        dh_dy = np.gradient(h, dy, axis=1)
        
        # Update velocities (simplified shallow water equations)
        u_new = u - g * dt * dh_dx
        v_new = v - g * dt * dh_dy
        
        # Update water depth (continuity equation)
        du_dx = np.gradient(u_new, dx, axis=0)
        dv_dy = np.gradient(v_new, dy, axis=1)
        h_new = h - dt * h * (du_dx + dv_dy)
        
        # Apply boundary conditions
        h_new[0, :] = h_new[1, :]
        h_new[-1, :] = h_new[-2, :]
        h_new[:, 0] = h_new[:, 1]
        h_new[:, -1] = h_new[:, -2]
        
        # Update fields
        h = h_new
        u = u_new
        v = v_new
        
        # Simulate some additional processing
        if step % 20 == 0:
            # Calculate some statistics
            max_depth = np.max(h)
            total_volume = np.sum(h) * dx * dy
            max_velocity = np.sqrt(np.max(u**2 + v**2))
            
            print(f"Step {step}: Max depth={max_depth:.2f}, "
                  f"Total volume={total_volume:.0f}, Max velocity={max_velocity:.2f}")
    
    return h, u, v


def simulate_data_processing():
    """Simulate data processing operations."""
    print("Simulating data processing...")
    
    # Generate synthetic rainfall data
    time_steps = 1000
    stations = 50
    
    # Create rainfall time series
    rainfall_data = np.random.exponential(2.0, (time_steps, stations))
    
    # Apply some processing
    # 1. Smoothing
    from scipy.ndimage import gaussian_filter1d
    smoothed_data = gaussian_filter1d(rainfall_data, sigma=2.0, axis=0)
    
    # 2. Interpolation to finer grid
    from scipy.interpolate import griddata
    
    # Create station coordinates
    station_coords = np.random.uniform(0, 100, (stations, 2))
    
    # Create interpolation grid
    grid_x, grid_y = np.meshgrid(np.linspace(0, 100, 200), np.linspace(0, 100, 200))
    
    # Interpolate each time step
    interpolated_fields = []
    for t in range(0, time_steps, 10):  # Every 10th time step
        values = smoothed_data[t, :]
        interpolated = griddata(
            station_coords, values, 
            (grid_x, grid_y), 
            method='cubic', 
            fill_value=0.0
        )
        interpolated_fields.append(interpolated)
    
    # Convert to array
    interpolated_fields = np.array(interpolated_fields)
    
    # Calculate some statistics
    mean_rainfall = np.mean(interpolated_fields)
    max_rainfall = np.max(interpolated_fields)
    
    print(f"Processed {len(interpolated_fields)} time steps")
    print(f"Mean rainfall: {mean_rainfall:.2f} mm/h")
    print(f"Max rainfall: {max_rainfall:.2f} mm/h")
    
    return interpolated_fields


def memory_intensive_operation():
    """Simulate a memory-intensive operation."""
    print("Simulating memory-intensive operation...")
    
    # Create large arrays
    arrays = []
    for i in range(10):
        # Create progressively larger arrays
        size = (100 + i * 50, 100 + i * 50, 10)
        array = np.random.random(size)
        arrays.append(array)
        
        # Do some computation
        result = np.fft.fftn(array)
        result = np.abs(result)
        
        print(f"Created array {i+1} with shape {size}, memory: {array.nbytes / 1024 / 1024:.1f} MB")
        
        # Simulate some delay
        time.sleep(0.1)
    
    # Clean up
    del arrays
    import gc
    gc.collect()
    
    print("Memory-intensive operation completed")


def run_performance_example():
    """Run the complete performance monitoring example."""
    print("=" * 60)
    print("🌊 Hydrology Framework Performance Monitoring Example")
    print("=" * 60)
    
    if not PERFORMANCE_AVAILABLE:
        print("❌ Performance monitoring is not available.")
        print("Please install required dependencies: pip install psutil")
        return
    
    # Check system information
    print("\n📊 System Information:")
    system_info = get_system_info()
    for key, value in system_info.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
    
    # Check dependencies
    print("\n📦 Dependency Status:")
    deps = check_dependencies()
    for category, category_deps in deps.items():
        print(f"  {category.title()}:")
        for dep, available in category_deps.items():
            status = "✅" if available else "❌"
            print(f"    {status} {dep}")
    
    # Setup performance monitoring
    print("\n🔧 Setting up performance monitoring...")
    
    # Try to load configuration
    config_file = Path(__file__).parent.parent / "config" / "performance_config.yaml"
    
    monitor_setup = setup_performance_monitoring(
        config_file=str(config_file) if config_file.exists() else None,
        auto_start=True,
        enable_dashboard=False  # Set to True to enable web dashboard
    )
    
    if monitor_setup['status'] != 'success':
        print(f"❌ Failed to setup monitoring: {monitor_setup.get('error', 'Unknown error')}")
        return
    
    monitor = monitor_setup['monitor']
    print("✅ Performance monitoring started successfully")
    
    # Wait a moment for initial metrics
    time.sleep(2)
    
    print("\n🚀 Running performance tests...")
    
    # Test 1: Hydrological computation with timing
    print("\n1️⃣ Testing hydrological computation performance...")
    with monitor.timer("hydrological_simulation"):
        h, u, v = simulate_hydrological_computation()
    
    # Record custom metrics
    monitor.record_custom_metric("mesh_elements", h.size)
    monitor.record_custom_metric("max_water_depth", float(np.max(h)))
    monitor.record_custom_metric("total_water_volume", float(np.sum(h)))
    
    # Test 2: Data processing
    print("\n2️⃣ Testing data processing performance...")
    with monitor.timer("data_processing"):
        try:
            interpolated_data = simulate_data_processing()
            monitor.record_custom_metric("processed_time_steps", len(interpolated_data))
        except ImportError as e:
            print(f"⚠️ Skipping data processing test (missing scipy): {e}")
    
    # Test 3: Memory-intensive operation
    print("\n3️⃣ Testing memory usage...")
    with monitor.timer("memory_intensive_operation"):
        memory_intensive_operation()
    
    # Test 4: Using decorator
    print("\n4️⃣ Testing performance decorator...")
    
    @performance_monitor("decorated_function", monitor)
    def example_decorated_function():
        """Example function with performance monitoring decorator."""
        # Simulate some work
        data = np.random.random((1000, 1000))
        result = np.linalg.svd(data, full_matrices=False)
        return result
    
    result = example_decorated_function()
    print(f"Decorated function completed, result shape: {result[0].shape}")
    
    # Wait for more metrics to accumulate
    print("\n⏱️ Collecting performance data...")
    time.sleep(3)
    
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
    report_file = Path("performance_report.json")
    monitor.save_report(str(report_file))
    print(f"\n💾 Detailed report saved to: {report_file.absolute()}")
    
    # Stop monitoring
    print("\n🛑 Stopping performance monitoring...")
    monitor.stop_monitoring()
    
    print("\n✅ Performance monitoring example completed successfully!")
    print("\n📝 Summary:")
    print("  - Monitored system resources (CPU, memory, disk, network)")
    print("  - Timed multiple operations with detailed metrics")
    print("  - Tracked custom hydrological metrics")
    print("  - Generated comprehensive performance report")
    print("  - Provided optimization recommendations")
    
    if monitor_setup.get('dashboard'):
        dashboard_url = monitor_setup['dashboard'].get_url()
        print(f"\n🌐 Performance dashboard available at: {dashboard_url}")


if __name__ == '__main__':
    try:
        run_performance_example()
    except KeyboardInterrupt:
        print("\n\n⏹️ Example interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error running example: {e}")
        import traceback
        traceback.print_exc()