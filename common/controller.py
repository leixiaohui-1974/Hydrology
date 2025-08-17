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
        """Runs the full simulation for a specified number of time steps."""
        print("--- Initializing Simulation Controller ---")
        if not self.execution_order:
            print("Warning: No components in simulation.")
            return

        # --- Main Simulation Loop ---
        print("--- Starting Simulation Loop ---")
        for t in range(num_steps):
            print(f"--- Controller: Time step {t+1}/{num_steps} ---")

            # This dictionary will store the inflows for each component for the current step
            inflows_for_step: Dict[str, Dict] = {name: {} for name in self.components}

            # Add global inputs to all components that might need them
            if global_inputs:
                for name in self.components:
                    for key, values in global_inputs.items():
                        if t < len(values):
                            inflows_for_step[name][key] = values[t]

            # --- Execute each component in the specified order ---
            for component_name in self.execution_order:

                # --- Gather inflows for the current component ---
                parent_names = self.parents.get(component_name, [])
                for parent_name in parent_names:
                    parent_component = self.components[parent_name]

                    if isinstance(parent_component, Junction):
                        # If parent is a junction, it has multiple outflows.
                        # We need to get the specific outflow for this child component.
                        # First, ensure the junction has calculated its splits.
                        downstream_connections = self.network.get(parent_name, [])
                        parent_component.get_outflows(downstream_connections)
                        # Now get the specific flow for this component
                        inflows_for_step[component_name][parent_name] = parent_component.outflows.get(component_name, 0.0)
                    else:
                        # If parent is a regular component, it has one outflow.
                        inflows_for_step[component_name][parent_name] = parent_component.get_outflow()

                # --- Execute the component's step ---
                component = self.components[component_name]
                component.step(inflows_for_step[component_name], dt)

        print("--- Simulation Finished ---")
