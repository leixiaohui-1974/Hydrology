"""
实时仪表板模块
==============

本模块提供实时监控和可视化功能
"""

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure

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
        except ValueError as exc:  # pragma: no cover - defensive
            raise TypeError(f"Cannot convert '{value}' to timedelta") from exc
        else:
            target_unit = unit_map.get(default_unit, default_unit)
            return timedelta(**{target_unit: numeric})

    raise TypeError(f"Unsupported duration type: {type(value)!r}")


@dataclass
class DashboardMetric:
    """仪表板指标结构"""
    name: str
    value: float
    unit: str
    status: str  # 'normal', 'warning', 'critical'
    timestamp: datetime
    trend: str  # 'increasing', 'decreasing', 'stable'
    metadata: Dict[str, Any] = None


class RealTimeDashboard:
    """实时仪表板"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.metrics: Dict[str, DashboardMetric] = {}
        self.update_interval = config.get('update_interval', 5)  # 秒
        self.is_running = False
        self.dashboard_thread = None
        self.lock = threading.Lock()
        
        # 数据源配置
        self.data_sources = config.get('data_sources', {})
        self.alert_thresholds = config.get('alert_thresholds', {})
        
        logger.info("RealTimeDashboard initialized")

    def start_dashboard(self) -> bool:
        """启动仪表板"""
        if self.is_running:
            logger.warning("Dashboard already running")
            return False

        try:
            self.is_running = True
            self.dashboard_thread = threading.Thread(target=self._dashboard_loop)
            self.dashboard_thread.daemon = True
            self.dashboard_thread.start()
            logger.info("Dashboard started")
            return True
        except Exception as e:
            logger.error(f"Failed to start dashboard: {e}")
            self.is_running = False
            return False

    def stop_dashboard(self) -> bool:
        """停止仪表板"""
        if not self.is_running:
            return True

        try:
            self.is_running = False
            if self.dashboard_thread:
                self.dashboard_thread.join(timeout=5)
            logger.info("Dashboard stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop dashboard: {e}")
            return False

    def _dashboard_loop(self):
        """仪表板主循环"""
        while self.is_running:
            try:
                # 更新所有指标
                self._update_metrics()
                
                # 检查告警
                self._check_alerts()
                
                # 等待下次更新
                time.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"Error in dashboard loop: {e}")
                time.sleep(5)

    def _update_metrics(self):
        """更新指标"""
        try:
            with self.lock:
                for metric_name, data_source in self.data_sources.items():
                    try:
                        # 从数据源获取最新值
                        current_value = self._get_metric_value(data_source)
                        if current_value is not None:
                            # 更新指标
                            self._update_metric(metric_name, current_value, data_source)
                    except Exception as e:
                        logger.error(f"Failed to update metric {metric_name}: {e}")

        except Exception as e:
            logger.error(f"Metrics update failed: {e}")

    def _get_metric_value(self, data_source: Dict[str, Any]) -> Optional[float]:
        """从数据源获取指标值"""
        try:
            # 这里实现具体的数据获取逻辑
            # 例如：从数据库、API、文件等获取数据
            
            # 模拟数据获取
            import random
            return random.uniform(0, 100)
            
        except Exception as e:
            logger.error(f"Failed to get metric value: {e}")
            return None

    def _update_metric(self, metric_name: str, value: float, data_source: Dict[str, Any]):
        """更新单个指标"""
        try:
            # 获取历史值用于计算趋势
            old_metric = self.metrics.get(metric_name)
            old_value = old_metric.value if old_metric else value
            
            # 计算趋势
            if abs(value - old_value) < 0.01:
                trend = 'stable'
            elif value > old_value:
                trend = 'increasing'
            else:
                trend = 'decreasing'
            
            # 确定状态
            status = self._determine_status(metric_name, value)
            
            # 创建或更新指标
            metric = DashboardMetric(
                name=metric_name,
                value=value,
                unit=data_source.get('unit', ''),
                status=status,
                timestamp=datetime.now(),
                trend=trend,
                metadata={
                    'data_source': data_source.get('name', 'unknown'),
                    'update_frequency': data_source.get('update_frequency', '5s')
                }
            )
            
            self.metrics[metric_name] = metric
            
        except Exception as e:
            logger.error(f"Failed to update metric {metric_name}: {e}")

    def _determine_status(self, metric_name: str, value: float) -> str:
        """确定指标状态"""
        try:
            if metric_name in self.alert_thresholds:
                thresholds = self.alert_thresholds[metric_name]
                
                if 'critical' in thresholds and value >= thresholds['critical']:
                    return 'critical'
                elif 'warning' in thresholds and value >= thresholds['warning']:
                    return 'warning'
            
            return 'normal'
            
        except Exception as e:
            logger.error(f"Status determination failed: {e}")
            return 'normal'

    def _check_alerts(self):
        """检查告警"""
        try:
            for metric_name, metric in self.metrics.items():
                if metric.status in ['warning', 'critical']:
                    self._trigger_alert(metric)
                    
        except Exception as e:
            logger.error(f"Alert check failed: {e}")

    def _trigger_alert(self, metric: DashboardMetric):
        """触发告警"""
        try:
            alert_message = f"告警: {metric.name} = {metric.value}{metric.unit}, 状态: {metric.status}"
            logger.warning(alert_message)
            
            # 这里可以实现告警通知逻辑
            # 例如：发送邮件、短信、Webhook等
            
        except Exception as e:
            logger.error(f"Alert triggering failed: {e}")

    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表板数据"""
        try:
            with self.lock:
                dashboard_data = {
                    'timestamp': datetime.now().isoformat(),
                    'total_metrics': len(self.metrics),
                    'metrics': {},
                    'summary': self._get_dashboard_summary()
                }
                
                for metric_name, metric in self.metrics.items():
                    dashboard_data['metrics'][metric_name] = {
                        'value': metric.value,
                        'unit': metric.unit,
                        'status': metric.status,
                        'trend': metric.trend,
                        'timestamp': metric.timestamp.isoformat()
                    }
                
                return dashboard_data
                
        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            return {}

    def _get_dashboard_summary(self) -> Dict[str, Any]:
        """获取仪表板摘要"""
        try:
            if not self.metrics:
                return {'message': '无指标数据'}

            # 统计各状态的数量
            status_counts = {}
            trend_counts = {}
            
            for metric in self.metrics.values():
                status_counts[metric.status] = status_counts.get(metric.status, 0) + 1
                trend_counts[metric.trend] = trend_counts.get(metric.trend, 0) + 1

            # 计算平均值
            values = [m.value for m in self.metrics.values()]
            avg_value = np.mean(values) if values else 0

            return {
                'status_distribution': status_counts,
                'trend_distribution': trend_counts,
                'average_value': avg_value,
                'last_update': max(m.timestamp for m in self.metrics.values()).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Dashboard summary failed: {e}")
            return {}


class ForecastVisualizer:
    """预报可视化器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.plot_style = config.get('plot_style', 'default')
        self.color_scheme = config.get('color_scheme', 'default')
        self.figure_size = config.get('figure_size', (12, 8))
        
        # 设置绘图样式
        self._setup_plot_style()
        
        logger.info("ForecastVisualizer initialized")

    def _setup_plot_style(self):
        """设置绘图样式"""
        try:
            if self.plot_style == 'seaborn':
                sns.set_style("whitegrid")
            elif self.plot_style == 'modern':
                plt.style.use('default')
                plt.rcParams['figure.facecolor'] = 'white'
                plt.rcParams['axes.facecolor'] = '#f8f9fa'
                plt.rcParams['axes.grid'] = True
                plt.rcParams['grid.alpha'] = 0.3
        except Exception as e:
            logger.error(f"Plot style setup failed: {e}")

    def plot_forecast_comparison(self, observed_data: List[float], 
                                forecast_data: List[float],
                                time_index: List[datetime],
                                confidence_intervals: Optional[Dict[str, List[float]]] = None,
                                title: str = "预报对比图",
                                save_path: Optional[str] = None) -> Figure:
        """绘制预报对比图"""
        try:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=self.figure_size)
            
            # 主图：观测值vs预报值
            ax1.plot(time_index, observed_data, 'b-', label='观测值', linewidth=2, alpha=0.8)
            ax1.plot(time_index, forecast_data, 'r--', label='预报值', linewidth=2, alpha=0.8)
            
            # 绘制置信区间
            if confidence_intervals:
                if 'lower' in confidence_intervals and 'upper' in confidence_intervals:
                    ax1.fill_between(time_index,
                                    confidence_intervals['lower'],
                                    confidence_intervals['upper'],
                                    alpha=0.3, color='red', label='置信区间')
            
            ax1.set_xlabel('时间')
            ax1.set_ylabel('数值')
            ax1.set_title(title)
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 格式化x轴时间
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax1.xaxis.set_major_locator(mdates.HourLocator(interval=6))
            plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
            
            # 残差图
            residuals = np.array(forecast_data) - np.array(observed_data)
            ax2.plot(time_index, residuals, 'g-', linewidth=1, alpha=0.7, label='残差')
            ax2.axhline(y=0, color='k', linestyle='--', alpha=0.5)
            ax2.set_xlabel('时间')
            ax2.set_ylabel('残差 (预报值 - 观测值)')
            ax2.set_title('残差分析')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            # 格式化x轴时间
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax2.xaxis.set_major_locator(mdates.HourLocator(interval=6))
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Forecast comparison plot saved to {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"Forecast comparison plot failed: {e}")
            raise

    def plot_ensemble_forecast(self, ensemble_data: List[List[float]], 
                              time_index: List[datetime],
                              observed_data: Optional[List[float]] = None,
                              title: str = "集合预报图",
                              save_path: Optional[str] = None) -> Figure:
        """绘制集合预报图"""
        try:
            fig, ax = plt.subplots(1, 1, figsize=self.figure_size)
            
            # 绘制集合成员
            ensemble_array = np.array(ensemble_data)
            for i in range(ensemble_array.shape[0]):
                alpha = 0.3 if i > 0 else 0.5
                ax.plot(time_index, ensemble_array[i], 'b-', alpha=alpha, linewidth=1)
            
            # 绘制集合平均
            ensemble_mean = np.mean(ensemble_array, axis=0)
            ax.plot(time_index, ensemble_mean, 'r-', label='集合平均', linewidth=3)
            
            # 绘制观测值
            if observed_data:
                ax.plot(time_index, observed_data, 'k-', label='观测值', linewidth=2, alpha=0.8)
            
            # 绘制集合范围
            ensemble_min = np.min(ensemble_array, axis=0)
            ensemble_max = np.max(ensemble_array, axis=0)
            ax.fill_between(time_index, ensemble_min, ensemble_max, 
                           alpha=0.2, color='blue', label='集合范围')
            
            ax.set_xlabel('时间')
            ax.set_ylabel('数值')
            ax.set_title(title)
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # 格式化x轴时间
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Ensemble forecast plot saved to {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"Ensemble forecast plot failed: {e}")
            raise

    def plot_forecast_skill(self, skill_metrics: Dict[str, float],
                           title: str = "预报技能评分",
                           save_path: Optional[str] = None) -> Figure:
        """绘制预报技能评分图"""
        try:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
            
            # 技能指标柱状图
            metrics_names = list(skill_metrics.keys())
            metrics_values = list(skill_metrics.values())
            
            bars = ax1.bar(metrics_names, metrics_values, color='skyblue', alpha=0.7)
            ax1.set_xlabel('评估指标')
            ax1.set_ylabel('评分')
            ax1.set_title('预报技能评分')
            ax1.grid(True, alpha=0.3)
            
            # 添加数值标签
            for bar, value in zip(bars, metrics_values):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                         f'{value:.3f}', ha='center', va='bottom')
            
            # 技能指标雷达图
            angles = np.linspace(0, 2 * np.pi, len(metrics_names), endpoint=False).tolist()
            angles += angles[:1]  # 闭合图形
            
            values = list(skill_metrics.values()) + [skill_metrics[metrics_names[0]]]
            
            ax2.plot(angles, values, 'o-', linewidth=2, color='red', alpha=0.7)
            ax2.fill(angles, values, alpha=0.25, color='red')
            ax2.set_xticks(angles[:-1])
            ax2.set_xticklabels(metrics_names)
            ax2.set_ylim(0, 1)
            ax2.set_title('预报技能雷达图')
            ax2.grid(True)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Forecast skill plot saved to {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"Forecast skill plot failed: {e}")
            raise


class WarningMonitor:
    """预警监控器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.active_warnings: Dict[str, Any] = {}
        self.warning_history: List[Dict[str, Any]] = []
        self.monitoring_interval = config.get('monitoring_interval', 10)  # 秒
        
        # 监控配置
        self.auto_resolve = config.get('auto_resolve', True)
        self.escalation_enabled = config.get('escalation_enabled', True)
        
        logger.info("WarningMonitor initialized")

    def add_warning(self, warning_event: Any):
        """添加预警事件"""
        try:
            warning_id = warning_event.warning_id
            self.active_warnings[warning_id] = {
                'event': warning_event,
                'created_time': datetime.now(),
                'status': 'active',
                'escalation_count': 0
            }
            
            # 记录到历史
            self.warning_history.append({
                'warning_id': warning_id,
                'timestamp': datetime.now(),
                'action': 'created',
                'details': {
                    'variable': warning_event.variable,
                    'level': warning_event.warning_level.name,
                    'value': warning_event.current_value
                }
            })
            
            logger.info(f"Warning added: {warning_id}")
            
        except Exception as e:
            logger.error(f"Failed to add warning: {e}")

    def resolve_warning(self, warning_id: str, resolution_reason: str = "手动解除"):
        """解除预警"""
        try:
            if warning_id in self.active_warnings:
                warning_info = self.active_warnings[warning_id]
                warning_info['status'] = 'resolved'
                warning_info['resolution_time'] = datetime.now()
                warning_info['resolution_reason'] = resolution_reason
                
                # 记录到历史
                self.warning_history.append({
                    'warning_id': warning_id,
                    'timestamp': datetime.now(),
                    'action': 'resolved',
                    'details': {
                        'reason': resolution_reason,
                        'duration': (datetime.now() - warning_info['created_time']).total_seconds()
                    }
                })
                
                logger.info(f"Warning resolved: {warning_id}")
                
        except Exception as e:
            logger.error(f"Failed to resolve warning {warning_id}: {e}")

    def escalate_warning(self, warning_id: str, escalation_reason: str = "自动升级"):
        """升级预警"""
        try:
            if warning_id in self.active_warnings:
                warning_info = self.active_warnings[warning_id]
                warning_info['escalation_count'] += 1
                warning_info['last_escalation'] = datetime.now()
                
                # 记录到历史
                self.warning_history.append({
                    'warning_id': warning_id,
                    'timestamp': datetime.now(),
                    'action': 'escalated',
                    'details': {
                        'reason': escalation_reason,
                        'escalation_count': warning_info['escalation_count']
                    }
                })
                
                logger.info(f"Warning escalated: {warning_id}")
                
        except Exception as e:
            logger.error(f"Failed to escalate warning {warning_id}: {e}")

    def get_active_warnings(self) -> List[Dict[str, Any]]:
        """获取活动预警"""
        try:
            active_warnings = []
            for warning_id, warning_info in self.active_warnings.items():
                if warning_info['status'] == 'active':
                    warning_event = warning_info['event']
                    active_warnings.append({
                        'warning_id': warning_id,
                        'variable': warning_event.variable,
                        'level': warning_event.warning_level.name,
                        'value': warning_event.current_value,
                        'created_time': warning_info['created_time'].isoformat(),
                        'escalation_count': warning_info['escalation_count']
                    })
            
            return active_warnings
            
        except Exception as e:
            logger.error(f"Failed to get active warnings: {e}")
            return []

    def get_warning_summary(self, time_window: timedelta = timedelta(hours=24)) -> Dict[str, Any]:
        """获取预警摘要"""
        try:
            time_window = _ensure_timedelta(time_window, 'hours')
            cutoff_time = datetime.now() - time_window
            recent_warnings = [
                w for w in self.warning_history 
                if w['timestamp'] >= cutoff_time
            ]

            if not recent_warnings:
                return {'message': '无预警记录'}

            # 统计各操作的数量
            action_counts = {}
            for warning in recent_warnings:
                action = warning['action']
                action_counts[action] = action_counts.get(action, 0) + 1

            # 统计活动预警
            active_count = len([w for w in self.active_warnings.values() if w['status'] == 'active'])

            return {
                'time_window': str(time_window),
                'total_events': len(recent_warnings),
                'action_distribution': action_counts,
                'active_warnings': active_count,
                'escalation_enabled': self.escalation_enabled,
                'auto_resolve': self.auto_resolve
            }
            
        except Exception as e:
            logger.error(f"Warning summary failed: {e}")
            return {}


class PerformanceTracker:
    """性能跟踪器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.performance_metrics: Dict[str, List[Dict[str, Any]]] = {}
        self.tracking_enabled = config.get('tracking_enabled', True)
        self.metric_retention = _ensure_timedelta(
            config.get('metric_retention', timedelta(days=7)),
            'days'
        )
        
        logger.info("PerformanceTracker initialized")

    def track_metric(self, metric_name: str, value: float, 
                    metadata: Optional[Dict[str, Any]] = None):
        """跟踪性能指标"""
        try:
            if not self.tracking_enabled:
                return

            if metric_name not in self.performance_metrics:
                self.performance_metrics[metric_name] = []

            metric_record = {
                'timestamp': datetime.now(),
                'value': value,
                'metadata': metadata or {}
            }

            self.performance_metrics[metric_name].append(metric_record)

            # 清理过期数据
            self._cleanup_old_metrics()

        except Exception as e:
            logger.error(f"Failed to track metric {metric_name}: {e}")

    def _cleanup_old_metrics(self):
        """清理过期的性能指标"""
        try:
            cutoff_time = datetime.now() - self.metric_retention
            
            for metric_name in self.performance_metrics:
                self.performance_metrics[metric_name] = [
                    m for m in self.performance_metrics[metric_name]
                    if m['timestamp'] >= cutoff_time
                ]

        except Exception as e:
            logger.error(f"Metrics cleanup failed: {e}")

    def get_performance_summary(self, metric_name: str,
                               time_window: timedelta = timedelta(hours=1)) -> Dict[str, Any]:
        """获取性能摘要"""
        try:
            if metric_name not in self.performance_metrics:
                return {'message': f'无指标数据: {metric_name}'}

            time_window = _ensure_timedelta(time_window, 'hours')
            cutoff_time = datetime.now() - time_window
            recent_metrics = [
                m for m in self.performance_metrics[metric_name]
                if m['timestamp'] >= cutoff_time
            ]

            if not recent_metrics:
                return {'message': '无最近数据'}

            values = [m['value'] for m in recent_metrics]
            
            summary = {
                'metric_name': metric_name,
                'time_window': str(time_window),
                'data_points': len(recent_metrics),
                'min_value': min(values),
                'max_value': max(values),
                'mean_value': np.mean(values),
                'std_value': np.std(values),
                'last_value': values[-1],
                'last_update': recent_metrics[-1]['timestamp'].isoformat()
            }

            return summary

        except Exception as e:
            logger.error(f"Performance summary failed: {e}")
            return {}

    def get_all_metrics_summary(self, time_window: timedelta = timedelta(hours=1)) -> Dict[str, Any]:
        """获取所有指标的摘要"""
        try:
            time_window = _ensure_timedelta(time_window, 'hours')
            all_summaries = {}

            for metric_name in self.performance_metrics:
                summary = self.get_performance_summary(metric_name, time_window)
                if 'message' not in summary:
                    all_summaries[metric_name] = summary

            return {
                'time_window': str(time_window),
                'total_metrics': len(all_summaries),
                'metrics': all_summaries
            }

        except Exception as e:
            logger.error(f"All metrics summary failed: {e}")
            return {}

    def export_metrics(self, metric_name: str, 
                       start_time: datetime, 
                       end_time: datetime) -> Optional[pd.DataFrame]:
        """导出性能指标数据"""
        try:
            if metric_name not in self.performance_metrics:
                return None

            metrics_in_range = [
                m for m in self.performance_metrics[metric_name]
                if start_time <= m['timestamp'] <= end_time
            ]

            if not metrics_in_range:
                return None

            # 转换为DataFrame
            df = pd.DataFrame(metrics_in_range)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            return df

        except Exception as e:
            logger.error(f"Metrics export failed: {e}")
            return None

