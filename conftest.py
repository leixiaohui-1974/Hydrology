"""全局 Pytest 配置，跳过外部依赖的测试目录。"""


def pytest_ignore_collect(path, config):  # type: ignore[override]
    path_str = str(path)
    if "pyswmm-2.0.1" in path_str:
        return True
    if path_str.endswith("tests/test_hydro_model.py"):
        return True
    if path_str.endswith("tests/test_integration.py"):
        return True
    return False
