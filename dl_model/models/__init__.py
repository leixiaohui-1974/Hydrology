"""深度学习时序模型注册表。

所有模型实现统一接口 HydroTSModel，通过 MODEL_REGISTRY 注册。
"""
from __future__ import annotations
from typing import Any

MODEL_REGISTRY: dict[str, dict[str, Any]] = {}


def register_model(name: str, cls: type, description: str = "") -> None:
    MODEL_REGISTRY[name] = {"cls": cls, "description": description}


def get_model(name: str, **kwargs: Any):
    if name not in MODEL_REGISTRY:
        raise ValueError(f"Unknown model '{name}'. Available: {list(MODEL_REGISTRY.keys())}")
    return MODEL_REGISTRY[name]["cls"](**kwargs)


def list_models() -> list[dict[str, str]]:
    return [{"name": k, "description": v["description"]} for k, v in MODEL_REGISTRY.items()]
