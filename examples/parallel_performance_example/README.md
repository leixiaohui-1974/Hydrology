# Parallel Performance Example

This example demonstrates the performance improvements achieved by using the parallel simulation controllers in the Hydrology framework.

## Overview

The parallel controllers provide three different parallelization strategies:

1. **Process-based parallelization**: Uses multiple processes for true parallelism (best for CPU-intensive tasks)
2. **Thread-based parallelization**: Uses multiple threads for I/O-bound tasks
3. **Hybrid parallelization**: Automatically chooses between processes and threads based on component characteristics

## Features

- **Automatic dependency analysis**: Identifies components that can run in parallel
- **Performance monitoring**: Real-time monitoring of CPU, memory, and execution time
- **Benchmarking**: Compare different parallelization strategies
- **Scalability analysis**: Test performance with different numbers of workers

## Requirements

```bash
pip install psutil matplotlib numpy pandas
```

## Usage

### Basic Example

```python
from common.parallel_controller import ParallelSimulationController

# Create parallel controller
controller = ParallelSimulationController(max_workers=4, use_processes=True)

# Add components and run simulation
# ... (see run_parallel_example.py for complete example)
```

### Performance Monitoring

```python
from utils.performance_monitor import PerformanceMonitor

# Monitor a simulation
monitor = PerformanceMonitor()
monitor.start_monitoring()

# Run your simulation
run_simulation()

# Get performance report
metrics = monitor.finalize_metrics()
report = monitor.generate_report()
```

### Benchmarking

```python
from utils.performance_monitor import PerformanceBenchmark

benchmark = PerformanceBenchmark()
benchmark.benchmark_configuration("Serial", run_serial_simulation)
benchmark.benchmark_configuration("Parallel", run_parallel_simulation)

# Compare results
comparison = benchmark.compare_configurations()
print(comparison)
```

## Running the Example

1. **Run the complete benchmark**:
   ```bash
   python run_parallel_example.py
   ```

2. **Run with configuration file**:
   ```bash
   python ../../run_from_config.py config_parallel.yaml
   ```

## Expected Results

With a 4-core system, you should see:
- **Serial execution**: ~100% CPU usage on 1 core
- **Parallel execution**: ~400% CPU usage across all cores
- **Speedup**: 2-4x improvement depending on dependencies

## Configuration Options

### Parallel Controller Settings

```yaml
parallel:
  enabled: true
  controller_type: "hybrid"  # "process", "thread", or "hybrid"
  max_workers: 4
  auto_detect_workers: true
```

### Performance Monitoring

```yaml
performance_monitoring:
  enabled: true
  metrics:
    - execution_time
    - memory_usage
    - cpu_usage
    - throughput
    - parallelization_speedup
```

## Output Files

- `benchmark_results.json`: Detailed benchmark results
- `performance_report.txt`: Human-readable performance summary
- `performance_timeline.png`: Resource usage over time
- `parallelization_analysis.png`: Speedup analysis
- `parallel_simulation_results.csv`: Simulation results

## Performance Tips

1. **Choose the right controller**:
   - Use `ProcessPoolExecutor` for CPU-intensive numerical computations
   - Use `ThreadPoolExecutor` for I/O-bound operations
   - Use `HybridParallelController` for mixed workloads

2. **Optimize worker count**:
   - Start with `max_workers = CPU_count`
   - Test different values to find optimal performance
   - Consider memory constraints for large models

3. **Minimize dependencies**:
   - Components with fewer dependencies can run more in parallel
   - Use junctions to reduce coupling between components

## Troubleshooting

### Common Issues

1. **Memory errors**: Reduce `max_workers` or use streaming data processing
2. **Poor speedup**: Check for tight dependencies between components
3. **Process creation overhead**: Use threads for short-running tasks

### Debug Mode

Enable debug output by setting:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Advanced Usage

### Custom Parallelization

```python
class CustomParallelController(ParallelSimulationController):
    def _identify_parallel_groups(self):
        # Custom logic for identifying parallel groups
        pass
```

### Integration with Existing Models

The parallel controllers are drop-in replacements for the standard `SimulationController`:

```python
# Replace this:
# controller = SimulationController()

# With this:
controller = ParallelSimulationController(max_workers=4)
```

## Contributing

To add new parallelization strategies or performance monitoring features:

1. Extend the base classes in `common/parallel_controller.py`
2. Add new metrics to `utils/performance_monitor.py`
3. Update the configuration parser to support new options
4. Add tests in the `tests/` directory

## References

- [Python multiprocessing](https://docs.python.org/3/library/multiprocessing.html)
- [concurrent.futures](https://docs.python.org/3/library/concurrent.futures.html)
- [psutil documentation](https://psutil.readthedocs.io/)

