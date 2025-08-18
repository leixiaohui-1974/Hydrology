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
    def __init__(self, name: str, mesh: Mesh, main_inflow_cell_id: int = None, outlet_edge_id: int = None):
        """
        Initializes the 2D model component.

        Args:
            name (str): The unique name of the component.
            mesh (Mesh): The mesh object representing the 2D domain.
            main_inflow_cell_id (int, optional): The ID of the cell where main
                                                 (e.g., from a river) inflows
                                                 will be applied.
            outlet_edge_id (int, optional): The ID of the boundary edge where
                                            outflow should be calculated.
        """
        super().__init__(name)
        self.mesh = mesh
        self.main_inflow_cell_id = main_inflow_cell_id
        self.outlet_edge_id = outlet_edge_id

    def step(self, inflows: dict, dt: float):
        """
        Executes one time step of the 2D simulation.
        """
        # --- Pre-solver step: Apply all inflows as source terms ---

        # 1. Apply main inflow (e.g., from a river junction)
        if self.main_inflow_cell_id is not None:
            # Sum all inflows that are not special keys like 'lateral'
            main_inflow = sum(v for k, v in inflows.items() if k != 'lateral')
            source_face = self.mesh.faces[self.main_inflow_cell_id]
            if source_face.area > 1e-6:
                source_face.h += (main_inflow * dt) / source_face.area

        # 2. Apply lateral inflows (e.g., from LateralLink components)
        lateral_flows = inflows.get('lateral', {})
        for face_idx, flow_value in lateral_flows.items():
            if 0 <= face_idx < len(self.mesh.faces):
                lateral_face = self.mesh.faces[face_idx]
                if lateral_face.area > 1e-6:
                    lateral_face.h += (flow_value * dt) / lateral_face.area
            else:
                print(f"Warning: Invalid face index {face_idx} for lateral flow in {self.name}")

        # --- Call the core solver ---
        self.mesh = finite_volume_step(self.mesh, dt)

        # --- Post-solver step: Calculate outflow ---
        if self.outlet_edge_id is not None:
            # ... (outflow logic remains the same)
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
