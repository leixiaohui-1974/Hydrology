# Performance Improvements

This document outlines the efforts and strategies employed to improve the performance of the Hydro-Suite framework.

## 1. Profiling with `PerformanceMonitor`

A key step in optimization is identifying bottlenecks. The `utils.performance_monitor.PerformanceMonitor` class was developed for this purpose. It provides a simple way to time the execution of different parts of the code using a decorator (`@time_func`) or a context manager.

By applying this monitor to the data assimilation test suite, we identified that the primary bottleneck was the repeated, non-vectorized calls to the model function (e.g., `lorenz63_system`) within the filter loops. The particle filter, in particular, was making hundreds of thousands of individual calls.

## 2. Targeted Optimization: Vectorization

Based on the profiling results, a targeted optimization was performed on the bottleneck function.

**Before (Non-Vectorized):**
The original approach used `np.apply_along_axis` to loop over each particle/ensemble member and call the model function individually. This is inefficient as it operates like a Python loop.

**After (Vectorized):**
A new, vectorized version of the model function (`lorenz63_system_vectorized`) was created. This function performs the calculations on the entire matrix of states at once using efficient NumPy operations.

### Results

By replacing the non-vectorized calls with the vectorized version in the data assimilation tests, we observed a **~67x performance improvement**, with the total test execution time dropping from over 30 seconds to approximately 0.5 seconds.

This demonstrates the immense impact of vectorization on numerical code and serves as a key strategy for future optimizations.

## 3. GPU Acceleration (Proof-of-Concept)

To explore further performance gains for highly parallelizable tasks, a proof-of-concept for GPU acceleration was developed. The example compares the performance of the vectorized Lorenz '63 simulation on a CPU (using NumPy) versus a GPU (using PyTorch and CUDA).

### Example Code

The following script (`examples/hpc_optimization_example/gpu_acceleration_poc.py`) demonstrates how to structure such a comparison.

**Note:** To run this example, you must have a CUDA-compatible GPU and the necessary PyTorch and CUDA toolkit versions installed. The script will exit gracefully if a CUDA device is not found.

```python
import time
import numpy as np
import torch
import logging

# ... (lorenz63_cpu and lorenz63_gpu functions as defined in the example) ...

def main():
    logger.info("--- 开始 GPU 加速性能比较 ---")

    n_particles = 100000
    n_steps = 100

    # Check for CUDA device
    if not torch.cuda.is_available():
        logger.error("CUDA is not available on this system. Cannot run GPU benchmark.")
        return

    device = torch.device("cuda")

    # Prepare data
    cpu_states = np.random.randn(n_particles, 3)
    gpu_states = torch.from_numpy(cpu_states).to(device)

    # --- Run CPU Benchmark ---
    logger.info("--- 正在运行 CPU 基准测试... ---")
    cpu_start = time.perf_counter()
    for _ in range(n_steps):
        cpu_states = lorenz63_cpu(cpu_states)
    cpu_duration = time.perf_counter() - cpu_start

    # --- Run GPU Benchmark ---
    logger.info("--- 正在运行 GPU 基准测试... ---")
    gpu_start = time.perf_counter()
    for _ in range(n_steps):
        gpu_states = lorenz63_gpu(gpu_states)
    torch.cuda.synchronize()
    gpu_duration = time.perf_counter() - gpu_start

    # --- Print Results ---
    logger.info("\n--- 性能比较结果 ---")
    print(f"CPU (NumPy) 总执行时间: {cpu_duration:.4f} 秒")
    print(f"GPU (PyTorch) 总执行时间: {gpu_duration:.4f} 秒")

    if gpu_duration > 0:
        speedup = cpu_duration / gpu_duration
        print(f"\nGPU 相对于 CPU 的加速比: {speedup:.2f}x")

if __name__ == "__main__":
    main()
```

This proof-of-concept provides a clear template for migrating other computationally intensive parts of the Hydro-Suite to GPUs for significant performance gains.

## Future Enhancements

- **Wider GPU Integration**: Apply the GPU acceleration pattern to core hydrological and hydraulic models.
- **Distributed Computing**: Extend parallelization to run across multiple machines for very large-scale simulations.
- **Advanced Load Balancing**: Dynamically distribute work in heterogeneous (CPU/GPU) environments.
