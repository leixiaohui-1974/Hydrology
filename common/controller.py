"""
Simulation Controller Module
============================
This module provides the SimulationController class, which manages the
execution of a network of coupled model components.
"""
from typing import List, Dict, Set
import numpy as np
from .base_model import BaseModelComponent
from .junction import Junction
from hydro_model.parameter_zone import ParameterZone

# Import for type checking
from preissmann_model.model import HydraulicModel

class SimulationController:
    """
    Manages and executes a network of model components, including looped networks.
    """
    def __init__(self):
        self.components: Dict[str, BaseModelComponent] = {}
        self.network: Dict[str, List[str]] = {}
        self.parents: Dict[str, List[str]] = {}
        self.results: Dict = {}
        self.execution_order: List[str] = []
        self.looped_components: Set[str] = set()
        self.parameter_zones: Dict[str, ParameterZone] = {}

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

        # --- Gather inflows (Q) from parents ---
        parent_names = self.parents.get(component_name, [])
        for parent_name in parent_names:
            parent_component = self.components[parent_name]
            # ... (inflow logic remains the same)
            if isinstance(parent_component, Junction):
                downstream_connections = self.network.get(parent_name, [])
                parent_component.get_outflows(downstream_connections)
                inflows_for_step[component_name][parent_name] = parent_component.outflows.get(component_name, 0.0)
            else:
                inflows_for_step[component_name]['Q_inflow'] = parent_component.get_outflow()

        # --- Set downstream boundary condition for hydraulic models ---
        if isinstance(component, HydraulicModel):
            downstream_connections = self.network.get(component_name, [])
            if downstream_connections:
                # Assume first downstream connection sets the boundary level
                downstream_comp = self.components[downstream_connections[0]]
                if isinstance(downstream_comp, HydraulicModel):
                    # The boundary is the water level at the start of the next reach
                    component.downstream_level = downstream_comp.Z[0]
                elif isinstance(downstream_comp, Junction):
                    # Junctions don't have a water level. This is a limitation.
                    # We need to find the component downstream of the junction.
                    # This logic can get complex. For now, we assume a simple loop.
                    pass

        component.step(inflows_for_step[component_name], self.dt)

    def run(self, num_steps: int, dt: float, global_inputs: Dict = None):
        """Runs the full simulation, handling DAGs and looped networks."""
        print("--- Initializing Simulation Controller ---")
        if not self.components: return
        self.dt = dt
        self._detect_and_sort_components()

        print("--- Starting Simulation Loop ---")
        for t in range(num_steps):
            print(f"--- Controller: Time step {t+1}/{num_steps} ---")
            inflows_for_step: Dict[str, Dict] = {name: {} for name in self.components}
            if global_inputs:
                for name in self.components:
                    for key, values in global_inputs.items():
                        if t < len(values): inflows_for_step[name][key] = values[t]

            # Execute DAG components
            for component_name in self.execution_order:
                if component_name not in self.looped_components:
                    self._execute_component(component_name, inflows_for_step)

            # Iteratively solve looped components
            if self.looped_components:
                max_iterations = 15
                tolerance = 1e-3
                for it in range(max_iterations):
                    prev_state = {name: self.components[name].get_outflow() for name in self.looped_components}

                    for component_name in self.looped_components:
                        self._execute_component(component_name, inflows_for_step)

                    max_change = 0.0
                    for name in self.looped_components:
                        change = abs(self.components[name].get_outflow() - prev_state[name])
                        if change > max_change: max_change = change

                    if max_change < tolerance:
                        print(f"  ...Loop converged in {it+1} iterations.")
                        break
                else:
                    print(f"  ...Warning: Loop did not converge after {max_iterations} iterations.")

            # Store results and yield status
            final_component_name = self.execution_order[-1] if self.execution_order else list(self.components.keys())[0]
            status = {"step": t + 1, "num_steps": num_steps, "final_outflow": self.components[final_component_name].get_outflow()}
            yield status

        print("--- Simulation Finished ---")
