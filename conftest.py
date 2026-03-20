"""Pytest collection settings for the Hydrology repo."""

from importlib.util import find_spec
from pathlib import Path
from unittest.mock import _patch


OPTIONAL_TEST_DEPENDENCIES = {
    "tests/test_1d_2d_coupling.py": ("rasterio",),
    "tests/test_2d_solver.py": ("rasterio",),
    "tests/test_data_assimilation.py": ("psutil",),
    "tests/test_dl_models.py": ("torch",),
    "tests/test_gui_integration.py": ("rasterio",),
    "tests/test_performance.py": ("psutil",),
    "tests/test_uncertainty_analysis.py": ("seaborn",),
}


def _missing_dependencies(path_str: str) -> bool:
    normalized = path_str.replace("\\", "/")
    for suffix, modules in OPTIONAL_TEST_DEPENDENCIES.items():
        if normalized.endswith(suffix):
            return any(find_spec(module) is None for module in modules)
    return False


def pytest_ignore_collect(collection_path: Path, config):  # type: ignore[override]
    path_str = str(collection_path)
    if "pyswmm-2.0.1" in path_str:
        return True
    if path_str.endswith("tests/test_integration.py"):
        return True
    if _missing_dependencies(path_str):
        return True
    return False


_original_patch_exit = _patch.__exit__


def _safe_patch_exit(self, *exc_info):
    try:
        return _original_patch_exit(self, *exc_info)
    except TypeError as exc:
        if self.attribute == "__name__" and "cannot delete '__name__'" in str(exc):
            return False
        raise


_patch.__exit__ = _safe_patch_exit
