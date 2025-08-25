"""
并行计算框架模块
================

本模块提供水文模型的并行计算优化功能，包括：
- GPU加速计算（CUDA、OpenCL）
- 分布式计算（MPI、任务分解）
- 异步计算（任务调度、事件驱动）
"""

import numpy as np
import logging
import time
import threading
import queue
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import Optional, List, Dict, Any, Callable, Tuple
import psutil

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GPUAccelerator:
    """GPU加速计算器"""
    
    def __init__(self, device_type: str = "cuda", device_id: int = 0):
        self.device_type = device_type
        self.device_id = device_id
        self.is_available = False
        self.device_info = {}
        
        # 检测GPU可用性
        self._detect_gpu()
        
        logger.info(f"GPUAccelerator initialized: {device_type}:{device_id}")
    
    def _detect_gpu(self):
        """检测GPU可用性"""
        try:
            if self.device_type == "cuda":
                import torch
                if torch.cuda.is_available():
                    self.is_available = True
                    self.device_info = {
                        'name': torch.cuda.get_device_name(self.device_id),
                        'memory': torch.cuda.get_device_properties(self.device_id).total_memory,
                        'compute_capability': torch.cuda.get_device_capability(self.device_id)
                    }
                    logger.info(f"CUDA GPU detected: {self.device_info['name']}")
                else:
                    logger.warning("CUDA not available")
            
            elif self.device_type == "opencl":
                try:
                    import pyopencl as cl
                    platforms = cl.get_platforms()
                    if platforms:
                        devices = platforms[0].get_devices()
                        if devices:
                            self.is_available = True
                            self.device_info = {
                                'name': devices[0].name,
                                'memory': devices[0].global_mem_size,
                                'compute_units': devices[0].compute_units
                            }
                            logger.info(f"OpenCL GPU detected: {self.device_info['name']}")
                except ImportError:
                    logger.warning("PyOpenCL not available")
            
        except Exception as e:
            logger.warning(f"GPU detection failed: {e}")
    
    def accelerate_tensor_operations(self, data: np.ndarray, operation: str) -> np.ndarray:
        """加速张量运算"""
        if not self.is_available:
            logger.warning("GPU not available, using CPU")
            return self._cpu_tensor_operation(data, operation)
        
        try:
            if self.device_type == "cuda":
                return self._cuda_tensor_operation(data, operation)
            elif self.device_type == "opencl":
                return self._opencl_tensor_operation(data, operation)
        except Exception as e:
            logger.error(f"GPU operation failed: {e}, falling back to CPU")
            return self._cpu_tensor_operation(data, operation)
    
    def _cuda_tensor_operation(self, data: np.ndarray, operation: str) -> np.ndarray:
        """CUDA张量运算"""
        import torch
        
        # 转换为PyTorch张量
        device = torch.device(f'cuda:{self.device_id}')
        tensor = torch.from_numpy(data).to(device)
        
        # 执行运算
        if operation == "matrix_multiply":
            result = torch.mm(tensor, tensor.T)
        elif operation == "element_wise_multiply":
            result = tensor * tensor
        elif operation == "reduce_sum":
            result = torch.sum(tensor, dim=0)
        else:
            result = tensor
        
        # 返回CPU上的numpy数组
        return result.cpu().numpy()
    
    def _opencl_tensor_operation(self, data: np.ndarray, operation: str) -> np.ndarray:
        """OpenCL张量运算"""
        # 简化的OpenCL实现
        logger.info("OpenCL tensor operation not fully implemented")
        return data
    
    def _cpu_tensor_operation(self, data: np.ndarray, operation: str) -> np.ndarray:
        """CPU张量运算"""
        if operation == "matrix_multiply":
            return np.dot(data, data.T)
        elif operation == "element_wise_multiply":
            return data * data
        elif operation == "reduce_sum":
            return np.sum(data, axis=0)
        else:
            return data
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """获取GPU内存使用情况"""
        if not self.is_available:
            return {"error": "GPU not available"}
        
        try:
            if self.device_type == "cuda":
                import torch
                allocated = torch.cuda.memory_allocated(self.device_id)
                cached = torch.cuda.memory_reserved(self.device_id)
                return {
                    "allocated_mb": allocated / 1024**2,
                    "cached_mb": cached / 1024**2,
                    "total_mb": self.device_info['memory'] / 1024**2
                }
        except Exception as e:
            return {"error": str(e)}
        
        return {"error": "Memory info not available"}

class DistributedComputing:
    """分布式计算框架"""
    
    def __init__(self, n_workers: int = None, backend: str = "multiprocessing"):
        self.n_workers = n_workers or mp.cpu_count()
        self.backend = backend
        self.executor = None
        self._setup_executor()
        
        logger.info(f"DistributedComputing initialized: {self.n_workers} workers, {self.backend} backend")
    
    def _setup_executor(self):
        """设置执行器"""
        if self.backend == "multiprocessing":
            self.executor = ProcessPoolExecutor(max_workers=self.n_workers)
        elif self.backend == "threading":
            self.executor = ThreadPoolExecutor(max_workers=self.n_workers)
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")
    
    def parallel_map(self, func: Callable, data: List, chunk_size: int = 1) -> List:
        """并行映射函数"""
        logger.info(f"Starting parallel map with {self.n_workers} workers")
        start_time = time.time()
        
        try:
            if self.backend == "multiprocessing":
                # 使用multiprocessing的map
                with mp.Pool(processes=self.n_workers) as pool:
                    result = pool.map(func, data, chunksize=chunk_size)
            else:
                # 使用concurrent.futures
                result = list(self.executor.map(func, data))
            
            elapsed_time = time.time() - start_time
            logger.info(f"Parallel map completed in {elapsed_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Parallel map failed: {e}")
            # 回退到串行执行
            logger.info("Falling back to serial execution")
            return [func(item) for item in data]
    
    def parallel_reduce(self, func: Callable, data: List, initial_value: Any = None) -> Any:
        """并行归约"""
        logger.info(f"Starting parallel reduce with {self.n_workers} workers")
        
        try:
            # 分块处理
            chunk_size = max(1, len(data) // self.n_workers)
            chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
            
            # 并行处理每个块
            chunk_results = self.parallel_map(lambda chunk: self._reduce_chunk(func, chunk), chunks)
            
            # 合并结果
            if initial_value is not None:
                result = initial_value
            else:
                result = chunk_results[0]
                chunk_results = chunk_results[1:]
            
            for chunk_result in chunk_results:
                result = func(result, chunk_result)
            
            return result
            
        except Exception as e:
            logger.error(f"Parallel reduce failed: {e}")
            # 回退到串行执行
            return self._reduce_chunk(func, data, initial_value)
    
    def _reduce_chunk(self, func: Callable, chunk: List, initial_value: Any = None) -> Any:
        """处理单个数据块"""
        if not chunk:
            return initial_value
        
        if initial_value is not None:
            result = initial_value
            for item in chunk:
                result = func(result, item)
        else:
            result = chunk[0]
            for item in chunk[1:]:
                result = func(result, item)
        
        return result
    
    def shutdown(self):
        """关闭执行器"""
        if self.executor:
            self.executor.shutdown(wait=True)
            logger.info("DistributedComputing executor shutdown")

class AsyncComputing:
    """异步计算框架"""
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.workers = []
        self.is_running = False
        
        logger.info(f"AsyncComputing initialized: max_concurrent={max_concurrent}")
    
    def start_workers(self):
        """启动工作线程"""
        if self.is_running:
            return
        
        self.is_running = True
        for i in range(self.max_concurrent):
            worker = threading.Thread(target=self._worker_loop, args=(i,))
            worker.daemon = True
            worker.start()
            self.workers.append(worker)
        
        logger.info(f"Started {self.max_concurrent} worker threads")
    
    def stop_workers(self):
        """停止工作线程"""
        self.is_running = False
        
        # 等待所有工作线程完成
        for worker in self.workers:
            worker.join()
        
        self.workers.clear()
        logger.info("All worker threads stopped")
    
    def submit_task(self, task_id: str, func: Callable, *args, **kwargs):
        """提交任务"""
        task = {
            'id': task_id,
            'func': func,
            'args': args,
            'kwargs': kwargs,
            'timestamp': time.time()
        }
        self.task_queue.put(task)
        logger.info(f"Task {task_id} submitted")
    
    def get_result(self, timeout: float = None) -> Optional[Tuple[str, Any]]:
        """获取结果"""
        try:
            result = self.result_queue.get(timeout=timeout)
            return result['task_id'], result['result']
        except queue.Empty:
            return None
    
    def _worker_loop(self, worker_id: int):
        """工作线程循环"""
        logger.info(f"Worker {worker_id} started")
        
        while self.is_running:
            try:
                # 获取任务
                task = self.task_queue.get(timeout=1.0)
                if task is None:
                    continue
                
                # 执行任务
                start_time = time.time()
                try:
                    result = task['func'](*task['args'], **task['kwargs'])
                    execution_time = time.time() - start_time
                    
                    # 提交结果
                    result_data = {
                        'task_id': task['id'],
                        'result': result,
                        'execution_time': execution_time,
                        'worker_id': worker_id
                    }
                    self.result_queue.put(result_data)
                    
                    logger.info(f"Task {task['id']} completed by worker {worker_id} in {execution_time:.2f}s")
                    
                except Exception as e:
                    # 任务执行失败
                    error_result = {
                        'task_id': task['id'],
                        'result': None,
                        'error': str(e),
                        'worker_id': worker_id
                    }
                    self.result_queue.put(error_result)
                    logger.error(f"Task {task['id']} failed: {e}")
                
                finally:
                    self.task_queue.task_done()
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        logger.info(f"Worker {worker_id} stopped")

class TaskScheduler:
    """任务调度器"""
    
    def __init__(self, scheduling_policy: str = "fifo"):
        self.scheduling_policy = scheduling_policy
        self.task_queue = queue.PriorityQueue()
        self.completed_tasks = []
        self.failed_tasks = []
        
        logger.info(f"TaskScheduler initialized: policy={scheduling_policy}")
    
    def submit_task(self, task_id: str, priority: int = 0, func: Callable = None, 
                   *args, **kwargs):
        """提交任务"""
        task = {
            'id': task_id,
            'priority': priority,
            'func': func,
            'args': args,
            'kwargs': kwargs,
            'status': 'pending',
            'submit_time': time.time()
        }
        
        if self.scheduling_policy == "fifo":
            # FIFO策略：按提交时间排序
            self.task_queue.put((task['submit_time'], task))
        else:
            # 优先级策略：按优先级排序
            self.task_queue.put((-priority, task['submit_time'], task))
        
        logger.info(f"Task {task_id} scheduled with priority {priority}")
    
    def get_next_task(self) -> Optional[Dict]:
        """获取下一个任务"""
        try:
            if self.scheduling_policy == "fifo":
                _, task = self.task_queue.get_nowait()
            else:
                _, _, task = self.task_queue.get_nowait()
            
            task['status'] = 'running'
            task['start_time'] = time.time()
            return task
            
        except queue.Empty:
            return None
    
    def mark_task_completed(self, task_id: str, result: Any):
        """标记任务完成"""
        task = self._find_task(task_id)
        if task:
            task['status'] = 'completed'
            task['result'] = result
            task['completion_time'] = time.time()
            task['execution_time'] = task['completion_time'] - task['start_time']
            self.completed_tasks.append(task)
            logger.info(f"Task {task_id} marked as completed")
    
    def mark_task_failed(self, task_id: str, error: str):
        """标记任务失败"""
        task = self._find_task(task_id)
        if task:
            task['status'] = 'failed'
            task['error'] = error
            task['completion_time'] = time.time()
            self.failed_tasks.append(task)
            logger.error(f"Task {task_id} marked as failed: {error}")
    
    def _find_task(self, task_id: str) -> Optional[Dict]:
        """查找任务"""
        # 这里简化实现，实际应用中需要更高效的数据结构
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'pending_tasks': self.task_queue.qsize(),
            'completed_tasks': len(self.completed_tasks),
            'failed_tasks': len(self.failed_tasks),
            'scheduling_policy': self.scheduling_policy
        }

class LoadBalancer:
    """负载均衡器"""
    
    def __init__(self, n_workers: int = None):
        self.n_workers = n_workers or mp.cpu_count()
        self.worker_loads = [0] * self.n_workers
        self.worker_status = ['idle'] * self.n_workers
        self.task_assignments = {}
        
        logger.info(f"LoadBalancer initialized: {self.n_workers} workers")
    
    def assign_task(self, task_id: str, task_size: int = 1) -> int:
        """分配任务到工作节点"""
        # 选择负载最轻的工作节点
        worker_id = self._select_worker()
        
        # 更新负载
        self.worker_loads[worker_id] += task_size
        self.worker_status[worker_id] = 'busy'
        self.task_assignments[task_id] = worker_id
        
        logger.info(f"Task {task_id} assigned to worker {worker_id}")
        return worker_id
    
    def complete_task(self, task_id: str, task_size: int = 1):
        """标记任务完成"""
        if task_id in self.task_assignments:
            worker_id = self.task_assignments[task_id]
            self.worker_loads[worker_id] = max(0, self.worker_loads[worker_id] - task_size)
            
            # 如果负载为0，标记为空闲
            if self.worker_loads[worker_id] == 0:
                self.worker_status[worker_id] = 'idle'
            
            del self.task_assignments[task_id]
            logger.info(f"Task {task_id} completed on worker {worker_id}")
    
    def _select_worker(self) -> int:
        """选择工作节点"""
        # 选择负载最轻的节点
        min_load = min(self.worker_loads)
        candidates = [i for i, load in enumerate(self.worker_loads) if load == min_load]
        
        # 如果有多个候选节点，选择第一个
        return candidates[0]
    
    def get_worker_status(self) -> List[Dict[str, Any]]:
        """获取工作节点状态"""
        status = []
        for i in range(self.n_workers):
            status.append({
                'worker_id': i,
                'load': self.worker_loads[i],
                'status': self.worker_status[i],
                'assigned_tasks': [tid for tid, wid in self.task_assignments.items() if wid == i]
            })
        return status
    
    def get_balance_metrics(self) -> Dict[str, Any]:
        """获取负载均衡指标"""
        loads = self.worker_loads
        return {
            'total_load': sum(loads),
            'average_load': sum(loads) / len(loads),
            'max_load': max(loads),
            'min_load': min(loads),
            'load_variance': np.var(loads) if loads else 0,
            'idle_workers': self.worker_status.count('idle'),
            'busy_workers': self.worker_status.count('busy')
        }

