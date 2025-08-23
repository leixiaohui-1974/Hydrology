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

    def run(self, num_steps: int, dt: float, global_inputs: Dict = None, monitored_components: Dict = None, data_queue: Queue = None):
        """
        Runs the full simulation, handling both DAG and looped network components.

        Args:
            num_steps (int): The number of simulation steps.
            dt (float): The time step duration in seconds.
            global_inputs (Dict, optional): Dictionary of global inputs. Defaults to None.
            monitored_components (Dict, optional): Dictionary specifying which components and variables to monitor.
                                                  Example: {'RiverReach_1': ['Q', 'Z'], 'Catchment_A': ['outflow']}. Defaults to None.
            data_queue (Queue, optional): A queue to push live data to for GUI updates. Defaults to None.
        """
        print("--- Initializing Simulation Controller ---")
        if not self.components:
            return
        self.dt = dt
        self._detect_and_sort_components()

        # The 'execution_order' now correctly refers to only the DAG components
        dag_components = self.execution_order

        # Initialize exchange flows from links for the first time step (usually zero)
        exchange_flows = {link.name: 0.0 for link in self.links}

        print("--- Starting Simulation Loop ---")
        for t in range(num_steps):
            # Prepare all inflows for the current time step 't'
            inflows_for_step: Dict[str, Dict] = {name: {} for name in self.components}
            if global_inputs:
                for name in self.components:
                    for key, values in global_inputs.items():
                        if t < len(values):
                            inflows_for_step[name][key] = values[t]

            # Aggregate lateral flows from all links for each component
            lateral_flows = {comp_name: 0.0 for comp_name in self.components}
            for link in self.links:
                flow = exchange_flows[link.name]
                # Flow is positive from 1D to 2D.
                # So it's a sink for 1D model, source for 2D model.
                lateral_flows[link.model_1d.name] -= flow
                lateral_flows[link.model_2d.name] += flow

            # Add the aggregated lateral flow to the inflows for each component
            for comp_name, flow in lateral_flows.items():
                if comp_name in inflows_for_step:
                    inflows_for_step[comp_name]['lateral_flow'] = flow

            # 1. Execute DAG components once in their topological order
            for component_name in dag_components:
                self._execute_component(component_name, inflows_for_step)

            # 2. Iteratively solve looped components until they converge
            if self.looped_components:
                max_iterations = 20
                tolerance = 1e-4
                for it in range(max_iterations):
                    # Store the outflows of looped components from the previous iteration
                    prev_outflows = {name: self.components[name].get_outflow() for name in self.looped_components}

                    # Execute each component in the loop
                    for component_name in self.looped_components:
                        self._execute_component(component_name, inflows_for_step)

                    # Check for convergence
                    max_change = 0.0
                    for name in self.looped_components:
                        current_outflow = self.components[name].get_outflow()
                        change = abs(current_outflow - prev_outflows[name])
                        if change > max_change:
                            max_change = change

                    if max_change < tolerance:
                        if t < 5: # Only print for the first few timesteps to avoid clutter
                            print(f"  ...Loop for timestep {t+1} converged in {it+1} iterations.")
                        break
                else:
                    # This 'else' belongs to the 'for' loop, it runs if the loop finishes without break
                    print(f"  ...Warning: Loop for timestep {t+1} did not converge after {max_iterations} iterations.")

            # 3. Push monitored data to the queue for live updates
            if data_queue and monitored_components:
                for comp_name, variables in monitored_components.items():
                    if comp_name in self.components:
                        component = self.components[comp_name]
                        for var_name in variables:
                            value = None
                            if hasattr(component, var_name):
                                attr = getattr(component, var_name)
                                if callable(attr):
                                    value = attr()
                                else:
                                    value = attr
                                # Convert numpy arrays to lists for serialization
                                if isinstance(value, np.ndarray):
                                    value = value.tolist()

                                data_packet = {
                                    'component_id': comp_name,
                                    'variable': var_name,
                                    'time_step': t,
                                    'value': value
                                }
                                data_queue.put(data_packet)

            # After stepping all components, calculate the new exchange flows for the next timestep
            for link in self.links:
                exchange_flows[link.name] = link.calculate_exchange_flow()

            # 4. Yield status for this time step
            # Find the final component in the network to report its outflow
            # This assumes a single outlet for the whole system.
            final_component_name = None
            for name in self.components:
                if not self.network.get(name): # Node with no children is an outlet
                    final_component_name = name
                    break
            if final_component_name is None:
                 final_component_name = list(self.components.keys())[-1] # Fallback

            status = {"step": t + 1, "num_steps": num_steps, "final_outflow": self.components[final_component_name].get_outflow()}
            yield status

        # Signal that the simulation is done
        if data_queue:
            data_queue.put(None) # Sentinel value

        print("--- Simulation Finished ---")
