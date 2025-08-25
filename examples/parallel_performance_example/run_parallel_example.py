"""
Parallel Performance Example
===========================
This example demonstrates the performance improvements achieved by using
the parallel simulation controller.
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from common.parallel_controller import ParallelSimulationController, HybridParallelController
from common.controller import SimulationController
from hydro_model.runoff import SCSCurveNumberModule
from hydro_model.routing import MuskingumRoutingModule
from hydro_model.model import HydrologicalModel
from utils.performance_monitor import PerformanceMonitor, PerformanceBenchmark
import time


def create_test_model(name: str) -> HydrologicalModel:
    """Create a test hydrological model."""
    # Create runoff module
    runoff_module = SCSCurveNumberModule(
        area=100.0,  # km²
        curve_number=70,
        impervious_fraction=0.1
    )
    
    # Create routing module
    routing_module = MuskingumRoutingModule(
        k=2.0,  # hours
        x=0.2
    )
    
    # Create hydrological model
    model = HydrologicalModel(
        name=name,
        runoff_module=runoff_module,
        routing_module=routing_module
    )
    
    return model


def create_test_data(time_steps: int = 1000) -> dict:
    """Create test input data."""
    # Generate synthetic rainfall data
    np.random.seed(42)
    rainfall = np.random.exponential(5.0, time_steps)  # mm/hour
    rainfall[rainfall > 20] = 20  # Cap at 20 mm/hour
    
    # Generate PET data
    pet = np.random.normal(2.0, 0.5, time_steps)  # mm/hour
    pet[pet < 0] = 0
    
    return {
        'rainfall': rainfall.tolist(),
        'pet': pet.tolist()
    }


def run_serial_simulation():
    """Run simulation using the standard serial controller."""
    print("Running serial simulation...")
    
    # Create controller and models
    controller = SimulationController()
    
    # Add multiple models
    for i in range(4):
        model = create_test_model(f"Catchment{i+1}")
        controller.add_component(model)
    
    # Connect models in a simple chain
    for i in range(3):
        controller.connect(f"Catchment{i+1}", f"Catchment{i+2}")
    
    # Create test data
    test_data = create_test_data(1000)
    
    # Run simulation
    start_time = time.time()
    controller.run(1000, dt=1.0, inputs=test_data)
    execution_time = time.time() - start_time
    
    print(f"Serial simulation completed in {execution_time:.2f} seconds")
    return execution_time


def run_parallel_simulation(use_processes: bool = True, max_workers: int = None):
    """Run simulation using the parallel controller."""
    print(f"Running parallel simulation (processes: {use_processes})...")
    
    # Create parallel controller
    controller = ParallelSimulationController(
        max_workers=max_workers,
        use_processes=use_processes
    )
    
    # Add multiple models
    for i in range(4):
        model = create_test_model(f"Catchment{i+1}")
        controller.add_component(model)
    
    # Connect models in a simple chain
    for i in range(3):
        controller.connect(f"Catchment{i+1}", f"Catchment{i+2}")
    
    # Create test data
    test_data = create_test_data(1000)
    
    # Run simulation
    start_time = time.time()
    controller.run_parallel(1000, dt=1.0, inputs=test_data)
    execution_time = time.time() - start_time
    
    print(f"Parallel simulation completed in {execution_time:.2f} seconds")
    return execution_time


def run_hybrid_simulation(max_workers: int = None):
    """Run simulation using the hybrid controller."""
    print("Running hybrid simulation...")
    
    # Create hybrid controller
    controller = HybridParallelController(max_workers=max_workers)
    
    # Add multiple models
    for i in range(4):
        model = create_test_model(f"Catchment{i+1}")
        controller.add_component(model)
    
    # Connect models in a simple chain
    for i in range(3):
        controller.connect(f"Catchment{i+1}", f"Catchment{i+2}")
    
    # Create test data
    test_data = create_test_data(1000)
    
    # Run simulation
    start_time = time.time()
    controller.run_parallel(1000, dt=1.0, inputs=test_data)
    execution_time = time.time() - start_time
    
    print(f"Hybrid simulation completed in {execution_time:.2f} seconds")
    return execution_time


def benchmark_different_configurations():
    """Benchmark different simulation configurations."""
    print("Starting performance benchmark...")
    
    benchmark = PerformanceBenchmark()
    
    # Benchmark serial execution
    benchmark.benchmark_configuration("Serial", run_serial_simulation)
    
    # Benchmark parallel execution with processes
    benchmark.benchmark_configuration("Parallel (Processes)", 
                                    lambda: run_parallel_simulation(use_processes=True))
    
    # Benchmark parallel execution with threads
    benchmark.benchmark_configuration("Parallel (Threads)", 
                                    lambda: run_parallel_simulation(use_processes=False))
    
    # Benchmark hybrid execution
    benchmark.benchmark_configuration("Hybrid", run_hybrid_simulation)
    
    # Generate comparison report
    report = benchmark.compare_configurations()
    print("\n" + report)
    
    # Save results
    benchmark.save_benchmark_results("benchmark_results.json")
    
    return benchmark


def demonstrate_parallelization_benefits():
    """Demonstrate the benefits of parallelization with different numbers of workers."""
    print("\nDemonstrating parallelization benefits...")
    
    # Test with different numbers of workers
    worker_counts = [1, 2, 4, 8]
    execution_times = []
    
    for workers in worker_counts:
        print(f"\nTesting with {workers} workers...")
        execution_time = run_parallel_simulation(use_processes=True, max_workers=workers)
        execution_times.append(execution_time)
    
    # Calculate speedup
    baseline_time = execution_times[0]
    speedups = [baseline_time / time for time in execution_times]
    
    # Plot results
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    # Execution time
    ax1.plot(worker_counts, execution_times, 'bo-', linewidth=2, markersize=8)
    ax1.set_xlabel('Number of Workers')
    ax1.set_ylabel('Execution Time (seconds)')
    ax1.set_title('Execution Time vs Number of Workers')
    ax1.grid(True)
    
    # Speedup
    ax2.plot(worker_counts, speedups, 'ro-', linewidth=2, markersize=8)
    ax2.plot(worker_counts, worker_counts, 'k--', alpha=0.5, label='Ideal Speedup')
    ax2.set_xlabel('Number of Workers')
    ax2.set_ylabel('Speedup')
    ax2.set_title('Speedup vs Number of Workers')
    ax2.legend()
    ax2.grid(True)
    
    plt.tight_layout()
    plt.savefig('parallelization_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    print(f"\nSpeedup with {max(worker_counts)} workers: {max(speedups):.2f}x")


def main():
    """Main function to run the parallel performance example."""
    print("Parallel Performance Example")
    print("=" * 50)
    
    # Run basic benchmark
    benchmark = benchmark_different_configurations()
    
    # Demonstrate parallelization benefits
    demonstrate_parallelization_benefits()
    
    print("\nExample completed successfully!")
    print("Check 'benchmark_results.json' for detailed results")
    print("Check 'parallelization_analysis.png' for visualization")


if __name__ == "__main__":
    main()

