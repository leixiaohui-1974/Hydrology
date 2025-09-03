"""
GPU 加速概念验证 (Proof-of-Concept)
========================================

本示例旨在比较一个计算密集型函数（Lorenz '63 系统）在 CPU (使用 NumPy)
和 GPU (使用 PyTorch) 上的执行性能。

工作流程:
1. 定义一个使用 NumPy 的向量化函数来在 CPU 上模拟 Lorenz 系统。
2. 定义一个使用 PyTorch 的等效函数，并将其移动到 CUDA 设备上。
3. 创建一个大规模的状态矩阵（例如，模拟一个大型粒子滤波器的粒子）。
4. 分别运行 CPU 和 GPU 版本的函数，并使用 `time` 模块精确测量执行时间。
5. 打印性能比较结果。
"""
import time
import numpy as np
import torch
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def lorenz63_cpu(states, dt=0.01):
    """使用 NumPy 在 CPU 上模拟 Lorenz '63 系统。"""
    sigma = 10.0
    rho = 28.0
    beta = 8.0 / 3.0

    x = states[:, 0]
    y = states[:, 1]
    z = states[:, 2]

    dx = sigma * (y - x)
    dy = x * (rho - z) - y
    dz = x * y - beta * z

    return states + np.vstack([dx, dy, dz]).T * dt

def lorenz63_gpu(states_tensor, dt=0.01):
    """使用 PyTorch 在 GPU 上模拟 Lorenz '63 系统。"""
    sigma = 10.0
    rho = 28.0
    beta = 8.0 / 3.0

    x = states_tensor[:, 0]
    y = states_tensor[:, 1]
    z = states_tensor[:, 2]

    dx = sigma * (y - x)
    dy = x * (rho - z) - y
    dz = x * y - beta * z

    return states_tensor + torch.stack([dx, dy, dz]).T * dt

def main():
    logger.info("--- 开始 GPU 加速性能比较 ---")

    # --- 1. 设置实验参数 ---
    n_particles = 100000  # 使用大量粒子来突显性能差异
    n_steps = 100
    dt = 0.01

    logger.info(f"模拟参数: {n_particles} 个粒子, {n_steps} 个时间步")

    # --- 2. 准备数据 ---
    # CPU 数据 (NumPy)
    cpu_states = np.random.randn(n_particles, 3)

    # GPU 数据 (PyTorch)
    # 检查 CUDA 是否可用
    if not torch.cuda.is_available():
        logger.error("CUDA is not available on this system. Cannot run GPU benchmark.")
        return

    device = torch.device("cuda")
    gpu_states = torch.from_numpy(cpu_states).to(device)

    logger.info(f"数据已准备好并移动到 {device} 设备。")

    # --- 3. 运行 CPU 基准测试 ---
    logger.info("--- 正在运行 CPU 基准测试... ---")
    start_time_cpu = time.perf_counter()

    # 预热一次以避免首次调用的开销
    _ = lorenz63_cpu(cpu_states, dt)

    # 正式计时
    cpu_start = time.perf_counter()
    for _ in range(n_steps):
        cpu_states = lorenz63_cpu(cpu_states, dt)
    cpu_end = time.perf_counter()
    cpu_duration = cpu_end - cpu_start

    logger.info(f"CPU 执行完成。")

    # --- 4. 运行 GPU 基准测试 ---
    logger.info("--- 正在运行 GPU 基准测试... ---")

    # 预热一次
    _ = lorenz63_gpu(gpu_states, dt)
    torch.cuda.synchronize() # 等待 GPU 操作完成

    # 正式计时
    gpu_start = time.perf_counter()
    for _ in range(n_steps):
        gpu_states = lorenz63_gpu(gpu_states, dt)
    torch.cuda.synchronize() # 确保所有 GPU 计算都已完成
    gpu_end = time.perf_counter()
    gpu_duration = gpu_end - gpu_start

    logger.info(f"GPU 执行完成。")

    # --- 5. 打印结果 ---
    logger.info("\n--- 性能比较结果 ---")
    print(f"CPU (NumPy) 总执行时间: {cpu_duration:.4f} 秒")
    print(f"GPU (PyTorch) 总执行时间: {gpu_duration:.4f} 秒")

    if gpu_duration > 0:
        speedup = cpu_duration / gpu_duration
        print(f"\nGPU 相对于 CPU 的加速比: {speedup:.2f}x")
    else:
        print("\n无法计算加速比（GPU执行时间为0）。")

    logger.info("--- 示例完成 ---")


if __name__ == "__main__":
    main()
