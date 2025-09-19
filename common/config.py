"""向后兼容模块，重定向到新的配置解析器实现。"""
from .config_parser import ConfigParser

__all__ = ["ConfigParser"]
