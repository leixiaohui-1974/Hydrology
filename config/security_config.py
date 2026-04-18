#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全配置模块 - Hydrology Framework Security Configuration

定义安全相关的配置选项和默认值。

作者: Hydrology Framework Team
版本: 1.0.0
日期: 2024
"""

import os
import secrets
from typing import Dict, List, Optional
from pathlib import Path


class SecurityConfig:
    """
    安全配置类 - 管理所有安全相关的配置
    """
    
    def __init__(self, config_file: str = None):
        """
        初始化安全配置
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self._config = self._load_default_config()
        
        if config_file and os.path.exists(config_file):
            self._load_from_file(config_file)
    
    def _load_default_config(self) -> Dict:
        """
        加载默认配置
        """
        return {
            # 用户管理配置
            'user_management': {
                'storage_path': 'data/users.json',
                'password_policy': {
                    'min_length': 8,
                    'require_uppercase': True,
                    'require_lowercase': True,
                    'require_digits': True,
                    'require_special_chars': True,
                    'special_chars': '@$!%*?&',
                    'max_failed_attempts': 5,
                    'lockout_duration_minutes': 30
                },
                'username_policy': {
                    'min_length': 3,
                    'max_length': 20,
                    'allowed_chars': 'a-zA-Z0-9_'
                }
            },
            
            # 会话管理配置
            'session_management': {
                'secret_key': None,  # 将在运行时生成
                'session_timeout': 3600,  # 1小时
                'cleanup_interval': 300,  # 5分钟清理一次过期会话
                'secure_cookies': True,
                'httponly_cookies': True,
                'samesite': 'Strict'
            },
            
            # JWT配置
            'jwt': {
                'secret_key': None,  # 将在运行时生成
                'algorithm': 'HS256',
                'token_expiry': 3600,  # 1小时
                'refresh_token_expiry': 86400,  # 24小时
                'issuer': 'hydrology-framework',
                'audience': 'hydrology-users'
            },
            
            # 加密配置
            'encryption': {
                'key': None,  # 将在运行时生成
                'key_derivation': {
                    'algorithm': 'PBKDF2HMAC',
                    'hash_algorithm': 'SHA256',
                    'iterations': 100000,
                    'salt_length': 16
                },
                'file_encryption': {
                    'enabled': True,
                    'encrypted_extensions': ['.dat', '.csv', '.json'],
                    'backup_original': True
                }
            },
            
            # 输入验证配置
            'input_validation': {
                'sanitize_html': True,
                'sanitize_sql': True,
                'max_string_length': 1000,
                'max_list_length': 100,
                'allowed_file_extensions': ['.py', '.txt', '.csv', '.json', '.yaml', '.yml'],
                'max_file_size': 10 * 1024 * 1024,  # 10MB
                'blocked_patterns': [
                    r'<script[^>]*>.*?</script>',
                    r'javascript:',
                    r'vbscript:',
                    r'onload\s*=',
                    r'onerror\s*='
                ]
            },
            
            # 访问控制配置
            'access_control': {
                'default_roles': ['user'],
                'role_hierarchy': {
                    'admin': ['user', 'moderator', 'admin'],
                    'moderator': ['user', 'moderator'],
                    'user': ['user']
                },
                'default_permissions': {
                    'admin': ['*'],  # 所有权限
                    'moderator': [
                        'read_data', 'write_data', 'manage_users', 
                        'view_reports', 'export_data'
                    ],
                    'user': [
                        'read_data', 'view_reports'
                    ]
                }
            },
            
            # 审计日志配置
            'audit_logging': {
                'enabled': True,
                'log_file': 'logs/security_audit.log',
                'log_level': 'INFO',
                'log_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'max_file_size': 10 * 1024 * 1024,  # 10MB
                'backup_count': 5,
                'events_to_log': [
                    'user_login', 'user_logout', 'user_creation', 'user_deletion',
                    'password_change', 'permission_change', 'role_change',
                    'file_access', 'data_export', 'configuration_change',
                    'security_violation', 'authentication_failure'
                ]
            },
            
            # 安全策略配置
            'security_policies': {
                'enforce_https': True,
                'require_authentication': True,
                'enable_rate_limiting': True,
                'rate_limit': {
                    'requests_per_minute': 60,
                    'requests_per_hour': 1000
                },
                'ip_whitelist': [],
                'ip_blacklist': [],
                'enable_csrf_protection': True,
                'enable_xss_protection': True,
                'content_security_policy': {
                    'default-src': "'self'",
                    'script-src': "'self' 'unsafe-inline'",
                    'style-src': "'self' 'unsafe-inline'",
                    'img-src': "'self' data:",
                    'font-src': "'self'",
                    'connect-src': "'self'"
                }
            },
            
            # 数据保护配置
            'data_protection': {
                'encrypt_sensitive_data': True,
                'sensitive_fields': [
                    'password', 'email', 'phone', 'address', 'ssn', 'credit_card'
                ],
                'data_retention': {
                    'user_data_days': 365,
                    'log_data_days': 90,
                    'session_data_days': 7
                },
                'backup_encryption': True,
                'secure_delete': True
            },
            
            # 监控和告警配置
            'monitoring': {
                'enabled': True,
                'alert_thresholds': {
                    'failed_login_attempts': 10,
                    'suspicious_activity_score': 80,
                    'unusual_access_patterns': 5
                },
                'notification_channels': {
                    'email': {
                        'enabled': False,
                        'recipients': [],
                        'smtp_server': None,
                        'smtp_port': 587,
                        'use_tls': True
                    },
                    'webhook': {
                        'enabled': False,
                        'url': None,
                        'secret': None
                    }
                }
            }
        }
    
    def _load_from_file(self, config_file: str):
        """
        从文件加载配置
        """
        try:
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
            
            # 递归合并配置
            self._merge_config(self._config, file_config)
            
        except Exception as e:
            print(f"警告: 无法加载配置文件 {config_file}: {str(e)}")
    
    def _merge_config(self, base_config: Dict, new_config: Dict):
        """
        递归合并配置
        """
        for key, value in new_config.items():
            if key in base_config and isinstance(base_config[key], dict) and isinstance(value, dict):
                self._merge_config(base_config[key], value)
            else:
                base_config[key] = value
    
    def get(self, key: str, default=None):
        """
        获取配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键
            default: 默认值
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
                
        return value
    
    def set(self, key: str, value):
        """
        设置配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键
            value: 配置值
        """
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
            
        config[keys[-1]] = value
    
    def generate_secrets(self):
        """
        生成安全密钥
        """
        # 生成会话密钥
        if not self.get('session_management.secret_key'):
            self.set('session_management.secret_key', secrets.token_urlsafe(32))
        
        # 生成JWT密钥
        if not self.get('jwt.secret_key'):
            self.set('jwt.secret_key', secrets.token_urlsafe(32))
        
        # 生成加密密钥
        if not self.get('encryption.key'):
            try:
                from cryptography.fernet import Fernet
                self.set('encryption.key', Fernet.generate_key().decode())
            except ImportError:
                # 如果没有cryptography库，生成一个简单的密钥
                self.set('encryption.key', secrets.token_urlsafe(32))
    
    def validate_config(self) -> List[str]:
        """
        验证配置
        
        Returns:
            List[str]: 验证错误列表
        """
        errors = []
        
        # 检查必需的配置
        required_configs = [
            'user_management.storage_path',
            'session_management.session_timeout',
            'jwt.algorithm',
            'encryption.key_derivation.iterations'
        ]
        
        for config_key in required_configs:
            if self.get(config_key) is None:
                errors.append(f"缺少必需的配置: {config_key}")
        
        # 验证密码策略
        min_length = self.get('user_management.password_policy.min_length')
        if min_length and min_length < 6:
            errors.append("密码最小长度不能少于6位")
        
        # 验证会话超时
        session_timeout = self.get('session_management.session_timeout')
        if session_timeout and session_timeout < 300:  # 5分钟
            errors.append("会话超时时间不能少于5分钟")
        
        # 验证JWT过期时间
        jwt_expiry = self.get('jwt.token_expiry')
        if jwt_expiry and jwt_expiry < 300:  # 5分钟
            errors.append("JWT令牌过期时间不能少于5分钟")
        
        return errors
    
    def save_to_file(self, config_file: str = None):
        """
        保存配置到文件
        """
        if config_file is None:
            config_file = self.config_file
            
        if not config_file:
            raise ValueError("未指定配置文件路径")
        
        # 确保目录存在
        Path(config_file).parent.mkdir(parents=True, exist_ok=True)
        
        try:
            import json
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise Exception(f"保存配置文件失败: {str(e)}")
    
    def get_password_policy(self) -> Dict:
        """
        获取密码策略
        """
        return self.get('user_management.password_policy', {})
    
    def get_session_config(self) -> Dict:
        """
        获取会话配置
        """
        return self.get('session_management', {})
    
    def get_jwt_config(self) -> Dict:
        """
        获取JWT配置
        """
        return self.get('jwt', {})
    
    def get_encryption_config(self) -> Dict:
        """
        获取加密配置
        """
        return self.get('encryption', {})
    
    def get_access_control_config(self) -> Dict:
        """
        获取访问控制配置
        """
        return self.get('access_control', {})
    
    def get_audit_config(self) -> Dict:
        """
        获取审计配置
        """
        return self.get('audit_logging', {})
    
    def get_security_policies(self) -> Dict:
        """
        获取安全策略
        """
        return self.get('security_policies', {})
    
    def is_development_mode(self) -> bool:
        """
        检查是否为开发模式
        """
        return self.get('development_mode', False)
    
    def is_debug_mode(self) -> bool:
        """
        检查是否为调试模式
        """
        return self.get('debug_mode', False)
    
    def get_allowed_origins(self) -> List[str]:
        """
        获取允许的来源列表（用于CORS）
        """
        return self.get('security_policies.allowed_origins', ['http://localhost:*'])
    
    def to_dict(self) -> Dict:
        """
        转换为字典
        """
        return self._config.copy()


# 默认安全配置实例
default_security_config = SecurityConfig()


def get_security_config(config_file: str = None) -> SecurityConfig:
    """
    获取安全配置实例
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        SecurityConfig: 安全配置实例
    """
    if config_file:
        return SecurityConfig(config_file)
    else:
        return default_security_config


def create_default_config_file(config_file: str):
    """
    创建默认配置文件
    
    Args:
        config_file: 配置文件路径
    """
    config = SecurityConfig()
    config.generate_secrets()
    config.save_to_file(config_file)
    print(f"已创建默认安全配置文件: {config_file}")


if __name__ == '__main__':
    # 创建示例配置文件
    config = SecurityConfig()
    config.generate_secrets()
    
    # 验证配置
    errors = config.validate_config()
    if errors:
        print("配置验证错误:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("配置验证通过")
    
    # 保存示例配置
    try:
        config.save_to_file('config/security_config.json')
        print("已保存示例配置文件: config/security_config.json")
    except Exception as e:
        print(f"保存配置文件失败: {str(e)}")