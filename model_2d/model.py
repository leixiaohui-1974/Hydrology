"""
2D Hydraulic Model Component
============================

This module provides the Model2D class, which wraps the 2D solver
and conforms to the BaseModelComponent interface.
"""
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

    def step(self, inflows: dict, dt: float):
        """
        Executes one time step of the 2D simulation.
        """
        # --- Pre-solver step: Apply inflows as source terms ---
        if self.source_cell_id is not None:
            total_inflow = sum(inflows.values()) if inflows else 0.0
            source_face = self.mesh.faces[self.source_cell_id]

            # Add inflow as a volume change to the source cell's depth
            # This is a simple source term application
            source_face.h += (total_inflow * dt) / source_face.area

        # --- Call the core solver ---
        # The solver will update the h, uh, vh states on all faces
        self.mesh = finite_volume_step(self.mesh, dt)

        # --- Post-solver step: Calculate outflow ---
        # For this PoC, outflow is the flux across a single, predefined outlet edge.
        if self.outlet_edge_id is not None:
            outlet_edge = self.mesh.edges[self.outlet_edge_id]
            face = outlet_edge.face1 # Assume it's a boundary edge with only one face

            h, uh, vh = face.h, face.uh, face.vh
            u = uh / h if h > 1e-6 else 0
            v = vh / h if h > 1e-6 else 0

            # Outflow Q is the normal velocity * area = (u*nx + v*ny) * (h*L)
            normal_velocity = u * outlet_edge.normal[0] + v * outlet_edge.normal[1]
            self.outflow = normal_velocity * h * outlet_edge.length
        else:
            self.outflow = 0.0

    def get_outflow(self) -> float:
        return self.outflow
