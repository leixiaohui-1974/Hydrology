"""
机器学习模型基础模块
====================

本模块定义了机器学习模型的通用接口和基础包装类。
"""

import abc
import joblib
import logging
from typing import Optional, Any, Dict
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MLModelWrapper(abc.ABC):
    """
    机器学习模型包装器的抽象基类.

    定义了一个通用接口，所有具体的模型包装器都应遵循此接口。
    """

    def __init__(self, model_name: str, **kwargs):
        """
        初始化模型包装器.

        Args:
            model_name (str): 模型的名称.
            **kwargs: 模型的特定参数.
        """
        self.model_name = model_name
        self._model = None
        self.is_fitted = False
        logger.info(f"Initializing model wrapper for: {self.model_name}")

    @abc.abstractmethod
    def fit(self, X: Any, y: Any, **kwargs):
        """
        训练模型.

        Args:
            X: 训练数据特征.
            y: 训练数据标签.
            **kwargs: 额外的训练参数.
        """
        pass

    @abc.abstractmethod
    def predict(self, X: Any, **kwargs) -> Any:
        """
        使用训练好的模型进行预测.

        Args:
            X: 用于预测的输入数据.
            **kwargs: 额外的预测参数.

        Returns:
            预测结果.
        """
        pass

    def save(self, file_path: str):
        """
        将训练好的模型保存到文件.

        使用 joblib 进行序列化，这对于包含大型numpy数组的scikit-learn模型很高效.

        Args:
            file_path (str): 模型保存路径.
        """
        if not self.is_fitted:
            raise ValueError("Only fitted models can be saved.")

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            joblib.dump(self._model, path)
            logger.info(f"Model '{self.model_name}' saved to {path}")
        except Exception as e:
            logger.error(f"Error saving model '{self.model_name}' to {path}: {e}")
            raise

    def load(self, file_path: str):
        """
        从文件加载模型.

        Args:
            file_path (str): 模型文件路径.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found at: {path}")

        try:
            self._model = joblib.load(path)
            self.is_fitted = True
            logger.info(f"Model '{self.model_name}' loaded from {path}")
        except Exception as e:
            logger.error(f"Error loading model '{self.model_name}' from {path}: {e}")
            raise

    @property
    def model(self):
        """获取底层模型对象."""
        return self._model

    def get_params(self) -> Dict[str, Any]:
        """获取模型的参数."""
        if hasattr(self._model, 'get_params'):
            return self._model.get_params()
        return {}

    def set_params(self, **params):
        """设置模型的参数."""
        if hasattr(self._model, 'set_params'):
            self._model.set_params(**params)
        else:
            logger.warning(f"Model of type {type(self._model)} does not support set_params.")
        return self
