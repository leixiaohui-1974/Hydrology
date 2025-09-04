"""
Main Hydraulic Model Module
===========================

This module contains the main HydraulicModel class that orchestrates the
1D hydraulic simulation using the Preissmann scheme.
"""

import numpy as np
from typing import List, Optional
from .reach import RiverReach
from .structures import HydraulicStructure, Gate, Pump, Weir
from common.base_model import BaseModelComponent

class HydraulicModel(BaseModelComponent):
    """
    Main class for the 1D hydraulic model.
    This component represents a river reach.
    """
    def __init__(self,
                 name: str,
                 reach: RiverReach,
                 dt: float,
                 downstream_level: float,
                 structures: Optional[List[HydraulicStructure]] = None,
                 initial_Z: Optional[list] = None,
                 initial_Q: Optional[list] = None,
                 theta: float = 1.0,
                 g: float = 9.81) -> None:
        super().__init__(name)
        self.reach: RiverReach = reach
        self.dt: float = dt
        self.theta: float = theta
        self.g: float = g
        self.structures: List[HydraulicStructure] = structures if structures is not None else []
        self.structure_map: dict = {s.node_index: s for s in self.structures}
        self.downstream_level: float = downstream_level

        # Initialize state variables
        self.num_nodes: int = self.reach.num_sections
        if initial_Z is not None:
            if len(initial_Z) != self.num_nodes:
                raise ValueError(f"Length of initial_Z ({len(initial_Z)}) must match number of nodes ({self.num_nodes}).")
            self.Z: np.ndarray = np.array(initial_Z, dtype=float)
        else:
            self.Z: np.ndarray = np.zeros(self.num_nodes)

        if initial_Q is not None:
            if len(initial_Q) != self.num_nodes:
                raise ValueError(f"Length of initial_Q ({len(initial_Q)}) must match number of nodes ({self.num_nodes}).")
            self.Q = np.array(initial_Q, dtype=float)
        else:
            self.Q = np.zeros(self.num_nodes)

        # Bed elevation
        self.Z_bed = np.zeros(self.num_nodes)
        cumulative_length = 0
        for i in range(self.num_nodes - 2, -1, -1):
            cumulative_length += self.reach.lengths[i]
            self.Z_bed[i] = self.Z_bed[i+1] + self.reach.slope * self.reach.lengths[i]

        # For storing results
        self.Z_history = []
        self.Q_history = []

    def _get_segment_equations(self, i):
        """Calculates the coefficient matrices for a single segment `i`."""
        dx = self.reach.lengths[i]
        Z_i, Q_i = self.Z[i], self.Q[i]
        Z_i1, Q_i1 = self.Z[i+1], self.Q[i+1]
        y_i = Z_i - self.Z_bed[i]
        y_i1 = Z_i1 - self.Z_bed[i+1]
        cs_i = self.reach.cross_sections[i]
        area_i = cs_i.area(y_i)
        T_i = cs_i.top_width(y_i)
        Rh_i = cs_i.hydraulic_radius(y_i)
        cs_i1 = self.reach.cross_sections[i+1]
        area_i1 = cs_i1.area(y_i1)
        T_i1 = cs_i1.top_width(y_i1)
        Rh_i1 = cs_i1.hydraulic_radius(y_i1)

        Q = 0.5 * (Q_i + Q_i1); A = 0.5 * (area_i + area_i1)
        T = 0.5 * (T_i + T_i1); Rh = 0.5 * (Rh_i + Rh_i1)

        if A < 1e-6: return np.identity(2), -np.identity(2), np.zeros(2)

        psi = 0.5
        L1_c = psi * T / self.dt; L2_c = (1-psi) * T / self.dt
        L3_c = -self.theta / dx; L4_c = self.theta / dx
        RHS_c = -(Q_i1 - Q_i)/dx

        if A < 1e-6 or Rh < 1e-6: Sf = 0; d_Sf_dQ = 0
        else:
            Sf = (self.reach.manning_n**2 * Q * abs(Q)) / (A**2 * Rh**(4/3))
            d_Sf_dQ = (2 * self.reach.manning_n**2 * abs(Q)) / (A**2 * Rh**(4/3))

        L1_m = -self.g * A * self.theta / dx
        L2_m = self.g * A * self.theta / dx
        fric_term_Q = self.g * A * self.theta * d_Sf_dQ
        L3_m = (1-psi)/self.dt + fric_term_Q
        L4_m = psi/self.dt + fric_term_Q
        RHS_m = -self.g*A*((Z_i1 - Z_i)/dx - self.reach.slope) - self.g*A*Sf

        aa_i = np.array([[L1_c, L3_c], [L1_m, L3_m]])
        bb_i = np.array([[L2_c, L4_c], [L2_m, L4_m]])
        dd_i = np.array([RHS_c, RHS_m])
        return aa_i, bb_i, dd_i

    def step(self, inflows: dict, dt: float):
        n_vars = self.num_nodes * 2
        M = np.zeros((n_vars, n_vars))
        R = np.zeros(n_vars)

        # Build the matrix with standard segment equations first
        for i in range(self.num_nodes - 1):
            aa_i, bb_i, dd_i = self._get_segment_equations(i)
            row = i * 2
            M[row:row+2, 2*i:2*i+2] = aa_i
            M[row:row+2, 2*(i+1):2*(i+1)+2] = bb_i
            R[row:row+2] = dd_i

        # Add lateral flow as a source/sink term.
        # This is a simplification: we apply the entire lateral flow to the
        # continuity equation of the middle segment of the reach.
        lateral_flow = inflows.get('lateral_flow', 0.0)
        if abs(lateral_flow) > 1e-9:
            middle_segment_idx = (self.num_nodes - 1) // 2
            continuity_eq_row = middle_segment_idx * 2
            # Add to the RHS of the continuity equation for this segment.
            # The term q in dQ/dx + dA/dt = q is flow per unit length (m^2/s).
            # We must divide the total lateral flow (m^3/s) by the length of the segment it's applied to.
            segment_length = self.reach.lengths[middle_segment_idx]
            if segment_length > 1e-6:
                R[continuity_eq_row] += lateral_flow / segment_length

        # Overwrite rows for boundary conditions and structures

        # Upstream BC - can be Q_inflow or Z_inflow
        M[n_vars-2, :] = 0; R[n_vars-2] = 0 # Clear the equation row
        if 'Q_inflow' in inflows:
            Q_inflow = inflows['Q_inflow']
            # Equation is 1*dQ_0 = Q_inflow - Q_0^n
            M[n_vars-2, 1] = 1.0
            R[n_vars-2] = Q_inflow - self.Q[0]
        elif 'Z_inflow' in inflows:
            Z_inflow = inflows['Z_inflow']
            # Equation is 1*dZ_0 = Z_inflow - Z_0^n
            M[n_vars-2, 0] = 1.0
            R[n_vars-2] = Z_inflow - self.Z[0]
        else:
            # Default to zero inflow if no BC is specified
            M[n_vars-2, 1] = 1.0
            R[n_vars-2] = 0.0 - self.Q[0]

        # Downstream BC
        M[n_vars-1, :] = 0; R[n_vars-1] = 0
        M[n_vars-1, n_vars-2] = 1.0
        R[n_vars-1] = self.downstream_level - self.Z[self.num_nodes-1]

        # Structures
        for i, s in self.structure_map.items():
             if i > 0 and i < self.num_nodes -1: # Structures cannot be at the very ends
                 row_to_replace = (i-1)*2 + 1 # Replace momentum eq of upstream reach
                 M[row_to_replace, :] = 0
                 R[row_to_replace] = 0

                 if isinstance(s, Gate):
                     coeffs, rhs = s.get_linearized_equation(
                         self.Z[i-1], self.Z[i], self.Q[i], self.g
                     )
                     # Equation is: C1*dZ_up + C2*dZ_down + C3*dQ = RHS
                     M[row_to_replace, (i-1)*2]     = coeffs.get('dZ_up', 0.0)
                     M[row_to_replace, i*2]         = coeffs.get('dZ_down', 0.0)
                     M[row_to_replace, i*2 + 1]     = coeffs.get('dQ', 0.0)
                     R[row_to_replace] = rhs
                     print(f"Applying physical gate equation at node {i}")

                 elif isinstance(s, Pump):
                     coeffs, rhs = s.get_linearized_equation(
                         self.Z[i-1], self.Z[i], self.Q[i]
                     )
                     M[row_to_replace, (i-1)*2]     = coeffs.get('dZ_up', 0.0)
                     M[row_to_replace, i*2]         = coeffs.get('dZ_down', 0.0)
                     M[row_to_replace, i*2 + 1]     = coeffs.get('dQ', 0.0)
                     R[row_to_replace] = rhs
                     print(f"Applying physical pump equation at node {i}")

                 elif isinstance(s, Weir):
                     coeffs, rhs = s.get_linearized_equation(
                         self.Z[i-1], self.Z[i], self.Q[i], self.g
                     )
                     M[row_to_replace, (i-1)*2]     = coeffs.get('dZ_up', 0.0)
                     M[row_to_replace, i*2]         = coeffs.get('dZ_down', 0.0)
                     M[row_to_replace, i*2 + 1]     = coeffs.get('dQ', 0.0)
                     R[row_to_replace] = rhs
                     print(f"Applying physical weir equation at node {i}")

                 else:
                     print(f"Warning: Structure type for '{s.name}' not implemented in matrix assembly.")

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

        # Store results for this timestep
        self.Z_history.append(self.Z.copy())
        self.Q_history.append(self.Q.copy())

    def get_water_level_at_node(self, node_idx: int) -> float:
        """Returns the water surface elevation Z at a specific node index."""
        if 0 <= node_idx < self.num_nodes:
            return self.Z[node_idx]
        else:
            raise IndexError(f"Node index {node_idx} is out of bounds for this reach ({self.num_nodes} nodes).")

    def get_results(self):
        """Returns the stored history of water levels and discharges."""
        return {
            "Z": np.array(self.Z_history),
            "Q": np.array(self.Q_history),
            "x_coords": np.array([0] + np.cumsum(self.reach.lengths).tolist())
        }

    def run(self, num_steps: int, Q_inflow_hydrograph: list, Z_downstream_hydrograph: list):
        # This is a standalone runner, not used by the main SimulationController.
        # It's useful for testing this component in isolation.
        if len(Q_inflow_hydrograph) < num_steps or len(Z_downstream_hydrograph) < num_steps:
            raise ValueError("Boundary condition hydrographs must be at least as long as num_steps.")
        print(f"--- Running standalone simulation for component '{self.name}' ---")
        for i in range(num_steps):
            # The main controller passes inflows differently. This is for standalone mode.
            inflows = {'Q_inflow': Q_inflow_hydrograph[i]}
            self.downstream_level = Z_downstream_hydrograph[i]
            self.step(inflows, self.dt)
        print("--- Standalone simulation finished ---")
