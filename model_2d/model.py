import numpy as np
from typing import Dict, List, Tuple
from common.base_model import BaseModelComponent
from .mesh import Mesh
from .solver import finite_volume_step

class Model2D(BaseModelComponent):
    """
    2D Hydraulic model component that fakes the implicit interface to work
    with the implicit controller, while running an explicit solver internally.
    """
    def __init__(self, name: str, mesh: Mesh):
        super().__init__(name)
        self.mesh = mesh

        self.h_history = [[f.h for f in self.mesh.faces]]
        self.uh_history = [[f.uh for f in self.mesh.faces]]
        self.vh_history = [[f.vh for f in self.mesh.faces]]

    def get_num_vars(self) -> int:
        # This is an explicit model, it does not contribute variables to the implicit solve.
        return 0

    def get_matrix_contributions(self, controller) -> Tuple[List, List]:
        # This is where we "hide" the explicit step for the 2D model.
        dt = controller.dt

        # The controller needs to pass the lateral inflows to this component before calling this.
        # This requires a change in the controller logic.
        # For now, assume inflows are passed somehow.
        lateral_inflows = getattr(self, 'inflows', {})

        for face_idx, flow_value in lateral_inflows.items():
            if 0 <= face_idx < len(self.mesh.faces):
                face = self.mesh.faces[face_idx]
                if face.area > 1e-6:
                    face.h += (flow_value * dt) / face.area
            else:
                print(f"Warning: Invalid face index {face_idx} for inflow in {self.name}")

        # Call the core explicit solver
        self.mesh = finite_volume_step(self.mesh, dt)

        # After stepping, we save the new state to history
        self.h_history.append([f.h for f in self.mesh.faces])
        self.uh_history.append([f.uh for f in self.mesh.faces])
        self.vh_history.append([f.vh for f in self.mesh.faces])

        # This component does not add any equations to the global matrix.
        return [], []

    def update_state(self, dX_slice):
        # The state was already updated in get_matrix_contributions.
        # This method just needs to exist to satisfy the abstract base class.
        pass

    def get_results(self):
        return {
            "h": np.array(self.h_history),
            "uh": np.array(self.uh_history),
            "vh": np.array(self.vh_history),
        }
