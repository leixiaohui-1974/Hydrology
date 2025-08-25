"""
内存和存储优化模块
==================

本模块提供水文模型的内存和存储优化功能，包括：
- 智能内存分配
- 内存池管理
- 数据压缩算法
- 缓存策略优化
- 数据分片存储
"""

import numpy as np
import logging
import time
import gc
import psutil
import os
import pickle
import gzip
import lz4.frame
from typing import Optional, List, Dict, Any, Union, Tuple
from collections import defaultdict, deque
import threading

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MemoryManager:
    """智能内存管理器"""
    
    def __init__(self, max_memory_mb: float = None, memory_threshold: float = 0.8):
        self.max_memory_mb = max_memory_mb or (psutil.virtual_memory().total / 1024**2)
        self.memory_threshold = memory_threshold
        self.allocated_blocks = {}
        self.memory_usage_history = deque(maxlen=100)
        self.lock = threading.Lock()
        
        logger.info(f"MemoryManager initialized: max_memory={self.max_memory_mb:.1f}MB")
    
    def allocate_memory(self, block_id: str, size_mb: float, priority: int = 0) -> bool:
        """分配内存块"""
        with self.lock:
            # 检查内存是否足够
            if not self._check_memory_available(size_mb):
                # 尝试释放低优先级内存
                if not self._free_low_priority_memory(size_mb):
                    logger.warning(f"Insufficient memory for block {block_id}")
                    return False
            
            # 分配内存
            self.allocated_blocks[block_id] = {
                'size_mb': size_mb,
                'priority': priority,
                'allocation_time': time.time(),
                'last_access': time.time()
            }
            
            logger.info(f"Memory block {block_id} allocated: {size_mb:.1f}MB")
            return True
    
    def free_memory(self, block_id: str) -> bool:
        """释放内存块"""
        with self.lock:
            if block_id in self.allocated_blocks:
                size_mb = self.allocated_blocks[block_id]['size_mb']
                del self.allocated_blocks[block_id]
                logger.info(f"Memory block {block_id} freed: {size_mb:.1f}MB")
                return True
            return False
    
    def _check_memory_available(self, required_mb: float) -> bool:
        """检查是否有足够的内存"""
        current_usage = self._get_current_memory_usage()
        available_mb = self.max_memory_mb - current_usage
        return available_mb >= required_mb
    
    def _free_low_priority_memory(self, required_mb: float) -> bool:
        """释放低优先级内存"""
        # 按优先级排序
        sorted_blocks = sorted(
            self.allocated_blocks.items(),
            key=lambda x: (x[1]['priority'], x[1]['last_access'])
        )
        
        freed_mb = 0
        for block_id, block_info in sorted_blocks:
            if freed_mb >= required_mb:
                break
            
            # 释放低优先级块
            if block_info['priority'] < 5:  # 低优先级阈值
                freed_mb += block_info['size_mb']
                del self.allocated_blocks[block_id]
                logger.info(f"Freed low-priority memory block {block_id}")
        
        return freed_mb >= required_mb
    
    def _get_current_memory_usage(self) -> float:
        """获取当前内存使用量"""
        total_allocated = sum(block['size_mb'] for block in self.allocated_blocks.values())
        
        # 记录使用历史
        self.memory_usage_history.append({
            'timestamp': time.time(),
            'allocated_mb': total_allocated,
            'system_mb': psutil.virtual_memory().used / 1024**2
        })
        
        return total_allocated
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取内存统计信息"""
        with self.lock:
            current_usage = self._get_current_memory_usage()
            return {
                'max_memory_mb': self.max_memory_mb,
                'current_usage_mb': current_usage,
                'available_mb': self.max_memory_mb - current_usage,
                'usage_percentage': (current_usage / self.max_memory_mb) * 100,
                'allocated_blocks': len(self.allocated_blocks),
                'total_allocated_mb': current_usage
            }
    
    def optimize_memory(self):
        """内存优化"""
        with self.lock:
            # 强制垃圾回收
            gc.collect()
            
            # 释放长时间未访问的内存块
            current_time = time.time()
            blocks_to_free = []
            
            for block_id, block_info in self.allocated_blocks.items():
                if current_time - block_info['last_access'] > 3600:  # 1小时未访问
                    blocks_to_free.append(block_id)
            
            for block_id in blocks_to_free:
                self.free_memory(block_id)
            
            logger.info(f"Memory optimization completed, freed {len(blocks_to_free)} blocks")

class MemoryPool:
    """内存池管理器"""
    
    def __init__(self, pool_size_mb: float = 100, block_size_mb: float = 1):
        self.pool_size_mb = pool_size_mb
        self.block_size_mb = block_size_mb
        self.n_blocks = int(pool_size_mb / block_size_mb)
        self.available_blocks = list(range(self.n_blocks))
        self.allocated_blocks = {}
        self.lock = threading.Lock()
        
        logger.info(f"MemoryPool initialized: {self.n_blocks} blocks of {block_size_mb:.1f}MB each")
    
    def get_block(self) -> Optional[int]:
        """获取内存块"""
        with self.lock:
            if self.available_blocks:
                block_id = self.available_blocks.pop()
                self.allocated_blocks[block_id] = time.time()
                return block_id
            return None
    
    def return_block(self, block_id: int):
        """返回内存块"""
        with self.lock:
            if block_id in self.allocated_blocks:
                del self.allocated_blocks[block_id]
                self.available_blocks.append(block_id)
                logger.info(f"Memory block {block_id} returned to pool")
    
    def get_pool_status(self) -> Dict[str, Any]:
        """获取内存池状态"""
        with self.lock:
            return {
                'total_blocks': self.n_blocks,
                'available_blocks': len(self.available_blocks),
                'allocated_blocks': len(self.allocated_blocks),
                'utilization_percentage': (len(self.allocated_blocks) / self.n_blocks) * 100
            }

class DataCompressor:
    """数据压缩器"""
    
    def __init__(self, compression_method: str = "lz4"):
        self.compression_method = compression_method
        self.compression_stats = defaultdict(int)
        
        logger.info(f"DataCompressor initialized: method={compression_method}")
    
    def compress_data(self, data: Union[np.ndarray, bytes, str], 
                     compression_level: int = 1) -> bytes:
        """压缩数据"""
        start_time = time.time()
        
        try:
            if isinstance(data, np.ndarray):
                # 将numpy数组转换为字节
                data_bytes = data.tobytes()
            elif isinstance(data, str):
                data_bytes = data.encode('utf-8')
            else:
                data_bytes = data
            
            if self.compression_method == "gzip":
                compressed = gzip.compress(data_bytes, compresslevel=compression_level)
            elif self.compression_method == "lz4":
                compressed = lz4.frame.compress(data_bytes, compression_level=compression_level)
            else:
                raise ValueError(f"Unsupported compression method: {self.compression_method}")
            
            compression_time = time.time() - start_time
            compression_ratio = len(compressed) / len(data_bytes)
            
            # 记录统计信息
            self.compression_stats['compression_time'] += compression_time
            self.compression_stats['compression_ratio'] += compression_ratio
            self.compression_stats['compression_count'] += 1
            
            logger.info(f"Data compressed: {len(data_bytes)} -> {len(compressed)} bytes "
                       f"(ratio: {compression_ratio:.2f}) in {compression_time:.3f}s")
            
            return compressed
            
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return data_bytes
    
    def decompress_data(self, compressed_data: bytes) -> bytes:
        """解压数据"""
        start_time = time.time()
        
        try:
            if self.compression_method == "gzip":
                decompressed = gzip.decompress(compressed_data)
            elif self.compression_method == "lz4":
                decompressed = lz4.frame.decompress(compressed_data)
            else:
                raise ValueError(f"Unsupported compression method: {self.compression_method}")
            
            decompression_time = time.time() - start_time
            
            # 记录统计信息
            self.compression_stats['decompression_time'] += decompression_time
            self.compression_stats['decompression_count'] += 1
            
            logger.info(f"Data decompressed: {len(compressed_data)} -> {len(decompressed)} bytes "
                       f"in {decompression_time:.3f}s")
            
            return decompressed
            
        except Exception as e:
            logger.error(f"Decompression failed: {e}")
            return compressed_data
    
    def get_compression_stats(self) -> Dict[str, Any]:
        """获取压缩统计信息"""
        stats = dict(self.compression_stats)
        if stats['compression_count'] > 0:
            stats['avg_compression_ratio'] = stats['compression_ratio'] / stats['compression_count']
            stats['avg_compression_time'] = stats['compression_time'] / stats['compression_count']
        if stats['decompression_count'] > 0:
            stats['avg_decompression_time'] = stats['decompression_time'] / stats['decompression_count']
        
        return stats

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, max_cache_size_mb: float = 100, eviction_policy: str = "lru"):
        self.max_cache_size_mb = max_cache_size_mb
        self.eviction_policy = eviction_policy
        self.cache = {}
        self.access_order = deque()
        self.current_size_mb = 0
        self.lock = threading.Lock()
        
        logger.info(f"CacheManager initialized: max_size={max_cache_size_mb:.1f}MB, "
                   f"policy={eviction_policy}")
    
    def put(self, key: str, value: Any, size_mb: float = None):
        """放入缓存"""
        with self.lock:
            if size_mb is None:
                # 估算大小
                size_mb = self._estimate_size(value)
            
            # 检查是否需要清理缓存
            while self.current_size_mb + size_mb > self.max_cache_size_mb:
                if not self._evict_item():
                    logger.warning("Cache full, cannot add new item")
                    return
            
            # 添加到缓存
            self.cache[key] = {
                'value': value,
                'size_mb': size_mb,
                'access_count': 0,
                'last_access': time.time()
            }
            self.current_size_mb += size_mb
            self.access_order.append(key)
            
            logger.info(f"Item {key} added to cache: {size_mb:.1f}MB")
    
    def get(self, key: str) -> Optional[Any]:
        """从缓存获取"""
        with self.lock:
            if key in self.cache:
                item = self.cache[key]
                item['access_count'] += 1
                item['last_access'] = time.time()
                
                # 更新访问顺序
                if key in self.access_order:
                    self.access_order.remove(key)
                self.access_order.append(key)
                
                return item['value']
            return None
    
    def remove(self, key: str) -> bool:
        """从缓存移除"""
        with self.lock:
            if key in self.cache:
                item = self.cache[key]
                self.current_size_mb -= item['size_mb']
                del self.cache[key]
                
                if key in self.access_order:
                    self.access_order.remove(key)
                
                logger.info(f"Item {key} removed from cache")
                return True
            return False
    
    def _evict_item(self) -> bool:
        """驱逐缓存项"""
        if not self.cache:
            return False
        
        if self.eviction_policy == "lru":
            # 最近最少使用
            key_to_evict = self.access_order[0]
        elif self.eviction_policy == "lfu":
            # 最少使用频率
            key_to_evict = min(self.cache.keys(), 
                              key=lambda k: self.cache[k]['access_count'])
        else:
            # 默认LRU
            key_to_evict = self.access_order[0]
        
        self.remove(key_to_evict)
        return True
    
    def _estimate_size(self, value: Any) -> float:
        """估算对象大小"""
        try:
            if isinstance(value, np.ndarray):
                return value.nbytes / 1024**2
            elif isinstance(value, str):
                return len(value.encode('utf-8')) / 1024**2
            elif isinstance(value, bytes):
                return len(value) / 1024**2
            else:
                # 使用pickle估算
                return len(pickle.dumps(value)) / 1024**2
        except:
            return 0.1  # 默认0.1MB
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self.lock:
            return {
                'max_size_mb': self.max_cache_size_mb,
                'current_size_mb': self.current_size_mb,
                'utilization_percentage': (self.current_size_mb / self.max_cache_size_mb) * 100,
                'item_count': len(self.cache),
                'eviction_policy': self.eviction_policy
            }
    
    def clear_cache(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.access_order.clear()
            self.current_size_mb = 0
            logger.info("Cache cleared")

class StorageOptimizer:
    """存储优化器"""
    
    def __init__(self, base_path: str = "./data"):
        self.base_path = base_path
        self.data_files = {}
        self.compression_enabled = True
        self.chunk_size_mb = 10
        
        # 确保目录存在
        os.makedirs(base_path, exist_ok=True)
        
        logger.info(f"StorageOptimizer initialized: base_path={base_path}")
    
    def save_data(self, data_id: str, data: Any, compress: bool = True) -> str:
        """保存数据"""
        file_path = os.path.join(self.base_path, f"{data_id}.pkl")
        
        try:
            if compress and self.compression_enabled:
                # 压缩保存
                with gzip.open(file_path, 'wb') as f:
                    pickle.dump(data, f)
                file_path += '.gz'
            else:
                # 普通保存
                with open(file_path, 'wb') as f:
                    pickle.dump(data, f)
            
            # 记录文件信息
            file_size = os.path.getsize(file_path) / 1024**2
            self.data_files[data_id] = {
                'path': file_path,
                'size_mb': file_size,
                'compressed': compress and self.compression_enabled,
                'save_time': time.time()
            }
            
            logger.info(f"Data {data_id} saved: {file_size:.1f}MB")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save data {data_id}: {e}")
            raise
    
    def load_data(self, data_id: str) -> Any:
        """加载数据"""
        if data_id not in self.data_files:
            raise KeyError(f"Data {data_id} not found")
        
        file_info = self.data_files[data_id]
        file_path = file_info['path']
        
        try:
            if file_info['compressed']:
                # 加载压缩数据
                with gzip.open(file_path, 'rb') as f:
                    data = pickle.load(f)
            else:
                # 加载普通数据
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)
            
            logger.info(f"Data {data_id} loaded: {file_info['size_mb']:.1f}MB")
            return data
            
        except Exception as e:
            logger.error(f"Failed to load data {data_id}: {e}")
            raise
    
    def delete_data(self, data_id: str) -> bool:
        """删除数据"""
        if data_id not in self.data_files:
            return False
        
        file_info = self.data_files[data_id]
        file_path = file_info['path']
        
        try:
            os.remove(file_path)
            del self.data_files[data_id]
            logger.info(f"Data {data_id} deleted")
            return True
        except Exception as e:
            logger.error(f"Failed to delete data {data_id}: {e}")
            return False
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        total_size = sum(info['size_mb'] for info in self.data_files.values())
        compressed_count = sum(1 for info in self.data_files.values() if info['compressed'])
        
        return {
            'total_files': len(self.data_files),
            'total_size_mb': total_size,
            'compressed_files': compressed_count,
            'uncompressed_files': len(self.data_files) - compressed_count,
            'compression_enabled': self.compression_enabled
        }
    
    def optimize_storage(self):
        """存储优化"""
        logger.info("Starting storage optimization...")
        
        # 压缩未压缩的文件
        uncompressed_files = [data_id for data_id, info in self.data_files.items() 
                            if not info['compressed']]
        
        for data_id in uncompressed_files:
            try:
                # 加载数据
                data = self.load_data(data_id)
                
                # 删除原文件
                self.delete_data(data_id)
                
                # 重新保存为压缩格式
                self.save_data(data_id, data, compress=True)
                
                logger.info(f"File {data_id} compressed")
                
            except Exception as e:
                logger.error(f"Failed to compress {data_id}: {e}")
        
        logger.info("Storage optimization completed")

