#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全模块使用示例 - Hydrology Framework Security Example

展示如何使用Hydrology框架的安全功能，包括用户管理、数据加密、
输入验证、会话管理和安全审计等。

作者: Hydrology Framework Team
版本: 1.0.0
日期: 2024
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from common.security import (
        InputValidator, DataEncryption, PasswordManager, User, UserManager,
        SessionManager, SecurityManager, setup_security, get_security_manager
    )
    from common.security_audit import SecurityAuditManager
    from config.security_config import SecurityConfig
    from common.error_handler import SecurityError, ValidationError
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保所有依赖模块都已正确安装")
    sys.exit(1)


def demo_input_validation():
    """
    演示输入验证功能
    """
    print("\n=== 输入验证演示 ===")
    
    # 字符串验证
    print("\n1. 字符串验证:")
    test_strings = ["hello", "hi", "this is a very long string that exceeds limit"]
    
    for test_str in test_strings:
        try:
            InputValidator.validate_string(test_str, min_length=3, max_length=20)
            print(f"  ✅ '{test_str}' - 验证通过")
        except ValidationError as e:
            print(f"  ❌ '{test_str}' - 验证失败: {e}")
    
    # 邮箱验证
    print("\n2. 邮箱验证:")
    test_emails = ["user@example.com", "invalid-email", "test@domain.co.uk"]
    
    for email in test_emails:
        try:
            InputValidator.validate_email(email)
            print(f"  ✅ '{email}' - 验证通过")
        except ValidationError as e:
            print(f"  ❌ '{email}' - 验证失败: {e}")
    
    # 密码验证
    print("\n3. 密码验证:")
    test_passwords = ["Password123!", "weak", "NoSpecialChar123"]
    
    for password in test_passwords:
        try:
            InputValidator.validate_password(password)
            print(f"  ✅ 密码验证通过")
        except ValidationError as e:
            print(f"  ❌ 密码验证失败: {e}")
    
    # 输入清理
    print("\n4. 输入清理:")
    malicious_input = "<script>alert('XSS')</script>Hello World"
    sanitized = InputValidator.sanitize_input(malicious_input)
    print(f"  原始输入: {malicious_input}")
    print(f"  清理后: {sanitized}")


def demo_password_management():
    """
    演示密码管理功能
    """
    print("\n=== 密码管理演示 ===")
    
    # 生成安全密码
    print("\n1. 生成安全密码:")
    for length in [8, 12, 16]:
        password = PasswordManager.generate_secure_password(length)
        print(f"  {length}位密码: {password}")
    
    # 密码哈希和验证
    print("\n2. 密码哈希和验证:")
    original_password = "MySecurePassword123!"
    
    # 哈希密码
    password_hash, salt = PasswordManager.hash_password(original_password)
    print(f"  原始密码: {original_password}")
    print(f"  密码哈希: {password_hash[:50]}...")
    print(f"  盐值: {salt[:20]}...")
    
    # 验证密码
    is_valid = PasswordManager.verify_password(original_password, password_hash, salt)
    print(f"  密码验证结果: {'✅ 通过' if is_valid else '❌ 失败'}")
    
    # 验证错误密码
    is_valid = PasswordManager.verify_password("WrongPassword", password_hash, salt)
    print(f"  错误密码验证: {'✅ 通过' if is_valid else '❌ 失败'}")


def demo_data_encryption():
    """
    演示数据加密功能
    """
    print("\n=== 数据加密演示 ===")
    
    try:
        encryption = DataEncryption()
        
        # 字符串加密
        print("\n1. 字符串加密:")
        original_data = "这是需要加密的敏感数据"
        print(f"  原始数据: {original_data}")
        
        # 加密为字符串格式
        encrypted_string = encryption.encrypt_to_string(original_data)
        print(f"  加密数据: {encrypted_string[:50]}...")
        
        # 解密
        decrypted_data = encryption.decrypt_from_string(encrypted_string)
        print(f"  解密数据: {decrypted_data}")
        print(f"  数据完整性: {'✅ 正确' if original_data == decrypted_data else '❌ 错误'}")
        
        # 文件加密
        print("\n2. 文件加密:")
        test_file = "temp_test_file.txt"
        test_content = "这是测试文件的内容\n包含多行数据\n用于测试文件加密功能"
        
        # 创建测试文件
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        # 加密文件
        encrypted_file = test_file + ".enc"
        encryption.encrypt_file(test_file, encrypted_file)
        print(f"  原始文件: {test_file}")
        print(f"  加密文件: {encrypted_file}")
        
        # 解密文件
        decrypted_file = "decrypted_" + test_file
        encryption.decrypt_file(encrypted_file, decrypted_file)
        
        # 验证文件内容
        with open(decrypted_file, 'r', encoding='utf-8') as f:
            decrypted_content = f.read()
        
        print(f"  文件加密解密: {'✅ 成功' if test_content == decrypted_content else '❌ 失败'}")
        
        # 清理临时文件
        for file in [test_file, encrypted_file, decrypted_file]:
            if os.path.exists(file):
                os.remove(file)
        
    except Exception as e:
        print(f"  ⚠️ 加密功能不可用: {e}")
        print("  请安装 cryptography 库: pip install cryptography")


def demo_user_management():
    """
    演示用户管理功能
    """
    print("\n=== 用户管理演示 ===")
    
    # 创建临时用户存储
    temp_storage = "temp_users.json"
    
    try:
        user_manager = UserManager(temp_storage)
        
        # 创建用户
        print("\n1. 创建用户:")
        users_data = [
            {"username": "admin", "email": "admin@example.com", "password": "AdminPass123!", "roles": ["admin", "user"]},
            {"username": "analyst", "email": "analyst@example.com", "password": "AnalystPass123!", "roles": ["analyst", "user"]},
            {"username": "viewer", "email": "viewer@example.com", "password": "ViewerPass123!", "roles": ["viewer"]}
        ]
        
        for user_data in users_data:
            try:
                user = user_manager.create_user(**user_data)
                print(f"  ✅ 创建用户: {user.username} ({user.email})")
            except SecurityError as e:
                print(f"  ❌ 创建用户失败: {e}")
        
        # 用户认证
        print("\n2. 用户认证:")
        auth_tests = [
            ("admin", "AdminPass123!", True),
            ("analyst", "WrongPassword", False),
            ("nonexistent", "AnyPassword", False)
        ]
        
        for username, password, expected in auth_tests:
            user = user_manager.authenticate_user(username, password)
            success = user is not None
            status = "✅ 成功" if success == expected else "❌ 失败"
            print(f"  {username}: {status}")
        
        # 角色和权限管理
        print("\n3. 角色和权限管理:")
        admin_user = user_manager.get_user("admin")
        if admin_user:
            print(f"  管理员角色: {admin_user.roles}")
            
            # 添加权限
            admin_user.add_permission("system_config")
            admin_user.add_permission("user_management")
            print(f"  管理员权限: {admin_user.permissions}")
            
            # 检查权限
            has_config = admin_user.has_permission("system_config")
            has_delete = admin_user.has_permission("delete_data")
            print(f"  系统配置权限: {'✅ 有' if has_config else '❌ 无'}")
            print(f"  数据删除权限: {'✅ 有' if has_delete else '❌ 无'}")
        
        # 用户状态管理
        print("\n4. 用户状态管理:")
        test_user = user_manager.get_user("viewer")
        if test_user:
            print(f"  用户状态: {'活跃' if test_user.is_active else '禁用'}")
            print(f"  账户锁定: {'是' if test_user.is_locked() else '否'}")
            
            # 锁定账户
            test_user.lock_account(30)  # 锁定30分钟
            print(f"  锁定后状态: {'锁定' if test_user.is_locked() else '正常'}")
            
            # 解锁账户
            test_user.unlock_account()
            print(f"  解锁后状态: {'锁定' if test_user.is_locked() else '正常'}")
        
    finally:
        # 清理临时文件
        if os.path.exists(temp_storage):
            os.remove(temp_storage)


def demo_session_management():
    """
    演示会话管理功能
    """
    print("\n=== 会话管理演示 ===")
    
    session_manager = SessionManager()
    
    # 创建测试用户
    test_user = User("testuser", "test@example.com")
    test_user.add_role("user")
    
    # 创建会话
    print("\n1. 创建会话:")
    session_id = session_manager.create_session(test_user)
    print(f"  会话ID: {session_id}")
    
    # 获取会话信息
    print("\n2. 会话信息:")
    session = session_manager.get_session(session_id)
    if session:
        print(f"  用户ID: {session['user_id']}")
        print(f"  创建时间: {session['created_at']}")
        print(f"  最后访问: {session['last_accessed']}")
        print(f"  IP地址: {session.get('ip_address', 'N/A')}")
    
    # 更新会话
    print("\n3. 更新会话:")
    time.sleep(1)  # 等待1秒
    session_manager.update_session(session_id, ip_address="192.168.1.100")
    
    updated_session = session_manager.get_session(session_id)
    if updated_session:
        print(f"  更新后IP: {updated_session.get('ip_address')}")
        print(f"  最后访问时间已更新")
    
    # 会话验证
    print("\n4. 会话验证:")
    is_valid = session_manager.is_session_valid(session_id)
    print(f"  会话有效性: {'✅ 有效' if is_valid else '❌ 无效'}")
    
    # 获取活跃会话
    print("\n5. 活跃会话:")
    active_sessions = session_manager.get_active_sessions()
    print(f"  活跃会话数: {len(active_sessions)}")
    
    # 销毁会话
    print("\n6. 销毁会话:")
    destroyed = session_manager.destroy_session(session_id)
    print(f"  销毁结果: {'✅ 成功' if destroyed else '❌ 失败'}")
    
    # 验证会话已销毁
    session = session_manager.get_session(session_id)
    print(f"  会话状态: {'存在' if session else '已销毁'}")


def demo_security_audit():
    """
    演示安全审计功能
    """
    print("\n=== 安全审计演示 ===")
    
    # 创建临时审计日志
    temp_log = "temp_audit.log"
    
    try:
        config = {
            'log_file': temp_log,
            'enable_monitoring': False  # 禁用监控以简化演示
        }
        audit_manager = SecurityAuditManager(config)
        
        # 记录各种安全事件
        print("\n1. 记录安全事件:")
        
        # 用户登录事件
        audit_manager.log_user_login("admin", "192.168.1.100", success=True)
        audit_manager.log_user_login("hacker", "10.0.0.1", success=False)
        print("  ✅ 记录用户登录事件")
        
        # 数据访问事件
        audit_manager.log_data_access(
            user_id="admin",
            resource="/data/sensitive.csv",
            action="read",
            result="success",
            ip_address="192.168.1.100"
        )
        print("  ✅ 记录数据访问事件")
        
        # 权限变更事件
        audit_manager.log_permission_change(
            user_id="admin",
            target_user="analyst",
            permission="data_export",
            action="grant",
            ip_address="192.168.1.100"
        )
        print("  ✅ 记录权限变更事件")
        
        # 系统配置变更
        audit_manager.log_system_config_change(
            user_id="admin",
            config_key="max_login_attempts",
            old_value="3",
            new_value="5",
            ip_address="192.168.1.100"
        )
        print("  ✅ 记录系统配置变更")
        
        # 安全违规事件
        audit_manager.log_security_violation(
            user_id="hacker",
            violation_type="brute_force",
            description="连续失败登录尝试",
            ip_address="10.0.0.1"
        )
        print("  ✅ 记录安全违规事件")
        
        # 获取最近事件
        print("\n2. 最近安全事件:")
        recent_events = audit_manager.audit_logger.get_recent_events(5)
        for i, event in enumerate(recent_events, 1):
            print(f"  {i}. {event.timestamp.strftime('%H:%M:%S')} - {event.event_type.value} - {event.user_id}")
        
        # 生成审计报告
        print("\n3. 审计报告:")
        report = audit_manager.get_audit_report()
        
        summary = report['summary']
        print(f"  总事件数: {summary['total_events']}")
        print(f"  唯一用户: {summary['unique_users']}")
        print(f"  时间范围: {summary['time_range']['start']} 到 {summary['time_range']['end']}")
        
        # 用户活动统计
        user_activity = report['user_activity']
        print(f"\n  用户活动统计:")
        for user, count in user_activity.items():
            print(f"    {user}: {count} 次活动")
        
        # 安全统计
        security_stats = report['security_statistics']
        print(f"\n  安全统计:")
        print(f"    成功登录: {security_stats.get('successful_logins', 0)}")
        print(f"    失败登录: {security_stats.get('failed_logins', 0)}")
        print(f"    安全违规: {security_stats.get('security_violations', 0)}")
        
    finally:
        # 清理
        if 'audit_manager' in locals():
            audit_manager.shutdown()
        if os.path.exists(temp_log):
            os.remove(temp_log)


def demo_security_integration():
    """
    演示安全模块集成使用
    """
    print("\n=== 安全模块集成演示 ===")
    
    # 创建临时文件
    temp_users = "temp_users_integration.json"
    temp_audit = "temp_audit_integration.log"
    
    try:
        # 配置安全系统
        config = {
            'user_storage_path': temp_users,
            'log_file': temp_audit,
            'enable_monitoring': False
        }
        
        # 初始化安全管理器
        security_manager = SecurityManager(config)
        
        print("\n1. 完整用户工作流程:")
        
        # 创建用户
        user = security_manager.user_manager.create_user(
            username="demo_user",
            email="demo@example.com",
            password="DemoPass123!",
            roles=["user", "analyst"]
        )
        print(f"  ✅ 创建用户: {user.username}")
        
        # 用户认证
        auth_user = security_manager.user_manager.authenticate_user(
            "demo_user", "DemoPass123!"
        )
        if auth_user:
            print(f"  ✅ 用户认证成功")
            
            # 创建会话
            session_id = security_manager.session_manager.create_session(
                auth_user, ip_address="192.168.1.200"
            )
            print(f"  ✅ 创建会话: {session_id[:8]}...")
            
            # 记录登录事件
            security_manager.audit_manager.log_user_login(
                user_id=auth_user.username,
                ip_address="192.168.1.200",
                success=True
            )
            print(f"  ✅ 记录登录事件")
            
            # 模拟数据访问
            security_manager.audit_manager.log_data_access(
                user_id=auth_user.username,
                resource="/api/data/analysis",
                action="read",
                result="success",
                ip_address="192.168.1.200"
            )
            print(f"  ✅ 记录数据访问")
            
            # 会话验证
            is_valid = security_manager.session_manager.is_session_valid(session_id)
            print(f"  ✅ 会话验证: {'有效' if is_valid else '无效'}")
            
            # 销毁会话
            security_manager.session_manager.destroy_session(session_id)
            print(f"  ✅ 销毁会话")
        
        # 获取安全状态
        print("\n2. 安全系统状态:")
        status = security_manager.get_security_status()
        print(f"  总用户数: {status['total_users']}")
        print(f"  活跃会话: {status['active_sessions']}")
        print(f"  加密启用: {'是' if status['encryption_enabled'] else '否'}")
        print(f"  JWT启用: {'是' if status['jwt_enabled'] else '否'}")
        
        # 生成安全报告
        print("\n3. 安全报告摘要:")
        report = security_manager.audit_manager.get_audit_report()
        summary = report['summary']
        print(f"  审计事件: {summary['total_events']}")
        print(f"  活跃用户: {summary['unique_users']}")
        
    finally:
        # 清理临时文件
        for temp_file in [temp_users, temp_audit]:
            if os.path.exists(temp_file):
                os.remove(temp_file)


def main():
    """
    主函数 - 运行所有安全功能演示
    """
    print("Hydrology Framework 安全模块演示")
    print("=" * 50)
    
    try:
        # 运行各个演示
        demo_input_validation()
        demo_password_management()
        demo_data_encryption()
        demo_user_management()
        demo_session_management()
        demo_security_audit()
        demo_security_integration()
        
        print("\n" + "=" * 50)
        print("✅ 所有安全功能演示完成！")
        print("\n安全模块提供了以下功能:")
        print("• 输入验证和清理")
        print("• 密码管理和哈希")
        print("• 数据加密和解密")
        print("• 用户管理和认证")
        print("• 会话管理")
        print("• 安全审计和监控")
        print("• 权限和角色管理")
        print("\n请根据需要在您的应用中集成这些安全功能。")
        
    except Exception as e:
        print(f"\n❌ 演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == '__main__':
    success = main()
    if not success:
        sys.exit(1)