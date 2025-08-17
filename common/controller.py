"""
Simulation Controller Module
============================

This module provides the SimulationController class, which manages the
execution of a network of coupled model components.
"""
from typing import List, Dict
from .base_model import BaseModelComponent

class SimulationController:
    """
    Manages and executes a network of model components.
    """
    def __init__(self):
        self.components: Dict[str, BaseModelComponent] = {}
        # The execution order is simply the order of addition for now.
        # A more robust implementation would use a topological sort on the network.
        self.execution_order: List[str] = []
        # Adjacency list for the network graph: {upstream_name: [downstream_name, ...]}
        self.network: Dict[str, List[str]] = {}

    def add_component(self, component: BaseModelComponent):
        """
        Adds a model component to the simulation.

        Args:
            component (BaseModelComponent): The component instance to add.
        """
        if component.name in self.components:
            raise ValueError(f"Component with name '{component.name}' already exists.")
        self.components[component.name] = component
        self.execution_order.append(component.name)
        self.network[component.name] = []

    def connect(self, upstream_name: str, downstream_name: str):
        """
        Defines a connection between two components.
        The outflow of the upstream component will be an inflow to the downstream one.

        Args:
            upstream_name (str): The name of the upstream component.
            downstream_name (str): The name of the downstream component.
        """
        if upstream_name not in self.components:
            raise ValueError(f"Upstream component '{upstream_name}' not found.")
        if downstream_name not in self.components:
            raise ValueError(f"Downstream component '{downstream_name}' not found.")

        self.network[upstream_name].append(downstream_name)

    def run(self, num_steps: int, dt: float, global_inputs: Dict = None):
        """
        Runs the full simulation for a specified number of time steps.

        Args:
            num_steps (int): The number of steps to simulate.
            dt (float): The duration of each time step in seconds.
            global_inputs (Dict, optional): A dictionary of global inputs for each
                                            time step, e.g., {'rainfall': [...], 'pet': [...]}.
                                            The lists must have length `num_steps`.
        """
        print("--- Initializing Simulation Controller ---")
        # A dictionary to hold the outflow of each component at each time step
        # We only need to store the results of the previous step to feed the next one.
        step_outflows: Dict[str, float] = {name: comp.get_outflow() for name, comp in self.components.items()}

        # --- Main Simulation Loop ---
        print("--- Starting Simulation Loop ---")
        for t in range(num_steps):
            print(f"--- Controller: Time step {t+1}/{num_steps} ---")

            # Find all upstream connections for each component
            # This is inefficient to do in the loop, but clearer for now.
            # A better way is to pre-calculate the inverse network.
            all_inflows: Dict[str, Dict] = {name: {} for name in self.components}

            for up_name, down_names in self.network.items():
                for down_name in down_names:
                    # The inflow for the downstream component from this upstream one
                    # is the outflow calculated in the *previous* time step.
                    all_inflows[down_name][up_name] = step_outflows[up_name]

            # Execute each component in order
            for name in self.execution_order:
                component = self.components[name]

                # Get the inflows for the current component
                component_inflows = all_inflows[name]

                # Add any global inputs for the current time step
                if global_inputs:
                    for key, values in global_inputs.items():
                        if t < len(values):
                            component_inflows[key] = values[t]

                # Execute the component's step
                component.step(component_inflows, dt)

            # After all components have stepped, update the outflows for the next step
            for name in self.components:
                step_outflows[name] = self.components[name].get_outflow()

        print("--- Simulation Finished ---")
