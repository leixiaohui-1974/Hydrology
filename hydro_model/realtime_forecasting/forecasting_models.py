"""
预报模型模块
============

本模块提供各种预报模型和算法
"""

import logging
import queue
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

# 配置日志
logger = logging.getLogger(__name__)


DurationInput = Union[int, float, str, timedelta, Dict[str, Union[int, float]]]


def _ensure_timedelta(value: DurationInput, default_unit: str) -> timedelta:
    """将配置值转换为 :class:`datetime.timedelta`."""
    if isinstance(value, timedelta):
        return value

    if isinstance(value, dict):
        return timedelta(**value)

    unit_map = {
        'seconds': 'seconds',
        'minutes': 'minutes',
        'hours': 'hours',
        'days': 'days'
    }

    if isinstance(value, (int, float)):
        target_unit = unit_map.get(default_unit, default_unit)
        return timedelta(**{target_unit: float(value)})

    if isinstance(value, str):
        stripped = value.strip().lower()
        suffix_map = {
            'ms': ('milliseconds', 1),
            's': ('seconds', 1),
            'sec': ('seconds', 1),
            'second': ('seconds', 1),
            'seconds': ('seconds', 1),
            'm': ('minutes', 1),
            'min': ('minutes', 1),
            'minute': ('minutes', 1),
            'minutes': ('minutes', 1),
            'h': ('hours', 1),
            'hr': ('hours', 1),
            'hour': ('hours', 1),
            'hours': ('hours', 1),
            'd': ('days', 1),
            'day': ('days', 1),
            'days': ('days', 1)
        }

        for suffix, (unit, multiplier) in suffix_map.items():
            if stripped.endswith(suffix):
                number = stripped[:-len(suffix)].strip()
                value_num = float(number) * multiplier if number else 0.0
                return timedelta(**{unit: value_num})

        try:
            numeric = float(stripped)
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise TypeError(f"Cannot convert '{value}' to timedelta") from exc
        else:
            target_unit = unit_map.get(default_unit, default_unit)
            return timedelta(**{target_unit: numeric})

    raise TypeError(f"Unsupported duration type: {type(value)!r}")


@dataclass
class ForecastResult:
    """预报结果数据结构"""
    timestamp: datetime
    forecast_time: datetime
    lead_time: timedelta
    variable: str
    value: float
    unit: str
    confidence_lower: Optional[float] = None
    confidence_upper: Optional[float] = None
    uncertainty: Optional[float] = None
    model_id: str = ""
    metadata: Dict[str, Any] = None


class BaseForecaster(ABC):
    """预报器基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model_id = config.get('model_id', 'base_forecaster')
        self.forecast_history: List[ForecastResult] = []
        self.is_trained = False
        self.lock = threading.Lock()

    @abstractmethod
    def train(self, training_data: List[Any]) -> bool:
        """训练模型"""
        pass

    @abstractmethod
    def forecast(self, input_data: Any, lead_time: timedelta) -> ForecastResult:
        """进行预报"""
        pass

    @abstractmethod
    def evaluate_forecast(self, observed: List[float], 
                         forecasted: List[float]) -> Dict[str, float]:
        """评估预报精度"""
        pass

    def get_forecast_history(self, time_window: timedelta = timedelta(days=7)) -> List[ForecastResult]:
        """获取预报历史"""
        cutoff_time = datetime.now() - time_window
        return [f for f in self.forecast_history if f.timestamp >= cutoff_time]

    def add_forecast_result(self, result: ForecastResult):
        """添加预报结果到历史记录"""
        with self.lock:
            self.forecast_history.append(result)
            # 保持历史记录在合理范围内
            if len(self.forecast_history) > 10000:
                self.forecast_history = self.forecast_history[-5000:]


class ShortTermForecaster(BaseForecaster):
    """短期预报器 (1-6小时)"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.forecast_horizon = _ensure_timedelta(
            config.get('forecast_horizon', timedelta(hours=6)),
            'hours'
        )
        self.time_step = _ensure_timedelta(
            config.get('time_step', timedelta(minutes=15)),
            'minutes'
        )
        self.correction_method = config.get('correction_method', 'kalman_filter')

        # 预报模型参数
        self.model_params = config.get('model_params', {})
        self.correction_params = config.get('correction_params', {})
        
        logger.info(f"ShortTermForecaster initialized with {self.forecast_horizon} horizon")

    def train(self, training_data: List[Any]) -> bool:
        """训练短期预报模型"""
        try:
            # 这里实现具体的训练逻辑
            # 例如：时间序列模型、机器学习模型等
            
            logger.info("Short-term forecast model training completed")
            self.is_trained = True
            return True
            
        except Exception as e:
            logger.error(f"Short-term forecast model training failed: {e}")
            return False

    def forecast(self, input_data: Any, lead_time: timedelta) -> ForecastResult:
        """进行短期预报"""
        if not self.is_trained:
            raise RuntimeError("Model not trained yet")

        if lead_time > self.forecast_horizon:
            raise ValueError(f"Lead time {lead_time} exceeds forecast horizon {self.forecast_horizon}")

        try:
            # 这里实现具体的预报逻辑
            forecast_value = self._calculate_forecast(input_data, lead_time)
            
            # 计算不确定性
            uncertainty = self._estimate_uncertainty(lead_time)
            confidence_lower = forecast_value - uncertainty
            confidence_upper = forecast_value + uncertainty
            
            result = ForecastResult(
                timestamp=datetime.now(),
                forecast_time=datetime.now() + lead_time,
                lead_time=lead_time,
                variable=input_data.get('variable', 'unknown'),
                value=forecast_value,
                unit=input_data.get('unit', 'unknown'),
                confidence_lower=confidence_lower,
                confidence_upper=confidence_upper,
                uncertainty=uncertainty,
                model_id=self.model_id,
                metadata={'forecast_type': 'short_term'}
            )
            
            self.add_forecast_result(result)
            return result
            
        except Exception as e:
            logger.error(f"Short-term forecasting failed: {e}")
            raise

    def _calculate_forecast(self, input_data: Any, lead_time: timedelta) -> float:
        """计算预报值"""
        # 这里实现具体的预报算法
        # 例如：线性外推、ARIMA模型、神经网络等
        
        base_value = input_data.get('current_value', 0.0)
        trend = input_data.get('trend', 0.0)
        
        # 简单的线性外推
        hours_ahead = lead_time.total_seconds() / 3600
        forecast_value = base_value + trend * hours_ahead
        
        return forecast_value

    def _estimate_uncertainty(self, lead_time: timedelta) -> float:
        """估计预报不确定性"""
        # 不确定性随预报时间增加而增加
        hours_ahead = lead_time.total_seconds() / 3600
        base_uncertainty = self.correction_params.get('base_uncertainty', 0.1)
        uncertainty_growth = self.correction_params.get('uncertainty_growth', 0.05)
        
        return base_uncertainty + uncertainty_growth * hours_ahead

    def evaluate_forecast(self, observed: List[float], 
                         forecasted: List[float]) -> Dict[str, float]:
        """评估短期预报精度"""
        try:
            if len(observed) != len(forecasted):
                raise ValueError("Observed and forecasted data lengths must match")

            # 计算各种评估指标
            errors = np.array(forecasted) - np.array(observed)
            
            metrics = {
                'rmse': np.sqrt(np.mean(errors ** 2)),
                'mae': np.mean(np.abs(errors)),
                'mape': np.mean(np.abs(errors / np.array(observed))) * 100,
                'correlation': np.corrcoef(observed, forecasted)[0, 1],
                'bias': np.mean(errors)
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Forecast evaluation failed: {e}")
            return {}


class MediumTermForecaster(BaseForecaster):
    """中期预报器 (1-7天)"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.forecast_horizon = _ensure_timedelta(
            config.get('forecast_horizon', timedelta(days=7)),
            'days'
        )
        self.time_step = _ensure_timedelta(
            config.get('time_step', timedelta(hours=1)),
            'hours'
        )
        self.ensemble_size = config.get('ensemble_size', 10)
        
        # 集合预报参数
        self.ensemble_params = config.get('ensemble_params', {})
        
        logger.info(f"MediumTermForecaster initialized with {self.forecast_horizon} horizon")

    def train(self, training_data: List[Any]) -> bool:
        """训练中期预报模型"""
        try:
            # 这里实现具体的训练逻辑
            # 例如：集合预报模型、统计降尺度等
            
            logger.info("Medium-term forecast model training completed")
            self.is_trained = True
            return True
            
        except Exception as e:
            logger.error(f"Medium-term forecast model training failed: {e}")
            return False

    def forecast(self, input_data: Any, lead_time: timedelta) -> ForecastResult:
        """进行中期预报"""
        if not self.is_trained:
            raise RuntimeError("Model not trained yet")

        if lead_time > self.forecast_horizon:
            raise ValueError(f"Lead time {lead_time} exceeds forecast horizon {self.forecast_horizon}")

        try:
            # 生成集合预报
            ensemble_forecasts = self._generate_ensemble_forecast(input_data, lead_time)
            
            # 计算集合统计量
            forecast_value = np.mean(ensemble_forecasts)
            uncertainty = np.std(ensemble_forecasts)
            confidence_lower = np.percentile(ensemble_forecasts, 5)
            confidence_upper = np.percentile(ensemble_forecasts, 95)
            
            result = ForecastResult(
                timestamp=datetime.now(),
                forecast_time=datetime.now() + lead_time,
                lead_time=lead_time,
                variable=input_data.get('variable', 'unknown'),
                value=forecast_value,
                unit=input_data.get('unit', 'unknown'),
                confidence_lower=confidence_lower,
                confidence_upper=confidence_upper,
                uncertainty=uncertainty,
                model_id=self.model_id,
                metadata={
                    'forecast_type': 'medium_term',
                    'ensemble_size': self.ensemble_size,
                    'ensemble_forecasts': ensemble_forecasts
                }
            )
            
            self.add_forecast_result(result)
            return result
            
        except Exception as e:
            logger.error(f"Medium-term forecasting failed: {e}")
            raise

    def _generate_ensemble_forecast(self, input_data: Any, lead_time: timedelta) -> List[float]:
        """生成集合预报"""
        ensemble_forecasts = []
        
        for i in range(self.ensemble_size):
            # 为每个集合成员添加扰动
            perturbed_data = self._perturb_input_data(input_data, i)
            forecast = self._calculate_ensemble_forecast(perturbed_data, lead_time)
            ensemble_forecasts.append(forecast)
        
        return ensemble_forecasts

    def _perturb_input_data(self, input_data: Any, member_id: int) -> Any:
        """扰动输入数据"""
        # 这里实现具体的扰动逻辑
        # 例如：添加随机噪声、参数扰动等
        
        perturbed_data = input_data.copy()
        if 'current_value' in perturbed_data:
            noise_level = self.ensemble_params.get('noise_level', 0.05)
            noise = np.random.normal(0, noise_level * perturbed_data['current_value'])
            perturbed_data['current_value'] += noise
        
        return perturbed_data

    def _calculate_ensemble_forecast(self, input_data: Any, lead_time: timedelta) -> float:
        """计算集合预报值"""
        # 这里实现具体的预报算法
        # 例如：物理模型、统计模型等
        
        base_value = input_data.get('current_value', 0.0)
        trend = input_data.get('trend', 0.0)
        
        # 中期预报通常需要考虑周期性变化
        days_ahead = lead_time.total_seconds() / 86400
        seasonal_factor = np.sin(2 * np.pi * days_ahead / 365.25) * 0.1
        
        forecast_value = base_value + trend * days_ahead + seasonal_factor
        
        return forecast_value

    def evaluate_forecast(self, observed: List[float], 
                         forecasted: List[float]) -> Dict[str, float]:
        """评估中期预报精度"""
        try:
            if len(observed) != len(forecasted):
                raise ValueError("Observed and forecasted data lengths must match")

            # 计算各种评估指标
            errors = np.array(forecasted) - np.array(observed)
            
            metrics = {
                'rmse': np.sqrt(np.mean(errors ** 2)),
                'mae': np.mean(np.abs(errors)),
                'mape': np.mean(np.abs(errors / np.array(observed))) * 100,
                'correlation': np.corrcoef(observed, forecasted)[0, 1],
                'bias': np.mean(errors),
                'ensemble_spread': np.mean([f.metadata.get('ensemble_forecasts', []) for f in self.forecast_history[-len(observed):]])
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Forecast evaluation failed: {e}")
            return {}


class EnsembleForecaster(BaseForecaster):
    """集合预报器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.forecasters: List[BaseForecaster] = []
        self.weights: List[float] = []
        self.ensemble_method = config.get('ensemble_method', 'weighted_average')
        
        logger.info("EnsembleForecaster initialized")

    def add_forecaster(self, forecaster: BaseForecaster, weight: float = 1.0):
        """添加预报器到集合"""
        self.forecasters.append(forecaster)
        self.weights.append(weight)
        
        # 重新归一化权重
        total_weight = sum(self.weights)
        self.weights = [w / total_weight for w in self.weights]
        
        logger.info(f"Added forecaster {forecaster.model_id} with weight {weight}")

    def forecast(self, input_data: Any, lead_time: timedelta) -> ForecastResult:
        """进行集合预报"""
        if not self.forecasters:
            raise RuntimeError("No forecasters in ensemble")

        try:
            # 获取各个预报器的预报结果
            individual_forecasts = []
            for forecaster in self.forecasters:
                try:
                    forecast = forecaster.forecast(input_data, lead_time)
                    individual_forecasts.append(forecast)
                except Exception as e:
                    logger.warning(f"Forecaster {forecaster.model_id} failed: {e}")

            if not individual_forecasts:
                raise RuntimeError("All forecasters failed")

            # 组合预报结果
            if self.ensemble_method == 'weighted_average':
                result = self._weighted_average_ensemble(individual_forecasts, lead_time, input_data)
            elif self.ensemble_method == 'median':
                result = self._median_ensemble(individual_forecasts, lead_time, input_data)
            else:
                result = self._weighted_average_ensemble(individual_forecasts, lead_time, input_data)

            self.add_forecast_result(result)
            return result
            
        except Exception as e:
            logger.error(f"Ensemble forecasting failed: {e}")
            raise

    def _weighted_average_ensemble(self, forecasts: List[ForecastResult], 
                                  lead_time: timedelta, input_data: Any) -> ForecastResult:
        """加权平均集合"""
        # 计算加权平均
        total_weight = 0
        weighted_sum = 0
        weighted_uncertainty_sum = 0
        
        for i, forecast in enumerate(forecasts):
            weight = self.weights[i] if i < len(self.weights) else 1.0
            weighted_sum += forecast.value * weight
            if forecast.uncertainty:
                weighted_uncertainty_sum += forecast.uncertainty * weight
            total_weight += weight

        ensemble_value = weighted_sum / total_weight
        ensemble_uncertainty = weighted_uncertainty_sum / total_weight if weighted_uncertainty_sum > 0 else None

        # 计算置信区间
        confidence_lower = None
        confidence_upper = None
        if all(f.confidence_lower is not None and f.confidence_upper is not None for f in forecasts):
            lower_bounds = [f.confidence_lower for f in forecasts]
            upper_bounds = [f.confidence_upper for f in forecasts]
            confidence_lower = np.percentile(lower_bounds, 10)
            confidence_upper = np.percentile(upper_bounds, 90)

        return ForecastResult(
            timestamp=datetime.now(),
            forecast_time=datetime.now() + lead_time,
            lead_time=lead_time,
            variable=input_data.get('variable', 'unknown'),
            value=ensemble_value,
            unit=input_data.get('unit', 'unknown'),
            confidence_lower=confidence_lower,
            confidence_upper=confidence_upper,
            uncertainty=ensemble_uncertainty,
            model_id=f"ensemble_{self.model_id}",
            metadata={
                'ensemble_method': self.ensemble_method,
                'individual_forecasts': [f.value for f in forecasts],
                'weights': self.weights[:len(forecasts)]
            }
        )

    def _median_ensemble(self, forecasts: List[ForecastResult], 
                        lead_time: timedelta, input_data: Any) -> ForecastResult:
        """中位数集合"""
        values = [f.value for f in forecasts]
        ensemble_value = np.median(values)
        
        # 计算不确定性
        ensemble_uncertainty = np.std(values)
        
        # 计算置信区间
        confidence_lower = np.percentile(values, 10)
        confidence_upper = np.percentile(values, 90)

        return ForecastResult(
            timestamp=datetime.now(),
            forecast_time=datetime.now() + lead_time,
            lead_time=lead_time,
            variable=input_data.get('variable', 'unknown'),
            value=ensemble_value,
            unit=input_data.get('unit', 'unknown'),
            confidence_lower=confidence_lower,
            confidence_upper=confidence_upper,
            uncertainty=ensemble_uncertainty,
            model_id=f"ensemble_{self.model_id}",
            metadata={
                'ensemble_method': self.ensemble_method,
                'individual_forecasts': values
            }
        )

    def train(self, training_data: List[Any]) -> bool:
        """训练集合预报器"""
        try:
            success_count = 0
            for forecaster in self.forecasters:
                if forecaster.train(training_data):
                    success_count += 1
            
            self.is_trained = success_count > 0
            logger.info(f"Ensemble training completed: {success_count}/{len(self.forecasters)} successful")
            return self.is_trained
            
        except Exception as e:
            logger.error(f"Ensemble training failed: {e}")
            return False

    def evaluate_forecast(self, observed: List[float], 
                         forecasted: List[float]) -> Dict[str, float]:
        """评估集合预报精度"""
        try:
            if len(observed) != len(forecasted):
                raise ValueError("Observed and forecasted data lengths must match")

            # 计算各种评估指标
            errors = np.array(forecasted) - np.array(observed)
            
            metrics = {
                'rmse': np.sqrt(np.mean(errors ** 2)),
                'mae': np.mean(np.abs(errors)),
                'mape': np.mean(np.abs(errors / np.array(observed))) * 100,
                'correlation': np.corrcoef(observed, forecasted)[0, 1],
                'bias': np.mean(errors)
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Ensemble forecast evaluation failed: {e}")
            return {}


class ForecastCorrector:
    """预报校正器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.correction_method = config.get('correction_method', 'kalman_filter')
        self.correction_params = config.get('correction_params', {})
        self.correction_history: List[Dict[str, Any]] = []
        
        logger.info(f"ForecastCorrector initialized with {self.correction_method} method")

    def correct_forecast(self, forecast: ForecastResult, 
                        observed: Optional[float] = None) -> ForecastResult:
        """校正预报结果"""
        try:
            if self.correction_method == 'kalman_filter':
                corrected_result = self._kalman_filter_correction(forecast, observed)
            elif self.correction_method == 'bias_correction':
                corrected_result = self._bias_correction(forecast, observed)
            elif self.correction_method == 'statistical_correction':
                corrected_result = self._statistical_correction(forecast, observed)
            else:
                logger.warning(f"Unknown correction method: {self.correction_method}")
                corrected_result = forecast

            # 记录校正历史
            self.correction_history.append({
                'timestamp': datetime.now(),
                'original_forecast': forecast.value,
                'corrected_forecast': corrected_result.value,
                'correction_method': self.correction_method,
                'observed': observed
            })

            return corrected_result
            
        except Exception as e:
            logger.error(f"Forecast correction failed: {e}")
            return forecast

    def _kalman_filter_correction(self, forecast: ForecastResult, 
                                 observed: Optional[float]) -> ForecastResult:
        """卡尔曼滤波校正"""
        if observed is None:
            return forecast

        # 简化的卡尔曼滤波实现
        # 这里可以实现完整的卡尔曼滤波算法
        
        # 计算校正因子
        correction_factor = observed / forecast.value if forecast.value != 0 else 1.0
        
        # 应用校正
        corrected_value = forecast.value * correction_factor
        
        # 更新不确定性
        corrected_uncertainty = forecast.uncertainty * 0.8 if forecast.uncertainty else None
        
        # 创建校正后的结果
        corrected_result = ForecastResult(
            timestamp=forecast.timestamp,
            forecast_time=forecast.forecast_time,
            lead_time=forecast.lead_time,
            variable=forecast.variable,
            value=corrected_value,
            unit=forecast.unit,
            confidence_lower=forecast.confidence_lower,
            confidence_upper=forecast.confidence_upper,
            uncertainty=corrected_uncertainty,
            model_id=f"{forecast.model_id}_corrected",
            metadata={
                'correction_method': 'kalman_filter',
                'correction_factor': correction_factor,
                'original_forecast': forecast.value
            }
        )
        
        return corrected_result

    def _bias_correction(self, forecast: ForecastResult, 
                         observed: Optional[float]) -> ForecastResult:
        """偏差校正"""
        if observed is None:
            return forecast

        # 计算偏差
        bias = observed - forecast.value
        
        # 应用偏差校正
        corrected_value = forecast.value + bias
        
        # 创建校正后的结果
        corrected_result = ForecastResult(
            timestamp=forecast.timestamp,
            forecast_time=forecast.forecast_time,
            lead_time=forecast.lead_time,
            variable=forecast.variable,
            value=corrected_value,
            unit=forecast.unit,
            confidence_lower=forecast.confidence_lower,
            confidence_upper=forecast.confidence_upper,
            uncertainty=forecast.uncertainty,
            model_id=f"{forecast.model_id}_corrected",
            metadata={
                'correction_method': 'bias_correction',
                'bias': bias,
                'original_forecast': forecast.value
            }
        )
        
        return corrected_result

    def _statistical_correction(self, forecast: ForecastResult, 
                               observed: Optional[float]) -> ForecastResult:
        """统计校正"""
        if observed is None:
            return forecast

        # 基于历史校正的统计校正
        if len(self.correction_history) > 0:
            # 计算平均校正因子
            recent_corrections = self.correction_history[-10:]  # 最近10次校正
            correction_factors = []
            
            for correction in recent_corrections:
                if correction['observed'] is not None and correction['original_forecast'] != 0:
                    factor = correction['observed'] / correction['original_forecast']
                    correction_factors.append(factor)
            
            if correction_factors:
                avg_correction_factor = np.mean(correction_factors)
                corrected_value = forecast.value * avg_correction_factor
            else:
                corrected_value = forecast.value
        else:
            corrected_value = forecast.value

        # 创建校正后的结果
        corrected_result = ForecastResult(
            timestamp=forecast.timestamp,
            forecast_time=forecast.forecast_time,
            lead_time=forecast.lead_time,
            variable=forecast.variable,
            value=corrected_value,
            unit=forecast.unit,
            confidence_lower=forecast.confidence_lower,
            confidence_upper=forecast.confidence_upper,
            uncertainty=forecast.uncertainty,
            model_id=f"{forecast.model_id}_corrected",
            metadata={
                'correction_method': 'statistical_correction',
                'original_forecast': forecast.value
            }
        )
        
        return corrected_result

    def get_correction_summary(self, time_window: timedelta = timedelta(hours=24)) -> Dict[str, Any]:
        """获取校正摘要"""
        cutoff_time = datetime.now() - time_window
        recent_corrections = [
            c for c in self.correction_history 
            if c['timestamp'] >= cutoff_time
        ]

        if not recent_corrections:
            return {'message': '无校正数据'}

        # 计算校正统计量
        corrections = []
        for correction in recent_corrections:
            if correction['observed'] is not None and correction['original_forecast'] != 0:
                correction_factor = correction['observed'] / correction['original_forecast']
                corrections.append(correction_factor)

        if corrections:
            return {
                'total_corrections': len(recent_corrections),
                'average_correction_factor': np.mean(corrections),
                'correction_factor_std': np.std(corrections),
                'correction_method': self.correction_method
            }
        else:
            return {'message': '无有效校正数据'}

