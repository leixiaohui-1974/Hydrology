import importlib.util
from pathlib import Path


def _load_models_module():
    module_path = Path(__file__).resolve().parents[1] / "api" / "models.py"
    spec = importlib.util.spec_from_file_location("hydrology_api_models", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_simulation_request_preserves_explicit_empty_input_data():
    models = _load_models_module()

    request = models.validate_simulation_request(
        {
            "config": {"data_sources": {"rainfall": [1.0, 2.0, 3.0]}},
            "input_data": {},
        }
    )

    assert request.data_sources == {}
