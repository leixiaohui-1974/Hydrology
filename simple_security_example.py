#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的安全模块演示 - Simplified Security Example

不依赖外部库的安全功能演示

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_security_features():
    """
    测试基本安全功能（不依赖外部库）
    """
    print("=== 基本安全功能测试 ===")
    
    try:
        # 测试输入验证
        print("\n1. 测试输入验证:")
        from common.security import InputValidator
        
        # 字符串验证
        try:
            InputValidator.validate_string("hello", min_length=3, max_length=10)
            print("  ✅ 字符串验证通过")
        except Exception as e:
            print(f"  ❌ 字符串验证失败: {e}")
        
        # 邮箱验证
        try:
            InputValidator.validate_email("test@example.com")
            print("  ✅ 邮箱验证通过")
        except Exception as e:
            print(f"  ❌ 邮箱验证失败: {e}")
        
        # 密码验证
        try:
            InputValidator.validate_password("TestPass123!")
            print("  ✅ 密码验证通过")
        except Exception as e:
            print(f"  ❌ 密码验证失败: {e}")
        
        # 输入清理
        try:
            malicious = "<script>alert('xss')</script>Hello"
            clean = InputValidator.sanitize_input(malicious)
            print(f"  ✅ 输入清理: '{malicious}' -> '{clean}'")
        except Exception as e:
            print(f"  ❌ 输入清理失败: {e}")
        
    except ImportError as e:
        print(f"  ⚠️ 输入验证模块导入失败: {e}")
    
    try:
        # 测试密码管理
        print("\n2. 测试密码管理:")
        from common.security import PasswordManager
        
        # 生成安全密码
        password = PasswordManager.generate_secure_password(12)
        print(f"  ✅ 生成安全密码: {password}")
        
        # 密码哈希和验证
        test_password = "TestPassword123!"
        hash_result, salt = PasswordManager.hash_password(test_password)
        print(f"  ✅ 密码哈希成功")
        
        # 验证密码
        is_valid = PasswordManager.verify_password(test_password, hash_result, salt)
        print(f"  ✅ 密码验证: {'通过' if is_valid else '失败'}")
        
    except ImportError as e:
        print(f"  ⚠️ 密码管理模块导入失败: {e}")
    
    try:
        # 测试用户管理
        print("\n3. 测试用户管理:")
        from common.security import User, UserManager
        
        # 创建临时用户存储
        temp_storage = "temp_test_users.json"
        
        try:
            user_manager = UserManager(temp_storage)
            
            # 创建用户
            user = user_manager.create_user(
                username="testuser",
                email="test@example.com",
                password="TestPass123!",
                roles=["user"]
            )
            print(f"  ✅ 创建用户: {user.username}")
            
            # 用户认证
            auth_user = user_manager.authenticate_user("testuser", "TestPass123!")
            if auth_user:
                print(f"  ✅ 用户认证成功")
            else:
                print(f"  ❌ 用户认证失败")
            
            # 角色管理
            user.add_role("admin")
            print(f"  ✅ 添加角色: {user.roles}")
            
            # 权限管理
            user.add_permission("read_data")
            print(f"  ✅ 添加权限: {user.permissions}")
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_storage):
                os.remove(temp_storage)
        
    except ImportError as e:
        print(f"  ⚠️ 用户管理模块导入失败: {e}")
    
    try:
        # 测试会话管理
        print("\n4. 测试会话管理:")
        from common.security import SessionManager, User
        
        session_manager = SessionManager()
        test_user = User("sessiontest", "session@example.com")
        
        # 创建会话
        session_id = session_manager.create_session(test_user)
        print(f"  ✅ 创建会话: {session_id[:8]}...")
        
        # 验证会话
        is_valid = session_manager.is_session_valid(session_id)
        print(f"  ✅ 会话验证: {'有效' if is_valid else '无效'}")
        
        # 销毁会话
        destroyed = session_manager.destroy_session(session_id)
        print(f"  ✅ 销毁会话: {'成功' if destroyed else '失败'}")
        
    except ImportError as e:
        print(f"  ⚠️ 会话管理模块导入失败: {e}")
    
    try:
        # 测试安全审计
        print("\n5. 测试安全审计:")
        from common.security_audit import SecurityAuditManager
        
        temp_log = "temp_test_audit.log"
        
        try:
            config = {
                'log_file': temp_log,
                'enable_monitoring': False
            }
            audit_manager = SecurityAuditManager(config)
            
            # 记录登录事件
            audit_manager.log_user_login("testuser", "192.168.1.1", True)
            print(f"  ✅ 记录登录事件")
            
            # 记录数据访问
            audit_manager.log_data_access(
                "testuser", "/data/test.csv", 
                "read", "success", "192.168.1.1"
            )
            print(f"  ✅ 记录数据访问")
            
            # 获取最近事件
            recent_events = audit_manager.audit_logger.get_recent_events(5)
            print(f"  ✅ 获取最近事件: {len(recent_events)} 个")
            
            # 生成报告
            report = audit_manager.get_audit_report()
            print(f"  ✅ 生成审计报告: {report['summary']['total_events']} 个事件")
            
        finally:
            if 'audit_manager' in locals():
                audit_manager.shutdown()
            if os.path.exists(temp_log):
                os.remove(temp_log)
        
    except ImportError as e:
        print(f"  ⚠️ 安全审计模块导入失败: {e}")
    
    # 测试数据加密（可选）
    try:
        print("\n6. 测试数据加密:")
        from common.security import DataEncryption
        
        encryption = DataEncryption()
        test_data = "这是测试数据"
        
        # 加密
        encrypted = encryption.encrypt_to_string(test_data)
        print(f"  ✅ 数据加密成功")
        
        # 解密
        decrypted = encryption.decrypt_from_string(encrypted)
        print(f"  ✅ 数据解密: {'成功' if test_data == decrypted else '失败'}")
        
    except ImportError as e:
        print(f"  ⚠️ 数据加密模块导入失败: {e}")
    except Exception as e:
        print(f"  ⚠️ 数据加密功能不可用: {e}")
        print(f"  提示: 可安装 cryptography 库以启用加密功能")


def test_security_integration():
    """
    测试安全模块集成
    """
    print("\n=== 安全模块集成测试 ===")
    
    try:
        from common.security import SecurityManager
        
        # 创建临时文件
        temp_users = "temp_integration_users.json"
        temp_audit = "temp_integration_audit.log"
        
        try:
            config = {
                'user_storage_path': temp_users,
                'log_file': temp_audit,
                'enable_monitoring': False
            }
            
            # 创建安全管理器
            security_manager = SecurityManager(config)
            print("  ✅ 创建安全管理器")
            
            # 创建用户
            user = security_manager.user_manager.create_user(
                username="integrationtest",
                email="integration@example.com",
                password="IntegrationPass123!",
                roles=["user"]
            )
            print(f"  ✅ 创建用户: {user.username}")
            
            # 用户认证
            auth_user = security_manager.user_manager.authenticate_user(
                "integrationtest", "IntegrationPass123!"
            )
            print(f"  ✅ 用户认证: {'成功' if auth_user else '失败'}")
            
            # 创建会话
            if auth_user:
                session_id = security_manager.session_manager.create_session(
                    auth_user, ip_address="192.168.1.100"
                )
                print(f"  ✅ 创建会话: {session_id[:8]}...")
                
                # 记录安全事件
                security_manager.audit_manager.log_user_login(
                    auth_user.username, "192.168.1.100", True
                )
                print(f"  ✅ 记录安全事件")
                
                # 获取安全状态
                status = security_manager.get_security_status()
                print(f"  ✅ 安全状态: {status['total_users']} 用户, {status['active_sessions']} 会话")
                
                # 销毁会话
                security_manager.session_manager.destroy_session(session_id)
                print(f"  ✅ 销毁会话")
        
        finally:
            # 清理临时文件
            for temp_file in [temp_users, temp_audit]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        
    except ImportError as e:
        print(f"  ⚠️ 安全管理器导入失败: {e}")
    except Exception as e:
        print(f"  ❌ 集成测试失败: {e}")


def main():
    """
    主函数
    """
    print("Hydrology Framework 安全模块简化测试")
    print("=" * 50)
    
    try:
        # 运行基本功能测试
        test_basic_security_features()
        
        # 运行集成测试
        test_security_integration()
        
        print("\n" + "=" * 50)
        print("✅ 安全模块测试完成！")
        print("\n安全功能状态:")
        
        # 检查各模块可用性
        modules_status = {
            'common.security': False,
            'common.security_audit': False,
            'config.security_config': False
        }
        
        for module_name in modules_status.keys():
            try:
                __import__(module_name)
                modules_status[module_name] = True
                print(f"  ✅ {module_name}: 可用")
            except ImportError:
                print(f"  ❌ {module_name}: 不可用")
        
        # 检查可选依赖
        print("\n可选依赖状态:")
        optional_deps = {
            'cryptography': '数据加密功能',
            'bcrypt': '密码哈希增强',
            'PyJWT': 'JWT令牌支持',
            'yaml': '配置文件支持'
        }
        
        for dep_name, description in optional_deps.items():
            try:
                if dep_name == 'PyJWT':
                    import jwt
                else:
                    __import__(dep_name)
                print(f"  ✅ {dep_name}: 已安装 - {description}")
            except ImportError:
                print(f"  ⚠️ {dep_name}: 未安装 - {description}")
        
        print("\n提示: 安装可选依赖可以获得完整的安全功能")
        print("安装命令: pip install cryptography bcrypt PyJWT pyyaml")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = main()
    if not success:
        sys.exit(1)