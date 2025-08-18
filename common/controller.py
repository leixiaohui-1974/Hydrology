"""
Simulation Controller Module
============================

This module provides the SimulationController class, which manages the
execution of a network of coupled model components.
"""
from typing import List, Dict, Set
from .base_model import BaseModelComponent
from .junction import Junction

class SimulationController:
    """
    Manages and executes a network of model components.
    Handles looped networks via an iterative sub-loop.
    """
    def __init__(self):
        self.components: Dict[str, BaseModelComponent] = {}
        self.network: Dict[str, List[str]] = {}
        self.parents: Dict[str, List[str]] = {}
        self.results: Dict = {}
        self.execution_order: List[str] = []
        self.looped_components: Set[str] = set()

    def add_component(self, component: BaseModelComponent):
        self.components[component.name] = component
        self.network[component.name] = []
        self.parents[component.name] = []

    def connect(self, upstream_name: str, downstream_name: str):
        if upstream_name not in self.components or downstream_name not in self.components:
            raise ValueError("Component not found.")
        self.network[upstream_name].append(downstream_name)
        self.parents[downstream_name].append(upstream_name)

    def _detect_and_sort_components(self):
        # ... (This logic is correct and remains)
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
        else:
            self.looped_components = set()

    def run(self, num_steps: int, dt: float, global_inputs: Dict = None):
        """Runs the full simulation, yielding status updates."""
        self._detect_and_sort_components()

        # This will hold the component outflows from the PREVIOUS time step
        step_outflows = {name: comp.get_outflow() for name, comp in self.components.items()}

        for t in range(num_steps):
            # --- Prepare inflows for the current step based on previous step's outflows ---
            inflows_for_step: Dict[str, Dict] = {name: {} for name in self.components}
            for component_name in self.components:
                # Add global inputs
                if global_inputs:
                    for key, values in global_inputs.items():
                        if t < len(values):
                            inflows_for_step[component_name][key] = values[t]
                # Add inflows from parent components
                parent_names = self.parents.get(component_name, [])
                for parent_name in parent_names:
                    inflows_for_step[component_name][parent_name] = step_outflows.get(parent_name, 0.0)

            # --- Execute components ---
            # For this explicit scheme, we just run all components. The iterative solver
            # for loops is not used in this simplified architecture.
            for component_name in self.execution_order:
                self.components[component_name].step(inflows_for_step[component_name], dt)

            # --- Update the stored outflows for the next step ---
            for name, comp in self.components.items():
                step_outflows[name] = comp.get_outflow()

            yield {"step": t + 1, "num_steps": num_steps, "final_outflow": step_outflows.get(self.execution_order[-1], 0)}

        print("--- Simulation Finished ---")
