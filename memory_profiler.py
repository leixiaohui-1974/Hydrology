"""轻量级的 memory_profiler 兼容层，用于测试环境。"""
from typing import Callable, Any
from functools import wraps

def profile(func: Callable = None, **decorator_kwargs: Any):
    """简单的 profile 装饰器，占位实现。"""
    if func is None:
        def wrapper(inner_func: Callable) -> Callable:
            return profile(inner_func, **decorator_kwargs)
        return wrapper

    @wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    return wrapped
