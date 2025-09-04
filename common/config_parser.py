import os
import json
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
    from hydro_model.runoff import (SCSCurveNumberModule, SimpleRunoffModule, XinanjiangRunoffModule,
                                    HymodRunoffModule, SnowmeltRunoffModule)
    from hydro_model.routing import SimpleRouting, MuskingumRouting, MuskingumCungeRouting
    from hydro_model.areal_precipitation import ArealPrecipitation
    from hydro_model.parameter_zone import ParameterZone
    HYDRO_MODEL_AVAILABLE = True
except ImportError:
    HYDRO_MODEL_AVAILABLE = False

try:
    from preissmann_model.model import HydraulicModel
    from preissmann_model.reach import RiverReach
    from preissmann_model.cross_section import (RectangularCrossSection, TrapezoidalCrossSection,
                                                IrregularCrossSection)
    from preissmann_model.structures import Gate, Pump, Weir
    PREISSMANN_MODEL_AVAILABLE = True
except ImportError:
    PREISSMANN_MODEL_AVAILABLE = False

try:
    from model_2d.model import Model2D
    from model_2d.mesh import Mesh
    MODEL_2D_AVAILABLE = True
except ImportError:
    MODEL_2D_AVAILABLE = False

try:
    from dl_model.lstm_model import LSTMModel
    from dl_model.gnn_model import GNNModel
    DL_MODEL_AVAILABLE = True
except ImportError:
    DL_MODEL_AVAILABLE = False

try:
    from preprocessing.runoff_analysis import calculate_runoff_coefficient
    from preprocessing.baseflow_separation import lyne_hollick_filter
    PREPROCESSING_AVAILABLE = True
except ImportError:
    PREPROCESSING_AVAILABLE = False
from .db_loader import load_from_db

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
    Parses a configuration from a file or a dictionary to build a SimulationController.
    """
    def __init__(self, config_source: Union[str, Dict[str, Any]], base_path: str = '.') -> None:
        self.error_handler: ErrorHandler = ErrorHandler()
        
        try:
            if isinstance(config_source, dict):
                self.config: Dict[str, Any] = config_source
                self.config_dir: str = base_path
            elif isinstance(config_source, str):
                self.filepath: str = config_source
                if not os.path.exists(config_source):
                    raise ConfigurationError(
                        f"配置文件不存在: {config_source}",
                        config_path=config_source,
                        suggestions=[
                            "检查文件路径是否正确",
                            "确认文件是否存在",
                            "使用绝对路径",
                            "参考examples目录中的示例配置"
                        ]
                    )
                
                try:
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        if YAML_AVAILABLE and (self.filepath.endswith('.yaml') or self.filepath.endswith('.yml')):
                            self.config = yaml.safe_load(f)
                        else:
                            # 尝试JSON解析
                            f.seek(0)
                            self.config = json.load(f)
                except (json.JSONDecodeError, Exception) as e:
                    if YAML_AVAILABLE:
                        try:
                            with open(self.filepath, 'r', encoding='utf-8') as f:
                                self.config = yaml.safe_load(f)
                        except yaml.YAMLError as yaml_e:
                            raise ConfigurationError(
                                f"配置文件格式错误: {str(yaml_e)}",
                                config_path=config_source,
                                suggestions=[
                                    "检查YAML语法是否正确",
                                    "验证缩进和格式",
                                    "使用YAML验证工具检查",
                                    "参考示例配置文件"
                                ]
                            )
                    else:
                        raise ConfigurationError(
                            f"配置文件格式错误: {str(e)}。YAML模块不可用，请使用JSON格式或安装pyyaml",
                            config_path=config_source,
                            suggestions=[
                                "将配置文件转换为JSON格式",
                                "安装pyyaml: pip install pyyaml",
                                "检查JSON语法是否正确",
                                "参考示例配置文件"
                            ]
                        )
                except Exception as e:
                    raise ConfigurationError(
                        f"读取配置文件失败: {str(e)}",
                        config_path=config_source,
                        suggestions=[
                            "检查文件编码格式（推荐UTF-8）",
                            "确认文件访问权限",
                            "检查文件是否被占用"
                        ]
                    )
                
                self.config_dir = os.path.dirname(self.filepath)
            else:
                raise ConfigurationError(
                    "配置源必须是文件路径（字符串）或字典",
                    suggestions=[
                        "传入有效的配置文件路径",
                        "或传入配置字典对象",
                        "检查参数类型"
                    ]
                )
            
            # 验证基本配置结构
            if not isinstance(self.config, dict):
                raise ConfigurationError(
                    "配置文件必须包含有效的字典结构",
                    config_path=getattr(self, 'filepath', None),
                    suggestions=[
                        "确认配置文件为有效的YAML/JSON格式",
                        "检查文件内容结构",
                        "参考示例配置文件"
                    ]
                )
            
            # 验证必需的配置项
            required_keys = ['components']
            validate_config(self.config, required_keys, getattr(self, 'filepath', None))
            
            self.component_factory: Dict[str, Any] = self._build_factory()
            self.data_registry: Dict[str, Any] = {}
            
        except (ConfigurationError, DependencyError, DataError) as e:
            self.error_handler.handle_error(e)
            raise
        except Exception as e:
            error = ConfigurationError(
                f"初始化配置解析器时发生未预期错误: {str(e)}",
                config_path=getattr(self, 'filepath', None),
                suggestions=[
                    "检查配置文件格式和内容",
                    "确认所有依赖已安装",
                    "查看详细错误信息",
                    "联系技术支持"
                ]
            )
            self.error_handler.handle_error(error)
            raise error

    def _build_factory(self) -> Dict[str, Any]:
        # This can be refactored to be more dynamic in the future
        return {
            "HydrologicalModel": HydrologicalModel, "HydraulicModel": HydraulicModel,
            "Junction": Junction,
            "SCSCurveNumberModule": SCSCurveNumberModule,
            "SimpleRunoffModule": SimpleRunoffModule,
            "XinanjiangRunoffModule": XinanjiangRunoffModule,
            "HymodRunoffModule": HymodRunoffModule,
            "SnowmeltRunoffModule": SnowmeltRunoffModule,
            "SimpleRouting": SimpleRouting,
            "MuskingumRouting": MuskingumRouting, "MuskingumCungeRouting": MuskingumCungeRouting,
            "RiverReach": RiverReach,
            "RectangularCrossSection": RectangularCrossSection,
            "TrapezoidalCrossSection": TrapezoidalCrossSection,
            "IrregularCrossSection": IrregularCrossSection,
            "Gate": Gate, "Pump": Pump, "Weir": Weir,
            "HydraulicModel2D": Model2D,
            "LSTMModel": LSTMModel,
            "GNNModel": GNNModel,
            "SimplePassthroughModel": SimplePassthroughModel
        }

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
                available_types = list(self.component_factory.keys())
                raise ModelError(
                    f"未知的组件类型: '{comp_type_str}' (组件: {comp_name})",
                    model_name=comp_name,
                    suggestions=[
                        f"支持的组件类型: {', '.join(available_types[:10])}{'...' if len(available_types) > 10 else ''}",
                        "检查组件类型拼写",
                        "确认组件类型是否已注册",
                        "查看文档了解支持的组件类型"
                    ]
                )

            for key, value in comp_params.items():
                # Prevent recursion into data-only parameters that happen to have a 'type' key
                if key in ['boundary_conditions']:
                    continue
                if isinstance(value, dict) and 'type' in value:
                    comp_params[key] = self._instantiate_component(value, dt=dt)
                elif isinstance(value, list) and value and isinstance(value[0], dict) and 'type' in value[0]:
                     comp_params[key] = [self._instantiate_component(v, dt=dt) for v in value]

            if 'name' in comp_config: comp_params['name'] = comp_config['name']
            
            # 尝试实例化组件
            try:
                component = comp_class(**comp_params)
                return component
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

        if dt is not None and comp_type_str in ["MuskingumRouting", "MuskingumCungeRouting"]:
            if 'dt' not in comp_params: comp_params['dt'] = dt

        if comp_type_str == "RiverReach":
            if 'num_nodes' in comp_params and 'length' in comp_params:
                num_nodes = comp_params.pop('num_nodes')
                length = comp_params.pop('length')
                template_cs = comp_params['cross_sections'][0]
                comp_params['cross_sections'] = [template_cs for _ in range(num_nodes)]
                dx = length / (num_nodes - 1)
                comp_params['lengths'] = np.full(num_nodes - 1, dx)
                # Pop the 'width' parameter as it's not used in the constructor,
                # but is useful in the config for defining the cross-section.
                comp_params.pop('width', None)

        elif comp_type_str == "HydraulicModel2D":
            mesh_file_path = os.path.join(self.config_dir, comp_params.pop('mesh_file'))
            # The DEM file is used for setting elevation, which can be done
            # after mesh creation. For now, we just pop it from the params.
            comp_params.pop('dem_file', None) # Safely remove dem_file if it exists

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

        return comp_class(**comp_params)

    def _load_data_sources(self) -> None:
        """Loads all initial data sources from files or DB into the data registry."""
        print("--- Loading Data Sources ---")
        db_params = self.config.get('database_connection')
        for name, config in self.config.get("data_sources", {}).items():
            if 'file' in config:
                path = os.path.join(self.config_dir, config['file'])
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

    def _prepare_global_inputs(self, num_steps: int) -> Dict[str, Any]:
        """
        Prepares the final global_inputs dictionary for the SimulationController.
        The controller expects a flat dictionary: {variable_name: numpy_array}.
        """
        print("\n--- Preparing Global Inputs for Simulation ---")
        final_global_inputs = {}
        input_configs = self.config.get("global_inputs", [])

        for input_config in input_configs:
            # The 'target_component' is mainly for readability in the config.
            # The key of the 'inputs' dict is the variable name that components will look for.
            for var_name, source_info in input_config.get('inputs', {}).items():
                if var_name in final_global_inputs:
                    print(f"Warning: Global input '{var_name}' is being overwritten. The last definition in the config will be used.")

                if 'from_source' in source_info:
                    source_name = source_info['from_source']
                    col_name = source_info['from_column']
                    if source_name not in self.data_registry:
                        raise ValueError(f"Data source '{source_name}' not found.")
                    if col_name not in self.data_registry[source_name].columns:
                        raise ValueError(f"Column '{col_name}' not found in source '{source_name}'.")
                    final_global_inputs[var_name] = self.data_registry[source_name][col_name].to_numpy()

                elif 'value' in source_info:
                    constant_value = source_info['value']
                    final_global_inputs[var_name] = np.full(num_steps, constant_value)

            # This handles the special case for inflows where the component name
            # itself is the key for the input (e.g., for HydraulicModel2D).
            comp_name = input_config.get('target_component')
            if comp_name and comp_name not in input_config.get('inputs', {}):
                 # This block is for when the input is defined directly under the component name
                 # e.g., global_inputs: - target_component: Channel2D, inputs: { Channel2D: { value: 10.0 } }
                 # In this case, var_name would be "Channel2D"
                 pass # The loop above already handles this logic correctly.

        print(f"Prepared global inputs: {list(final_global_inputs.keys())}")
        return final_global_inputs

    def build_simulation(self) -> Tuple[Any, Dict[str, Any], Dict[str, Any]]:
        """Builds the SimulationController and simulation parameters from the config."""
        try:
            controller = SimulationController()
            sim_params = self.config.get("simulation_parameters", {})
            
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
                # Create a map of component name to component object for easy lookup
                component_map = controller.components
                # Create a map of node ID to component name from the original GUI data
                node_id_to_name = {node_id: data['name'] for node_id, data in self.config.get("nodes", {}).items()}

                for link_config in self.config.get("lateral_connections", []):
                    from_node_id = link_config.get("from")
                    to_node_id = link_config.get("to")

                    from_comp_name = node_id_to_name.get(from_node_id)
                    to_comp_name = node_id_to_name.get(to_node_id)

                    if not from_comp_name or not to_comp_name: continue

                    comp1 = component_map.get(from_comp_name)
                    comp2 = component_map.get(to_comp_name)

                    if not comp1 or not comp2: continue

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
