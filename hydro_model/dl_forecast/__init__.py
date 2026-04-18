"""深度学习时序预测产品模块。

产品化设计：
  - 配置驱动，零硬编码
  - 多模型统一接口：LSTM / Transformer / TimesFM
  - 自动特征工程 + 评价 + 模型选择
  - 支持 case_id 驱动的端到端预测

Usage::

    from hydro_model.dl_forecast import build_model, ForecastConfig
    cfg = ForecastConfig(model_type="lstm", seq_len=168, horizon=24)
    model = build_model(cfg)
    model.fit(train_ds)
    preds = model.predict(test_ds)
"""

from hydro_model.dl_forecast.config import ForecastConfig
from hydro_model.dl_forecast.dataset import TimeSeriesDataset
from hydro_model.dl_forecast.evaluator import ForecastEvaluator
from hydro_model.dl_forecast.base import BaseForecastModel

MODEL_REGISTRY: dict[str, type] = {}


def register_model(name: str, cls: type) -> None:
    MODEL_REGISTRY[name] = cls


def build_model(cfg: ForecastConfig) -> BaseForecastModel:
    if cfg.model_type not in MODEL_REGISTRY:
        raise ValueError(
            f"Unknown model '{cfg.model_type}'. Available: {list(MODEL_REGISTRY.keys())}"
        )
    return MODEL_REGISTRY[cfg.model_type](cfg)


def _auto_register() -> None:
    from hydro_model.dl_forecast.models.lstm import LSTMForecastModel
    register_model("lstm", LSTMForecastModel)

    from hydro_model.dl_forecast.models.transformer import TransformerForecastModel
    register_model("transformer", TransformerForecastModel)

    try:
        from hydro_model.dl_forecast.models.timesfm_wrapper import TimesFMForecastModel
        register_model("timesfm", TimesFMForecastModel)
    except ImportError:
        pass


_auto_register()

__all__ = [
    "ForecastConfig", "TimeSeriesDataset", "ForecastEvaluator",
    "BaseForecastModel", "build_model", "MODEL_REGISTRY", "register_model",
    "transfer", "autolearn",
]
