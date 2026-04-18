#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全模块测试 - Hydrology Framework Security Tests

测试安全模块的各项功能，包括输入验证、数据加密、用户管理等。

作者: Hydrology Framework Team
版本: 1.0.0
日期: 2024
"""

import os
import sys
import unittest
import tempfile
import shutil
import json
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from common.security import (
        InputValidator, DataEncryption, PasswordManager, User, UserManager,
        SessionManager, SecurityManager, get_security_manager, setup_security
    )
    from common.security_audit import (
        SecurityEvent, SecurityEventType, SecurityEventSeverity,
        SecurityAuditLogger, SecurityMonitor, SecurityAuditManager
    )
    from config.security_config import SecurityConfig
    from common.error_handler import SecurityError, ValidationError
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保所有依赖模块都已正确安装")
    sys.exit(1)


class TestInputValidator(unittest.TestCase):
    """
    输入验证器测试
    """
    
    def test_validate_string(self):
        """
        测试字符串验证
        """
        # 正常情况
        self.assertTrue(InputValidator.validate_string("hello", min_length=3, max_length=10))
        
        # 长度不足
        with self.assertRaises(ValidationError):
            InputValidator.validate_string("hi", min_length=3)
        
        # 长度超出
        with self.assertRaises(ValidationError):
            InputValidator.validate_string("hello world!", max_length=10)
        
        # 空字符串（必需）
        with self.assertRaises(ValidationError):
            InputValidator.validate_string("", required=True)
        
        # 空字符串（非必需）
        self.assertTrue(InputValidator.validate_string("", required=False))
    
    def test_validate_email(self):
        """
        测试邮箱验证
        """
        # 有效邮箱
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "user+tag@example.org"
        ]
        
        for email in valid_emails:
            self.assertTrue(InputValidator.validate_email(email))
        
        # 无效邮箱
        invalid_emails = [
            "invalid-email",
            "@example.com",
            "user@",
            "user@.com",
            "user name@example.com"
        ]
        
        for email in invalid_emails:
            with self.assertRaises(ValidationError):
                InputValidator.validate_email(email)
    
    def test_validate_username(self):
        """
        测试用户名验证
        """
        # 有效用户名
        valid_usernames = ["user123", "test_user", "admin"]
        
        for username in valid_usernames:
            self.assertTrue(InputValidator.validate_username(username))
        
        # 无效用户名
        invalid_usernames = ["us", "user-name", "user@name", "a" * 25]
        
        for username in invalid_usernames:
            with self.assertRaises(ValidationError):
                InputValidator.validate_username(username)
    
    def test_validate_password(self):
        """
        测试密码验证
        """
        # 有效密码
        valid_passwords = ["Password123!", "MySecure@Pass1"]
        
        for password in valid_passwords:
            self.assertTrue(InputValidator.validate_password(password))
        
        # 无效密码
        invalid_passwords = [
            "weak",  # 太短
            "password",  # 没有大写字母、数字、特殊字符
            "PASSWORD123!",  # 没有小写字母
            "Password!",  # 没有数字
            "Password123"  # 没有特殊字符
        ]
        
        for password in invalid_passwords:
            with self.assertRaises(ValidationError):
                InputValidator.validate_password(password)
    
    def test_validate_number(self):
        """
        测试数值验证
        """
        # 正常情况
        self.assertTrue(InputValidator.validate_number(5, min_value=0, max_value=10))
        self.assertTrue(InputValidator.validate_number(5.5, min_value=0, max_value=10))
        
        # 超出范围
        with self.assertRaises(ValidationError):
            InputValidator.validate_number(-1, min_value=0)
        
        with self.assertRaises(ValidationError):
            InputValidator.validate_number(15, max_value=10)
        
        # 类型错误
        with self.assertRaises(ValidationError):
            InputValidator.validate_number("5")
        
        # 整数验证
        self.assertTrue(InputValidator.validate_number(5, integer_only=True))
        
        with self.assertRaises(ValidationError):
            InputValidator.validate_number(5.5, integer_only=True)
    
    def test_sanitize_input(self):
        """
        测试输入清理
        """
        # HTML清理
        html_input = "<script>alert('xss')</script>Hello"
        sanitized = InputValidator.sanitize_input(html_input)
        self.assertNotIn("<script>", sanitized)
        self.assertIn("Hello", sanitized)
        
        # SQL注入清理
        sql_input = "'; DROP TABLE users; --"
        sanitized = InputValidator.sanitize_input(sql_input)
        self.assertNotIn("--", sanitized)
        self.assertNotIn("DROP", sanitized)


class TestPasswordManager(unittest.TestCase):
    """
    密码管理器测试
    """
    
    def test_hash_password(self):
        """
        测试密码哈希
        """
        password = "TestPassword123!"
        hash1, salt1 = PasswordManager.hash_password(password)
        hash2, salt2 = PasswordManager.hash_password(password)
        
        # 不同的盐值应该产生不同的哈希
        self.assertNotEqual(hash1, hash2)
        self.assertNotEqual(salt1, salt2)
        
        # 使用相同盐值应该产生相同哈希
        hash3, _ = PasswordManager.hash_password(password, salt1)
        self.assertEqual(hash1, hash3)
    
    def test_verify_password(self):
        """
        测试密码验证
        """
        password = "TestPassword123!"
        password_hash, salt = PasswordManager.hash_password(password)
        
        # 正确密码
        self.assertTrue(PasswordManager.verify_password(password, password_hash, salt))
        
        # 错误密码
        self.assertFalse(PasswordManager.verify_password("WrongPassword", password_hash, salt))
    
    def test_generate_secure_password(self):
        """
        测试安全密码生成
        """
        password = PasswordManager.generate_secure_password(12)
        
        # 检查长度
        self.assertEqual(len(password), 12)
        
        # 检查包含各种字符类型
        self.assertTrue(any(c.islower() for c in password))
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.isdigit() for c in password))
        self.assertTrue(any(c in "@$!%*?&" for c in password))


class TestDataEncryption(unittest.TestCase):
    """
    数据加密测试
    """
    
    def setUp(self):
        """
        设置测试环境
        """
        try:
            self.encryption = DataEncryption()
            self.crypto_available = True
        except Exception:
            self.crypto_available = False
            self.skipTest("加密功能不可用")
    
    def test_encrypt_decrypt_string(self):
        """
        测试字符串加密解密
        """
        if not self.crypto_available:
            return
        
        original_data = "这是一个测试字符串"
        
        # 加密
        encrypted_data = self.encryption.encrypt(original_data)
        self.assertNotEqual(original_data.encode(), encrypted_data)
        
        # 解密
        decrypted_data = self.encryption.decrypt(encrypted_data)
        self.assertEqual(original_data.encode(), decrypted_data)
    
    def test_encrypt_decrypt_to_string(self):
        """
        测试字符串格式的加密解密
        """
        if not self.crypto_available:
            return
        
        original_data = "测试数据"
        
        # 加密为字符串
        encrypted_string = self.encryption.encrypt_to_string(original_data)
        self.assertIsInstance(encrypted_string, str)
        
        # 从字符串解密
        decrypted_data = self.encryption.decrypt_from_string(encrypted_string)
        self.assertEqual(original_data, decrypted_data)
    
    def test_key_derivation(self):
        """
        测试密钥派生
        """
        if not self.crypto_available:
            return
        
        password = "TestPassword123!"
        key1, salt1 = DataEncryption.derive_key_from_password(password)
        key2, salt2 = DataEncryption.derive_key_from_password(password)
        
        # 不同的盐值应该产生不同的密钥
        self.assertNotEqual(key1, key2)
        self.assertNotEqual(salt1, salt2)
        
        # 使用相同盐值应该产生相同密钥
        key3, _ = DataEncryption.derive_key_from_password(password, salt1)
        self.assertEqual(key1, key3)


class TestUser(unittest.TestCase):
    """
    用户类测试
    """
    
    def test_user_creation(self):
        """
        测试用户创建
        """
        user = User("testuser", "test@example.com")
        
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertTrue(user.is_active)
        self.assertEqual(user.failed_login_attempts, 0)
        self.assertIsNone(user.locked_until)
    
    def test_password_operations(self):
        """
        测试密码操作
        """
        user = User("testuser", "test@example.com")
        password = "TestPassword123!"
        
        # 设置密码
        user.set_password(password)
        self.assertIsNotNone(user.password_hash)
        self.assertIsNotNone(user.salt)
        
        # 验证密码
        self.assertTrue(user.verify_password(password))
        self.assertFalse(user.verify_password("WrongPassword"))
    
    def test_role_management(self):
        """
        测试角色管理
        """
        user = User("testuser", "test@example.com")
        
        # 添加角色
        user.add_role("admin")
        self.assertTrue(user.has_role("admin"))
        
        # 移除角色
        user.remove_role("admin")
        self.assertFalse(user.has_role("admin"))
    
    def test_permission_management(self):
        """
        测试权限管理
        """
        user = User("testuser", "test@example.com")
        
        # 添加权限
        user.add_permission("read_data")
        self.assertTrue(user.has_permission("read_data"))
        
        # 移除权限
        user.remove_permission("read_data")
        self.assertFalse(user.has_permission("read_data"))
    
    def test_account_locking(self):
        """
        测试账户锁定
        """
        user = User("testuser", "test@example.com")
        
        # 锁定账户
        user.lock_account(30)  # 30分钟
        self.assertTrue(user.is_locked())
        
        # 解锁账户
        user.unlock_account()
        self.assertFalse(user.is_locked())
        self.assertEqual(user.failed_login_attempts, 0)


class TestUserManager(unittest.TestCase):
    """
    用户管理器测试
    """
    
    def setUp(self):
        """
        设置测试环境
        """
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.temp_dir, "test_users.json")
        self.user_manager = UserManager(self.storage_path)
    
    def tearDown(self):
        """
        清理测试环境
        """
        shutil.rmtree(self.temp_dir)
    
    def test_create_user(self):
        """
        测试创建用户
        """
        user = self.user_manager.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123!",
            roles=["user"]
        )
        
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertIn("user", user.roles)
        
        # 检查用户是否已保存
        self.assertIn("testuser", self.user_manager.users)
    
    def test_duplicate_user_creation(self):
        """
        测试重复用户创建
        """
        self.user_manager.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123!"
        )
        
        # 尝试创建同名用户
        with self.assertRaises(SecurityError):
            self.user_manager.create_user(
                username="testuser",
                email="another@example.com",
                password="TestPassword123!"
            )
        
        # 尝试使用相同邮箱
        with self.assertRaises(SecurityError):
            self.user_manager.create_user(
                username="anotheruser",
                email="test@example.com",
                password="TestPassword123!"
            )
    
    def test_authenticate_user(self):
        """
        测试用户认证
        """
        password = "TestPassword123!"
        self.user_manager.create_user(
            username="testuser",
            email="test@example.com",
            password=password
        )
        
        # 正确认证
        user = self.user_manager.authenticate_user("testuser", password)
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "testuser")
        
        # 错误密码
        user = self.user_manager.authenticate_user("testuser", "WrongPassword")
        self.assertIsNone(user)
        
        # 不存在的用户
        user = self.user_manager.authenticate_user("nonexistent", password)
        self.assertIsNone(user)
    
    def test_user_persistence(self):
        """
        测试用户数据持久化
        """
        # 创建用户
        self.user_manager.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123!",
            roles=["admin"]
        )
        
        # 创建新的用户管理器实例
        new_manager = UserManager(self.storage_path)
        
        # 检查用户是否被正确加载
        self.assertIn("testuser", new_manager.users)
        user = new_manager.get_user("testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertIn("admin", user.roles)


class TestSecurityAudit(unittest.TestCase):
    """
    安全审计测试
    """
    
    def setUp(self):
        """
        设置测试环境
        """
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "test_audit.log")
        
        config = {
            'log_file': self.log_file,
            'enable_monitoring': False  # 禁用监控以避免线程问题
        }
        self.audit_manager = SecurityAuditManager(config)
    
    def tearDown(self):
        """
        清理测试环境
        """
        self.audit_manager.shutdown()
        shutil.rmtree(self.temp_dir)
    
    def test_log_user_login(self):
        """
        测试用户登录日志
        """
        # 成功登录
        self.audit_manager.log_user_login(
            user_id="testuser",
            ip_address="192.168.1.1",
            success=True
        )
        
        # 失败登录
        self.audit_manager.log_user_login(
            user_id="testuser",
            ip_address="192.168.1.1",
            success=False
        )
        
        # 检查事件是否被记录
        recent_events = self.audit_manager.audit_logger.get_recent_events(10)
        self.assertEqual(len(recent_events), 2)
        
        success_event = recent_events[0]
        failed_event = recent_events[1]
        
        self.assertEqual(success_event.event_type, SecurityEventType.USER_LOGIN)
        self.assertEqual(failed_event.event_type, SecurityEventType.LOGIN_FAILED)
    
    def test_log_data_access(self):
        """
        测试数据访问日志
        """
        self.audit_manager.log_data_access(
            user_id="testuser",
            resource="/data/test.csv",
            action="read",
            result="success",
            ip_address="192.168.1.1"
        )
        
        recent_events = self.audit_manager.audit_logger.get_recent_events(1)
        self.assertEqual(len(recent_events), 1)
        
        event = recent_events[0]
        self.assertEqual(event.event_type, SecurityEventType.DATA_READ)
        self.assertEqual(event.resource, "/data/test.csv")
        self.assertEqual(event.action, "read")
    
    def test_audit_report(self):
        """
        测试审计报告生成
        """
        # 记录一些事件
        self.audit_manager.log_user_login("user1", "192.168.1.1", True)
        self.audit_manager.log_user_login("user2", "192.168.1.2", False)
        self.audit_manager.log_data_access("user1", "/data/test.csv", "read")
        
        # 生成报告
        report = self.audit_manager.get_audit_report()
        
        self.assertIn('summary', report)
        self.assertIn('user_activity', report)
        self.assertIn('security_statistics', report)
        
        # 检查统计数据
        summary = report['summary']
        self.assertEqual(summary['total_events'], 3)
        self.assertEqual(summary['unique_users'], 2)


class TestSecurityConfig(unittest.TestCase):
    """
    安全配置测试
    """
    
    def test_default_config(self):
        """
        测试默认配置
        """
        config = SecurityConfig()
        
        # 检查基本配置项
        self.assertIsNotNone(config.get('user_management'))
        self.assertIsNotNone(config.get('session_management'))
        self.assertIsNotNone(config.get('jwt'))
        self.assertIsNotNone(config.get('encryption'))
    
    def test_config_validation(self):
        """
        测试配置验证
        """
        config = SecurityConfig()
        
        # 生成密钥
        config.generate_secrets()
        
        # 验证配置
        errors = config.validate_config()
        self.assertEqual(len(errors), 0)
    
    def test_config_persistence(self):
        """
        测试配置持久化
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_file = f.name
        
        try:
            # 创建配置并保存
            config1 = SecurityConfig()
            config1.set('test_key', 'test_value')
            config1.save_to_file(config_file)
            
            # 加载配置
            config2 = SecurityConfig(config_file)
            self.assertEqual(config2.get('test_key'), 'test_value')
            
        finally:
            os.unlink(config_file)


class TestSecurityIntegration(unittest.TestCase):
    """
    安全模块集成测试
    """
    
    def setUp(self):
        """
        设置测试环境
        """
        self.temp_dir = tempfile.mkdtemp()
        
        # 创建测试配置
        self.config = {
            'user_storage_path': os.path.join(self.temp_dir, 'users.json'),
            'log_file': os.path.join(self.temp_dir, 'audit.log'),
            'enable_monitoring': False
        }
    
    def tearDown(self):
        """
        清理测试环境
        """
        shutil.rmtree(self.temp_dir)
    
    def test_complete_user_workflow(self):
        """
        测试完整的用户工作流程
        """
        # 设置安全系统
        security_manager = SecurityManager(self.config)
        
        # 创建用户
        user = security_manager.user_manager.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123!",
            roles=["user"]
        )
        
        # 用户认证
        authenticated_user = security_manager.user_manager.authenticate_user(
            "testuser", "TestPassword123!"
        )
        self.assertIsNotNone(authenticated_user)
        
        # 创建会话
        session_id = security_manager.session_manager.create_session(user)
        self.assertIsNotNone(session_id)
        
        # 获取会话
        session = security_manager.session_manager.get_session(session_id)
        self.assertIsNotNone(session)
        self.assertEqual(session['user_id'], "testuser")
        
        # 销毁会话
        result = security_manager.session_manager.destroy_session(session_id)
        self.assertTrue(result)
        
        # 验证会话已销毁
        session = security_manager.session_manager.get_session(session_id)
        self.assertIsNone(session)
    
    def test_security_status(self):
        """
        测试安全状态检查
        """
        security_manager = SecurityManager(self.config)
        status = security_manager.get_security_status()
        
        self.assertIn('total_users', status)
        self.assertIn('active_sessions', status)
        self.assertIn('encryption_enabled', status)
        self.assertIn('jwt_enabled', status)


def run_security_tests():
    """
    运行所有安全测试
    """
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestInputValidator,
        TestPasswordManager,
        TestDataEncryption,
        TestUser,
        TestUserManager,
        TestSecurityAudit,
        TestSecurityConfig,
        TestSecurityIntegration
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    print("开始运行安全模块测试...")
    print("=" * 50)
    
    success = run_security_tests()
    
    print("=" * 50)
    if success:
        print("✅ 所有安全测试通过！")
    else:
        print("❌ 部分安全测试失败！")
        sys.exit(1)