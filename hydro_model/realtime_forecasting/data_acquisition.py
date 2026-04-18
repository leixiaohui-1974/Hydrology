"""
实时数据接入模块
================

本模块负责实时数据的采集、质量控制和处理
"""

import time
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from abc import ABC, abstractmethod
import threading
import queue

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class SensorData:
    """传感器数据结构"""
    timestamp: datetime
    sensor_id: str
    data_type: str
    value: float
    unit: str
    quality_flag: int
    metadata: Dict[str, Any]


class DataSource(ABC):
    """数据源抽象基类"""

    @abstractmethod
    def connect(self) -> bool:
        """连接数据源"""
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """断开数据源"""
        pass

    @abstractmethod
    def fetch_data(self, start_time: datetime, end_time: datetime) -> List[SensorData]:
        """获取数据"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """检查连接状态"""
        pass


class SensorDataAcquisition:
    """传感器数据接入器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.data_sources: Dict[str, DataSource] = {}
        self.data_buffer: queue.Queue = queue.Queue(maxsize=10000)
        self.is_running = False
        self.acquisition_thread = None
        self.lock = threading.Lock()

        # 数据源配置
        self.sensor_configs = config.get('sensors', {})
        self.acquisition_interval = config.get('acquisition_interval', 60)  # 秒

        logger.info(f"SensorDataAcquisition initialized with {len(self.sensor_configs)} sensors")

    def add_data_source(self, source_id: str, data_source: DataSource) -> bool:
        """添加数据源"""
        try:
            with self.lock:
                self.data_sources[source_id] = data_source
                logger.info(f"Added data source: {source_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to add data source {source_id}: {e}")
            return False

    def start_acquisition(self) -> bool:
        """开始数据采集"""
        if self.is_running:
            logger.warning("Data acquisition already running")
            return False

        try:
            self.is_running = True
            self.acquisition_thread = threading.Thread(target=self._acquisition_loop)
            self.acquisition_thread.daemon = True
            self.acquisition_thread.start()
            logger.info("Data acquisition started")
            return True
        except Exception as e:
            logger.error(f"Failed to start data acquisition: {e}")
            self.is_running = False
            return False

    def stop_acquisition(self) -> bool:
        """停止数据采集"""
        if not self.is_running:
            return True

        try:
            self.is_running = False
            if self.acquisition_thread:
                self.acquisition_thread.join(timeout=5)
            logger.info("Data acquisition stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop data acquisition: {e}")
            return False

    def _acquisition_loop(self):
        """数据采集循环"""
        while self.is_running:
            try:
                current_time = datetime.now()
                
                # 从所有数据源获取数据
                for source_id, data_source in self.data_sources.items():
                    if data_source.is_connected():
                        try:
                            # 获取最近的数据
                            end_time = current_time
                            start_time = end_time - timedelta(minutes=5)
                            data = data_source.fetch_data(start_time, end_time)
                            
                            # 将数据放入缓冲区
                            for item in data:
                                if not self.data_buffer.full():
                                    self.data_buffer.put(item)
                                
                        except Exception as e:
                            logger.error(f"Error fetching data from {source_id}: {e}")

                # 等待下次采集
                time.sleep(self.acquisition_interval)

            except Exception as e:
                logger.error(f"Error in acquisition loop: {e}")
                time.sleep(5)

    def get_latest_data(self, data_type: Optional[str] = None) -> List[SensorData]:
        """获取最新数据"""
        data = []
        try:
            while not self.data_buffer.empty():
                item = self.data_buffer.get_nowait()
                if data_type is None or item.data_type == data_type:
                    data.append(item)
        except queue.Empty:
            pass
        
        return data

    def get_data_statistics(self) -> Dict[str, Any]:
        """获取数据统计信息"""
        stats = {
            'total_sources': len(self.data_sources),
            'connected_sources': sum(1 for s in self.data_sources.values() if s.is_connected()),
            'buffer_size': self.data_buffer.qsize(),
            'is_running': self.is_running
        }
        return stats


class DataQualityControl:
    """数据质量控制器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.quality_rules = config.get('quality_rules', {})
        self.anomaly_detectors = config.get('anomaly_detectors', {})
        
        logger.info("DataQualityControl initialized")

    def validate_data(self, data: SensorData) -> Tuple[bool, str]:
        """验证数据质量"""
        try:
            # 范围检查
            if not self._check_range(data):
                return False, "数据超出有效范围"

            # 一致性检查
            if not self._check_consistency(data):
                return False, "数据不一致"

            # 异常检测
            if self._detect_anomaly(data):
                return False, "检测到异常数据"

            return True, "数据质量良好"

        except Exception as e:
            logger.error(f"Data validation error: {e}")
            return False, f"验证过程出错: {e}"

    def _check_range(self, data: SensorData) -> bool:
        """检查数据范围"""
        data_type = data.data_type
        if data_type in self.quality_rules:
            rules = self.quality_rules[data_type]
            min_val = rules.get('min_value', float('-inf'))
            max_val = rules.get('max_value', float('inf'))
            
            return min_val <= data.value <= max_val
        return True

    def _check_consistency(self, data: SensorData) -> bool:
        """检查数据一致性"""
        # 这里可以实现更复杂的一致性检查逻辑
        # 例如检查数据变化率是否合理
        return True

    def _detect_anomaly(self, data: SensorData) -> bool:
        """异常检测"""
        # 这里可以实现统计异常检测算法
        # 例如Z-score方法、IQR方法等
        return False

    def repair_data(self, data: SensorData, repair_method: str = 'interpolation') -> Optional[float]:
        """修复数据"""
        try:
            if repair_method == 'interpolation':
                return self._interpolate_data(data)
            elif repair_method == 'statistical':
                return self._statistical_repair(data)
            else:
                logger.warning(f"Unknown repair method: {repair_method}")
                return None
        except Exception as e:
            logger.error(f"Data repair error: {e}")
            return None

    def _interpolate_data(self, data: SensorData) -> Optional[float]:
        """插值修复"""
        # 这里可以实现时间序列插值算法
        return None

    def _statistical_repair(self, data: SensorData) -> Optional[float]:
        """统计修复"""
        # 这里可以使用均值、中位数等统计量进行修复
        return None


class RealTimeDataValidator:
    """实时数据验证器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.validation_history: List[Dict[str, Any]] = []
        self.validation_rules = config.get('validation_rules', {})
        
        logger.info("RealTimeDataValidator initialized")

    def validate_stream(self, data_stream: List[SensorData]) -> Dict[str, Any]:
        """验证数据流"""
        validation_results = {
            'total_count': len(data_stream),
            'valid_count': 0,
            'invalid_count': 0,
            'validation_details': [],
            'overall_quality': 0.0
        }

        try:
            for data in data_stream:
                is_valid, message = self._validate_single_data(data)
                validation_results['validation_details'].append({
                    'sensor_id': data.sensor_id,
                    'timestamp': data.timestamp,
                    'is_valid': is_valid,
                    'message': message
                })

                if is_valid:
                    validation_results['valid_count'] += 1
                else:
                    validation_results['invalid_count'] += 1

            # 计算整体质量
            if validation_results['total_count'] > 0:
                validation_results['overall_quality'] = (
                    validation_results['valid_count'] / validation_results['total_count']
                )

            # 记录验证历史
            self.validation_history.append({
                'timestamp': datetime.now(),
                'results': validation_results
            })

            return validation_results

        except Exception as e:
            logger.error(f"Stream validation error: {e}")
            return validation_results

    def _validate_single_data(self, data: SensorData) -> Tuple[bool, str]:
        """验证单个数据"""
        try:
            # 基本验证
            if data.value is None or np.isnan(data.value):
                return False, "数据为空或NaN"

            # 时间验证
            if data.timestamp > datetime.now() + timedelta(minutes=5):
                return False, "时间戳异常"

            # 传感器ID验证
            if not data.sensor_id or len(data.sensor_id.strip()) == 0:
                return False, "传感器ID无效"

            return True, "验证通过"

        except Exception as e:
            return False, f"验证异常: {e}"

    def get_validation_summary(self, time_window: timedelta = timedelta(hours=1)) -> Dict[str, Any]:
        """获取验证摘要"""
        cutoff_time = datetime.now() - time_window
        recent_validations = [
            v for v in self.validation_history 
            if v['timestamp'] >= cutoff_time
        ]

        if not recent_validations:
            return {'message': '无验证数据'}

        total_validations = len(recent_validations)
        avg_quality = np.mean([v['results']['overall_quality'] for v in recent_validations])

        return {
            'time_window': str(time_window),
            'total_validations': total_validations,
            'average_quality': avg_quality,
            'quality_trend': self._calculate_quality_trend(recent_validations)
        }

    def _calculate_quality_trend(self, validations: List[Dict[str, Any]]) -> str:
        """计算质量趋势"""
        if len(validations) < 2:
            return "数据不足"

        qualities = [v['results']['overall_quality'] for v in validations]
        if qualities[-1] > qualities[0]:
            return "质量改善"
        elif qualities[-1] < qualities[0]:
            return "质量下降"
        else:
            return "质量稳定"


class DataInterpolation:
    """数据插补器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.interpolation_methods = config.get('interpolation_methods', {})
        
        logger.info("DataInterpolation initialized")

    def interpolate_missing_data(self, data_series: List[SensorData], 
                                method: str = 'linear') -> List[SensorData]:
        """插补缺失数据"""
        try:
            if not data_series:
                return data_series

            # 转换为DataFrame便于处理
            df = pd.DataFrame([
                {
                    'timestamp': d.timestamp,
                    'sensor_id': d.sensor_id,
                    'data_type': d.data_type,
                    'value': d.value,
                    'unit': d.unit,
                    'quality_flag': d.quality_flag,
                    'metadata': d.metadata
                }
                for d in data_series
            ])

            # 按时间排序
            df = df.sort_values('timestamp')

            # 插补缺失值
            if method == 'linear':
                df['value'] = df['value'].interpolate(method='linear')
            elif method == 'cubic':
                df['value'] = df['value'].interpolate(method='cubic')
            elif method == 'polynomial':
                df['value'] = df['value'].interpolate(method='polynomial', order=2)
            else:
                logger.warning(f"Unknown interpolation method: {method}")
                df['value'] = df['value'].interpolate(method='linear')

            # 转换回SensorData列表
            interpolated_data = []
            for _, row in df.iterrows():
                data = SensorData(
                    timestamp=row['timestamp'],
                    sensor_id=row['sensor_id'],
                    data_type=row['data_type'],
                    value=row['value'],
                    unit=row['unit'],
                    quality_flag=row['quality_flag'],
                    metadata=row['metadata']
                )
                interpolated_data.append(data)

            logger.info(f"Interpolated {len(interpolated_data)} data points using {method} method")
            return interpolated_data

        except Exception as e:
            logger.error(f"Data interpolation error: {e}")
            return data_series

    def fill_gaps(self, data_series: List[SensorData], 
                  max_gap_duration: timedelta = timedelta(hours=1)) -> List[SensorData]:
        """填充数据间隙"""
        try:
            if len(data_series) < 2:
                return data_series

            # 按时间排序
            sorted_data = sorted(data_series, key=lambda x: x.timestamp)
            filled_data = []

            for i in range(len(sorted_data) - 1):
                current = sorted_data[i]
                next_data = sorted_data[i + 1]
                
                filled_data.append(current)
                
                # 检查时间间隙
                time_gap = next_data.timestamp - current.timestamp
                if time_gap > max_gap_duration:
                    # 在间隙中插入插值数据
                    gap_data = self._create_gap_data(current, next_data, time_gap)
                    filled_data.extend(gap_data)

            filled_data.append(sorted_data[-1])
            
            logger.info(f"Filled gaps in data series, total points: {len(filled_data)}")
            return filled_data

        except Exception as e:
            logger.error(f"Gap filling error: {e}")
            return data_series

    def _create_gap_data(self, start_data: SensorData, end_data: SensorData, 
                         gap_duration: timedelta) -> List[SensorData]:
        """创建间隙数据"""
        gap_data = []
        
        # 计算需要插入的点数（假设每5分钟一个点）
        time_step = timedelta(minutes=5)
        num_points = int(gap_duration.total_seconds() / time_step.total_seconds()) - 1
        
        if num_points <= 0:
            return gap_data

        # 线性插值
        start_value = start_data.value
        end_value = end_data.value
        value_step = (end_value - start_value) / (num_points + 1)

        for i in range(1, num_points + 1):
            timestamp = start_data.timestamp + time_step * i
            value = start_value + value_step * i
            
            gap_data.append(SensorData(
                timestamp=timestamp,
                sensor_id=start_data.sensor_id,
                data_type=start_data.data_type,
                value=value,
                unit=start_data.unit,
                quality_flag=2,  # 插值数据标志
                metadata={'interpolated': True, 'method': 'linear'}
            ))

        return gap_data

