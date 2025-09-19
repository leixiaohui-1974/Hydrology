import os
import json
import copy
from typing import Dict, Any, Optional, Union, List, Tuple

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None
from .controller import SimulationController
from .junction import Junction
from .base_model import BaseModelComponent
from .error_handler import (
    ErrorHandler, ConfigurationError, DependencyError, DataError, 
    ModelError, safe_import, safe_file_operation, validate_config
)


# 可选的模型导入
try:
    from hydro_model.model import HydrologicalModel
    from hydro_model.runoff import (
        SCSCurveNumberModule,
        SimpleRunoffModule,
        XinanjiangRunoffModule,
        HymodRunoffModule,
        SnowmeltRunoffModule,
    )
    from hydro_model.routing import (
        SimpleRouting,
        MuskingumRouting,
        MuskingumCungeRouting,
    )
    from hydro_model.areal_precipitation import ArealPrecipitation
    from hydro_model.parameter_zone import ParameterZone
    HYDRO_MODEL_AVAILABLE = True
except ImportError:
    HYDRO_MODEL_AVAILABLE = False
    HydrologicalModel = None  # type: ignore[assignment]
    SCSCurveNumberModule = None  # type: ignore[assignment]
    SimpleRunoffModule = None  # type: ignore[assignment]
    XinanjiangRunoffModule = None  # type: ignore[assignment]
    HymodRunoffModule = None  # type: ignore[assignment]
    SnowmeltRunoffModule = None  # type: ignore[assignment]
    SimpleRouting = None  # type: ignore[assignment]
    MuskingumRouting = None  # type: ignore[assignment]
    MuskingumCungeRouting = None  # type: ignore[assignment]
    ArealPrecipitation = None  # type: ignore[assignment]
    ParameterZone = None  # type: ignore[assignment]

try:
    from preissmann_model.model import HydraulicModel
    from preissmann_model.reach import RiverReach
    from preissmann_model.cross_section import (
        RectangularCrossSection,
        TrapezoidalCrossSection,
        IrregularCrossSection,
    )
    from preissmann_model.structures import Gate, Pump, Weir
    PREISSMANN_MODEL_AVAILABLE = True
except ImportError:
    PREISSMANN_MODEL_AVAILABLE = False
    HydraulicModel = None  # type: ignore[assignment]
    RiverReach = None  # type: ignore[assignment]
    RectangularCrossSection = None  # type: ignore[assignment]
    TrapezoidalCrossSection = None  # type: ignore[assignment]
    IrregularCrossSection = None  # type: ignore[assignment]
    Gate = None  # type: ignore[assignment]
    Pump = None  # type: ignore[assignment]
    Weir = None  # type: ignore[assignment]

try:
    from model_2d.model import Model2D
    from model_2d.mesh import Mesh
    MODEL_2D_AVAILABLE = True
except ImportError:
    MODEL_2D_AVAILABLE = False
    Model2D = None  # type: ignore[assignment]
    Mesh = None  # type: ignore[assignment]

try:
    from dl_model.lstm_model import LSTMModel
    from dl_model.gnn_model import GNNModel
    DL_MODEL_AVAILABLE = True
except ImportError:
    DL_MODEL_AVAILABLE = False
    LSTMModel = None  # type: ignore[assignment]
    GNNModel = None  # type: ignore[assignment]

try:
    from preprocessing.runoff_analysis import calculate_runoff_coefficient
    from preprocessing.baseflow_separation import lyne_hollick_filter
    PREPROCESSING_AVAILABLE = True
except ImportError:
    PREPROCESSING_AVAILABLE = False
from .db_loader import load_from_db

# 为可选组件维护依赖映射，便于在缺失依赖时给出友好提示
HYDRO_COMPONENT_NAMES = [
    "HydrologicalModel",
    "SCSCurveNumberModule",
    "SimpleRunoffModule",
    "XinanjiangRunoffModule",
    "HymodRunoffModule",
    "SnowmeltRunoffModule",
    "SimpleRouting",
    "MuskingumRouting",
    "MuskingumCungeRouting",
    "ArealPrecipitation",
    "ParameterZone",
]

PREISSMANN_COMPONENT_NAMES = [
    "HydraulicModel",
    "RiverReach",
    "RectangularCrossSection",
    "TrapezoidalCrossSection",
    "IrregularCrossSection",
    "Gate",
    "Pump",
    "Weir",
]

MODEL_2D_COMPONENT_NAMES = ["HydraulicModel2D"]

DL_COMPONENT_NAMES = ["LSTMModel", "GNNModel"]

OPTIONAL_COMPONENT_DEPENDENCIES = {
    name: ("hydro_model", HYDRO_MODEL_AVAILABLE) for name in HYDRO_COMPONENT_NAMES
}
OPTIONAL_COMPONENT_DEPENDENCIES.update(
    {name: ("preissmann_model", PREISSMANN_MODEL_AVAILABLE) for name in PREISSMANN_COMPONENT_NAMES}
)
OPTIONAL_COMPONENT_DEPENDENCIES.update(
    {name: ("model_2d", MODEL_2D_AVAILABLE) for name in MODEL_2D_COMPONENT_NAMES}
)
OPTIONAL_COMPONENT_DEPENDENCIES.update(
    {name: ("dl_model", DL_MODEL_AVAILABLE) for name in DL_COMPONENT_NAMES}
)

if HYDRO_MODEL_AVAILABLE:
    HYDRO_FACTORY_ENTRIES = {
        "HydrologicalModel": HydrologicalModel,
        "SCSCurveNumberModule": SCSCurveNumberModule,
        "SimpleRunoffModule": SimpleRunoffModule,
        "XinanjiangRunoffModule": XinanjiangRunoffModule,
        "HymodRunoffModule": HymodRunoffModule,
        "SnowmeltRunoffModule": SnowmeltRunoffModule,
        "SimpleRouting": SimpleRouting,
        "MuskingumRouting": MuskingumRouting,
        "MuskingumCungeRouting": MuskingumCungeRouting,
        "ArealPrecipitation": ArealPrecipitation,
        "ParameterZone": ParameterZone,
    }
else:
    HYDRO_FACTORY_ENTRIES = {}

if PREISSMANN_MODEL_AVAILABLE:
    PREISSMANN_FACTORY_ENTRIES = {
        "HydraulicModel": HydraulicModel,
        "RiverReach": RiverReach,
        "RectangularCrossSection": RectangularCrossSection,
        "TrapezoidalCrossSection": TrapezoidalCrossSection,
        "IrregularCrossSection": IrregularCrossSection,
        "Gate": Gate,
        "Pump": Pump,
        "Weir": Weir,
    }
else:
    PREISSMANN_FACTORY_ENTRIES = {}

if MODEL_2D_AVAILABLE:
    MODEL_2D_FACTORY_ENTRIES = {"HydraulicModel2D": Model2D}
else:
    MODEL_2D_FACTORY_ENTRIES = {}

if DL_MODEL_AVAILABLE:
    DL_FACTORY_ENTRIES = {
        "LSTMModel": LSTMModel,
        "GNNModel": GNNModel,
    }
else:
    DL_FACTORY_ENTRIES = {}

# --- WORKAROUND: Move SimplePassthroughModel here to avoid import issues ---
class SimplePassthroughModel(BaseModelComponent):
    """
    A very simple model that passes rainfall through with a coefficient.
    This is used for testing the Real-Twin framework without depending on
    complex hydrological models.
    """
    def __init__(self, name: str, coeff: float = 0.5, **kwargs: Any) -> None:
        super().__init__(name)
        self.coeff: float = coeff
        self.storage: float = 0.0  # Add a simple storage state

    def step(self, inflows: Dict[str, Union[float, int]], dt: float) -> None:
        """
        The model logic for one time step.
        """
        rainfall = inflows.get('rainfall', 0.0)
        upstream_inflow = sum(v for k, v in inflows.items() if k not in ['rainfall', 'pet', 'temperature', 'lateral_flow'])

        # Add to storage
        self.storage += rainfall + upstream_inflow
        # Release a fraction of storage as outflow
        release = self.storage * self.coeff
        self.storage -= release
        self.outflow = release
# --- END WORKAROUND ---


class ConfigParser:
    """
    负责解析配置并构建仿真控制器的核心类。

    新实现在保留增强功能的同时，兼容旧版测试对无参构造器及若干
    辅助方法的依赖。
    """

    def __init__(self, config_source: Optional[Union[str, Dict[str, Any]]] = None, base_path: str = '.') -> None:
        self.error_handler: ErrorHandler = ErrorHandler()
        self.config: Dict[str, Any] = {}
        self.config_dir: str = base_path
        self.component_factory: Dict[str, Any] = self._build_factory()
        self.data_registry: Dict[str, Any] = {}

        if config_source is not None:
            self.load_config(config_source, base_path=base_path)

    def load_config(self, config_source: Union[str, Dict[str, Any]], base_path: Optional[str] = None) -> Dict[str, Any]:
        """加载配置文件或字典，并更新解析器内部状态。"""
        base_path = base_path or self.config_dir or '.'

        try:
            if isinstance(config_source, dict):
                config = config_source
                config_dir = base_path
            elif isinstance(config_source, str):
                if not os.path.exists(config_source):
                    raise ConfigurationError(
                        f"配置文件不存在: {config_source}",
                        config_path=config_source,
                        suggestions=[
                            "检查文件路径是否正确",
                            "确认文件是否存在",
                            "使用绝对路径",
                            "参考examples目录中的示例配置",
                        ],
                    )

                try:
                    with open(config_source, 'r', encoding='utf-8') as f:
                        if YAML_AVAILABLE and (config_source.endswith('.yaml') or config_source.endswith('.yml')):
                            config = yaml.safe_load(f)
                        else:
                            config = json.load(f)
                except (json.JSONDecodeError, Exception) as e:
                    if YAML_AVAILABLE:
                        try:
                            with open(config_source, 'r', encoding='utf-8') as f:
                                config = yaml.safe_load(f)
                        except yaml.YAMLError as yaml_e:
                            raise ConfigurationError(
                                f"配置文件格式错误: {str(yaml_e)}",
                                config_path=config_source,
                                suggestions=[
                                    "检查YAML语法是否正确",
                                    "验证缩进和格式",
                                    "使用YAML验证工具检查",
                                    "参考示例配置文件",
                                ],
                            )
                    else:
                        raise ConfigurationError(
                            f"配置文件格式错误: {str(e)}。YAML模块不可用，请使用JSON格式或安装pyyaml",
                            config_path=config_source,
                            suggestions=[
                                "将配置文件转换为JSON格式",
                                "安装pyyaml: pip install pyyaml",
                                "检查JSON语法是否正确",
                                "参考示例配置文件",
                            ],
                        )
                except Exception as e:
                    raise ConfigurationError(
                        f"读取配置文件失败: {str(e)}",
                        config_path=config_source,
                        suggestions=[
                            "检查文件编码格式（推荐UTF-8）",
                            "确认文件访问权限",
                            "检查文件是否被占用",
                        ],
                    )

                config_dir = os.path.dirname(config_source)
            else:
                raise ConfigurationError(
                    "配置源必须是文件路径（字符串）或字典",
                    suggestions=[
                        "传入有效的配置文件路径",
                        "或传入配置字典对象",
                        "检查参数类型",
                    ],
                )

            if not isinstance(config, dict):
                raise ConfigurationError(
                    "配置文件必须包含有效的字典结构",
                    config_path=config_source if isinstance(config_source, str) else None,
                    suggestions=[
                        "确认配置文件为有效的YAML/JSON格式",
                        "检查文件内容结构",
                        "参考示例配置文件",
                    ],
                )

            self.config = config
            self.config_dir = config_dir
            self.component_factory = self._build_factory()
            self.data_registry = {}

            if 'components' in config:
                validate_config(config, ['components'], config_path=config_source if isinstance(config_source, str) else None)

            return config

        except (ConfigurationError, DependencyError, DataError) as e:
            self.error_handler.handle_error(e)
            raise
        except Exception as e:
            error = ConfigurationError(
                f"加载配置时发生未预期错误: {str(e)}",
                config_path=config_source if isinstance(config_source, str) else None,
                suggestions=[
                    "检查配置文件格式和内容",
                    "确认所有依赖已安装",
                    "查看详细错误信息",
                    "联系技术支持",
                ],
            )
            self.error_handler.handle_error(error)
            raise error

    def validate_config(self, config: Dict[str, Any], required_sections: Optional[List[str]] = None) -> bool:
        """验证配置中是否包含必需的顶层字段。"""
        required_sections = required_sections or ['simulation', 'models']
        missing = [section for section in required_sections if section not in config]
        if missing:
            raise ConfigurationError(
                f"配置缺少必需部分: {', '.join(missing)}",
                suggestions=[
                    "补充缺失的配置段落",
                    "参考示例配置文件",
                    "检查缩进与键名",
                ],
            )
        return True

    def get_model_config(self, config: Dict[str, Any], model_name: str) -> Dict[str, Any]:
        """从配置中提取指定模型的配置。"""
        models = config.get('models', {})
        if model_name not in models:
            raise ConfigurationError(
                f"未找到名为 '{model_name}' 的模型配置",
                suggestions=[
                    "确认模型名称拼写正确",
                    "检查 models 段落是否包含该模型",
                    "参考示例配置文件",
                ],
            )
        model_config = models[model_name]
        if not isinstance(model_config, dict):
            raise ConfigurationError(
                f"模型 '{model_name}' 的配置格式必须为字典",
                suggestions=[
                    "检查模型配置的缩进",
                    "确保模型字段下包含 type/name/parameters 等键",
                ],
            )
        return model_config

    def substitute_variables(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """解析配置中的 ${var} 变量引用，返回新字典。"""
        variables = {k: v for k, v in config.items() if isinstance(v, (str, int, float))}

        def _resolve(value: Any) -> Any:
            if isinstance(value, str):
                for key, var_value in variables.items():
                    placeholder = f"${{{key}}}"
                    if placeholder in value:
                        value = value.replace(placeholder, str(var_value))
                return value
            if isinstance(value, dict):
                return {k: _resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve(item) for item in value]
            return value

        return _resolve(config)

    def merge_configs(self, base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
        """递归合并两个配置字典，override_config 拥有更高优先级。"""

        def _merge(base: Any, override: Any) -> Any:
            if isinstance(base, dict) and isinstance(override, dict):
                merged = dict(base)
                for key, value in override.items():
                    merged[key] = _merge(base.get(key), value)
                return merged
            return override if override is not None else base

        return _merge(base_config, override_config)

    def _build_factory(self) -> Dict[str, Any]:
        base_factory: Dict[str, Any] = {
            "Junction": Junction,
            "SimplePassthroughModel": SimplePassthroughModel,
        }

        base_factory.update(HYDRO_FACTORY_ENTRIES)
        base_factory.update(PREISSMANN_FACTORY_ENTRIES)
        base_factory.update(MODEL_2D_FACTORY_ENTRIES)
        base_factory.update(DL_FACTORY_ENTRIES)

        return base_factory

    def _instantiate_component(self, comp_config: Dict[str, Any], dt: Optional[float] = None) -> Any:
        # This recursive instantiation is the core of the parser
        try:
            if not isinstance(comp_config, dict):
                raise ModelError(
                    "组件配置必须是字典格式",
                    suggestions=[
                        "检查配置文件中的组件定义",
                        "确认YAML格式正确",
                        "参考示例配置文件"
                    ]
                )
            
            comp_type_str = comp_config.get("type")
            comp_params = comp_config.get("parameters", {})
            comp_name = comp_config.get("name", "未命名组件")
            
            if not comp_type_str:
                raise ModelError(
                    f"组件 '{comp_name}' 缺少必需的 'type' 字段",
                    model_name=comp_name,
                    suggestions=[
                        "为组件添加 'type' 字段",
                        "检查组件配置格式",
                        "参考支持的组件类型列表",
                        "确认配置文件语法正确"
                    ]
                )
            
            comp_class = self.component_factory.get(comp_type_str)
            if not comp_class:
                dependency_info = OPTIONAL_COMPONENT_DEPENDENCIES.get(comp_type_str)
                if dependency_info and not dependency_info[1]:
                    missing_pkg = dependency_info[0]
                    raise DependencyError(
                        f"组件 '{comp_name}' 依赖的可选模块未安装: {missing_pkg}",
                        missing_packages=[missing_pkg],
                        suggestions=[
                            f"运行 'pip install {missing_pkg}' 安装依赖",
                            "安装依赖后重新运行配置",
                            "或在配置中移除该组件",
                        ],
                    )

                available_types = list(self.component_factory.keys())
                raise ModelError(
                    f"未知的组件类型: '{comp_type_str}' (组件: {comp_name})",
                    model_name=comp_name,
                    suggestions=[
                        f"支持的组件类型: {', '.join(available_types[:10])}{'...' if len(available_types) > 10 else ''}",
                        "检查组件类型拼写",
                        "确认组件类型是否已注册",
                        "查看文档了解支持的组件类型",
                    ]
                )

            for key, value in list(comp_params.items()):
                # Prevent recursion into data-only parameters that happen to have a 'type' key
                if key in ['boundary_conditions']:
                    continue
                if isinstance(value, dict) and 'type' in value:
                    comp_params[key] = self._instantiate_component(value, dt=dt)
                elif isinstance(value, list) and value and isinstance(value[0], dict) and 'type' in value[0]:
                     comp_params[key] = [self._instantiate_component(v, dt=dt) for v in value]

            if 'name' in comp_config: comp_params['name'] = comp_config['name']

            # 统一解析可能包含路径的参数
            for key, value in list(comp_params.items()):
                if key == 'mesh_file':
                    continue  # 2D 网格在后续特殊处理
                if isinstance(value, str) and key.endswith(('_path', '_file')):
                    if not os.path.isabs(value):
                        comp_params[key] = os.path.normpath(os.path.join(self.config_dir, value))

            # Apply configuration patches before instantiation so they are not skipped.
            if dt is not None and comp_type_str in ["MuskingumRouting", "MuskingumCungeRouting"]:
                comp_params.setdefault('dt', dt)

            if comp_type_str == "RiverReach":
                if 'num_nodes' in comp_params and 'length' in comp_params:
                    if not NUMPY_AVAILABLE:
                        raise DependencyError(
                            "RiverReach 组件需要 numpy 来计算单元长度",
                            missing_packages=['numpy'],
                            suggestions=[
                                "运行 'pip install numpy' 安装依赖",
                                "或在安装numpy后重新运行配置"
                            ]
                        )
                    num_nodes = comp_params.pop('num_nodes')
                    length = comp_params.pop('length')
                    if num_nodes < 2:
                        raise ConfigurationError(
                            "RiverReach 至少需要两个断面节点以构成河段",
                            suggestions=[
                                "将 num_nodes 设置为不小于 2 的整数",
                                "或直接在配置中提供完整的 cross_sections 列表"
                            ]
                        )

                    template_sections = comp_params.get('cross_sections') or []
                    if not template_sections:
                        raise ConfigurationError(
                            "RiverReach 缺少 cross_sections 模板",
                            suggestions=[
                                "在参数中提供至少一个截面定义",
                                "参考示例配置补充矩形或梯形断面设置"
                            ]
                        )

                    template_cs = template_sections[0]
                    comp_params['cross_sections'] = [copy.deepcopy(template_cs) for _ in range(num_nodes)]
                    dx = length / (num_nodes - 1)
                    comp_params['lengths'] = np.full(num_nodes - 1, dx)
                    # Pop the 'width' parameter as it's not used in the constructor,
                    # but is useful in the config for defining the cross-section.
                    comp_params.pop('width', None)

            elif comp_type_str == "HydraulicModel2D":
                mesh_file = comp_params.get('mesh_file')
                if mesh_file:
                    mesh_file_path = os.path.join(self.config_dir, comp_params.pop('mesh_file'))
                else:
                    mesh_file_path = None
                # The DEM file is used for setting elevation, which can be done
                # after mesh creation. For now, we just pop it from the params.
                comp_params.pop('dem_file', None) # Safely remove dem_file if it exists

                if mesh_file_path:
                    if not os.path.exists(mesh_file_path):
                        raise FileNotFoundError(f"Mesh file not found: {mesh_file_path}")

                    with open(mesh_file_path, 'r') as f:
                        mesh_data = json.load(f)

                    mesh = Mesh()
                    mesh.build_from_points_and_triangles(mesh_data['points'], mesh_data['triangles'])

                    # Configure boundary conditions
                    bcs = comp_params.pop('boundary_conditions', [])
                    for bc in bcs:
                        bc_type = bc['type']
                        for edge_id in bc['edge_ids']:
                            mesh.set_boundary_edge_type(edge_id, bc_type)

                    # Add the mesh object to the component parameters
                    comp_params['mesh'] = mesh

            # 尝试实例化组件
            try:
                component = comp_class(**comp_params)
            except TypeError as e:
                raise ModelError(
                    f"组件 '{comp_name}' 参数错误: {str(e)}",
                    model_name=comp_name,
                    suggestions=[
                        "检查组件参数是否正确",
                        "确认参数类型和数量",
                        "参考组件文档了解参数要求",
                        "检查必需参数是否提供"
                    ]
                )
            except Exception as e:
                raise ModelError(
                    f"实例化组件 '{comp_name}' 失败: {str(e)}",
                    model_name=comp_name,
                    suggestions=[
                        "检查组件配置是否完整",
                        "确认依赖模块已安装",
                        "验证参数值是否在有效范围内",
                        "查看详细错误信息定位问题"
                    ]
                )
        
        except (ModelError, ConfigurationError) as e:
            self.error_handler.handle_error(e)
            raise
        except Exception as e:
            error = ModelError(
                f"处理组件配置时发生未预期错误: {str(e)}",
                model_name=comp_config.get('name', '未知组件'),
                suggestions=[
                    "检查组件配置格式",
                    "确认所有依赖已安装",
                    "验证配置文件语法",
                    "联系技术支持"
                ]
            )
            self.error_handler.handle_error(error)
            raise error

        return component

    def _load_data_sources(self) -> None:
        """Loads all initial data sources from files or DB into the data registry."""
        print("--- Loading Data Sources ---")
        db_params = self.config.get('database_connection')
        for name, config in self.config.get("data_sources", {}).items():
            if 'file' in config:
                if not PANDAS_AVAILABLE:
                    raise DependencyError(
                        "读取文件型数据源需要 pandas 支持",
                        missing_packages=['pandas'],
                        suggestions=[
                            "运行 'pip install pandas' 安装依赖",
                            "或在安装依赖后重新构建仿真"
                        ]
                    )

                path = os.path.join(self.config_dir, config['file'])
                if not os.path.exists(path):
                    raise DataError(
                        f"数据源文件不存在: {config['file']}",
                        data_path=path,
                        suggestions=[
                            "检查文件路径是否正确",
                            "确认文件是否已经生成或复制到指定目录",
                            "如果使用相对路径，请确认相对于配置文件的位置"
                        ]
                    )

                self.data_registry[name] = pd.read_csv(path, index_col=0, parse_dates=True)
                print(f"Loaded source '{name}' from file: {config['file']}")
            elif 'database_source' in config:
                if not db_params: raise ValueError("Database source specified but no 'database_connection' config found.")
                query = config['database_source'].get('query')
                if not query: raise ValueError(f"Data source '{name}' is missing a 'query'.")
                self.data_registry[name] = load_from_db(db_params, query)
                print(f"Loaded source '{name}' from database.")

    def _run_areal_precipitation(self) -> None:
        """Runs the areal precipitation calculation if configured."""
        config = self.config.get("areal_precipitation")
        if not config:
            return

        if not HYDRO_MODEL_AVAILABLE or ArealPrecipitation is None:
            raise DependencyError(
                "ArealPrecipitation 模块需要 hydro_model 依赖",
                missing_packages=["hydro_model"],
                suggestions=[
                    "运行 'pip install hydro_model' 或安装相应子模块",
                    "确认已将 hydrological 模块添加到 Python 路径",
                    "若不需要面降雨计算，请从配置中移除 areal_precipitation 配置",
                ],
            )

        print("\n--- Performing Areal Precipitation Calculation ---")
        input_name = config['input_name']
        output_name = config['output_name']

        if input_name not in self.data_registry:
            raise ValueError(f"Input '{input_name}' for areal precipitation not found in data registry.")

        areal_module = ArealPrecipitation(
            os.path.join(self.config_dir, config['subbasins_shapefile']),
            os.path.join(self.config_dir, config['rain_gauges_file'])
        )

        raw_rainfall_df = self.data_registry[input_name]
        method = config.get('method', 'idw')
        params = config.get('parameters', {})

        if 'cache_file' in params:
            params['cache_file'] = os.path.join(self.config_dir, params['cache_file'])

        result = areal_module.calculate_areal_rainfall(raw_rainfall_df, method, **params)

        if method == 'kriging':
            mean_df, variance_df = result
            self.data_registry[output_name] = mean_df
            self.data_registry[f"{output_name}_variance"] = variance_df
            print(f"Areal rainfall calculated using '{method}'. New data sources created: '{output_name}' and '{output_name}_variance'.")
        else:
            self.data_registry[output_name] = result
            print(f"Areal rainfall calculated using '{method}'. New data source '{output_name}' created.")

    def _run_preprocessing(self) -> None:
        """Runs all configured preprocessing steps."""
        config = self.config.get("preprocessing")
        if not config: return

        if not PREPROCESSING_AVAILABLE:
            raise DependencyError(
                "预处理功能需要 preprocessing 子模块",
                missing_packages=["preprocessing"],
                suggestions=[
                    "确认 preprocessing 模块位于 PYTHONPATH 中",
                    "或安装包含 runoff_analysis/baseflow_separation 的依赖包",
                    "若暂不需要预处理，可从配置中移除 preprocessing 块",
                ],
            )

        print("\n--- Running Preprocessing Steps ---")
        if 'runoff_coefficient' in config:
            print("[Preprocessing] Calculating Runoff Coefficient...")
            rc_conf = config['runoff_coefficient']
            rainfall_df = self.data_registry[rc_conf['rainfall_input']]
            flow_df = self.data_registry[rc_conf['flow_input']]
            calculate_runoff_coefficient(
                rainfall_df.iloc[:, 0], flow_df.iloc[:, 0], rc_conf['catchment_area_km2']
            )

        if 'baseflow_separation' in config:
            print("[Preprocessing] Performing Baseflow Separation...")
            bs_conf = config['baseflow_separation']
            flow_df = self.data_registry[bs_conf['flow_input']]
            params = bs_conf.get('parameters', {})
            separated_df = lyne_hollick_filter(flow_df.iloc[:, 0], **params)
            self.data_registry[bs_conf['output_baseflow']] = separated_df[['baseflow']]
            self.data_registry[bs_conf['output_quickflow']] = separated_df[['quick_flow']]
            print(f"Baseflow separation complete. New inputs available: '{bs_conf['output_baseflow']}', '{bs_conf['output_quickflow']}'")

    def _normalize_global_input_configs(self) -> List[Dict[str, Any]]:
        """将 global_inputs 配置统一转换为带有 inputs 字段的列表。"""
        raw_config = self.config.get("global_inputs", [])

        if not raw_config:
            return []

        if isinstance(raw_config, dict):
            # 旧版本写法：直接使用 { rainfall: {...}, pet: {...} }
            return [{"inputs": raw_config}]

        if not isinstance(raw_config, list):
            raise ConfigurationError(
                "global_inputs 配置必须是列表或字典",
                config_path=getattr(self, 'filepath', None),
                suggestions=[
                    "确保 global_inputs 使用列表或键值对形式",
                    "参考 examples 目录下的示例配置"
                ]
            )

        normalized: List[Dict[str, Any]] = []
        for entry in raw_config:
            if not isinstance(entry, dict):
                raise ConfigurationError(
                    "global_inputs 列表中的元素必须是字典",
                    config_path=getattr(self, 'filepath', None),
                    suggestions=[
                        "检查 global_inputs 的缩进与结构",
                        "确保每个条目都是字典"
                    ]
                )

            inputs = entry.get('inputs')
            target_component = entry.get('target_component')

            if inputs is None:
                # 兼容写法：直接把变量定义在条目根部
                inputs = {
                    key: value for key, value in entry.items()
                    if key not in {'target_component', 'description'}
                }

            normalized.append({
                'inputs': inputs or {},
                'target_component': target_component
            })

        return normalized

    def _resolve_global_input(self, var_name: str, source_info: Dict[str, Any], num_steps: int) -> Any:
        """根据 source_info 解析单个全局输入的序列。"""
        if 'from_source' in source_info:
            source_name = source_info['from_source']
            col_name = source_info.get('from_column') or source_info.get('column')
            column_index = source_info.get('from_column_index') or source_info.get('column_index')

            if source_name not in self.data_registry:
                raise DataError(
                    f"未找到数据源: {source_name}",
                    suggestions=[
                        "确认 data_sources 中已声明该数据源",
                        "检查数据源名称拼写是否正确"
                    ]
                )

            source_df = self.data_registry[source_name]

            if col_name:
                if col_name not in source_df.columns:
                    raise DataError(
                        f"数据源 '{source_name}' 中不存在列: {col_name}",
                        suggestions=[
                            "检查列名是否正确",
                            "使用 pandas.DataFrame.columns 查看可用列"
                        ]
                    )
                series = source_df[col_name]
            elif column_index is not None:
                try:
                    series = source_df.iloc[:, int(column_index)]
                except (IndexError, ValueError):
                    raise DataError(
                        f"数据源 '{source_name}' 中无法通过索引 {column_index} 获取列",
                        suggestions=[
                            "确认 column_index 在有效范围内",
                            "使用整数索引列（从0开始或根据配置约定）"
                        ]
                    )
            else:
                raise DataError(
                    f"全局输入 '{var_name}' 缺少列定义",
                    suggestions=[
                        "为 from_source 指定 from_column 或 column_index",
                        "参考示例配置文件"
                    ]
                )

            return series.to_numpy()

        if 'file' in source_info:
            file_path = source_info['file']
            resolved_path = os.path.join(self.config_dir, file_path)
            if not os.path.exists(resolved_path):
                raise DataError(
                    f"全局输入文件不存在: {file_path}",
                    data_path=resolved_path,
                    suggestions=[
                        "检查文件路径是否正确",
                        "如果使用相对路径，请确认相对于配置文件的位置",
                        "必要时运行提供的数据生成脚本"
                    ]
                )

            if not PANDAS_AVAILABLE:
                raise DependencyError(
                    "读取全局输入文件需要 pandas 支持",
                    missing_packages=['pandas'],
                    suggestions=[
                        "运行 'pip install pandas' 安装依赖",
                        "或在安装依赖后重新运行示例"
                    ]
                )

            df = pd.read_csv(resolved_path)
            column_name = source_info.get('column')
            column_index = source_info.get('column_index', 0)

            if column_name:
                if column_name not in df.columns:
                    raise DataError(
                        f"文件 '{file_path}' 中不存在列: {column_name}",
                        data_path=resolved_path,
                        suggestions=[
                            "检查列名是否正确",
                            "使用 csv 查看文件表头"
                        ]
                    )
                series = df[column_name]
            else:
                try:
                    series = df.iloc[:, int(column_index)]
                except (IndexError, ValueError):
                    raise DataError(
                        f"文件 '{file_path}' 中无法通过索引 {column_index} 获取列",
                        data_path=resolved_path,
                        suggestions=[
                            "确认 column_index 在有效范围内",
                            "可通过指定 column 明确列名"
                        ]
                    )

            return series.to_numpy()

        if 'values' in source_info:
            values = source_info['values']
            if len(values) != num_steps:
                raise ConfigurationError(
                    f"全局输入 '{var_name}' 的 values 长度 ({len(values)}) 与仿真步数 ({num_steps}) 不一致",
                    suggestions=[
                        "调整 values 长度以匹配 num_steps",
                        "或修改 simulation_parameters.num_steps"
                    ]
                )
            return np.asarray(values) if NUMPY_AVAILABLE else list(values)

        if 'value' in source_info:
            constant_value = source_info['value']
            if NUMPY_AVAILABLE:
                return np.full(num_steps, constant_value)
            return [constant_value for _ in range(num_steps)]

        raise ConfigurationError(
            f"无法解析全局输入 '{var_name}'", 
            suggestions=[
                "检查该变量的配置字段是否正确",
                "支持的字段包括 from_source、file、values、value"
            ]
        )

    def _prepare_global_inputs(self, num_steps: int) -> Dict[str, Any]:
        """
        Prepares the final global_inputs dictionary for the SimulationController.
        The controller expects a flat dictionary: {variable_name: numpy_array}.
        """
        print("\n--- Preparing Global Inputs for Simulation ---")
        final_global_inputs: Dict[str, Any] = {}

        for input_config in self._normalize_global_input_configs():
            inputs = input_config.get('inputs', {}) or {}
            for var_name, source_info in inputs.items():
                if var_name in final_global_inputs:
                    print(f"Warning: Global input '{var_name}' is being overwritten. The last definition in the config will be used.")

                resolved = self._resolve_global_input(var_name, source_info or {}, num_steps)
                final_global_inputs[var_name] = resolved

        print(f"Prepared global inputs: {list(final_global_inputs.keys())}")
        return final_global_inputs

    def build_simulation(self) -> Tuple[Any, Dict[str, Any], Dict[str, Any]]:
        """Builds the SimulationController and simulation parameters from the config."""
        try:
            controller = SimulationController()
            sim_params = self.config.get("simulation_parameters", {})
            controller.set_global_input_configs(self._normalize_global_input_configs())
            
            # 验证仿真参数
            dt = sim_params.get("dt_seconds", 1)
            num_steps = sim_params.get("num_steps", 1)
            
            if not isinstance(dt, (int, float)) or dt <= 0:
                raise ConfigurationError(
                    f"时间步长必须是正数，当前值: {dt}",
                    config_path=getattr(self, 'filepath', None),
                    suggestions=[
                        "设置合理的时间步长（如1秒、60秒等）",
                        "确认时间步长为正数",
                        "检查数值稳定性条件"
                    ]
                )
            
            if not isinstance(num_steps, int) or num_steps <= 0:
                raise ConfigurationError(
                    f"仿真步数必须是正整数，当前值: {num_steps}",
                    config_path=getattr(self, 'filepath', None),
                    suggestions=[
                        "设置合理的仿真步数",
                        "确认步数为正整数",
                        "考虑计算资源和时间限制"
                    ]
                )

            # 添加组件
            components_config = self.config.get("components", [])
            if not components_config:
                raise ConfigurationError(
                    "配置文件中没有定义任何组件",
                    config_path=getattr(self, 'filepath', None),
                    suggestions=[
                        "在配置文件中添加至少一个组件",
                        "检查'components'字段是否存在",
                        "参考示例配置文件"
                    ]
                )
            
            for i, comp_config in enumerate(components_config):
                try:
                    component = self._instantiate_component(comp_config, dt=dt)
                    controller.add_component(component)
                except Exception as e:
                    raise ModelError(
                        f"添加第{i+1}个组件失败: {str(e)}",
                        model_name=comp_config.get('name', f'组件{i+1}'),
                        suggestions=[
                            "检查组件配置是否正确",
                            "确认组件类型和参数",
                            "验证依赖是否满足"
                        ]
                    )
            
            # 建立网络连接
            network_config = self.config.get("network", [])
            for i, conn in enumerate(network_config):
                try:
                    if 'from' not in conn or 'to' not in conn:
                        raise ConfigurationError(
                            f"网络连接{i+1}缺少'from'或'to'字段",
                            config_path=getattr(self, 'filepath', None),
                            suggestions=[
                                "为每个连接指定'from'和'to'字段",
                                "检查网络配置格式",
                                "确认组件名称正确"
                            ]
                        )
                    
                    controller.connect(conn['from'], conn['to'])
                except KeyError as e:
                    raise ConfigurationError(
                        f"网络连接{i+1}引用了不存在的组件: {str(e)}",
                        config_path=getattr(self, 'filepath', None),
                        suggestions=[
                            "检查组件名称是否正确",
                            "确认所有引用的组件都已定义",
                            "验证组件名称拼写"
                        ]
                    )
                except Exception as e:
                    raise ConfigurationError(
                        f"建立网络连接{i+1}失败: {str(e)}",
                        config_path=getattr(self, 'filepath', None),
                        suggestions=[
                            "检查连接配置是否正确",
                            "确认组件兼容性",
                            "验证网络拓扑结构"
                        ]
                    )

            # Build lateral links after main components are instantiated
            if "lateral_connections" in self.config:
                if not (PREISSMANN_MODEL_AVAILABLE and MODEL_2D_AVAILABLE and HydraulicModel and Model2D):
                    print("Warning: 跳过侧向耦合连接构建，因为缺少 Preissmann 或 2D 模型依赖。")
                else:
                    # Create a map of component name to component object for easy lookup
                    component_map = controller.components
                    # Create a map of node ID to component name from the original GUI data
                    node_id_to_name = {node_id: data['name'] for node_id, data in self.config.get("nodes", {}).items()}

                    for link_config in self.config.get("lateral_connections", []):
                        from_node_id = link_config.get("from")
                        to_node_id = link_config.get("to")

                        from_comp_name = node_id_to_name.get(from_node_id)
                        to_comp_name = node_id_to_name.get(to_node_id)

                        if not from_comp_name or not to_comp_name:
                            continue

                        comp1 = component_map.get(from_comp_name)
                        comp2 = component_map.get(to_comp_name)

                        if not comp1 or not comp2:
                            continue

                        # Figure out which one is 1D and which is 2D
                        if isinstance(comp1, HydraulicModel) and isinstance(comp2, Model2D):
                            model_1d, model_2d = comp1, comp2
                        elif isinstance(comp1, Model2D) and isinstance(comp2, HydraulicModel):
                            model_1d, model_2d = comp2, comp1
                        else:
                            print(f"Warning: Could not create lateral link for {link_config.get('id')}. Must connect a HydraulicModel and a Model2D.")
                            continue

                        # This is a simplification; we need to get the actual 1D node and 2D edges
                        # For now, we'll just link to the middle of the 1D reach and all 'flow' edges of the 2D model
                        link_params = {
                            "name": link_config.get('id'),
                            "model_1d": model_1d,
                            "model_2d": model_2d,
                            "reach_id": "main_reach", # Placeholder
                            "node_idx_1d": model_1d.num_nodes // 2, # Placeholder
                            "edge_ids_2d": [e.id for e in model_2d.mesh.boundary_edges.get('flow', [])], # Placeholder
                            "bank_elevation": link_config.get("params", {}).get("bank_elevation"),
                            "weir_coeff": link_config.get("params", {}).get("weir_coeff")
                        }

                        from .lateral_link import LateralWeirLink
                        link = LateralWeirLink(**link_params)
                        controller.add_link(link)
                        print(f"Successfully created lateral link: {link.name}")

            # 加载数据和预处理
            try:
                self._load_data_sources()
                self._run_areal_precipitation()
                self._run_preprocessing()
                global_inputs = self._prepare_global_inputs(num_steps)
            except Exception as e:
                raise DataError(
                    f"数据加载或预处理失败: {str(e)}",
                    suggestions=[
                        "检查数据文件路径是否正确",
                        "确认数据格式是否支持",
                        "验证数据文件完整性",
                        "检查预处理参数设置"
                    ]
                )
            
            return controller, sim_params, global_inputs
            
        except (ConfigurationError, ModelError, DataError) as e:
            self.error_handler.handle_error(e)
            raise
        except Exception as e:
            error = ConfigurationError(
                f"构建仿真时发生未预期错误: {str(e)}",
                config_path=getattr(self, 'filepath', None),
                suggestions=[
                    "检查完整的配置文件",
                    "确认所有依赖已安装",
                    "验证系统资源充足",
                    "查看详细错误日志",
                    "联系技术支持"
                ]
            )
            self.error_handler.handle_error(error)
            raise error
