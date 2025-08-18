"""
Main Hydraulic Model Module
===========================
This module contains the main HydraulicModel class that orchestrates the
1D hydraulic simulation using the Preissmann scheme.
"""
import numpy as np
from typing import List, Optional, Dict
from .reach import RiverReach
from .structures import HydraulicStructure, Gate, Pump
from common.base_model import BaseModelComponent

class HydraulicModel(BaseModelComponent):
    """
    Main class for the 1D hydraulic model.
    This component represents a river reach.
    """
    def __init__(self, name: str, reach: RiverReach, dt: float, downstream_level: float,
                 structures: Optional[List[HydraulicStructure]] = None, theta: float = 1.0, g: float = 9.81):
        super().__init__(name)
        self.reach = reach
        self.dt = dt
        self.theta = theta
        self.g = g
        self.structures = structures if structures is not None else []
        self.structure_map = {s.node_index: s for s in self.structures}
        self.downstream_level = downstream_level
        self.num_nodes = self.reach.num_sections
        self.Q = np.zeros(self.num_nodes)
        self.Z = np.zeros(self.num_nodes)
        self.Z_bed = np.zeros(self.num_nodes)
        for i in range(self.num_nodes - 2, -1, -1):
            self.Z_bed[i] = self.Z_bed[i+1] + self.reach.slope * self.reach.lengths[i]

    def _get_segment_equations(self, i: int, lateral_flows: Dict[int, float]):
        """Calculates the coefficient matrices for a single segment `i`."""
        dx = self.reach.lengths[i]
        # ... (hydraulic property calculations remain the same)
        Z_i, Q_i = self.Z[i], self.Q[i]; Z_i1, Q_i1 = self.Z[i+1], self.Q[i+1]
        y_i = Z_i - self.Z_bed[i]; y_i1 = Z_i1 - self.Z_bed[i+1]
        cs_i = self.reach.cross_sections[i]; area_i = cs_i.area(y_i); T_i = cs_i.top_width(y_i); Rh_i = cs_i.hydraulic_radius(y_i)
        cs_i1 = self.reach.cross_sections[i+1]; area_i1 = cs_i1.area(y_i1); T_i1 = cs_i1.top_width(y_i1); Rh_i1 = cs_i1.hydraulic_radius(y_i1)
        Q = 0.5 * (Q_i + Q_i1); A = 0.5 * (area_i + area_i1); T = 0.5 * (T_i + T_i1); Rh = 0.5 * (Rh_i + Rh_i1)
        if A < 1e-6: return np.identity(2), -np.identity(2), np.zeros(2)

        psi = 0.5
        L1_c = psi * T / self.dt; L2_c = (1-psi) * T / self.dt
        L3_c = -self.theta / dx; L4_c = self.theta / dx

        # Add lateral flow source/sink terms to the continuity equation's RHS
        # The flow is distributed between the two adjacent segments of a node.
        q_lat_i = lateral_flows.get(i, 0.0)
        q_lat_i1 = lateral_flows.get(i + 1, 0.0)
        RHS_c = -(Q_i1 - Q_i)/dx + 0.5 * q_lat_i + 0.5 * q_lat_i1

        # ... (momentum equation remains the same)
        if A < 1e-6 or Rh < 1e-6: Sf = 0; d_Sf_dQ = 0
        else:
            Sf = (self.reach.manning_n**2 * Q * abs(Q)) / (A**2 * Rh**(4/3))
            d_Sf_dQ = (2 * self.reach.manning_n**2 * abs(Q)) / (A**2 * Rh**(4/3))
        L1_m = -self.g * A * self.theta / dx; L2_m = self.g * A * self.theta / dx
        fric_term_Q = self.g * A * self.theta * d_Sf_dQ
        L3_m = (1-psi)/self.dt + fric_term_Q; L4_m = psi/self.dt + fric_term_Q
        RHS_m = -self.g*A*((Z_i1 - Z_i)/dx - self.reach.slope) - self.g*A*Sf

        aa_i = np.array([[L1_c, L3_c], [L1_m, L3_m]])
        bb_i = np.array([[L2_c, L4_c], [L2_m, L4_m]])
        dd_i = np.array([RHS_c, RHS_m])
        return aa_i, bb_i, dd_i

    def step(self, inflows: dict, dt: float):
        n_vars = self.num_nodes * 2
        M = np.zeros((n_vars, n_vars))
        R = np.zeros(n_vars)

        # Extract lateral inflows from the inflows dict
        lateral_flows = inflows.get('lateral', {})

        # Build the matrix with standard segment equations first
        for i in range(self.num_nodes - 1):
            aa_i, bb_i, dd_i = self._get_segment_equations(i, lateral_flows)
            row = i * 2
            M[row:row+2, 2*i:2*i+2] = aa_i
            M[row:row+2, 2*(i+1):2*(i+1)+2] = bb_i
            R[row:row+2] = dd_i

        # ... (BC and structure logic remains the same)
        M[n_vars-2, :] = 0; R[n_vars-2] = 0
        if 'Q_inflow' in inflows:
            M[n_vars-2, 1] = 1.0; R[n_vars-2] = inflows['Q_inflow'] - self.Q[0]
        elif 'Z_inflow' in inflows:
            M[n_vars-2, 0] = 1.0; R[n_vars-2] = inflows['Z_inflow'] - self.Z[0]
        else:
            M[n_vars-2, 1] = 1.0; R[n_vars-2] = 0.0 - self.Q[0]
        M[n_vars-1, :] = 0; R[n_vars-1] = 0
        M[n_vars-1, n_vars-2] = 1.0
        R[n_vars-1] = self.downstream_level - self.Z[self.num_nodes-1]
        for i, s in self.structure_map.items():
             if i > 0 and i < self.num_nodes -1:
                 row_to_replace = (i-1)*2 + 1
                 M[row_to_replace, :] = 0; R[row_to_replace] = 0
                 if isinstance(s, Gate):
                     coeffs, rhs = s.get_linearized_equation(self.Z[i-1], self.Z[i], self.Q[i], self.g)
                     M[row_to_replace, (i-1)*2] = coeffs.get('dZ_up', 0.0)
                     M[row_to_replace, i*2] = coeffs.get('dZ_down', 0.0)
                     M[row_to_replace, i*2 + 1] = coeffs.get('dQ', 0.0)
                     R[row_to_replace] = rhs
                 elif isinstance(s, Pump):
                     coeffs, rhs = s.get_linearized_equation(self.Z[i-1], self.Z[i], self.Q[i])
                     M[row_to_replace, (i-1)*2] = coeffs.get('dZ_up', 0.0)
                     M[row_to_replace, i*2] = coeffs.get('dZ_down', 0.0)
                     M[row_to_replace, i*2 + 1] = coeffs.get('dQ', 0.0)
                     R[row_to_replace] = rhs

        try:
            dX_flat = np.linalg.solve(M, R)
        except np.linalg.LinAlgError:
            print(f"Warning: Singular matrix in component '{self.name}'. Simulation may be unstable.")
            return

        relaxation_factor = 0.75
        for i in range(self.num_nodes):
            self.Z[i] += relaxation_factor * dX_flat[i*2]
            self.Q[i] += relaxation_factor * dX_flat[i*2 + 1]

        self.outflow = self.Q[-1]

    def run(self, num_steps: int, Q_inflow_hydrograph: list, Z_downstream_hydrograph: list):
        # This method is for standalone testing.
        # The main controller will call step() directly.
        pass
