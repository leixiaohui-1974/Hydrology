"""
2D Hydraulic Model Component
============================

This module provides the Model2D class, which wraps the 2D solver
and conforms to the BaseModelComponent interface.
"""
import numpy as np
from typing import List, Optional, Tuple
from common.base_model import BaseModelComponent
from .mesh import Mesh
from .solver import finite_volume_step

class Model2D(BaseModelComponent):
    """
    Represents a 2D model domain as a component in the simulation network.

    This class acts as a wrapper for the 2D finite volume solver. It handles
    the state of the mesh, applies boundary conditions (inflows), calls the
    solver for each time step, and collects results.
    """
    def __init__(self, name: str, mesh: Mesh, source_cell_id: Optional[int] = None, outlet_edge_id: Optional[int] = None) -> None:
        """
        Initializes the 2D model component.

        Args:
            name (str): The unique name of the component.
            mesh (Mesh): The mesh object representing the 2D domain and its
                         initial state. This is the core data structure for the model.
            source_cell_id (int, optional): Deprecated. The ID of the cell where inflows
                                            were previously applied as a simple source term.
            outlet_edge_id (int, optional): The ID of the boundary edge where
                                            outflow should be calculated. (Currently simplified).
        """
        super().__init__(name)
        self.mesh: Mesh = mesh
        self.source_cell_id: Optional[int] = source_cell_id
        self.outlet_edge_id: Optional[int] = outlet_edge_id

        # History lists for storing the state of the simulation at each timestep.
        # This allows for post-simulation analysis and visualization.
        self.h_history: List[np.ndarray] = []  # History of water depth (h) for all faces
        self.uh_history: List[np.ndarray] = [] # History of momentum in x-direction (uh)
        self.vh_history: List[np.ndarray] = [] # History of momentum in y-direction (vh)

    def _get_state_arrays(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Helper to get the current state from all faces as numpy arrays."""
        h = np.array([f.h for f in self.mesh.faces])
        uh = np.array([f.uh for f in self.mesh.faces])
        vh = np.array([f.vh for f in self.mesh.faces])
        return h, uh, vh

    def step(self, inflows: dict, dt: float) -> None:
        """
        Executes one time step of the 2D simulation.

        This method orchestrates the process of advancing the model by one `dt`.
        It involves applying inflows, running the solver, and calculating outflows.

        Args:
            inflows (dict): A dictionary of inflow values. Keys are component names
                            and values are flow rates (m^3/s).
            dt (float): The duration of the time step in seconds.
        """
        # --- Pre-solver step: Apply inflow boundary conditions ---
        # This section handles how water enters the 2D domain. The current
        # implementation distributes the total inflow evenly across all
        # boundary edges tagged with the 'flow' type.
        if 'flow' in self.mesh.boundary_edges:
            # Sum up inflows from direct network connections and lateral links
            main_inflow = inflows.get(self.name, 0.0)
            lateral_inflow = inflows.get('lateral_flow', 0.0)
            total_inflow = main_inflow + lateral_inflow

            # Distribute the total inflow among all 'flow' boundary edges.
            # A more advanced implementation could assign specific flows to
            # specific edges or use a more physically-based condition.
            flow_edges = self.mesh.boundary_edges['flow']
            if flow_edges:
                inflow_per_edge = total_inflow / len(flow_edges)
                for edge in flow_edges:
                    # Find the face adjacent to this boundary edge
                    face = edge.face1
                    # Add the volume of water (Q * dt) directly to the face,
                    # converting it to a change in water depth (h = V / A).
                    if face.area > 1e-9: # Avoid division by zero
                        face.h += (inflow_per_edge * dt) / face.area

        # --- Call the core solver ---
        # `finite_volume_step` is the heart of the 2D model. It takes the
        # current mesh state and `dt`, and returns the updated mesh state
        # after solving the shallow water equations.
        self.mesh = finite_volume_step(self.mesh, dt)

        # --- Post-solver step: Calculate outflow and store history ---
        self.outflow = 0.0 # Reset outflow for the current step
        if 'flow' in self.mesh.boundary_edges:
            # A simple way to calculate total outflow is to sum the flows
            # over all boundary edges where the calculated flow is negative.
            # This is a simplification; a better approach would be to tag
            # specific edges as 'outflow' boundaries.
            for edge in self.mesh.boundary_edges['flow']:
                if getattr(edge, 'flow_rate', 0.0) < 0: # Outflow is negative by convention
                    self.outflow += edge.flow_rate

        # Store the state of all faces for this timestep for later analysis.
        h, uh, vh = self._get_state_arrays()
        self.h_history.append(h)
        self.uh_history.append(uh)
        self.vh_history.append(vh)

    def get_results(self) -> dict:
        """
        Returns the stored history and mesh info for plotting and analysis.

        This method is called after the simulation is complete to retrieve
        all the data needed for visualization in the frontend.

        Returns:
            dict: A dictionary containing the time series of h, uh, vh,
                  and the static mesh geometry (points and triangles).
        """
        return {
            # Time series data, converted to NumPy arrays for efficiency
            "h": np.array(self.h_history),
            "uh": np.array(self.uh_history),
            "vh": np.array(self.vh_history),
            # Static mesh geometry
            "points": np.array([[n.x, n.y] for n in self.mesh.nodes]),
            "triangles": np.array([[n.id for n in f.nodes] for f in self.mesh.faces])
        }

    def get_outflow(self) -> float:
        return self.outflow
