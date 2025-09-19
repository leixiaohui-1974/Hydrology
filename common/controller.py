"""
Simulation Controller Module
============================
This module provides the SimulationController class, which manages the
execution of a network of coupled model components.
"""
from typing import List, Dict, Set, Optional, Any, Generator
from queue import Queue

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None
from .base_model import BaseModelComponent
from .junction import Junction
from .lateral_link import LateralWeirLink
from . import error_handler as error_handler_module

# 可选的模型导入
try:
    from hydro_model.parameter_zone import ParameterZone
    PARAMETER_ZONE_AVAILABLE = True
except ImportError:
    PARAMETER_ZONE_AVAILABLE = False
    ParameterZone = None

# Import for type checking
try:
    from preissmann_model.model import HydraulicModel
    HYDRAULIC_MODEL_AVAILABLE = True
except ImportError:
    HYDRAULIC_MODEL_AVAILABLE = False
    HydraulicModel = None

class SimulationController:
    """
    Manages and executes a network of model components, including looped networks.
    """
    def __init__(self) -> None:
        self.components: Dict[str, BaseModelComponent] = {}
        self.links: List[LateralWeirLink] = []
        self.network: Dict[str, List[str]] = {}
        self.parents: Dict[str, List[str]] = {}
        self.results: Dict[str, List[float]] = {}
        self.execution_order: List[str] = []
        self.looped_components: Set[str] = set()
        self.parameter_zones: Dict[str, Any] = {}
        self.diagnostic_engine: Optional[Any] = None
        self.global_input_configs: List[Dict[str, Any]] = [] # To store the mapping from the config
        self.dt: float = 0.0

    def set_diagnostic_engine(self, engine: Any) -> None:
        """Sets the diagnostic engine for the simulation."""
        self.diagnostic_engine = engine

    def set_global_input_configs(self, configs: List[Dict[str, Any]]) -> None:
        """Sets the global input configurations from the parser."""
        self.global_input_configs = configs

    def add_component(self, component: BaseModelComponent) -> None:
        """Adds a model component to the simulation."""
        if component.name in self.components:
            raise ValueError(f"Component '{component.name}' already exists.")

        print(f"DEBUG: Adding component '{component.name}' of type {type(component).__name__}")
        self.components[component.name] = component
        self.network[component.name] = []
        self.parents[component.name] = []

    def get_component(self, name: str) -> BaseModelComponent:
        """Returns a component by name."""
        if name not in self.components:
            raise KeyError(f"Component '{name}' not found.")
        return self.components[name]

    def remove_component(self, name: str) -> None:
        """Removes a component and all associated connections."""
        if name not in self.components:
            raise KeyError(f"Component '{name}' not found.")

        self.components.pop(name)
        self.network.pop(name, None)
        self.parents.pop(name, None)

        for downstream in self.network.values():
            if name in downstream:
                downstream.remove(name)
        for upstream in self.parents.values():
            if name in upstream:
                upstream.remove(name)

    def add_parameter_zone(self, zone: Any) -> None:
        """Adds a parameter zone to the simulation."""
        if zone.id in self.parameter_zones:
            raise ValueError(f"Parameter zone with id '{zone.id}' already exists.")
        self.parameter_zones[zone.id] = zone

    def add_link(self, link: LateralWeirLink) -> None:
        """Adds a lateral link to the simulation."""
        self.links.append(link)

    def connect(self, upstream_name: str, downstream_name: str) -> None:
        """Defines a connection between two components."""
        if upstream_name not in self.components:
            print(f"ERROR: Upstream component '{upstream_name}' not found in controller. Available components: {list(self.components.keys())}")
            raise ValueError(f"Upstream component '{upstream_name}' not found in controller.")
        if downstream_name not in self.components:
            print(f"ERROR: Downstream component '{downstream_name}' not found in controller. Available components: {list(self.components.keys())}")
            raise ValueError(f"Downstream component '{downstream_name}' not found in controller.")

        self.network[upstream_name].append(downstream_name)
        self.parents[downstream_name].append(upstream_name)

    def run_step(self, inflows: Optional[Dict[str, Dict[str, float]]] = None, dt: float = 0.0) -> Dict[str, float]:
        """Executes a single simulation step for all registered components."""
        if not self.components:
            return {}

        inflows = inflows or {}
        results: Dict[str, float] = {}

        for name, component in self.components.items():
            component_inflows = inflows.get(name, {})
            try:
                component.step(component_inflows, dt)
            except Exception as exc:
                error_handler_module.log_error(exc, name)
                raise error_handler_module.ModelError(
                    f"组件 '{name}' 执行失败: {exc}",
                    model_name=name,
                ) from exc
            results[name] = component.get_outflow()

        return results

    def _detect_and_sort_components(self) -> None:
        """Performs a topological sort and detects cycles using Kahn's algorithm."""
        in_degree = {name: len(self.parents.get(name, [])) for name in self.components}
        queue = [name for name, degree in in_degree.items() if degree == 0]
        self.execution_order = []
        while queue:
            u = queue.pop(0)
            self.execution_order.append(u)
            for v in self.network.get(u, []):
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)
        if len(self.execution_order) < len(self.components):
            self.looped_components = set(self.components.keys()) - set(self.execution_order)
            print(f"Cycle detected. Looped components: {self.looped_components}")
        else:
            self.looped_components = set()
        print(f"Execution order for DAG components: {self.execution_order}")

    def _execute_component(self, component_name: str, inflows_for_step: Dict[str, Dict[str, float]]) -> None:
        """Gathers inflows and executes a single component's step."""
        component = self.components[component_name]

        parent_names = self.parents.get(component_name, [])
        for parent_name in parent_names:
            parent_component = self.components[parent_name]
            if isinstance(parent_component, Junction):
                downstream_connections = self.network.get(parent_name, [])
                parent_component.get_outflows(downstream_connections)
                inflows_for_step[component_name][parent_name] = parent_component.outflows.get(component_name, 0.0)
            else:
                inflows_for_step[component_name][parent_name] = parent_component.get_outflow()

        component.step(inflows_for_step[component_name], self.dt)

    def run(self, num_steps: int, dt: float, global_inputs: Optional[Dict[str, Any]] = None, monitored_components: Optional[Dict[str, Any]] = None, data_queue: Optional[Queue] = None) -> Generator[Dict[str, Any], None, None]:
        print("--- Initializing Simulation Controller ---")
        if not self.components:
            return
        self.dt = dt
        self._detect_and_sort_components()

        self.results = {name: [] for name in self.components}
        if self.diagnostic_engine:
            self.diagnostic_engine.results_history = []

        if global_inputs is None:
            global_inputs = {}

        print("--- Starting Simulation Loop ---")
        for key, values in global_inputs.items():
            try:
                available_steps = len(values)
            except TypeError:
                raise error_handler_module.ConfigurationError(
                    f"全局输入 '{key}' 不支持按步访问，请提供具有长度的序列",
                    suggestions=[
                        "确保全局输入解析为列表或 numpy 数组",
                        "检查配置中是否错误地传入了生成器或标量"
                    ]
                ) from None

            if available_steps < num_steps:
                raise error_handler_module.ConfigurationError(
                    f"全局输入 '{key}' 提供的序列长度 ({available_steps}) 小于仿真步数 ({num_steps})",
                    suggestions=[
                        "检查数据源是否覆盖了全部仿真时段",
                        "缩短仿真步数或补充缺失的驱动数据"
                    ]
                )

        ordered_components: List[str] = list(self.execution_order)
        for loop_comp in self.looped_components:
            if loop_comp not in ordered_components:
                ordered_components.append(loop_comp)

        if not ordered_components:
            ordered_components = list(self.components.keys())

        for t in range(num_steps):
            # 1. Prepare raw global inputs
            step_global_inputs = {key: values[t] for key, values in global_inputs.items()}

            # 2. Run Diagnostics & Correction
            if self.diagnostic_engine:
                self.diagnostic_engine.run_step(t, step_global_inputs, self.results)

                corrected_global_inputs = step_global_inputs.copy()
                for gauge, health in self.diagnostic_engine.sensor_health.items():
                    if health < 50:
                        if gauge == 'RG2' and 'RG1' in corrected_global_inputs:
                            print(f"  CORRECTION: Replacing {gauge} value ({corrected_global_inputs.get(gauge, 0):.2f}) with RG1 value ({corrected_global_inputs['RG1']:.2f})")
                            corrected_global_inputs[gauge] = corrected_global_inputs['RG1']
                step_global_inputs = corrected_global_inputs

            # 3. Prepare inflows for each component
            inflows_for_step = {name: {} for name in self.components}
            for config in self.global_input_configs:
                target_comp = config.get('target_component')
                if target_comp in self.components:
                    for var_name, source_info in config.get('inputs', {}).items():
                        candidate_keys = [
                            source_info.get('from_column'),
                            source_info.get('column'),
                            var_name,
                        ]

                        for candidate in candidate_keys:
                            if candidate and candidate in step_global_inputs:
                                inflows_for_step[target_comp][var_name] = step_global_inputs[candidate]
                                break

            # 4. Execute components
            for component_name in ordered_components:
                self._execute_component(component_name, inflows_for_step)

            # 5. Store results
            for name, component in self.components.items():
                self.results[name].append(component.get_outflow())

            if self.diagnostic_engine:
                diag_results = {f'health_{k}': v for k, v in self.diagnostic_engine.sensor_health.items()}
                diag_results['reliability_index'] = self.diagnostic_engine.reliability_index
                self.diagnostic_engine.results_history.append(diag_results)

            final_component_name = ordered_components[-1]
            status = {"step": t + 1, "num_steps": num_steps, "final_outflow": self.components[final_component_name].get_outflow()}
            yield status

        if data_queue:
            data_queue.put(None)

        print("--- Simulation Finished ---")


# 兼容旧版代码中对 Controller 名称的引用
Controller = SimulationController
