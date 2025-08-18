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
    def __init__(self, name: str, mesh: Mesh, outlet_edge_id: int = None):
        super().__init__(name)
        self.mesh = mesh
        self.outlet_edge_id = outlet_edge_id

    def step(self, inflows: dict, dt: float):
        """
        Executes one time step of the 2D simulation.
        """
        # Apply all inflows as source terms to specified cells
        # The inflows dict is expected to be of the form {cell_idx: flow, ...}
        # This includes main inflows and lateral inflows.
        for cell_idx, flow_value in inflows.items():
            if 0 <= cell_idx < len(self.mesh.faces):
                face = self.mesh.faces[cell_idx]
                if face.area > 1e-6:
                    face.h += (flow_value * dt) / face.area
            else:
                print(f"Warning: Invalid face index {cell_idx} for inflow in {self.name}")

        # Call the core explicit solver
        self.mesh = finite_volume_step(self.mesh, dt)

        # Calculate outflow
        if self.outlet_edge_id is not None:
            outlet_edge = self.mesh.edges[self.outlet_edge_id]
            face = outlet_edge.face1
            h, uh, vh = face.h, face.uh, face.vh
            u = uh / h if h > 1e-6 else 0
            v = vh / h if h > 1e-6 else 0
            normal_velocity = u * outlet_edge.normal[0] + v * outlet_edge.normal[1]
            self.outflow = normal_velocity * h * outlet_edge.length
        else:
            self.outflow = 0.0

    def get_outflow(self) -> float:
        return self.outflow
