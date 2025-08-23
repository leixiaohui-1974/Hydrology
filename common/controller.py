"""
Simulation Controller Module
============================
This module provides the SimulationController class, which manages the
execution of a network of coupled model components.
"""
from typing import List, Dict, Set
from queue import Queue
import numpy as np
from .base_model import BaseModelComponent
from .junction import Junction
from hydro_model.parameter_zone import ParameterZone
from .lateral_link import LateralWeirLink
from typing import List

# Import for type checking
from preissmann_model.model import HydraulicModel

class SimulationController:
    """
    Manages and executes a network of model components, including looped networks.
    """
    def __init__(self):
        self.components: Dict[str, BaseModelComponent] = {}
        self.links: List[LateralWeirLink] = []
        self.network: Dict[str, List[str]] = {}
        self.parents: Dict[str, List[str]] = {}
        self.results: Dict[str, List[float]] = {}
        self.execution_order: List[str] = []
        self.looped_components: Set[str] = set()
        self.parameter_zones: Dict[str, ParameterZone] = {}
        self.diagnostic_engine = None

    def set_diagnostic_engine(self, engine):
        """Sets the diagnostic engine for the simulation."""
        self.diagnostic_engine = engine

    def add_component(self, component: BaseModelComponent):
        """Adds a model component to the simulation."""
        print(f"DEBUG: Adding component '{component.name}' of type {type(component).__name__}")
        self.components[component.name] = component
        self.network[component.name] = []
        self.parents[component.name] = []

    def add_parameter_zone(self, zone: ParameterZone):
        """Adds a parameter zone to the simulation."""
        if zone.id in self.parameter_zones:
            raise ValueError(f"Parameter zone with id '{zone.id}' already exists.")
        self.parameter_zones[zone.id] = zone

    def add_link(self, link: LateralWeirLink):
        """Adds a lateral link to the simulation."""
        self.links.append(link)

    def connect(self, upstream_name: str, downstream_name: str):
        """Defines a connection between two components."""
        if upstream_name not in self.components:
            print(f"ERROR: Upstream component '{upstream_name}' not found in controller. Available components: {list(self.components.keys())}")
            raise ValueError(f"Upstream component '{upstream_name}' not found in controller.")
        if downstream_name not in self.components:
            print(f"ERROR: Downstream component '{downstream_name}' not found in controller. Available components: {list(self.components.keys())}")
            raise ValueError(f"Downstream component '{downstream_name}' not found in controller.")

        self.network[upstream_name].append(downstream_name)
        self.parents[downstream_name].append(upstream_name)

    def _detect_and_sort_components(self):
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

    def _execute_component(self, component_name: str, inflows_for_step: Dict):
        """Gathers inflows and executes a single component's step."""
        component = self.components[component_name]

        # Gather inflows from parents
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

    def run(self, num_steps: int, dt: float, global_inputs: Dict = None, monitored_components: Dict = None, data_queue: Queue = None):
        """
        Runs the full simulation with integrated diagnostics and feedback.
        """
        print("--- Initializing Simulation Controller ---")
        if not self.components:
            return
        self.dt = dt
        self._detect_and_sort_components()

        self.results = {name: [] for name in self.components}
        if self.diagnostic_engine:
            self.diagnostic_engine.results_history = []


        print("--- Starting Simulation Loop ---")
        for t in range(num_steps):
            # 1. Prepare raw global inputs for the current step
            step_global_inputs = {key: values[t] for key, values in global_inputs.items() if t < len(values)}

            # 2. Run Diagnostics & Correction (if engine exists)
            if self.diagnostic_engine:
                self.diagnostic_engine.run_step(t, step_global_inputs, self.results)

                # Perform data correction
                corrected_global_inputs = step_global_inputs.copy()
                for gauge, health in self.diagnostic_engine.sensor_health.items():
                    if health < 50:
                        # Simple correction: use a healthy neighbor
                        if gauge == 'RG2' and 'RG1' in corrected_global_inputs:
                            print(f"  CORRECTION: Replacing {gauge} value ({corrected_global_inputs.get(gauge, 0):.2f}) with RG1 value ({corrected_global_inputs['RG1']:.2f})")
                            corrected_global_inputs[gauge] = corrected_global_inputs['RG1']
                step_global_inputs = corrected_global_inputs

            # 3. Prepare inflows for each component for the current time step
            inflows_for_step = {name: {} for name in self.components}
            for comp_name in self.components:
                # This logic assumes a simple mapping from global inputs to component inputs
                # A more robust system would use the mapping from the config file
                if comp_name == 'Catchment1': inflows_for_step[comp_name]['rainfall'] = step_global_inputs.get('RG1', 0)
                if comp_name == 'Catchment2': inflows_for_step[comp_name]['rainfall'] = step_global_inputs.get('RG2', 0)
                if comp_name == 'Catchment3': inflows_for_step[comp_name]['rainfall'] = step_global_inputs.get('RG3', 0)

            # 4. Execute components
            for component_name in self.execution_order:
                self._execute_component(component_name, inflows_for_step)

            # 5. Store results
            for name, component in self.components.items():
                self.results[name].append(component.get_outflow())

            if self.diagnostic_engine:
                diag_results = {f'health_{k}': v for k, v in self.diagnostic_engine.sensor_health.items()}
                diag_results['reliability_index'] = self.diagnostic_engine.reliability_index
                self.diagnostic_engine.results_history.append(diag_results)


            final_component_name = self.execution_order[-1]
            status = {"step": t + 1, "num_steps": num_steps, "final_outflow": self.components[final_component_name].get_outflow()}
            yield status

        if data_queue:
            data_queue.put(None)

        print("--- Simulation Finished ---")
