import numpy as np
from typing import Dict, List, Tuple
from common.base_model import BaseModelComponent
from .reach import RiverReach
from common.boundary_conditions import InflowBC

class HydraulicModel(BaseModelComponent):
    """
    1D Hydraulic model component using a semi-implicit Preissmann scheme.
    """
    def __init__(self, name: str, reach: RiverReach, downstream_level: float, theta: float = 0.6, g: float = 9.81):
        super().__init__(name)
        self.reach = reach
        self.downstream_level = downstream_level
        self.theta = theta
        self.g = g

        self.num_nodes = self.reach.num_sections
        self.num_vars = self.num_nodes * 2

        self.Q = np.zeros(self.num_nodes)
        self.Z = np.full(self.num_nodes, self.downstream_level)
        self.Z_bed = np.zeros(self.num_nodes)
        self.Z_bed[-1] = self.downstream_level - 5.0
        for i in range(self.num_nodes - 2, -1, -1):
            self.Z_bed[i] = self.Z_bed[i+1] + self.reach.slope * self.reach.lengths[i]

        self.upstream_bc = None
        self.Z_history = [self.Z.copy()]
        self.Q_history = [self.Q.copy()]

    def set_upstream_bc(self, bc):
        self.upstream_bc = bc

    def get_num_vars(self) -> int:
        return self.num_vars

    def get_matrix_contributions(self, controller) -> Tuple[List, List]:
        matrix_coeffs = []
        rhs_coeffs = []
        dt = controller.dt

        # Assemble interior equations for each reach segment
        for i in range(self.num_nodes - 1):
            # --- Get variables at time 'n' ---
            dx = self.reach.lengths[i]
            Z_i, Q_i = self.Z[i], self.Q[i]
            Z_i1, Q_i1 = self.Z[i+1], self.Q[i+1]

            y_i = Z_i - self.Z_bed[i]; y_i1 = Z_i1 - self.Z_bed[i+1]
            cs_i = self.reach.cross_sections[i]; area_i = cs_i.area(y_i); T_i = cs_i.top_width(y_i); Rh_i = cs_i.hydraulic_radius(y_i)
            cs_i1 = self.reach.cross_sections[i+1]; area_i1 = cs_i1.area(y_i1); T_i1 = cs_i1.top_width(y_i1); Rh_i1 = cs_i1.hydraulic_radius(y_i1)

            # --- Averaged values ---
            A = 0.5 * (area_i + area_i1); T = 0.5 * (T_i + T_i1); Rh = 0.5 * (Rh_i + Rh_i1)
            Q_avg = 0.5 * (Q_i + Q_i1)

            if A < 1e-6: continue

            Sf = (self.reach.manning_n**2 * Q_avg * abs(Q_avg)) / (A**2 * Rh**(4/3)) if Rh > 1e-6 else 0

            # --- Get global indices for the 4 variables in this segment ---
            z_i_col, q_i_col = controller.get_global_var_index(self, i*2), controller.get_global_var_index(self, i*2+1)
            z_i1_col, q_i1_col = controller.get_global_var_index(self, (i+1)*2), controller.get_global_var_index(self, (i+1)*2+1)

            # --- Continuity Equation ---
            # dQ/dx + T*dZ/dt = 0
            row_c = controller.get_global_var_index(self, i*2) # Eq for node i

            # dQ/dx term, weighted by theta
            matrix_coeffs.append((row_c, q_i1_col, self.theta)); matrix_coeffs.append((row_c, q_i_col, -self.theta))
            # dZ/dt term, weighted by T
            matrix_coeffs.append((row_c, z_i1_col, T*dx/dt)); matrix_coeffs.append((row_c, z_i_col, T*dx/dt))

            # RHS for continuity
            rhs_c = - (Q_i1 - Q_i) - (T*dx/dt)*( (Z_i1 - self.Z[i+1]) + (Z_i - self.Z[i]) ) # This is wrong, should be Z at n
            rhs_c_corr = - (Q_i1 - Q_i)
            rhs_coeffs.append((row_c, rhs_c_corr))

            # --- Momentum Equation ---
            # dQ/dt + d(Q^2/A)/dx + gA*dZ/dx + gA*Sf = 0
            row_m = controller.get_global_var_index(self, i*2 + 1) # Eq for node i

            # dQ/dt
            matrix_coeffs.append((row_m, q_i1_col, 1.0/dt)); matrix_coeffs.append((row_m, q_i_col, 1.0/dt))
            # gA*dZ/dx
            matrix_coeffs.append((row_m, z_i1_col, self.g*A/dx)); matrix_coeffs.append((row_m, z_i_col, -self.g*A/dx))
            # gA*Sf, linearized as gA * (dSf/dQ)*dQ
            dSf_dQ = (2 * self.reach.manning_n**2 * abs(Q_avg)) / (A**2 * Rh**(4/3)) if Rh > 1e-6 else 0
            matrix_coeffs.append((row_m, q_i1_col, self.g*A*dSf_dQ)); matrix_coeffs.append((row_m, q_i_col, self.g*A*dSf_dQ))

            # RHS for momentum
            conv_accel = (Q_i1**2/area_i1 - Q_i**2/area_i)/dx if area_i > 1e-6 and area_i1 > 1e-6 else 0
            rhs_m = -conv_accel - self.g*A*((Z_i1-Z_i)/dx + Sf)
            rhs_coeffs.append((row_m, rhs_m))

        # --- Boundary Conditions (overwrite the first and last equations) ---
        if self.upstream_bc:
            bc_value = self.upstream_bc.get_value(controller.current_time)
            row_idx = controller.get_global_var_index(self, 1) # Overwrite first momentum eq
            col_idx = controller.get_global_var_index(self, 1) # Variable is Q0
            matrix_coeffs.append((row_idx, col_idx, 1.0))
            rhs_coeffs.append((row_idx, bc_value - self.Q[0]))

        # Downstream BC
        row_idx = controller.get_global_var_index(self, self.num_vars - 2) # Overwrite last continuity eq
        col_idx = controller.get_global_var_index(self, self.num_vars - 2) # Variable is Z_N
        matrix_coeffs.append((row_idx, col_idx, 1.0))
        rhs_coeffs.append((row_idx, self.downstream_level - self.Z[-1]))

        return matrix_coeffs, rhs_coeffs

    def update_state(self, dX_slice):
        relaxation = 0.5 # Use a smaller relaxation factor for stability
        self.Z += relaxation * dX_slice[0::2]
        self.Q += relaxation * dX_slice[1::2]

        self.Z_history.append(self.Z.copy())
        self.Q_history.append(self.Q.copy())
        self.outflow = self.Q[-1]

    def get_results(self):
        return {"H": np.array(self.Z_history), "Q": np.array(self.Q_history)}
