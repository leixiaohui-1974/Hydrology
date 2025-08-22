"""
2D Hydraulic Model Component
============================

This module provides the Model2D class, which wraps the 2D solver
and conforms to the BaseModelComponent interface.
"""
import numpy as np
from common.base_model import BaseModelComponent
from .mesh import Mesh
from .solver import finite_volume_step

class Model2D(BaseModelComponent):
    """
    Represents a 2D model domain as a component in the simulation network.
    """
    def __init__(self, name: str, mesh: Mesh, source_cell_id: int = None, outlet_edge_id: int = None):
        """
        Initializes the 2D model component.

        Args:
            name (str): The unique name of the component.
            mesh (Mesh): The mesh object representing the 2D domain and its
                         initial state.
            source_cell_id (int, optional): The ID of the cell where inflows
                                            will be applied as a source term.
            outlet_edge_id (int, optional): The ID of the boundary edge where
                                            outflow should be calculated.
        """
        super().__init__(name)
        self.mesh = mesh
        self.source_cell_id = source_cell_id
        self.outlet_edge_id = outlet_edge_id

        # For storing results
        self.h_history = []
        self.uh_history = []
        self.vh_history = []

    def _get_state_arrays(self):
        """Helper to get the current state from all faces as numpy arrays."""
        h = np.array([f.h for f in self.mesh.faces])
        uh = np.array([f.uh for f in self.mesh.faces])
        vh = np.array([f.vh for f in self.mesh.faces])
        return h, uh, vh

    def step(self, inflows: dict, dt: float):
        """
        Executes one time step of the 2D simulation.
        """
        # --- Pre-solver step: Apply inflow boundary conditions ---
        # This is a more physically-based way than a simple source term.
        if 'flow' in self.mesh.boundary_edges:
            # Assume the inflow is provided under a key that matches the component's name
            total_inflow = inflows.get(self.name, 0.0)

            # Distribute the total inflow among all 'flow' boundary edges
            # A more advanced implementation could assign specific flows to specific edges
            flow_edges = self.mesh.boundary_edges['flow']
            if flow_edges:
                inflow_per_edge = total_inflow / len(flow_edges)
                for edge in flow_edges:
                    # The solver will read this attribute
                    edge.flow_rate = inflow_per_edge

        # --- Call the core solver ---
        # The solver will update the h, uh, vh states on all faces
        self.mesh = finite_volume_step(self.mesh, dt)

        # --- Post-solver step: Calculate outflow and store history ---
        self.outflow = 0.0 # Reset outflow for the step
        if 'flow' in self.mesh.boundary_edges:
            # A simple way to calculate total outflow is to sum the flows
            # over all boundary edges that are not inflows.
            # This is a simplification; a better way is to tag outflow edges.
            for edge in self.mesh.boundary_edges['flow']:
                if getattr(edge, 'flow_rate', 0.0) < 0: # Outflow convention
                    self.outflow += edge.flow_rate

        # Store the state of all faces for this timestep
        h, uh, vh = self._get_state_arrays()
        self.h_history.append(h)
        self.uh_history.append(uh)
        self.vh_history.append(vh)

    def get_results(self):
        """Returns the stored history and mesh info for plotting."""
        return {
            "h": np.array(self.h_history),
            "uh": np.array(self.uh_history),
            "vh": np.array(self.vh_history),
            "points": np.array([[n.x, n.y] for n in self.mesh.nodes]),
            "triangles": np.array([[n.id for n in f.nodes] for f in self.mesh.faces])
        }

    def get_outflow(self) -> float:
        return self.outflow
