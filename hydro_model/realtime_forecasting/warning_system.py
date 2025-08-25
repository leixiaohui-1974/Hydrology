"""
预警系统模块
============

本模块提供水文预警功能，包括阈值管理、信息生成和发布
"""

import time
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import threading
import queue
import json

# 配置日志
logger = logging.getLogger(__name__)


class WarningLevel(Enum):
    """预警等级枚举"""
    NORMAL = 0      # 正常
    ATTENTION = 1   # 注意
    WARNING = 2     # 预警
    SEVERE = 3      # 严重
    CRITICAL = 4    # 特急


@dataclass
class WarningThreshold:
    """预警阈值结构"""
    variable: str
    warning_level: WarningLevel
    threshold_value: float
    threshold_type: str  # 'above', 'below', 'range'
    threshold_lower: Optional[float] = None
    threshold_upper: Optional[float] = None
    description: str = ""
    action_required: str = ""


@dataclass
class WarningEvent:
    """预警事件结构"""
    warning_id: str
    timestamp: datetime
    variable: str
    current_value: float
    threshold_value: float
    warning_level: WarningLevel
    location: str
    description: str
    status: str  # 'active', 'escalated', 'resolved'
    metadata: Dict[str, Any] = None


class WarningThresholdManager:
    """预警阈值管理器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.thresholds: Dict[str, List[WarningThreshold]] = {}
        self.dynamic_thresholds = config.get('dynamic_thresholds', {})
        self.threshold_update_interval = config.get('threshold_update_interval', 3600)  # 秒
        
        # 动态阈值计算参数
        self.historical_data_window = config.get('historical_data_window', timedelta(days=30))
        self.percentile_levels = config.get('percentile_levels', [90, 95, 99])
        
        logger.info("WarningThresholdManager initialized")

    def add_threshold(self, variable: str, threshold: WarningThreshold) -> bool:
        """添加预警阈值"""
        try:
            if variable not in self.thresholds:
                self.thresholds[variable] = []
            
            self.thresholds[variable].append(threshold)
            
            # 按预警等级排序
            self.thresholds[variable].sort(key=lambda x: x.warning_level.value)
            
            logger.info(f"Added threshold for {variable}: {threshold.warning_level.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add threshold for {variable}: {e}")
            return False

    def remove_threshold(self, variable: str, warning_level: WarningLevel) -> bool:
        """移除预警阈值"""
        try:
            if variable in self.thresholds:
                self.thresholds[variable] = [
                    t for t in self.thresholds[variable] 
                    if t.warning_level != warning_level
                ]
                logger.info(f"Removed threshold for {variable}: {warning_level.name}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to remove threshold for {variable}: {e}")
            return False

    def get_thresholds(self, variable: str) -> List[WarningThreshold]:
        """获取变量的所有阈值"""
        return self.thresholds.get(variable, [])

    def check_warning(self, variable: str, current_value: float, 
                      location: str = "default") -> Optional[WarningEvent]:
        """检查是否需要发出预警"""
        try:
            if variable not in self.thresholds:
                return None

            # 检查每个阈值
            for threshold in self.thresholds[variable]:
                if self._is_threshold_exceeded(current_value, threshold):
                    warning_event = WarningEvent(
                        warning_id=f"{variable}_{threshold.warning_level.name}_{int(time.time())}",
                        timestamp=datetime.now(),
                        variable=variable,
                        current_value=current_value,
                        threshold_value=threshold.threshold_value,
                        warning_level=threshold.warning_level,
                        location=location,
                        description=threshold.description,
                        status='active',
                        metadata={
                            'threshold_type': threshold.threshold_type,
                            'action_required': threshold.action_required
                        }
                    )
                    
                    logger.info(f"Warning triggered: {variable} = {current_value}, level: {threshold.warning_level.name}")
                    return warning_event

            return None
            
        except Exception as e:
            logger.error(f"Warning check failed for {variable}: {e}")
            return None

    def _is_threshold_exceeded(self, current_value: float, threshold: WarningThreshold) -> bool:
        """检查是否超过阈值"""
        try:
            if threshold.threshold_type == 'above':
                return current_value > threshold.threshold_value
            elif threshold.threshold_type == 'below':
                return current_value < threshold.threshold_value
            elif threshold.threshold_type == 'range':
                if threshold.threshold_lower is not None and threshold.threshold_upper is not None:
                    return not (threshold.threshold_lower <= current_value <= threshold.threshold_upper)
            return False
            
        except Exception as e:
            logger.error(f"Threshold check failed: {e}")
            return False

    def calculate_dynamic_thresholds(self, historical_data: List[float], 
                                   variable: str) -> List[WarningThreshold]:
        """计算动态阈值"""
        try:
            if not historical_data:
                return []

            data_array = np.array(historical_data)
            dynamic_thresholds = []

            # 基于百分位数计算阈值
            for i, percentile in enumerate(self.percentile_levels):
                threshold_value = np.percentile(data_array, percentile)
                warning_level = WarningLevel(i + 1)  # 1=ATTENTION, 2=WARNING, 3=SEVERE
                
                threshold = WarningThreshold(
                    variable=variable,
                    warning_level=warning_level,
                    threshold_value=threshold_value,
                    threshold_type='above',
                    description=f"动态阈值 ({percentile}%)",
                    action_required=f"当{variable}超过{threshold_value:.2f}时注意"
                )
                
                dynamic_thresholds.append(threshold)

            logger.info(f"Calculated {len(dynamic_thresholds)} dynamic thresholds for {variable}")
            return dynamic_thresholds
            
        except Exception as e:
            logger.error(f"Dynamic threshold calculation failed: {e}")
            return []

    def update_thresholds(self, new_thresholds: Dict[str, List[WarningThreshold]]):
        """批量更新阈值"""
        try:
            for variable, thresholds in new_thresholds.items():
                self.thresholds[variable] = thresholds
                logger.info(f"Updated thresholds for {variable}: {len(thresholds)} thresholds")
                
        except Exception as e:
            logger.error(f"Threshold update failed: {e}")

    def get_threshold_summary(self) -> Dict[str, Any]:
        """获取阈值摘要"""
        summary = {
            'total_variables': len(self.thresholds),
            'total_thresholds': sum(len(ts) for ts in self.thresholds.values()),
            'variables': {}
        }

        for variable, thresholds in self.thresholds.items():
            summary['variables'][variable] = {
                'threshold_count': len(thresholds),
                'levels': [t.warning_level.name for t in thresholds]
            }

        return summary


class WarningInformationGenerator:
    """预警信息生成器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.template_config = config.get('templates', {})
        self.language = config.get('language', 'zh_CN')
        self.warning_templates = self._load_warning_templates()
        
        logger.info("WarningInformationGenerator initialized")

    def _load_warning_templates(self) -> Dict[str, str]:
        """加载预警模板"""
        templates = {
            'zh_CN': {
                'attention': "注意：{variable}当前值为{current_value}{unit}，接近预警阈值{threshold_value}{unit}",
                'warning': "预警：{variable}当前值为{current_value}{unit}，已超过预警阈值{threshold_value}{unit}",
                'severe': "严重预警：{variable}当前值为{current_value}{unit}，已超过严重预警阈值{threshold_value}{unit}",
                'critical': "特急预警：{variable}当前值为{current_value}{unit}，已超过特急预警阈值{threshold_value}{unit}"
            },
            'en_US': {
                'attention': "Attention: {variable} current value is {current_value}{unit}, approaching warning threshold {threshold_value}{unit}",
                'warning': "Warning: {variable} current value is {current_value}{unit}, exceeding warning threshold {threshold_value}{unit}",
                'severe': "Severe Warning: {variable} current value is {current_value}{unit}, exceeding severe warning threshold {threshold_value}{unit}",
                'critical': "Critical Warning: {variable} current value is {current_value}{unit}, exceeding critical warning threshold {threshold_value}{unit}"
            }
        }
        
        return templates.get(self.language, templates['zh_CN'])

    def generate_warning_message(self, warning_event: WarningEvent, 
                                message_type: str = 'standard') -> Dict[str, Any]:
        """生成预警信息"""
        try:
            # 获取模板
            level_name = warning_event.warning_level.name.lower()
            if level_name == 'normal':
                level_name = 'attention'
            
            template = self.warning_templates.get(level_name, self.warning_templates['warning'])
            
            # 填充模板
            message = template.format(
                variable=warning_event.variable,
                current_value=f"{warning_event.current_value:.2f}",
                unit=self._get_unit_display(warning_event.variable),
                threshold_value=f"{warning_event.threshold_value:.2f}"
            )

            # 生成不同格式的信息
            warning_info = {
                'warning_id': warning_event.warning_id,
                'timestamp': warning_event.timestamp.isoformat(),
                'level': warning_event.warning_level.name,
                'level_code': warning_event.warning_level.value,
                'variable': warning_event.variable,
                'current_value': warning_event.current_value,
                'threshold_value': warning_event.threshold_value,
                'location': warning_event.location,
                'message': message,
                'description': warning_event.description,
                'action_required': warning_event.metadata.get('action_required', ''),
                'status': warning_event.status
            }

            # 根据消息类型添加额外信息
            if message_type == 'detailed':
                warning_info.update({
                    'metadata': warning_event.metadata,
                    'recommendations': self._generate_recommendations(warning_event),
                    'contact_info': self._get_contact_info(warning_event.warning_level)
                })
            elif message_type == 'summary':
                warning_info = {
                    'level': warning_event.warning_level.name,
                    'variable': warning_event.variable,
                    'message': message,
                    'timestamp': warning_event.timestamp.isoformat()
                }

            return warning_info
            
        except Exception as e:
            logger.error(f"Warning message generation failed: {e}")
            return {'error': f"信息生成失败: {e}"}

    def _get_unit_display(self, variable: str) -> str:
        """获取单位显示"""
        unit_mapping = {
            'flow': 'm³/s',
            'water_level': 'm',
            'rainfall': 'mm',
            'temperature': '°C',
            'humidity': '%'
        }
        return unit_mapping.get(variable, '')

    def _generate_recommendations(self, warning_event: WarningEvent) -> List[str]:
        """生成建议"""
        recommendations = []
        level = warning_event.warning_level
        
        if level == WarningLevel.ATTENTION:
            recommendations.extend([
                "密切关注数据变化趋势",
                "准备应急响应预案",
                "通知相关人员注意"
            ])
        elif level == WarningLevel.WARNING:
            recommendations.extend([
                "启动预警响应机制",
                "加强监测频率",
                "准备应急物资",
                "通知相关部门"
            ])
        elif level == WarningLevel.SEVERE:
            recommendations.extend([
                "立即启动应急响应",
                "疏散危险区域人员",
                "调动应急资源",
                "通知上级部门"
            ])
        elif level == WarningLevel.CRITICAL:
            recommendations.extend([
                "立即启动最高级别应急响应",
                "紧急疏散所有人员",
                "调动所有可用资源",
                "通知所有相关部门"
            ])

        return recommendations

    def _get_contact_info(self, warning_level: WarningLevel) -> Dict[str, str]:
        """获取联系信息"""
        contact_info = {
            'emergency': '119',
            'weather_service': '12121',
            'water_authority': '12345'
        }
        
        if warning_level in [WarningLevel.SEVERE, WarningLevel.CRITICAL]:
            contact_info['emergency'] = '110'
            contact_info['command_center'] = '120'
        
        return contact_info

    def generate_batch_warnings(self, warning_events: List[WarningEvent], 
                               format_type: str = 'summary') -> List[Dict[str, Any]]:
        """批量生成预警信息"""
        try:
            batch_messages = []
            for warning_event in warning_events:
                message = self.generate_warning_message(warning_event, format_type)
                batch_messages.append(message)
            
            return batch_messages
            
        except Exception as e:
            logger.error(f"Batch warning generation failed: {e}")
            return []


class WarningDistributionSystem:
    """预警信息发布系统"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.channels = config.get('channels', {})
        self.distribution_rules = config.get('distribution_rules', {})
        self.distribution_history: List[Dict[str, Any]] = []
        
        # 发布渠道配置
        self.email_config = config.get('email', {})
        self.sms_config = config.get('sms', {})
        self.webhook_config = config.get('webhook', {})
        self.database_config = config.get('database', {})
        
        logger.info("WarningDistributionSystem initialized")

    def distribute_warning(self, warning_info: Dict[str, Any], 
                          channels: Optional[List[str]] = None) -> Dict[str, bool]:
        """发布预警信息"""
        try:
            if channels is None:
                channels = self._get_default_channels(warning_info['level_code'])

            distribution_results = {}
            
            for channel in channels:
                try:
                    success = self._send_to_channel(channel, warning_info)
                    distribution_results[channel] = success
                    
                    if success:
                        logger.info(f"Warning distributed to {channel} successfully")
                    else:
                        logger.warning(f"Warning distribution to {channel} failed")
                        
                except Exception as e:
                    logger.error(f"Error distributing to {channel}: {e}")
                    distribution_results[channel] = False

            # 记录发布历史
            self._record_distribution(warning_info, distribution_results)
            
            return distribution_results
            
        except Exception as e:
            logger.error(f"Warning distribution failed: {e}")
            return {}

    def _get_default_channels(self, warning_level: int) -> List[str]:
        """获取默认发布渠道"""
        if warning_level >= WarningLevel.CRITICAL.value:
            return ['email', 'sms', 'webhook', 'database']
        elif warning_level >= WarningLevel.SEVERE.value:
            return ['email', 'webhook', 'database']
        elif warning_level >= WarningLevel.WARNING.value:
            return ['webhook', 'database']
        else:
            return ['database']

    def _send_to_channel(self, channel: str, warning_info: Dict[str, Any]) -> bool:
        """发送到指定渠道"""
        try:
            if channel == 'email':
                return self._send_email(warning_info)
            elif channel == 'sms':
                return self._send_sms(warning_info)
            elif channel == 'webhook':
                return self._send_webhook(warning_info)
            elif channel == 'database':
                return self._save_to_database(warning_info)
            else:
                logger.warning(f"Unknown channel: {channel}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending to {channel}: {e}")
            return False

    def _send_email(self, warning_info: Dict[str, Any]) -> bool:
        """发送邮件"""
        try:
            # 这里实现具体的邮件发送逻辑
            # 例如：使用SMTP、邮件服务API等
            
            logger.info(f"Email sent: {warning_info['warning_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            return False

    def _send_sms(self, warning_info: Dict[str, Any]) -> bool:
        """发送短信"""
        try:
            # 这里实现具体的短信发送逻辑
            # 例如：使用短信服务API等
            
            logger.info(f"SMS sent: {warning_info['warning_id']}")
            return True
            
        except Exception as e:
            logger.error(f"SMS sending failed: {e}")
            return False

    def _send_webhook(self, warning_info: Dict[str, Any]) -> bool:
        """发送Webhook"""
        try:
            # 这里实现具体的Webhook发送逻辑
            # 例如：HTTP POST请求等
            
            logger.info(f"Webhook sent: {warning_info['warning_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Webhook sending failed: {e}")
            return False

    def _save_to_database(self, warning_info: Dict[str, Any]) -> bool:
        """保存到数据库"""
        try:
            # 这里实现具体的数据库保存逻辑
            # 例如：SQL插入、NoSQL存储等
            
            logger.info(f"Warning saved to database: {warning_info['warning_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Database save failed: {e}")
            return False

    def _record_distribution(self, warning_info: Dict[str, Any], 
                           results: Dict[str, bool]):
        """记录发布历史"""
        try:
            distribution_record = {
                'timestamp': datetime.now(),
                'warning_id': warning_info['warning_id'],
                'warning_level': warning_info['level'],
                'channels': list(results.keys()),
                'success_count': sum(results.values()),
                'total_count': len(results),
                'results': results
            }
            
            self.distribution_history.append(distribution_record)
            
            # 保持历史记录在合理范围内
            if len(self.distribution_history) > 10000:
                self.distribution_history = self.distribution_history[-5000:]
                
        except Exception as e:
            logger.error(f"Failed to record distribution: {e}")

    def get_distribution_summary(self, time_window: timedelta = timedelta(hours=24)) -> Dict[str, Any]:
        """获取发布摘要"""
        cutoff_time = datetime.now() - time_window
        recent_distributions = [
            d for d in self.distribution_history 
            if d['timestamp'] >= cutoff_time
        ]

        if not recent_distributions:
            return {'message': '无发布记录'}

        # 计算统计量
        total_warnings = len(recent_distributions)
        total_channels = sum(len(d['channels']) for d in recent_distributions)
        success_rate = np.mean([d['success_count'] / d['total_count'] for d in recent_distributions])

        # 按渠道统计
        channel_stats = {}
        for distribution in recent_distributions:
            for channel, success in distribution['results'].items():
                if channel not in channel_stats:
                    channel_stats[channel] = {'total': 0, 'success': 0}
                channel_stats[channel]['total'] += 1
                if success:
                    channel_stats[channel]['success'] += 1

        return {
            'time_window': str(time_window),
            'total_warnings': total_warnings,
            'total_channels': total_channels,
            'overall_success_rate': success_rate,
            'channel_statistics': channel_stats
        }


class WarningEscalationManager:
    """预警升级管理器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.escalation_rules = config.get('escalation_rules', {})
        self.escalation_history: List[Dict[str, Any]] = []
        self.escalation_timers: Dict[str, threading.Timer] = {}
        
        logger.info("WarningEscalationManager initialized")

    def check_escalation(self, warning_event: WarningEvent) -> Optional[WarningEvent]:
        """检查是否需要升级预警"""
        try:
            # 检查升级规则
            escalation_rule = self._get_escalation_rule(warning_event)
            if not escalation_rule:
                return None

            # 检查升级条件
            if self._should_escalate(warning_event, escalation_rule):
                escalated_warning = self._create_escalated_warning(warning_event, escalation_rule)
                
                # 记录升级历史
                self._record_escalation(warning_event, escalated_warning)
                
                # 设置升级定时器
                self._set_escalation_timer(escalated_warning, escalation_rule)
                
                logger.info(f"Warning escalated: {warning_event.warning_id} -> {escalated_warning.warning_id}")
                return escalated_warning

            return None
            
        except Exception as e:
            logger.error(f"Escalation check failed: {e}")
            return None

    def _get_escalation_rule(self, warning_event: WarningEvent) -> Optional[Dict[str, Any]]:
        """获取升级规则"""
        variable = warning_event.variable
        current_level = warning_event.warning_level.value
        
        if variable in self.escalation_rules:
            rules = self.escalation_rules[variable]
            for rule in rules:
                if rule['from_level'] == current_level:
                    return rule
        
        return None

    def _should_escalate(self, warning_event: WarningEvent, 
                         rule: Dict[str, Any]) -> bool:
        """判断是否应该升级"""
        try:
            # 检查时间条件
            if 'time_threshold' in rule:
                time_threshold = timedelta(seconds=rule['time_threshold'])
                warning_age = datetime.now() - warning_event.timestamp
                if warning_age < time_threshold:
                    return False

            # 检查数值条件
            if 'value_threshold' in rule:
                if warning_event.current_value < rule['value_threshold']:
                    return False

            # 检查趋势条件
            if 'trend_threshold' in rule:
                # 这里可以实现趋势分析逻辑
                pass

            return True
            
        except Exception as e:
            logger.error(f"Escalation condition check failed: {e}")
            return False

    def _create_escalated_warning(self, original_warning: WarningEvent, 
                                 rule: Dict[str, Any]) -> WarningEvent:
        """创建升级后的预警"""
        try:
            # 确定新的预警等级
            new_level_value = min(original_warning.warning_level.value + 1, WarningLevel.CRITICAL.value)
            new_level = WarningLevel(new_level_value)
            
            # 创建升级后的预警事件
            escalated_warning = WarningEvent(
                warning_id=f"{original_warning.warning_id}_escalated_{int(time.time())}",
                timestamp=datetime.now(),
                variable=original_warning.variable,
                current_value=original_warning.current_value,
                threshold_value=original_warning.threshold_value,
                warning_level=new_level,
                location=original_warning.location,
                description=f"升级预警：{original_warning.description}",
                status='escalated',
                metadata={
                    'original_warning_id': original_warning.warning_id,
                    'escalation_reason': rule.get('reason', '自动升级'),
                    'escalation_time': datetime.now().isoformat()
                }
            )
            
            return escalated_warning
            
        except Exception as e:
            logger.error(f"Failed to create escalated warning: {e}")
            raise

    def _record_escalation(self, original_warning: WarningEvent, 
                          escalated_warning: WarningEvent):
        """记录升级历史"""
        try:
            escalation_record = {
                'timestamp': datetime.now(),
                'original_warning_id': original_warning.warning_id,
                'escalated_warning_id': escalated_warning.warning_id,
                'original_level': original_warning.warning_level.name,
                'new_level': escalated_warning.warning_level.name,
                'escalation_reason': escalated_warning.metadata.get('escalation_reason', ''),
                'variable': original_warning.variable,
                'location': original_warning.location
            }
            
            self.escalation_history.append(escalation_record)
            
            # 保持历史记录在合理范围内
            if len(self.escalation_history) > 5000:
                self.escalation_history = self.escalation_history[-2500:]
                
        except Exception as e:
            logger.error(f"Failed to record escalation: {e}")

    def _set_escalation_timer(self, escalated_warning: WarningEvent, rule: Dict[str, Any]):
        """设置升级定时器"""
        try:
            if 'auto_resolve_time' in rule:
                auto_resolve_seconds = rule['auto_resolve_time']
                
                timer = threading.Timer(auto_resolve_seconds, self._auto_resolve_warning, 
                                      args=[escalated_warning.warning_id])
                timer.daemon = True
                timer.start()
                
                self.escalation_timers[escalated_warning.warning_id] = timer
                
        except Exception as e:
            logger.error(f"Failed to set escalation timer: {e}")

    def _auto_resolve_warning(self, warning_id: str):
        """自动解除预警"""
        try:
            # 这里可以实现自动解除逻辑
            # 例如：检查当前值是否已恢复正常
            
            logger.info(f"Auto-resolving warning: {warning_id}")
            
            # 清理定时器
            if warning_id in self.escalation_timers:
                del self.escalation_timers[warning_id]
                
        except Exception as e:
            logger.error(f"Auto-resolve failed for {warning_id}: {e}")

    def get_escalation_summary(self, time_window: timedelta = timedelta(hours=24)) -> Dict[str, Any]:
        """获取升级摘要"""
        cutoff_time = datetime.now() - time_window
        recent_escalations = [
            e for e in self.escalation_history 
            if e['timestamp'] >= cutoff_time
        ]

        if not recent_escalations:
            return {'message': '无升级记录'}

        # 计算统计量
        total_escalations = len(recent_escalations)
        
        # 按等级统计
        level_stats = {}
        for escalation in recent_escalations:
            new_level = escalation['new_level']
            if new_level not in level_stats:
                level_stats[new_level] = 0
            level_stats[new_level] += 1

        # 按变量统计
        variable_stats = {}
        for escalation in recent_escalations:
            variable = escalation['variable']
            if variable not in variable_stats:
                variable_stats[variable] = 0
            variable_stats[variable] += 1

        return {
            'time_window': str(time_window),
            'total_escalations': total_escalations,
            'level_statistics': level_stats,
            'variable_statistics': variable_stats,
            'active_timers': len(self.escalation_timers)
        }

    def cancel_escalation_timer(self, warning_id: str) -> bool:
        """取消升级定时器"""
        try:
            if warning_id in self.escalation_timers:
                timer = self.escalation_timers[warning_id]
                timer.cancel()
                del self.escalation_timers[warning_id]
                logger.info(f"Escalation timer cancelled for {warning_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to cancel escalation timer for {warning_id}: {e}")
            return False

