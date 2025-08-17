"""
Simulation Controller Module
============================

This module provides the SimulationController class, which manages the
execution of a network of coupled model components.
"""
from typing import List, Dict
from .base_model import BaseModelComponent
from .junction import Junction # Import Junction to check its type

class SimulationController:
    """
    Manages and executes a network of model components.
    """
    def __init__(self):
        self.components: Dict[str, BaseModelComponent] = {}
        self.execution_order: List[str] = []
        # Adjacency list for the network graph: {upstream_name: [downstream_name, ...]}
        self.network: Dict[str, List[str]] = {}
        # A reverse mapping for easily finding upstream connections (parents)
        self.parents: Dict[str, List[str]] = {}
        # A dictionary to store time-series results of the simulation
        self.results: Dict = {}

    def add_component(self, component: BaseModelComponent):
        """Adds a model component to the simulation."""
        if component.name in self.components:
            raise ValueError(f"Component with name '{component.name}' already exists.")
        self.components[component.name] = component
        self.execution_order.append(component.name)
        self.network[component.name] = []
        self.parents[component.name] = []

    def connect(self, upstream_name: str, downstream_name: str):
        """Defines a connection between two components."""
        if upstream_name not in self.components:
            raise ValueError(f"Upstream component '{upstream_name}' not found.")
        if downstream_name not in self.components:
            raise ValueError(f"Downstream component '{downstream_name}' not found.")

        self.network[upstream_name].append(downstream_name)
        self.parents[downstream_name].append(upstream_name)

    def run(self, num_steps: int, dt: float, global_inputs: Dict = None):
        """
        Runs the full simulation, yielding status updates at each time step.
        This is a generator function.
        """
        print("--- Initializing Simulation Controller ---")
        if not self.execution_order:
            print("Warning: No components in simulation.")
            return

        print("--- Starting Simulation Loop ---")
        for t in range(num_steps):
            inflows_for_step: Dict[str, Dict] = {name: {} for name in self.components}

            if global_inputs:
                for name in self.components:
                    for key, values in global_inputs.items():
                        if t < len(values):
                            inflows_for_step[name][key] = values[t]

            for component_name in self.execution_order:
                parent_names = self.parents.get(component_name, [])
                for parent_name in parent_names:
                    parent_component = self.components[parent_name]
                    if isinstance(parent_component, Junction):
                        downstream_connections = self.network.get(parent_name, [])
                        parent_component.get_outflows(downstream_connections)
                        inflows_for_step[component_name][parent_name] = parent_component.outflows.get(component_name, 0.0)
                    else:
                        inflows_for_step[component_name][parent_name] = parent_component.get_outflow()

                component = self.components[component_name]
                component.step(inflows_for_step[component_name], dt)

            # --- Store results for this time step ---
            for name, comp in self.components.items():
                if name not in self.results:
                    self.results[name] = {
                        "outflow": []
                    }
                    # Add specific states for hydraulic model
                    if hasattr(comp, 'Q'):
                        self.results[name]['Q'] = []
                        self.results[name]['Z'] = []

                self.results[name]['outflow'].append(comp.get_outflow())
                if hasattr(comp, 'Q'):
                    self.results[name]['Q'].append(np.copy(comp.Q))
                    self.results[name]['Z'].append(np.copy(comp.Z))

            # --- Yield status update for the GUI ---
            final_component_name = self.execution_order[-1]
            final_outflow = self.components[final_component_name].get_outflow()
            status = {
                "step": t + 1,
                "num_steps": num_steps,
                "final_outflow": final_outflow
            }
            yield status

        print("--- Simulation Finished ---")
