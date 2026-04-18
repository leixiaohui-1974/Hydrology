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
from functools import wraps
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from pathlib import Path
import json
from datetime import datetime


class HydrologyError(Exception):
    """水文建模框架基础异常类"""
    def __init__(self, message: str, error_code: Optional[str] = None, suggestions: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.message: str = message
        self.error_code: str = error_code or "HYDRO_ERROR"
        self.suggestions: List[str] = suggestions or []
        self.timestamp: datetime = datetime.now()

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"


class ConfigurationError(HydrologyError):
    """配置文件相关错误"""
    def __init__(self, message: str, config_path: Optional[str] = None, suggestions: Optional[List[str]] = None) -> None:
        super().__init__(message, "CONFIG_ERROR", suggestions)
        self.config_path: Optional[str] = config_path


class DependencyError(HydrologyError):
    """依赖包相关错误"""
    def __init__(self, message: str, missing_packages: Optional[List[str]] = None, suggestions: Optional[List[str]] = None) -> None:
        super().__init__(message, "DEPENDENCY_ERROR", suggestions)
        self.missing_packages: List[str] = missing_packages or []


class DataError(HydrologyError):
    """数据相关错误"""
    def __init__(self, message: str, data_path: Optional[str] = None, suggestions: Optional[List[str]] = None) -> None:
        super().__init__(message, "DATA_ERROR", suggestions)
        self.data_path: Optional[str] = data_path


class ModelError(HydrologyError):
    """模型相关错误"""
    def __init__(self, message: str, model_name: Optional[str] = None, suggestions: Optional[List[str]] = None) -> None:
        super().__init__(message, "MODEL_ERROR", suggestions)
        self.model_name: Optional[str] = model_name


class SimulationError(HydrologyError):
    """仿真运行错误"""
    def __init__(self, message: str, step: Optional[int] = None, suggestions: Optional[List[str]] = None) -> None:
        super().__init__(message, "SIMULATION_ERROR", suggestions)
        self.step: Optional[int] = step


class ValidationError(HydrologyError):
    """输入验证错误"""
    def __init__(self, message: str, field_name: Optional[str] = None, suggestions: Optional[List[str]] = None) -> None:
        super().__init__(message, "VALIDATION_ERROR", suggestions)
        self.field_name: Optional[str] = field_name


class SecurityError(HydrologyError):
    """安全相关错误"""
    def __init__(self, message: str, security_context: Optional[str] = None, suggestions: Optional[List[str]] = None) -> None:
        super().__init__(message, "SECURITY_ERROR", suggestions)
        self.security_context: Optional[str] = security_context


class ComputationError(HydrologyError):
    """计算相关错误"""
    def __init__(self, message: str, computation_context: Optional[str] = None, suggestions: Optional[List[str]] = None) -> None:
        super().__init__(message, "COMPUTATION_ERROR", suggestions)
        self.computation_context: Optional[str] = computation_context


class ErrorHandler:
    """统一错误处理器"""
    
    def __init__(self, log_file: Optional[str] = None, log_level: int = logging.ERROR) -> None:
        self.logger: logging.Logger = self._setup_logger(log_file, log_level)
        self.logging = logging
        self.error_suggestions: Dict[str, List[str]] = self._load_error_suggestions()
    
    def _setup_logger(self, log_file: Optional[str], log_level: int) -> logging.Logger:
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

    def log_error(self, error: Exception, context: Optional[str] = None) -> None:
        """Backwards-compatible instance method used by older tests."""
        prefix = f"[{context}] " if context else ""
        self.logging.error(f"{prefix}{type(error).__name__}: {error}")
    
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


def safe_file_operation(operation: Any, file_path: str, **kwargs: Any) -> Any:
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


def setup_global_error_handler(log_file: Optional[str] = None, log_level: int = logging.ERROR) -> ErrorHandler:
    """设置全局错误处理器"""
    global default_error_handler
    default_error_handler = ErrorHandler(log_file, log_level)
    return default_error_handler


# 为了向后兼容，提供error_handler别名
error_handler = default_error_handler


def handle_errors(context: Optional[str] = None) -> Any:
    """支持可选上下文参数的错误处理装饰器。"""

    def _decorator(func: Any) -> Any:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except HydrologyError:
                # 已经是框架内的异常，直接透传
                raise
            except Exception as e:
                message = context or func.__name__
                log_error(e, message)
                default_error_handler.handle_error(e, {"context": message})
                raise HydrologyError(f"{message} 执行失败: {e}") from e
        return wrapper

    if callable(context):
        func = context
        return _decorator(func)

    return _decorator


def log_error(error: Exception, context: Optional[str] = None) -> None:
    """向后兼容的简单日志函数，供旧版测试使用。"""
    prefix = f"[{context}] " if context else ""
    error_handler.logging.error(f"{prefix}{type(error).__name__}: {error}")


@contextmanager
def error_context(operation: str) -> Any:
    """为代码块提供统一的错误包装。"""
    try:
        yield
    except HydrologyError:
        raise
    except Exception as e:
        log_error(e, operation)
        default_error_handler.handle_error(e, {"context": operation})
        raise HydrologyError(f"{operation} 执行失败: {e}") from e


def validate_input(value: Any, validation_type: Optional[str] = None, **kwargs: Any) -> Any:
    """既可作为验证函数，也可作为装饰器使用。"""

    if callable(value) and validation_type is None:
        func = value

        @wraps(func)
        def wrapped(*args: Any, **kw: Any) -> Any:
            try:
                return func(*args, **kw)
            except ValidationError:
                raise
            except ValueError as e:
                raise ValidationError(str(e)) from e

        return wrapped

    if validation_type == "string":
        if not isinstance(value, str):
            raise ValidationError("输入必须是字符串类型")
        min_length = kwargs.get("min_length", 0)
        max_length = kwargs.get("max_length", float('inf'))
        if len(value) < min_length:
            raise ValidationError(f"字符串长度不能少于 {min_length} 个字符")
        if len(value) > max_length:
            raise ValidationError(f"字符串长度不能超过 {max_length} 个字符")
    elif validation_type == "number":
        if not isinstance(value, (int, float)):
            raise ValidationError("输入必须是数值类型")
        min_value = kwargs.get("min_value", float('-inf'))
        max_value = kwargs.get("max_value", float('inf'))
        if value < min_value:
            raise ValidationError(f"数值不能小于 {min_value}")
        if value > max_value:
            raise ValidationError(f"数值不能大于 {max_value}")
    elif validation_type == "list":
        if not isinstance(value, list):
            raise ValidationError("输入必须是列表类型")
        min_length = kwargs.get("min_length", 0)
        max_length = kwargs.get("max_length", float('inf'))
        if len(value) < min_length:
            raise ValidationError(f"列表长度不能少于 {min_length}")
        if len(value) > max_length:
            raise ValidationError(f"列表长度不能超过 {max_length}")
    else:
        raise ValidationError("未知的验证类型") if validation_type else None
    return True
