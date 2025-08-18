import numpy as np
from typing import Dict, List, Tuple
from common.base_model import BaseModelComponent
# These imports are for type hinting and will be needed by the test script
# from preissmann_model.model import HydraulicModel
# from model_2d.model import Model2D

class LateralLink(BaseModelComponent):
    """
    A LateralLink component that implicitly couples a 1D river node
    and a 2D mesh cell via a weir equation.
    """
    def __init__(self, name: str, model_1d, link_1d_node_idx: int, model_2d, link_2d_face_idx: int,
                 weir_crest_level: float, weir_length: float, weir_coefficient: float = 1.6):
        super().__init__(name)
        self.model_1d = model_1d
        self.link_1d_node_idx = link_1d_node_idx
        self.model_2d = model_2d
        self.link_2d_face_idx = link_2d_face_idx
        self.weir_crest_level = weir_crest_level
        self.weir_length = weir_length
        self.weir_coefficient = weir_coefficient

        self.Q = 0.0  # Current flow over the link, positive from 1D to 2D
        self.Q_history = [self.Q]

    def get_num_vars(self) -> int:
        return 1 # One variable: Q_link

    def get_matrix_contributions(self, controller) -> Tuple[List, List]:
        """
        Calculates the linearized weir equation to couple the models.
        The equation is: Q_link - f(H_1d, H_2d) = 0
        """
        matrix_coeffs = []
        rhs_coeffs = []

        # Get current water levels from the connected models
        h_1d = self.model_1d.Z[self.link_1d_node_idx]
        face_2d = self.model_2d.mesh.faces[self.link_2d_face_idx]
        h_2d = face_2d.z_bed + face_2d.h

        # Determine flow direction and calculate head-dependent terms
        if h_1d > h_2d:
            head = h_1d - self.weir_crest_level
            sign = 1.0
        else:
            head = h_2d - self.weir_crest_level
            sign = -1.0

        if head <= 0:
            Q_calc = 0.0
            dQ_dH = 0.0
        else:
            Q_calc = self.weir_coefficient * self.weir_length * head**1.5
            dQ_dH = 1.5 * self.weir_coefficient * self.weir_length * head**0.5

        # Get global indices for the variables
        row_idx = controller.get_global_var_index(self, 0)
        q_link_col = row_idx
        z_1d_col = controller.get_global_var_index(self.model_1d, self.link_1d_node_idx * 2)

        # The 2D model has no variables in the matrix, so we treat its water level
        # as a constant for the purpose of the Jacobian. This is the "semi" in semi-implicit.

        # Equation: dQ_link - (dQ/dH_1d)*dZ_1d = Q_weir_calc - Q_link_current
        matrix_coeffs.append((row_idx, q_link_col, 1.0))
        if sign > 0: # Flow 1D -> 2D
            matrix_coeffs.append((row_idx, z_1d_col, -dQ_dH))
        else: # Flow 2D -> 1D
            # dQ/dH is now with respect to H_2d, which is not in the matrix.
            # The derivative with respect to H_1d is effectively 0.
            pass

        rhs_coeffs.append((row_idx, sign * Q_calc - self.Q))

        # Now, we must add the source/sink term to the 1D model's continuity equation.
        # The flow Q_link is a lateral abstraction/inflow for the 1D model.
        # Continuity: T*dZ/dt + dQ/dx - q_lat = 0
        # We add -Q_link to the RHS of the continuity equation for the relevant node.
        # The controller will need to handle this. Let's assume for now the controller
        # will pass the link flow back to the model.
        # A better way is to add the term to the matrix directly.
        # The continuity equation for node i is at row 2*i.

        # This part is tricky. Let's add the dQ_link term to the continuity equation of the 1D model.
        row_1d_c = controller.get_global_var_index(self.model_1d, self.link_1d_node_idx * 2)
        # The term is -q_lat, and q_lat = Q_link. So we add -1 * dQ_link to the equation.
        matrix_coeffs.append((row_1d_c, q_link_col, -1.0))

        return matrix_coeffs, rhs_coeffs

    def update_state(self, dX_slice):
        self.Q += dX_slice[0]
        self.Q_history.append(self.Q)

    def get_results(self):
        return {"Q": np.array(self.Q_history)}
