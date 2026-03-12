#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全模块 - Hydrology Framework Security Module

提供输入验证、数据加密、用户权限管理等安全功能。

作者: Hydrology Framework Team
版本: 1.0.0
日期: 2024
"""

import os
import re
import hashlib
import secrets
import base64
import json
import time
from typing import Dict, List, Optional, Any, Union, Callable
from functools import wraps
from datetime import datetime, timedelta
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

from .error_handler import SecurityError, ValidationError
from .security_audit import get_audit_manager


class InputValidator:
    """
    输入验证器 - 提供各种输入数据的验证功能
    """
    
    # 常用正则表达式模式
    PATTERNS = {
        'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        'username': r'^[a-zA-Z0-9_]{3,20}$',
        'password': r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$',
        'filename': r'^[a-zA-Z0-9._-]+$',
        'path': r'^[a-zA-Z0-9._/\\:-]+$',
        'ip_address': r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
        'url': r'^https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?)?$'
    }
    
    @classmethod
    def validate_string(cls, value: str, pattern: Optional[str] = None, min_length: int = 0, 
                       max_length: Optional[int] = None, required: bool = True) -> bool:
        """
        验证字符串
        
        Args:
            value: 要验证的字符串
            pattern: 正则表达式模式
            min_length: 最小长度
            max_length: 最大长度
            required: 是否必需
            
        Returns:
            bool: 验证结果
        """
        if not required and not value:
            return True
            
        if required and not value:
            raise ValidationError("字符串不能为空")
            
        if not isinstance(value, str):
            raise ValidationError("输入必须是字符串类型")
            
        if len(value) < min_length:
            raise ValidationError(f"字符串长度不能少于 {min_length} 个字符")
            
        if max_length and len(value) > max_length:
            raise ValidationError(f"字符串长度不能超过 {max_length} 个字符")
            
        if pattern and not re.match(pattern, value):
            raise ValidationError("字符串格式不符合要求")
            
        return True
    
    @classmethod
    def validate_email(cls, email: str) -> bool:
        """
        验证邮箱地址
        """
        return cls.validate_string(email, cls.PATTERNS['email'])
    
    @classmethod
    def validate_username(cls, username: str) -> bool:
        """
        验证用户名
        """
        return cls.validate_string(username, cls.PATTERNS['username'])
    
    @classmethod
    def validate_password(cls, password: str) -> bool:
        """
        验证密码强度
        """
        return cls.validate_string(password, cls.PATTERNS['password'])
    
    @classmethod
    def validate_filename(cls, filename: str) -> bool:
        """
        验证文件名
        """
        return cls.validate_string(filename, cls.PATTERNS['filename'])
    
    @classmethod
    def validate_path(cls, path: str, must_exist: bool = False) -> bool:
        """
        验证文件路径
        """
        cls.validate_string(path, cls.PATTERNS['path'])
        
        if must_exist and not Path(path).exists():
            raise ValidationError(f"路径不存在: {path}")
            
        return True
    
    @classmethod
    def validate_number(cls, value: Union[int, float], min_value: float = None, 
                       max_value: float = None, integer_only: bool = False) -> bool:
        """
        验证数值
        """
        if not isinstance(value, (int, float)):
            raise ValidationError("输入必须是数值类型")
            
        if integer_only and not isinstance(value, int):
            raise ValidationError("输入必须是整数类型")
            
        if min_value is not None and value < min_value:
            raise ValidationError(f"数值不能小于 {min_value}")
            
        if max_value is not None and value > max_value:
            raise ValidationError(f"数值不能大于 {max_value}")
            
        return True
    
    @classmethod
    def validate_list(cls, value: List, min_length: int = 0, max_length: int = None,
                     item_validator: Callable = None) -> bool:
        """
        验证列表
        """
        if not isinstance(value, list):
            raise ValidationError("输入必须是列表类型")
            
        if len(value) < min_length:
            raise ValidationError(f"列表长度不能少于 {min_length}")
            
        if max_length and len(value) > max_length:
            raise ValidationError(f"列表长度不能超过 {max_length}")
            
        if item_validator:
            for i, item in enumerate(value):
                try:
                    item_validator(item)
                except ValidationError as e:
                    raise ValidationError(f"列表第 {i+1} 项验证失败: {str(e)}")
                    
        return True
    
    @classmethod
    def sanitize_input(cls, value: str, remove_html: bool = True, 
                      remove_sql: bool = True) -> str:
        """
        清理输入数据
        
        Args:
            value: 要清理的字符串
            remove_html: 是否移除HTML标签
            remove_sql: 是否移除SQL注入字符
            
        Returns:
            str: 清理后的字符串
        """
        if not isinstance(value, str):
            return value
            
        # 移除HTML标签
        if remove_html:
            value = re.sub(r'<[^>]+>', '', value)
            
        # 移除潜在的SQL注入字符和关键字
        if remove_sql:
            # SQL注入危险字符
            dangerous_chars = ['--', ';', '/*', '*/', 'xp_', 'sp_']
            for char in dangerous_chars:
                value = value.replace(char, '')
            
            # SQL注入危险关键字（不区分大小写）
            dangerous_keywords = [
                'DROP', 'DELETE', 'INSERT', 'UPDATE', 'SELECT', 'UNION',
                'ALTER', 'CREATE', 'TRUNCATE', 'EXEC', 'EXECUTE',
                'SCRIPT', 'JAVASCRIPT', 'VBSCRIPT', 'ONLOAD', 'ONERROR'
            ]
            
            for keyword in dangerous_keywords:
                # 使用正则表达式进行不区分大小写的替换
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                value = pattern.sub('', value)
                
        return value.strip()


class DataEncryption:
    """
    数据加密器 - 提供数据加密和解密功能
    """
    
    def __init__(self, key: bytes = None):
        """
        初始化加密器
        
        Args:
            key: 加密密钥，如果为None则生成新密钥
        """
        if not CRYPTO_AVAILABLE:
            raise SecurityError("加密功能不可用，请安装 cryptography 库")
            
        if key is None:
            key = Fernet.generate_key()
        elif isinstance(key, str):
            key = key.encode()
            
        self.key = key
        self.cipher = Fernet(key)
    
    @classmethod
    def generate_key(cls) -> bytes:
        """
        生成新的加密密钥
        """
        if not CRYPTO_AVAILABLE:
            raise SecurityError("加密功能不可用，请安装 cryptography 库")
        return Fernet.generate_key()
    
    @classmethod
    def derive_key_from_password(cls, password: str, salt: bytes = None) -> tuple:
        """
        从密码派生密钥
        
        Returns:
            tuple: (密钥, 盐值)
        """
        if not CRYPTO_AVAILABLE:
            raise SecurityError("加密功能不可用，请安装 cryptography 库")
            
        if salt is None:
            salt = os.urandom(16)
            
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt
    
    def encrypt(self, data: Union[str, bytes]) -> bytes:
        """
        加密数据
        """
        if isinstance(data, str):
            data = data.encode()
        return self.cipher.encrypt(data)
    
    def decrypt(self, encrypted_data: bytes) -> bytes:
        """
        解密数据
        """
        return self.cipher.decrypt(encrypted_data)
    
    def encrypt_to_string(self, data: Union[str, bytes]) -> str:
        """
        加密数据并返回base64字符串
        """
        encrypted = self.encrypt(data)
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt_from_string(self, encrypted_string: str) -> str:
        """
        从base64字符串解密数据
        """
        encrypted_data = base64.urlsafe_b64decode(encrypted_string.encode())
        decrypted = self.decrypt(encrypted_data)
        return decrypted.decode()
    
    def encrypt_file(self, file_path: str, output_path: str = None) -> str:
        """
        加密文件
        
        Returns:
            str: 加密后的文件路径
        """
        if output_path is None:
            output_path = file_path + '.encrypted'
            
        with open(file_path, 'rb') as f:
            data = f.read()
            
        encrypted_data = self.encrypt(data)
        
        with open(output_path, 'wb') as f:
            f.write(encrypted_data)
            
        return output_path
    
    def decrypt_file(self, encrypted_file_path: str, output_path: str = None) -> str:
        """
        解密文件
        
        Returns:
            str: 解密后的文件路径
        """
        if output_path is None:
            output_path = encrypted_file_path.replace('.encrypted', '')
            
        with open(encrypted_file_path, 'rb') as f:
            encrypted_data = f.read()
            
        decrypted_data = self.decrypt(encrypted_data)
        
        with open(output_path, 'wb') as f:
            f.write(decrypted_data)
            
        return output_path


class PasswordManager:
    """
    密码管理器 - 提供密码哈希和验证功能
    """
    
    @staticmethod
    def hash_password(password: str, salt: str = None) -> tuple:
        """
        哈希密码
        
        Returns:
            tuple: (哈希值, 盐值)
        """
        if salt is None:
            salt = secrets.token_hex(16)
        elif isinstance(salt, bytes):
            salt = salt.hex()
            
        # 使用PBKDF2进行密码哈希
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # 迭代次数
        )
        
        return password_hash.hex(), salt
    
    @staticmethod
    def verify_password(password: str, password_hash: str, salt: str) -> bool:
        """
        验证密码
        """
        computed_hash, _ = PasswordManager.hash_password(password, salt)
        return secrets.compare_digest(computed_hash, password_hash)
    
    @staticmethod
    def generate_secure_password(length: int = 12) -> str:
        """
        生成安全密码
        """
        import string
        
        # 确保包含各种字符类型
        chars = string.ascii_letters + string.digits + "@$!%*?&"
        password = ''.join(secrets.choice(chars) for _ in range(length))
        
        # 确保至少包含一个大写字母、小写字母、数字和特殊字符
        if not any(c.islower() for c in password):
            password = password[:-1] + secrets.choice(string.ascii_lowercase)
        if not any(c.isupper() for c in password):
            password = password[:-1] + secrets.choice(string.ascii_uppercase)
        if not any(c.isdigit() for c in password):
            password = password[:-1] + secrets.choice(string.digits)
        if not any(c in "@$!%*?&" for c in password):
            password = password[:-1] + secrets.choice("@$!%*?&")
            
        return password


class User:
    """
    用户类 - 表示系统用户
    """
    
    def __init__(self, username: str, email: str, password_hash: str = None, 
                 salt: str = None, roles: List[str] = None, permissions: List[str] = None):
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.salt = salt
        self.roles = roles or []
        self.permissions = permissions or []
        self.created_at = datetime.now()
        self.last_login = None
        self.is_active = True
        self.failed_login_attempts = 0
        self.locked_until = None
    
    def set_password(self, password: str):
        """
        设置密码
        """
        InputValidator.validate_password(password)
        self.password_hash, self.salt = PasswordManager.hash_password(password)
    
    def verify_password(self, password: str) -> bool:
        """
        验证密码
        """
        if not self.password_hash or not self.salt:
            return False
        return PasswordManager.verify_password(password, self.password_hash, self.salt)
    
    def add_role(self, role: str):
        """
        添加角色
        """
        if role not in self.roles:
            self.roles.append(role)
    
    def remove_role(self, role: str):
        """
        移除角色
        """
        if role in self.roles:
            self.roles.remove(role)
    
    def has_role(self, role: str) -> bool:
        """
        检查是否有指定角色
        """
        return role in self.roles
    
    def add_permission(self, permission: str):
        """
        添加权限
        """
        if permission not in self.permissions:
            self.permissions.append(permission)
    
    def remove_permission(self, permission: str):
        """
        移除权限
        """
        if permission in self.permissions:
            self.permissions.remove(permission)
    
    def has_permission(self, permission: str) -> bool:
        """
        检查是否有指定权限
        """
        return permission in self.permissions
    
    def is_locked(self) -> bool:
        """
        检查账户是否被锁定
        """
        if self.locked_until and datetime.now() < self.locked_until:
            return True
        return False
    
    def lock_account(self, duration_minutes: int = 30):
        """
        锁定账户
        """
        self.locked_until = datetime.now() + timedelta(minutes=duration_minutes)
    
    def unlock_account(self):
        """
        解锁账户
        """
        self.locked_until = None
        self.failed_login_attempts = 0
    
    def to_dict(self) -> Dict:
        """
        转换为字典
        """
        return {
            'username': self.username,
            'email': self.email,
            'roles': self.roles,
            'permissions': self.permissions,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'is_active': self.is_active,
            'failed_login_attempts': self.failed_login_attempts,
            'locked_until': self.locked_until.isoformat() if self.locked_until else None
        }


class UserManager:
    """
    用户管理器 - 管理系统用户
    """
    
    def __init__(self, storage_path: str = None):
        self.users: Dict[str, User] = {}
        self.storage_path = storage_path or "users.json"
        self.load_users()
    
    def create_user(self, username: str, email: str, password: str, 
                   roles: List[str] = None) -> User:
        """
        创建用户
        """
        # 验证输入
        InputValidator.validate_username(username)
        InputValidator.validate_email(email)
        InputValidator.validate_password(password)
        
        # 检查用户是否已存在
        if username in self.users:
            raise SecurityError(f"用户名 '{username}' 已存在")
            
        # 检查邮箱是否已被使用
        for user in self.users.values():
            if user.email == email:
                raise SecurityError(f"邮箱 '{email}' 已被使用")
        
        # 创建用户
        user = User(username, email, roles=roles)
        user.set_password(password)
        
        self.users[username] = user
        self.save_users()
        
        return user
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        用户认证
        """
        user = self.users.get(username)
        if not user:
            return None
            
        # 检查账户是否被锁定
        if user.is_locked():
            raise SecurityError("账户已被锁定，请稍后再试")
            
        # 检查账户是否激活
        if not user.is_active:
            raise SecurityError("账户已被禁用")
            
        # 验证密码
        if user.verify_password(password):
            user.last_login = datetime.now()
            user.failed_login_attempts = 0
            self.save_users()
            return user
        else:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.lock_account()
            self.save_users()
            return None
    
    def get_user(self, username: str) -> Optional[User]:
        """
        获取用户
        """
        return self.users.get(username)
    
    def update_user(self, username: str, **kwargs) -> bool:
        """
        更新用户信息
        """
        user = self.users.get(username)
        if not user:
            return False
            
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
                
        self.save_users()
        return True
    
    def delete_user(self, username: str) -> bool:
        """
        删除用户
        """
        if username in self.users:
            del self.users[username]
            self.save_users()
            return True
        return False
    
    def list_users(self) -> List[Dict]:
        """
        列出所有用户
        """
        return [user.to_dict() for user in self.users.values()]
    
    def save_users(self):
        """
        保存用户数据
        """
        try:
            data = {}
            for username, user in self.users.items():
                data[username] = {
                    'username': user.username,
                    'email': user.email,
                    'password_hash': user.password_hash,
                    'salt': user.salt,
                    'roles': user.roles,
                    'permissions': user.permissions,
                    'created_at': user.created_at.isoformat(),
                    'last_login': user.last_login.isoformat() if user.last_login else None,
                    'is_active': user.is_active,
                    'failed_login_attempts': user.failed_login_attempts,
                    'locked_until': user.locked_until.isoformat() if user.locked_until else None
                }
            
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise SecurityError(f"保存用户数据失败: {str(e)}")
    
    def load_users(self):
        """
        加载用户数据
        """
        try:
            if not os.path.exists(self.storage_path):
                return
                
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for username, user_data in data.items():
                user = User(
                    username=user_data['username'],
                    email=user_data['email'],
                    password_hash=user_data.get('password_hash'),
                    salt=user_data.get('salt'),
                    roles=user_data.get('roles', []),
                    permissions=user_data.get('permissions', [])
                )
                
                if user_data.get('created_at'):
                    user.created_at = datetime.fromisoformat(user_data['created_at'])
                if user_data.get('last_login'):
                    user.last_login = datetime.fromisoformat(user_data['last_login'])
                if user_data.get('locked_until'):
                    user.locked_until = datetime.fromisoformat(user_data['locked_until'])
                    
                user.is_active = user_data.get('is_active', True)
                user.failed_login_attempts = user_data.get('failed_login_attempts', 0)
                
                self.users[username] = user
                
        except Exception as e:
            raise SecurityError(f"加载用户数据失败: {str(e)}")


class SessionManager:
    """
    会话管理器 - 管理用户会话
    """
    
    def __init__(self, secret_key: str = None, session_timeout: int = 3600):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.session_timeout = session_timeout  # 秒
        self.sessions: Dict[str, Dict] = {}
    
    def create_session(self, user: User, *, ip_address: Optional[str] = None,
                       user_agent: Optional[str] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> str:
        """创建会话并允许附加上下文字段"""
        session_id = secrets.token_urlsafe(32)

        session_data: Dict[str, Any] = {
            'user_id': user.username,
            'created_at': time.time(),
            'last_accessed': time.time(),
            'user_agent': user_agent,
            'ip_address': ip_address
        }

        if metadata:
            session_data.update(metadata)

        self.sessions[session_id] = session_data
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        获取会话
        """
        session = self.sessions.get(session_id)
        if not session:
            return None
            
        # 检查会话是否过期
        if time.time() - session['last_accessed'] > self.session_timeout:
            self.destroy_session(session_id)
            return None
            
        # 更新最后访问时间
        session['last_accessed'] = time.time()
        return session

    def update_session(self, session_id: str, **updates: Any) -> bool:
        """更新会话信息并刷新最后访问时间"""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session['last_accessed'] = time.time()
        for key, value in updates.items():
            session[key] = value
        return True

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """返回当前未过期的会话列表"""
        self.cleanup_expired_sessions()
        active_sessions = []
        for session_id, session in self.sessions.items():
            session_copy = session.copy()
            session_copy['session_id'] = session_id
            active_sessions.append(session_copy)
        return active_sessions

    def destroy_session(self, session_id: str) -> bool:
        """
        销毁会话
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
    
    def is_session_valid(self, session_id: str) -> bool:
        """
        检查会话是否有效
        """
        session = self.get_session(session_id)
        return session is not None
    
    def cleanup_expired_sessions(self):
        """
        清理过期会话
        """
        current_time = time.time()
        expired_sessions = []
        
        for session_id, session in self.sessions.items():
            if current_time - session['last_accessed'] > self.session_timeout:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self.sessions[session_id]


class JWTManager:
    """
    JWT令牌管理器
    """
    
    def __init__(self, secret_key: str = None, algorithm: str = 'HS256', 
                 token_expiry: int = 3600):
        if not JWT_AVAILABLE:
            raise SecurityError("JWT功能不可用，请安装 PyJWT 库")
            
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = algorithm
        self.token_expiry = token_expiry
    
    def generate_token(self, user: User, additional_claims: Dict = None) -> str:
        """
        生成JWT令牌
        """
        payload = {
            'user_id': user.username,
            'email': user.email,
            'roles': user.roles,
            'permissions': user.permissions,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(seconds=self.token_expiry)
        }
        
        if additional_claims:
            payload.update(additional_claims)
            
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """
        验证JWT令牌
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise SecurityError("令牌已过期")
        except jwt.InvalidTokenError:
            raise SecurityError("无效的令牌")
    
    def refresh_token(self, token: str) -> str:
        """
        刷新令牌
        """
        try:
            # 解码令牌（忽略过期时间）
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], 
                               options={"verify_exp": False})
            
            # 生成新令牌
            new_payload = {
                'user_id': payload['user_id'],
                'email': payload['email'],
                'roles': payload['roles'],
                'permissions': payload['permissions'],
                'iat': datetime.utcnow(),
                'exp': datetime.utcnow() + timedelta(seconds=self.token_expiry)
            }
            
            return jwt.encode(new_payload, self.secret_key, algorithm=self.algorithm)
            
        except jwt.InvalidTokenError:
            raise SecurityError("无效的令牌")


def require_permission(permission: str):
    """
    权限装饰器 - 要求特定权限才能访问函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 这里需要从上下文中获取当前用户
            # 实际实现中可能需要从Flask的session或其他地方获取
            current_user = kwargs.get('current_user')
            if not current_user or not current_user.has_permission(permission):
                raise SecurityError(f"权限不足，需要权限: {permission}")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_role(role: str):
    """
    角色装饰器 - 要求特定角色才能访问函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user or not current_user.has_role(role):
                raise SecurityError(f"权限不足，需要角色: {role}")
            return func(*args, **kwargs)
        return wrapper
    return decorator


class SecurityManager:
    """
    安全管理器 - 统一管理所有安全功能
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # 初始化各个组件
        self.user_manager = UserManager(
            storage_path=self.config.get('user_storage_path', 'users.json')
        )
        
        self.session_manager = SessionManager(
            secret_key=self.config.get('session_secret_key'),
            session_timeout=self.config.get('session_timeout', 3600)
        )
        
        if JWT_AVAILABLE:
            self.jwt_manager = JWTManager(
                secret_key=self.config.get('jwt_secret_key'),
                token_expiry=self.config.get('jwt_token_expiry', 3600)
            )
        else:
            self.jwt_manager = None
            
        if CRYPTO_AVAILABLE:
            encryption_key = self.config.get('encryption_key')
            if encryption_key:
                self.encryption = DataEncryption(encryption_key)
            else:
                self.encryption = DataEncryption()
        else:
            self.encryption = None

        audit_config = self.config.get('audit', {})
        try:
            self.audit_manager = get_audit_manager(audit_config)
        except Exception as exc:
            # 审计系统初始化失败时保持兼容
            self.audit_manager = None
            print(f"[SECURITY WARNING] 安全审计初始化失败: {exc}")
    
    def initialize_default_users(self):
        """
        初始化默认用户
        """
        # 创建管理员用户
        if 'admin' not in self.user_manager.users:
            admin_password = PasswordManager.generate_secure_password()
            admin_user = self.user_manager.create_user(
                username='admin',
                email='admin@hydrology.local',
                password=admin_password,
                roles=['admin', 'user']
            )
            admin_user.add_permission('*')  # 所有权限
            
            print(f"创建管理员用户: admin")
            print(f"管理员密码: {admin_password}")
            print("请妥善保存管理员密码！")

    def ensure_development_test_user(
        self,
        username: str = 'test_user',
        password: str = 'test_password',
        email: str = 'test_user@hydrology.local'
    ) -> bool:
        """
        Ensure the documented API test user exists for development/testing.

        This intentionally bypasses password complexity validation so the
        documented default password remains usable in non-production flows.
        Returns True when user data was created or updated.
        """
        changed = False
        user = self.user_manager.get_user(username)

        if user is None:
            user = User(username=username, email=email, roles=['user'])
            user.password_hash, user.salt = PasswordManager.hash_password(password)
            self.user_manager.users[username] = user
            changed = True
        else:
            if user.email != email:
                user.email = email
                changed = True

            if not user.verify_password(password):
                user.password_hash, user.salt = PasswordManager.hash_password(password)
                changed = True

            if not user.is_active:
                user.is_active = True
                changed = True

            if user.is_locked() or user.failed_login_attempts:
                user.unlock_account()
                changed = True

        required_roles = ['user']
        required_permissions = ['run_simulation', 'delete_simulation']

        for role in required_roles:
            if role not in user.roles:
                user.add_role(role)
                changed = True

        for permission in required_permissions:
            if permission not in user.permissions:
                user.add_permission(permission)
                changed = True

        if changed:
            self.user_manager.save_users()

        return changed
    
    def get_security_status(self) -> Dict:
        """
        获取安全状态
        """
        return {
            'crypto_available': CRYPTO_AVAILABLE,
            'jwt_available': JWT_AVAILABLE,
            'total_users': len(self.user_manager.users),
            'active_sessions': len(self.session_manager.sessions),
            'encryption_enabled': self.encryption is not None,
            'jwt_enabled': self.jwt_manager is not None,
            'audit_enabled': self.audit_manager is not None
        }


# 全局安全管理器实例
security_manager = None


def get_security_manager(config: Dict = None) -> SecurityManager:
    """
    获取全局安全管理器实例
    """
    global security_manager
    if security_manager is None:
        security_manager = SecurityManager(config)
    return security_manager


def setup_security(config: Dict = None) -> SecurityManager:
    """
    设置安全系统
    """
    manager = get_security_manager(config)
    manager.initialize_default_users()
    return manager
