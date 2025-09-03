# -*- coding: utf-8 -*-
"""
错误处理模块

提供统一的错误处理机制，包括：
- 自定义异常类
- 错误日志记录
- 用户友好的错误信息
- 错误恢复建议
"""

import logging
import traceback
import sys
from typing import Optional, Dict, Any, List
from pathlib import Path
import json
from datetime import datetime


class HydrologyError(Exception):
    """水文建模框架基础异常类"""
    def __init__(self, message: str, error_code: str = None, suggestions: List[str] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "HYDRO_ERROR"
        self.suggestions = suggestions or []
        self.timestamp = datetime.now()

    def __str__(self):
        return f"[{self.error_code}] {self.message}"


class ConfigurationError(HydrologyError):
    """配置文件相关错误"""
    def __init__(self, message: str, config_path: str = None, suggestions: List[str] = None):
        super().__init__(message, "CONFIG_ERROR", suggestions)
        self.config_path = config_path


class DependencyError(HydrologyError):
    """依赖包相关错误"""
    def __init__(self, message: str, missing_packages: List[str] = None, suggestions: List[str] = None):
        super().__init__(message, "DEPENDENCY_ERROR", suggestions)
        self.missing_packages = missing_packages or []


class DataError(HydrologyError):
    """数据相关错误"""
    def __init__(self, message: str, data_path: str = None, suggestions: List[str] = None):
        super().__init__(message, "DATA_ERROR", suggestions)
        self.data_path = data_path


class ModelError(HydrologyError):
    """模型相关错误"""
    def __init__(self, message: str, model_name: str = None, suggestions: List[str] = None):
        super().__init__(message, "MODEL_ERROR", suggestions)
        self.model_name = model_name


class SimulationError(HydrologyError):
    """仿真运行错误"""
    def __init__(self, message: str, step: int = None, suggestions: List[str] = None):
        super().__init__(message, "SIMULATION_ERROR", suggestions)
        self.step = step


class ErrorHandler:
    """统一错误处理器"""
    
    def __init__(self, log_file: str = None, log_level: int = logging.ERROR):
        self.logger = self._setup_logger(log_file, log_level)
        self.error_suggestions = self._load_error_suggestions()
    
    def _setup_logger(self, log_file: str, log_level: int) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger('hydrology_error_handler')
        logger.setLevel(log_level)
        
        # 避免重复添加处理器
        if logger.handlers:
            return logger
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 文件处理器
        if log_file:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    def _load_error_suggestions(self) -> Dict[str, List[str]]:
        """加载错误建议数据库"""
        return {
            "CONFIG_ERROR": [
                "检查配置文件格式是否正确（YAML/JSON）",
                "验证所有必需的配置项是否存在",
                "确认文件路径是否正确",
                "参考示例配置文件"
            ],
            "DEPENDENCY_ERROR": [
                "运行 'python check_dependencies.py' 检查缺失的依赖",
                "使用 'pip install -r requirements.txt' 安装依赖",
                "检查Python版本是否兼容（推荐3.8+）",
                "参考INSTALL_GUIDE.md获取详细安装指南"
            ],
            "DATA_ERROR": [
                "检查数据文件是否存在",
                "验证数据格式是否正确",
                "确认数据文件权限",
                "检查数据文件编码格式"
            ],
            "MODEL_ERROR": [
                "检查模型参数是否在有效范围内",
                "验证模型配置是否完整",
                "确认模型类型是否支持",
                "查看模型文档了解参数要求"
            ],
            "SIMULATION_ERROR": [
                "检查仿真参数设置",
                "验证时间步长是否合理",
                "确认边界条件是否正确",
                "检查数值稳定性条件"
            ]
        }
    
    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> None:
        """处理错误并记录日志"""
        context = context or {}
        
        # 记录错误信息
        error_info = {
            "error_type": type(error).__name__,
            "message": str(error),
            "context": context,
            "traceback": traceback.format_exc()
        }
        
        self.logger.error(f"错误发生: {json.dumps(error_info, ensure_ascii=False, indent=2)}")
        
        # 如果是自定义错误，显示建议
        if isinstance(error, HydrologyError):
            self._display_error_with_suggestions(error)
        else:
            self._display_generic_error(error)
    
    def _display_error_with_suggestions(self, error: HydrologyError) -> None:
        """显示带建议的错误信息"""
        print(f"\n❌ 错误: {error}")
        print(f"⏰ 时间: {error.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 显示具体建议
        suggestions = error.suggestions or self.error_suggestions.get(error.error_code, [])
        if suggestions:
            print("\n💡 建议解决方案:")
            for i, suggestion in enumerate(suggestions, 1):
                print(f"   {i}. {suggestion}")
        
        # 显示额外信息
        if hasattr(error, 'config_path') and error.config_path:
            print(f"\n📁 配置文件: {error.config_path}")
        if hasattr(error, 'missing_packages') and error.missing_packages:
            print(f"\n📦 缺失包: {', '.join(error.missing_packages)}")
        if hasattr(error, 'data_path') and error.data_path:
            print(f"\n📊 数据文件: {error.data_path}")
        if hasattr(error, 'model_name') and error.model_name:
            print(f"\n🔧 模型名称: {error.model_name}")
        if hasattr(error, 'step') and error.step is not None:
            print(f"\n⏱️ 仿真步骤: {error.step}")
    
    def _display_generic_error(self, error: Exception) -> None:
        """显示通用错误信息"""
        print(f"\n❌ 未预期的错误: {type(error).__name__}: {error}")
        print("\n💡 通用建议:")
        print("   1. 检查错误堆栈信息定位问题")
        print("   2. 确认所有依赖已正确安装")
        print("   3. 验证输入数据和配置文件")
        print("   4. 查看日志文件获取详细信息")
        print("   5. 如问题持续，请提交Issue到GitHub仓库")


def safe_import(module_name: str, package_name: str = None) -> Any:
    """安全导入模块，提供友好的错误信息"""
    try:
        if package_name:
            module = __import__(module_name, fromlist=[package_name])
            return getattr(module, package_name)
        else:
            return __import__(module_name)
    except ImportError as e:
        package_name = package_name or module_name
        suggestions = [
            f"安装缺失的包: pip install {package_name}",
            "检查包名是否正确",
            "确认Python环境配置",
            "参考requirements.txt文件"
        ]
        raise DependencyError(
            f"无法导入模块 '{module_name}': {str(e)}",
            missing_packages=[package_name],
            suggestions=suggestions
        )


def safe_file_operation(operation, file_path: str, **kwargs):
    """安全文件操作包装器"""
    try:
        return operation(file_path, **kwargs)
    except FileNotFoundError:
        suggestions = [
            "检查文件路径是否正确",
            "确认文件是否存在",
            "检查文件权限",
            "使用绝对路径"
        ]
        raise DataError(
            f"文件未找到: {file_path}",
            data_path=file_path,
            suggestions=suggestions
        )
    except PermissionError:
        suggestions = [
            "检查文件访问权限",
            "以管理员身份运行",
            "确认文件未被其他程序占用"
        ]
        raise DataError(
            f"文件访问权限不足: {file_path}",
            data_path=file_path,
            suggestions=suggestions
        )
    except Exception as e:
        suggestions = [
            "检查文件格式是否正确",
            "验证文件编码",
            "确认文件完整性"
        ]
        raise DataError(
            f"文件操作失败: {file_path}, 错误: {str(e)}",
            data_path=file_path,
            suggestions=suggestions
        )


def validate_config(config: Dict[str, Any], required_keys: List[str], config_path: str = None) -> None:
    """验证配置文件完整性"""
    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        suggestions = [
            f"添加缺失的配置项: {', '.join(missing_keys)}",
            "参考示例配置文件",
            "检查配置文件格式",
            "验证YAML/JSON语法"
        ]
        raise ConfigurationError(
            f"配置文件缺少必需项: {', '.join(missing_keys)}",
            config_path=config_path,
            suggestions=suggestions
        )


def create_error_report(error: Exception, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """创建详细的错误报告"""
    return {
        "timestamp": datetime.now().isoformat(),
        "error_type": type(error).__name__,
        "message": str(error),
        "context": context or {},
        "traceback": traceback.format_exc(),
        "python_version": sys.version,
        "platform": sys.platform
    }


# 全局错误处理器实例
default_error_handler = ErrorHandler()


def setup_global_error_handler(log_file: str = None, log_level: int = logging.ERROR):
    """设置全局错误处理器"""
    global default_error_handler
    default_error_handler = ErrorHandler(log_file, log_level)
    return default_error_handler