#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全审计日志模块 - Hydrology Framework Security Audit

提供安全事件记录、监控和分析功能。

作者: Hydrology Framework Team
版本: 1.0.0
日期: 2024
"""

import os
import json
import time
import hashlib
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, asdict
from collections import defaultdict, deque

try:
    import logging
    from logging.handlers import RotatingFileHandler
    LOGGING_AVAILABLE = True
except ImportError:
    LOGGING_AVAILABLE = False

from .error_handler import SecurityError


class SecurityEventType(Enum):
    """
    安全事件类型枚举
    """
    # 认证事件
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGED = "password_changed"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    
    # 用户管理事件
    USER_CREATED = "user_created"
    USER_DELETED = "user_deleted"
    USER_UPDATED = "user_updated"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    
    # 数据访问事件
    DATA_READ = "data_read"
    DATA_WRITE = "data_write"
    DATA_DELETE = "data_delete"
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"
    FILE_ACCESS = "file_access"
    
    # 系统事件
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    CONFIG_CHANGED = "config_changed"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"
    
    # 安全事件
    SECURITY_VIOLATION = "security_violation"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    BRUTE_FORCE_ATTEMPT = "brute_force_attempt"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_BREACH_ATTEMPT = "data_breach_attempt"
    
    # 会话事件
    SESSION_CREATED = "session_created"
    SESSION_EXPIRED = "session_expired"
    SESSION_TERMINATED = "session_terminated"
    TOKEN_GENERATED = "token_generated"
    TOKEN_VALIDATED = "token_validated"
    TOKEN_EXPIRED = "token_expired"


class SecurityEventSeverity(Enum):
    """
    安全事件严重程度枚举
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityEvent:
    """
    安全事件数据类
    """
    event_type: SecurityEventType
    severity: SecurityEventSeverity
    timestamp: datetime
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    risk_score: Optional[int] = None
    
    def __post_init__(self) -> None:
        if isinstance(self.event_type, str):
            self.event_type = SecurityEventType(self.event_type)
        if isinstance(self.severity, str):
            self.severity = SecurityEventSeverity(self.severity)
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典
        """
        data = asdict(self)
        data['event_type'] = self.event_type.value
        data['severity'] = self.severity.value
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SecurityEvent':
        """
        从字典创建实例
        """
        return cls(**data)
    
    def get_event_id(self) -> str:
        """
        生成事件ID
        """
        content = f"{self.timestamp.isoformat()}{self.event_type.value}{self.user_id or ''}{self.ip_address or ''}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class SecurityAuditLogger:
    """
    安全审计日志记录器
    """
    
    def __init__(self, log_file: Optional[str] = None, max_file_size: int = 10*1024*1024, 
                 backup_count: int = 5, log_level: str = 'INFO') -> None:
        """
        初始化审计日志记录器
        
        Args:
            log_file: 日志文件路径
            max_file_size: 最大文件大小（字节）
            backup_count: 备份文件数量
            log_level: 日志级别
        """
        self.log_file: str = log_file or 'logs/security_audit.log'
        self.max_file_size: int = max_file_size
        self.backup_count: int = backup_count
        self.log_level: str = log_level
        
        # 确保日志目录存在
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)
        
        # 设置日志记录器
        self.logger: Optional[Any] = None
        if LOGGING_AVAILABLE:
            self._setup_logger()
        
        # 事件缓存
        self.event_cache: deque = deque(maxlen=1000)
        self.cache_lock: threading.Lock = threading.Lock()
    
    def _setup_logger(self) -> None:
        """
        设置日志记录器
        """
        self.logger = logging.getLogger('security_audit')
        self.logger.setLevel(getattr(logging, self.log_level.upper()))
        
        # 避免重复添加处理器
        if not self.logger.handlers:
            # 文件处理器
            file_handler = RotatingFileHandler(
                self.log_file,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            
            # 格式化器
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
    
    def log_event(self, event: SecurityEvent):
        """
        记录安全事件
        
        Args:
            event: 安全事件
        """
        # 添加到缓存
        with self.cache_lock:
            self.event_cache.append(event)
        
        # 记录到日志文件
        if self.logger:
            log_message = self._format_event_message(event)
            
            if event.severity == SecurityEventSeverity.CRITICAL:
                self.logger.critical(log_message)
            elif event.severity == SecurityEventSeverity.HIGH:
                self.logger.error(log_message)
            elif event.severity == SecurityEventSeverity.MEDIUM:
                self.logger.warning(log_message)
            else:
                self.logger.info(log_message)
        else:
            # 如果没有logging库，直接写入文件
            self._write_to_file(event)
    
    def _format_event_message(self, event: SecurityEvent) -> str:
        """
        格式化事件消息
        """
        message_parts = [
            f"EVENT_ID={event.get_event_id()}",
            f"TYPE={event.event_type.value}",
            f"SEVERITY={event.severity.value}"
        ]
        
        if event.user_id:
            message_parts.append(f"USER={event.user_id}")
        if event.session_id:
            message_parts.append(f"SESSION={event.session_id}")
        if event.ip_address:
            message_parts.append(f"IP={event.ip_address}")
        if event.resource:
            message_parts.append(f"RESOURCE={event.resource}")
        if event.action:
            message_parts.append(f"ACTION={event.action}")
        if event.result:
            message_parts.append(f"RESULT={event.result}")
        if event.risk_score is not None:
            message_parts.append(f"RISK_SCORE={event.risk_score}")
        
        if event.details:
            details_str = json.dumps(event.details, ensure_ascii=False)
            message_parts.append(f"DETAILS={details_str}")
        
        return " | ".join(message_parts)
    
    def _write_to_file(self, event: SecurityEvent):
        """
        直接写入文件（当logging不可用时）
        """
        try:
            message = f"{event.timestamp.isoformat()} - {self._format_event_message(event)}\n"
            
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message)
                
        except Exception as e:
            print(f"写入审计日志失败: {str(e)}")
    
    def get_recent_events(self, count: int = 100) -> List[SecurityEvent]:
        """
        获取最近的事件
        
        Args:
            count: 事件数量
            
        Returns:
            List[SecurityEvent]: 事件列表
        """
        with self.cache_lock:
            return list(self.event_cache)[-count:]
    
    def search_events(self, event_type: SecurityEventType = None, 
                     user_id: str = None, start_time: datetime = None, 
                     end_time: datetime = None, severity: SecurityEventSeverity = None) -> List[SecurityEvent]:
        """
        搜索事件
        
        Args:
            event_type: 事件类型
            user_id: 用户ID
            start_time: 开始时间
            end_time: 结束时间
            severity: 严重程度
            
        Returns:
            List[SecurityEvent]: 匹配的事件列表
        """
        with self.cache_lock:
            events = list(self.event_cache)
        
        filtered_events = []
        for event in events:
            if event_type and event.event_type != event_type:
                continue
            if user_id and event.user_id != user_id:
                continue
            if start_time and event.timestamp < start_time:
                continue
            if end_time and event.timestamp > end_time:
                continue
            if severity and event.severity != severity:
                continue
            
            filtered_events.append(event)
        
        return filtered_events


class SecurityMonitor:
    """
    安全监控器 - 监控和分析安全事件
    """
    
    def __init__(self, audit_logger: SecurityAuditLogger):
        """
        初始化安全监控器
        
        Args:
            audit_logger: 审计日志记录器
        """
        self.audit_logger = audit_logger
        self.alert_thresholds = {
            'failed_login_attempts': 5,
            'suspicious_activity_score': 80,
            'unusual_access_patterns': 3
        }
        self.monitoring_enabled = True
        self.alert_callbacks = []
        
        # 统计数据
        self.login_attempts = defaultdict(int)
        self.user_activity = defaultdict(list)
        self.ip_activity = defaultdict(list)
        
        # 监控线程
        self.monitor_thread = None
        self.stop_monitoring = threading.Event()
    
    def start_monitoring(self):
        """
        开始监控
        """
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        
        self.monitoring_enabled = True
        self.stop_monitoring.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring_service(self):
        """
        停止监控
        """
        self.monitoring_enabled = False
        self.stop_monitoring.set()
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
    
    def _monitor_loop(self):
        """
        监控循环
        """
        while not self.stop_monitoring.is_set():
            try:
                self._analyze_recent_events()
                self._cleanup_old_data()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                print(f"监控循环错误: {str(e)}")
    
    def _analyze_recent_events(self):
        """
        分析最近的事件
        """
        recent_events = self.audit_logger.get_recent_events(100)
        
        for event in recent_events:
            self._update_statistics(event)
            self._check_for_alerts(event)
    
    def _update_statistics(self, event: SecurityEvent):
        """
        更新统计数据
        """
        current_time = datetime.now()
        
        # 更新登录尝试统计
        if event.event_type == SecurityEventType.LOGIN_FAILED:
            key = f"{event.user_id}:{event.ip_address}"
            self.login_attempts[key] += 1
        
        # 更新用户活动统计
        if event.user_id:
            self.user_activity[event.user_id].append({
                'timestamp': current_time,
                'event_type': event.event_type,
                'ip_address': event.ip_address
            })
        
        # 更新IP活动统计
        if event.ip_address:
            self.ip_activity[event.ip_address].append({
                'timestamp': current_time,
                'event_type': event.event_type,
                'user_id': event.user_id
            })
    
    def _check_for_alerts(self, event: SecurityEvent):
        """
        检查是否需要发出警报
        """
        alerts = []
        
        # 检查失败登录尝试
        if event.event_type == SecurityEventType.LOGIN_FAILED:
            key = f"{event.user_id}:{event.ip_address}"
            if self.login_attempts[key] >= self.alert_thresholds['failed_login_attempts']:
                alerts.append({
                    'type': 'brute_force_attempt',
                    'severity': SecurityEventSeverity.HIGH,
                    'message': f"检测到暴力破解尝试: 用户 {event.user_id} 从 {event.ip_address} 连续失败登录 {self.login_attempts[key]} 次",
                    'event': event
                })
        
        # 检查可疑活动
        if event.severity == SecurityEventSeverity.HIGH or event.severity == SecurityEventSeverity.CRITICAL:
            alerts.append({
                'type': 'high_severity_event',
                'severity': event.severity,
                'message': f"检测到高严重程度安全事件: {event.event_type.value}",
                'event': event
            })
        
        # 检查异常访问模式
        if event.user_id and len(self.user_activity[event.user_id]) > 0:
            recent_ips = set()
            for activity in self.user_activity[event.user_id][-10:]:  # 最近10次活动
                if activity['ip_address']:
                    recent_ips.add(activity['ip_address'])
            
            if len(recent_ips) >= self.alert_thresholds['unusual_access_patterns']:
                alerts.append({
                    'type': 'unusual_access_pattern',
                    'severity': SecurityEventSeverity.MEDIUM,
                    'message': f"检测到异常访问模式: 用户 {event.user_id} 从 {len(recent_ips)} 个不同IP地址访问",
                    'event': event
                })
        
        # 发送警报
        for alert in alerts:
            self._send_alert(alert)
    
    def _send_alert(self, alert: Dict[str, Any]):
        """
        发送警报
        """
        # 记录警报事件
        alert_event = SecurityEvent(
            event_type=SecurityEventType.SECURITY_VIOLATION,
            severity=alert['severity'],
            timestamp=datetime.now(),
            user_id=alert['event'].user_id,
            ip_address=alert['event'].ip_address,
            details={
                'alert_type': alert['type'],
                'alert_message': alert['message']
            }
        )
        self.audit_logger.log_event(alert_event)
        
        # 调用警报回调函数
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                print(f"警报回调函数执行失败: {str(e)}")
    
    def _cleanup_old_data(self):
        """
        清理旧数据
        """
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        # 清理登录尝试统计
        expired_keys = []
        for key in self.login_attempts:
            # 这里简化处理，实际应该根据时间戳清理
            if self.login_attempts[key] > 100:  # 防止内存泄漏
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.login_attempts[key]
        
        # 清理用户活动统计
        for user_id in list(self.user_activity.keys()):
            activities = self.user_activity[user_id]
            self.user_activity[user_id] = [
                activity for activity in activities 
                if activity['timestamp'] > cutoff_time
            ]
            
            if not self.user_activity[user_id]:
                del self.user_activity[user_id]
        
        # 清理IP活动统计
        for ip_address in list(self.ip_activity.keys()):
            activities = self.ip_activity[ip_address]
            self.ip_activity[ip_address] = [
                activity for activity in activities 
                if activity['timestamp'] > cutoff_time
            ]
            
            if not self.ip_activity[ip_address]:
                del self.ip_activity[ip_address]
    
    def add_alert_callback(self, callback):
        """
        添加警报回调函数
        
        Args:
            callback: 回调函数，接收警报字典作为参数
        """
        self.alert_callbacks.append(callback)
    
    def remove_alert_callback(self, callback):
        """
        移除警报回调函数
        """
        if callback in self.alert_callbacks:
            self.alert_callbacks.remove(callback)
    
    def get_security_statistics(self) -> Dict[str, Any]:
        """
        获取安全统计信息
        """
        recent_events = self.audit_logger.get_recent_events(1000)
        
        # 统计事件类型
        event_type_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        
        for event in recent_events:
            event_type_counts[event.event_type.value] += 1
            severity_counts[event.severity.value] += 1
        
        return {
            'total_events': len(recent_events),
            'event_type_counts': dict(event_type_counts),
            'severity_counts': dict(severity_counts),
            'active_users': len(self.user_activity),
            'active_ips': len(self.ip_activity),
            'failed_login_attempts': dict(self.login_attempts),
            'monitoring_enabled': self.monitoring_enabled
        }


class SecurityAuditManager:
    """
    安全审计管理器 - 统一管理审计日志和监控
    """
    
    def __init__(self, config: Dict = None):
        """
        初始化安全审计管理器
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        
        # 初始化审计日志记录器
        self.audit_logger = SecurityAuditLogger(
            log_file=self.config.get('log_file', 'logs/security_audit.log'),
            max_file_size=self.config.get('max_file_size', 10*1024*1024),
            backup_count=self.config.get('backup_count', 5),
            log_level=self.config.get('log_level', 'INFO')
        )
        
        # 初始化安全监控器
        self.monitor = SecurityMonitor(self.audit_logger)
        
        # 设置警报阈值
        alert_thresholds = self.config.get('alert_thresholds', {})
        self.monitor.alert_thresholds.update(alert_thresholds)
        
        # 启动监控
        if self.config.get('enable_monitoring', True):
            self.monitor.start_monitoring()
    
    def log_user_login(self, user_id: str, ip_address: str = None, 
                      user_agent: str = None, success: bool = True):
        """
        记录用户登录事件
        """
        event_type = SecurityEventType.USER_LOGIN if success else SecurityEventType.LOGIN_FAILED
        severity = SecurityEventSeverity.LOW if success else SecurityEventSeverity.MEDIUM
        
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now(),
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result='success' if success else 'failed'
        )
        
        self.audit_logger.log_event(event)
    
    def log_data_access(self, user_id: str, resource: str, action: str, 
                       result: str = 'success', ip_address: str = None):
        """
        记录数据访问事件
        """
        event_type_map = {
            'read': SecurityEventType.DATA_READ,
            'write': SecurityEventType.DATA_WRITE,
            'delete': SecurityEventType.DATA_DELETE,
            'export': SecurityEventType.DATA_EXPORT,
            'import': SecurityEventType.DATA_IMPORT
        }
        
        event_type = event_type_map.get(action.lower(), SecurityEventType.FILE_ACCESS)
        severity = SecurityEventSeverity.LOW if result == 'success' else SecurityEventSeverity.MEDIUM
        
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now(),
            user_id=user_id,
            ip_address=ip_address,
            resource=resource,
            action=action,
            result=result
        )
        
        self.audit_logger.log_event(event)
    
    def log_permission_change(self, user_id: str, target_user: str, permission: str,
                              action: str, ip_address: str = None):
        """记录权限变更事件"""
        action_lower = action.lower()
        if action_lower in {'grant', 'add', 'allow'}:
            event_type = SecurityEventType.PERMISSION_GRANTED
        elif action_lower in {'revoke', 'remove', 'deny'}:
            event_type = SecurityEventType.PERMISSION_REVOKED
        else:
            event_type = SecurityEventType.PERMISSION_GRANTED

        event = SecurityEvent(
            event_type=event_type,
            severity=SecurityEventSeverity.MEDIUM,
            timestamp=datetime.now(),
            user_id=user_id,
            ip_address=ip_address,
            details={
                'target_user': target_user,
                'permission': permission,
                'action': action
            }
        )

        self.audit_logger.log_event(event)

    def log_system_config_change(self, user_id: str, config_key: str,
                                 old_value: Any, new_value: Any,
                                 ip_address: str = None):
        """记录系统配置变更事件"""
        event = SecurityEvent(
            event_type=SecurityEventType.CONFIG_CHANGED,
            severity=SecurityEventSeverity.MEDIUM,
            timestamp=datetime.now(),
            user_id=user_id,
            ip_address=ip_address,
            details={
                'config_key': config_key,
                'old_value': old_value,
                'new_value': new_value
            }
        )

        self.audit_logger.log_event(event)

    def log_security_violation(self, violation_type: str, user_id: str = None,
                             ip_address: str = None, description: str = None,
                             details: Dict = None):
        """
        记录安全违规事件
        """
        event = SecurityEvent(
            event_type=SecurityEventType.SECURITY_VIOLATION,
            severity=SecurityEventSeverity.HIGH,
            timestamp=datetime.now(),
            user_id=user_id,
            ip_address=ip_address,
            details={
                'violation_type': violation_type,
                **({'description': description} if description else {}),
                **(details or {})
            }
        )

        self.audit_logger.log_event(event)
    
    def log_system_event(self, event_type: str, details: Dict = None):
        """
        记录系统事件
        """
        event_type_map = {
            'start': SecurityEventType.SYSTEM_START,
            'stop': SecurityEventType.SYSTEM_STOP,
            'config_change': SecurityEventType.CONFIG_CHANGED
        }
        
        event = SecurityEvent(
            event_type=event_type_map.get(event_type, SecurityEventType.SYSTEM_START),
            severity=SecurityEventSeverity.LOW,
            timestamp=datetime.now(),
            details=details
        )
        
        self.audit_logger.log_event(event)
    
    def get_audit_report(self, start_time: datetime = None, 
                        end_time: datetime = None) -> Dict[str, Any]:
        """
        生成审计报告
        """
        if start_time is None:
            start_time = datetime.now() - timedelta(days=7)
        if end_time is None:
            end_time = datetime.now()
        
        events = self.audit_logger.search_events(
            start_time=start_time,
            end_time=end_time
        )
        
        # 统计分析
        event_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        user_activity = defaultdict(int)
        hourly_activity = defaultdict(int)
        
        for event in events:
            event_counts[event.event_type.value] += 1
            severity_counts[event.severity.value] += 1
            
            if event.user_id:
                user_activity[event.user_id] += 1
            
            hour_key = event.timestamp.strftime('%Y-%m-%d %H:00')
            hourly_activity[hour_key] += 1
        
        return {
            'report_period': {
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat()
            },
            'summary': {
                'total_events': len(events),
                'unique_users': len(user_activity),
                'event_types': dict(event_counts),
                'severity_distribution': dict(severity_counts),
                'time_range': {
                    'start': start_time.isoformat(),
                    'end': end_time.isoformat()
                }
            },
            'user_activity': dict(user_activity),
            'hourly_activity': dict(hourly_activity),
            'security_statistics': self.monitor.get_security_statistics()
        }
    
    def shutdown(self):
        """
        关闭审计管理器
        """
        self.monitor.stop_monitoring_service()
        
        # 记录系统停止事件
        self.log_system_event('stop')


# 全局审计管理器实例
audit_manager = None


def get_audit_manager(config: Dict = None) -> SecurityAuditManager:
    """
    获取全局审计管理器实例
    """
    global audit_manager
    if audit_manager is None:
        audit_manager = SecurityAuditManager(config)
    return audit_manager


def setup_security_audit(config: Dict = None) -> SecurityAuditManager:
    """
    设置安全审计系统
    """
    manager = get_audit_manager(config)
    
    # 记录系统启动事件
    manager.log_system_event('start', {
        'version': '1.0.0',
        'config': config or {}
    })
    
    return manager